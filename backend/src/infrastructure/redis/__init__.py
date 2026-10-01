"""
Redis toolkit: caching strategies, distributed locks, typed pub/sub, distributed queue,
bloom filter, sorted set and geospatial index — all behind `RedisToolkit`.

Rules:
    - Only this package imports redis-py; callers use the classes exported here.
    - Everything is async (`redis.asyncio`). Decorators require async functions.
    - All keys go through one KeyBuilder prefix (settings.redis_key_prefix).
"""

from .bloom import BloomFilter
from .cache import CacheFacade, CacheOptions, CacheStrategy
from .dependency import get_cache, get_lock_manager, get_pubsub, get_redis_toolkit
from .errors import (
    CacheError,
    LockAcquireError,
    LockError,
    LockNotOwnedError,
    QueueError,
    RateLimitError,
    RateLimitExceededError,
    RedisToolkitError,
    SerializationError,
)
from .geo import GeoIndex, GeoPoint, GeoResult, GeoUnit
from .keys import KeyBuilder
from .lock import WAIT_FOREVER, DistributedLock, LockKey, LockManager, TransactionLock
from .pubsub import Message, PubSubBroker, Topic
from .queue import DistributedQueue, QueueMessage, exponential_backoff, running_consumer
from .ratelimit import (
    Algorithm,
    Identity,
    IdentityResolver,
    Rate,
    RateLimiter,
    RateLimitResult,
    install_rate_limiting,
    rate_limit,
)
from .serializers import (
    JsonSerializer,
    PickleSerializer,
    Serializer,
    StrSerializer,
    TypeAdapterSerializer,
    serializer_for,
)
from .sorted_set import ScoredMember, SortedSet
from .toolkit import RedisToolkit

__all__ = [
    "WAIT_FOREVER",
    "Algorithm",
    "BloomFilter",
    "CacheError",
    "CacheFacade",
    "CacheOptions",
    "CacheStrategy",
    "DistributedLock",
    "DistributedQueue",
    "GeoIndex",
    "GeoPoint",
    "GeoResult",
    "GeoUnit",
    "Identity",
    "IdentityResolver",
    "JsonSerializer",
    "KeyBuilder",
    "LockAcquireError",
    "LockError",
    "LockKey",
    "LockManager",
    "LockNotOwnedError",
    "Message",
    "PickleSerializer",
    "PubSubBroker",
    "QueueError",
    "QueueMessage",
    "Rate",
    "RateLimitError",
    "RateLimitExceededError",
    "RateLimitResult",
    "RateLimiter",
    "RedisToolkit",
    "RedisToolkitError",
    "ScoredMember",
    "SerializationError",
    "Serializer",
    "SortedSet",
    "StrSerializer",
    "Topic",
    "TransactionLock",
    "TypeAdapterSerializer",
    "exponential_backoff",
    "get_cache",
    "get_lock_manager",
    "get_pubsub",
    "get_redis_toolkit",
    "install_rate_limiting",
    "rate_limit",
    "running_consumer",
    "serializer_for",
]
