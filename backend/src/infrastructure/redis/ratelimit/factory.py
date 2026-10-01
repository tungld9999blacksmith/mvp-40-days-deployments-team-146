"""Algorithm registry — pick a `RateLimiter` implementation by name."""

from __future__ import annotations

from enum import StrEnum

from redis.asyncio import Redis

from ..keys import KeyBuilder
from .base import Rate, RateLimiter
from .fixed_window import FixedWindowLimiter
from .leaky_bucket import LeakyBucketLimiter
from .sliding_window_counter import SlidingWindowCounterLimiter
from .sliding_window_log import SlidingWindowLogLimiter
from .token_bucket import TokenBucketLimiter


class Algorithm(StrEnum):
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"


_REGISTRY: dict[Algorithm, type[RateLimiter]] = {
    Algorithm.TOKEN_BUCKET: TokenBucketLimiter,
    Algorithm.LEAKY_BUCKET: LeakyBucketLimiter,
    Algorithm.FIXED_WINDOW: FixedWindowLimiter,
    Algorithm.SLIDING_WINDOW_LOG: SlidingWindowLogLimiter,
    Algorithm.SLIDING_WINDOW_COUNTER: SlidingWindowCounterLimiter,
}


def create_limiter(
    algorithm: Algorithm | str,
    redis: Redis,
    keys: KeyBuilder,
    rate: Rate,
) -> RateLimiter:
    """Instantiate the limiter for *algorithm* over the *keys* namespace."""
    algo = Algorithm(algorithm)
    return _REGISTRY[algo](redis, keys, rate)
