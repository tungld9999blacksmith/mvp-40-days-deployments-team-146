"""
RedisToolkit — one facade over every Redis utility, sharing a client and a key prefix.

    toolkit = get_redis_toolkit()
    toolkit.cache        # CacheFacade: strategies + @cached / @cache_write / @cache_evict
    toolkit.locks        # LockManager: data / critical-section / transaction locks
    toolkit.pubsub       # PubSubBroker: typed topics
    toolkit.queue(...)   # DistributedQueue[T]
    toolkit.bloom_filter(...), toolkit.sorted_set(...), toolkit.geo(...)
"""

from __future__ import annotations

from typing import Any

from redis.asyncio import Redis

from ...config import Settings
from .bloom import BloomFilter
from .cache import CacheFacade
from .client import create_redis_client
from .geo import GeoIndex
from .keys import KeyBuilder
from .lock import LockManager
from .pubsub import PubSubBroker
from .queue import DistributedQueue
from .ratelimit import Algorithm, Rate, RateLimiter, create_limiter
from .serializers import Serializer
from .sorted_set import SortedSet


class RedisToolkit:
    def __init__(self, redis: Redis, *, key_prefix: str = "", default_cache_ttl: float = 300.0) -> None:
        self.redis = redis
        self.keys = KeyBuilder(key_prefix)
        self.locks = LockManager(redis, self.keys)
        self.cache = CacheFacade(redis, self.keys, self.locks, default_ttl=default_cache_ttl)
        self.pubsub = PubSubBroker(redis, self.keys)

    @classmethod
    def from_settings(cls, settings: Settings) -> RedisToolkit:
        return cls(
            create_redis_client(settings),
            key_prefix=settings.redis_key_prefix,
            default_cache_ttl=settings.redis_default_cache_ttl,
        )

    # ----------------------------------------------------------- structures
    def queue(self, name: str, item_type: Any = None, **kwargs: Any) -> DistributedQueue[Any]:
        """See `DistributedQueue` for kwargs (group, consumer, visibility_timeout, max_attempts, maxlen, serializer)."""
        return DistributedQueue(self.redis, self.keys, name, item_type, **kwargs)

    def bloom_filter(
        self,
        name: str,
        capacity: int,
        error_rate: float = 0.01,
        *,
        serializer: Serializer[Any] | None = None,
        ttl: float | None = None,
    ) -> BloomFilter[Any]:
        return BloomFilter(
            self.redis, self.keys.build("bloom", name), capacity, error_rate, serializer=serializer, ttl=ttl
        )

    def sorted_set(
        self,
        name: str,
        member_type: Any = str,
        *,
        serializer: Serializer[Any] | None = None,
        ttl: float | None = None,
    ) -> SortedSet[Any]:
        return SortedSet(self.redis, self.keys.build("zset", name), member_type, serializer=serializer, ttl=ttl)

    def geo(self, name: str, member_type: Any = str, *, serializer: Serializer[Any] | None = None) -> GeoIndex[Any]:
        return GeoIndex(self.redis, self.keys.build("geo", name), member_type, serializer=serializer)

    def rate_limiter(
        self,
        name: str,
        rate: Rate,
        algorithm: Algorithm | str = Algorithm.SLIDING_WINDOW_COUNTER,
    ) -> RateLimiter:
        """
        A `RateLimiter` for endpoint *name* under this app's key prefix.

        Keys land under `{prefix}:ratelimit:{algorithm}:{name}:{identity}`, so the
        same *name* on different algorithms never shares state. Default algorithm
        is the sliding-window counter (O(1), smooth) — see `Algorithm` for the rest.
        """
        keys = self.keys.child("ratelimit", Algorithm(algorithm).value, name)
        return create_limiter(algorithm, self.redis, keys, rate)

    # ------------------------------------------------------------- lifecycle
    async def ping(self) -> bool:
        return bool(await self.redis.ping())

    async def start(self, write_back_interval: float = 5.0) -> None:
        """Start background workers: write-back flusher and pub/sub handlers (call in app lifespan)."""
        self.cache.write_back_buffer.start(write_back_interval)
        await self.pubsub.start()

    async def close(self) -> None:
        """Stop background workers (flushing pending write-backs) and close the connection pool."""
        await self.pubsub.stop()
        await self.cache.write_back_buffer.stop(final_flush=True)
        await self.redis.aclose()
