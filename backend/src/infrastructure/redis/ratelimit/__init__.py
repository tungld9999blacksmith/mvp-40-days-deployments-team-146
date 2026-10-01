"""
Redis-backed rate limiting.

An interface (`RateLimiter`) with five interchangeable algorithms, each enforced
atomically in Redis via Lua so concurrent requests can never over-admit:

    - TokenBucketLimiter          — burst up to capacity, steady refill (friendly default)
    - LeakyBucketLimiter          — perfectly smooth outflow to protect a downstream
    - FixedWindowLimiter          — O(1), cheapest, allows a boundary burst
    - SlidingWindowLogLimiter     — exact, per-event ZSET log (best for low, sensitive limits)
    - SlidingWindowCounterLimiter — O(1) two-counter approximation of the sliding window

Build one through the toolkit and attach it to routes with `rate_limit`:

    limiter = toolkit.rate_limiter("login", Rate(5, 60), Algorithm.SLIDING_WINDOW_LOG)

    @router.post("/login", dependencies=[Depends(rate_limit(limiter, by_api_token()))])
    async def login(): ...

`identity` chooses *whom* to limit (IP / API token / `X-RateLimit-Key` header /
authenticated user) per endpoint.
"""

from .base import Rate, RateLimiter, RateLimitResult
from .dependency import (
    install_rate_limiting,
    rate_limit,
    rate_limit_exceeded_handler,
)
from .factory import Algorithm, create_limiter
from .fixed_window import FixedWindowLimiter
from .identity import (
    RATE_LIMIT_KEY_HEADER,
    Identity,
    IdentityResolver,
    by_api_token,
    by_header,
    by_ip,
    by_state,
    first_of,
)
from .leaky_bucket import LeakyBucketLimiter
from .sliding_window_counter import SlidingWindowCounterLimiter
from .sliding_window_log import SlidingWindowLogLimiter
from .token_bucket import TokenBucketLimiter

__all__ = [
    "RATE_LIMIT_KEY_HEADER",
    "Algorithm",
    "FixedWindowLimiter",
    "Identity",
    "IdentityResolver",
    "LeakyBucketLimiter",
    "Rate",
    "RateLimitResult",
    "RateLimiter",
    "SlidingWindowCounterLimiter",
    "SlidingWindowLogLimiter",
    "TokenBucketLimiter",
    "by_api_token",
    "by_header",
    "by_ip",
    "by_state",
    "create_limiter",
    "first_of",
    "install_rate_limiting",
    "rate_limit",
    "rate_limit_exceeded_handler",
]
