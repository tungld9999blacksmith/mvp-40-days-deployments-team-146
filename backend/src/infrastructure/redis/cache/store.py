"""Low-level cache storage: bytes in Redis, TTL + jitter, negative caching, tags, pattern invalidation."""

from __future__ import annotations

import random
from typing import Any, Final

from redis.asyncio import Redis

from ..keys import KeyBuilder
from ..serializers import JsonSerializer, Serializer
from .options import CacheOptions


class _Miss:
    __slots__ = ()

    def __repr__(self) -> str:
        return "MISS"

    def __bool__(self) -> bool:
        return False


MISS: Final = _Miss()
"""Returned by `CacheStore.get` on a miss — distinct from a cached `None`."""

_NIL: Final = b"\x00__cache_nil__"
_DEFAULT_SERIALIZER = JsonSerializer()


class CacheStore:
    def __init__(self, redis: Redis, keys: KeyBuilder, default_ttl: float = 300.0) -> None:
        self.redis = redis
        self._keys = keys.child("cache")
        self.default_ttl = default_ttl

    # ---------------------------------------------------------------- keys
    def full_key(self, key: str, options: CacheOptions) -> str:
        return self._keys.build(options.namespace, key)

    def tag_key(self, tag: str) -> str:
        return self._keys.build("_tag", tag)

    @staticmethod
    def serializer(options: CacheOptions) -> Serializer[Any]:
        return options.serializer or _DEFAULT_SERIALIZER

    @staticmethod
    def _expiry(ttl: float, jitter: float) -> int | None:
        """TTL in ms (None = no expiry)."""
        if ttl <= 0:
            return None
        if jitter > 0:
            ttl *= 1 + random.uniform(0, jitter)
        return max(1, int(ttl * 1000))

    # ------------------------------------------------------------- read/write
    async def get(self, key: str, options: CacheOptions) -> Any:
        """Cached value, `None` for a cached "not found", or `MISS`."""
        raw = await self.redis.get(self.full_key(key, options))
        if raw is None:
            return MISS
        if raw == _NIL:
            return None
        return self.serializer(options).loads(raw)

    def encode(self, value: Any, options: CacheOptions) -> bytes:
        return _NIL if value is None else self.serializer(options).dumps(value)

    async def set(self, key: str, value: Any, options: CacheOptions) -> None:
        """Store *value* (None is stored as a negative-cache marker with `none_ttl`)."""
        if options.cache_if is not None and not options.cache_if(value):
            return
        ttl = options.ttl if options.ttl is not None else self.default_ttl
        if value is None:
            if not options.cache_none:
                return
            ttl = options.none_ttl
        full_key = self.full_key(key, options)
        px = self._expiry(ttl, options.ttl_jitter)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(full_key, self.encode(value, options), px=px)
            for tag in options.tags:
                tag_key = self.tag_key(tag)
                pipe.sadd(tag_key, full_key)
                if px is not None:
                    # tag set lives at least as long as its longest member
                    pipe.pexpire(tag_key, px, nx=True)
                    pipe.pexpire(tag_key, px, gt=True)
                else:
                    pipe.persist(tag_key)
            await pipe.execute()

    async def delete(self, *keys: str, options: CacheOptions) -> int:
        if not keys:
            return 0
        return int(await self.redis.unlink(*(self.full_key(k, options) for k in keys)))

    async def exists(self, key: str, options: CacheOptions) -> bool:
        return bool(await self.redis.exists(self.full_key(key, options)))

    async def ttl(self, key: str, options: CacheOptions) -> float | None:
        """Remaining TTL in seconds; None if the key is missing or has no expiry."""
        ms = await self.redis.pttl(self.full_key(key, options))
        return ms / 1000 if ms and ms > 0 else None

    # ------------------------------------------------------------ invalidation
    async def invalidate_tags(self, *tags: str) -> int:
        removed = 0
        for tag in tags:
            tag_key = self.tag_key(tag)
            members = await self.redis.smembers(tag_key)
            if members:
                removed += int(await self.redis.unlink(*members))
            await self.redis.unlink(tag_key)
        return removed

    async def invalidate_pattern(self, pattern: str, namespace: str | None = None, batch: int = 500) -> int:
        """Delete every cache key matching a glob *pattern* (relative to the cache prefix). Uses SCAN, never KEYS."""
        match = self._keys.build(namespace, pattern)
        removed = 0
        chunk: list[bytes] = []
        async for key in self.redis.scan_iter(match=match, count=batch):
            chunk.append(key)
            if len(chunk) >= batch:
                removed += int(await self.redis.unlink(*chunk))
                chunk.clear()
        if chunk:
            removed += int(await self.redis.unlink(*chunk))
        return removed
