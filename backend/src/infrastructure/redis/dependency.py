from __future__ import annotations

from functools import lru_cache

from ...config import get_settings
from .cache import CacheFacade
from .lock import LockManager
from .pubsub import PubSubBroker
from .toolkit import RedisToolkit


@lru_cache
def get_redis_toolkit() -> RedisToolkit:
    """Process-wide toolkit. Safe to call at import time (e.g. for decorators): nothing connects until first use."""
    return RedisToolkit.from_settings(get_settings())


def get_cache() -> CacheFacade:
    return get_redis_toolkit().cache


def get_lock_manager() -> LockManager:
    return get_redis_toolkit().locks


def get_pubsub() -> PubSubBroker:
    return get_redis_toolkit().pubsub
