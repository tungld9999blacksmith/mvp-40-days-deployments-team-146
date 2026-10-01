"""
Bloom filter on a plain Redis bitmap (works on stock Redis — no RedisBloom module needed).

"Have we possibly seen X?" in constant memory:
- `contains` -> False means *definitely not added*; True means *probably added*
  (false-positive rate ≈ `error_rate` while item count ≤ `capacity`).
- Items cannot be removed; `clear()` resets the whole filter.

Typical uses: skip DB lookups for ids that don't exist (cache-penetration guard),
"username taken?" pre-checks, de-duplicating events.

Sizing: m = -n·ln(p) / (ln 2)² bits, k = (m/n)·ln 2 hash functions. 1M items at 1% ≈ 1.2 MB.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from typing import Any, Generic, TypeVar

from redis.asyncio import Redis

from .serializers import JsonSerializer, Serializer, StrSerializer

T = TypeVar("T")

_MAX_BITS = 2**32  # Redis string limit is 512 MB = 2^32 bits


class BloomFilter(Generic[T]):
    def __init__(
        self,
        redis: Redis,
        key: str,
        capacity: int,
        error_rate: float = 0.01,
        *,
        serializer: Serializer[T] | None = None,
        ttl: float | None = None,
    ) -> None:
        """
        Args:
            capacity: expected number of distinct items. Exceeding it raises the false-positive rate.
            error_rate: target false-positive probability (0 < p < 1).
            serializer: how items are turned into bytes for hashing. Default: str as-is,
                anything else as sorted-key JSON (so equal dicts/models hash identically).
            ttl: optional expiry (seconds) of the whole filter, refreshed on every add.
        """
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        if not 0 < error_rate < 1:
            raise ValueError("error_rate must be between 0 and 1")
        self._redis = redis
        self.key = key
        self.capacity = capacity
        self.error_rate = error_rate
        self.ttl = ttl
        self.num_bits = min(_MAX_BITS, math.ceil(-capacity * math.log(error_rate) / math.log(2) ** 2))
        self.num_hashes = max(1, round(self.num_bits / capacity * math.log(2)))
        self._serializer = serializer

    def _encode(self, item: T) -> bytes:
        if self._serializer is not None:
            return self._serializer.dumps(item)
        if isinstance(item, str):
            return StrSerializer().dumps(item)
        if isinstance(item, bytes):
            return item
        return JsonSerializer(sort_keys=True).dumps(item)

    def offsets(self, item: T) -> list[int]:
        """Bit positions for *item* (Kirsch–Mitzenmacher double hashing over one 128-bit digest)."""
        digest = hashlib.blake2b(self._encode(item), digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:], "big") | 1
        return [(h1 + i * h2) % self.num_bits for i in range(self.num_hashes)]

    async def add(self, item: T) -> bool:
        """Add *item*. Returns True if it was (definitely) new, False if it was probably present."""
        return (await self.add_many([item]))[0]

    async def add_many(self, items: Iterable[T]) -> list[bool]:
        batches = [self.offsets(item) for item in items]
        if not batches:
            return []
        async with self._redis.pipeline(transaction=False) as pipe:
            for offsets in batches:
                for offset in offsets:
                    pipe.setbit(self.key, offset, 1)
            if self.ttl:
                pipe.expire(self.key, int(self.ttl))
            results = await pipe.execute()
        added: list[bool] = []
        cursor = 0
        for offsets in batches:
            previous = results[cursor : cursor + len(offsets)]
            cursor += len(offsets)
            added.append(not all(previous))
        return added

    async def contains(self, item: T) -> bool:
        return (await self.contains_many([item]))[0]

    async def contains_many(self, items: Iterable[T]) -> list[bool]:
        batches = [self.offsets(item) for item in items]
        if not batches:
            return []
        async with self._redis.pipeline(transaction=False) as pipe:
            for offsets in batches:
                for offset in offsets:
                    pipe.getbit(self.key, offset)
            results = await pipe.execute()
        found: list[bool] = []
        cursor = 0
        for offsets in batches:
            found.append(all(results[cursor : cursor + len(offsets)]))
            cursor += len(offsets)
        return found

    async def approximate_count(self) -> int:
        """Estimated number of distinct items added: n ≈ -(m/k)·ln(1 - X/m), X = bits set."""
        bits_set = int(await self._redis.bitcount(self.key))
        if bits_set == 0:
            return 0
        if bits_set >= self.num_bits:
            return self.capacity
        return round(-(self.num_bits / self.num_hashes) * math.log(1 - bits_set / self.num_bits))

    async def clear(self) -> None:
        await self._redis.delete(self.key)

    def info(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "capacity": self.capacity,
            "error_rate": self.error_rate,
            "num_bits": self.num_bits,
            "num_hashes": self.num_hashes,
            "memory_bytes": math.ceil(self.num_bits / 8),
        }
