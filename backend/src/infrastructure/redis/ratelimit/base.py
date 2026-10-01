"""
Rate-limiter interface shared by every algorithm.

A `RateLimiter` answers one question atomically in Redis: *may this identity
perform `cost` units of work right now?* — and returns a `RateLimitResult`
rich enough to build standard `X-RateLimit-*` / `Retry-After` HTTP headers.

All limiters share:
    - one `Rate` (how much, over how long, with optional burst),
    - a per-limiter `KeyBuilder` namespace (`{prefix}:ratelimit:{algorithm}:{name}`),
    - keys derived per identity, so limits are isolated per caller.

Concrete algorithms live next to this file (token bucket, leaky bucket, fixed
window, sliding window log, sliding window counter). Pick one per endpoint
depending on the burst / smoothness / memory trade-off you want.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from redis.asyncio import Redis

from ..errors import RateLimitExceededError
from ..keys import KeyBuilder


@dataclass(frozen=True)
class Rate:
    """
    A quota expressed as *limit* events per *period* seconds.

    `burst` only matters for the bucket algorithms (token / leaky): it is the
    bucket capacity — how many events may fire back-to-back before the steady
    `per_second` rate applies. It defaults to `limit`.

        Rate(limit=100, period=60)              # 100 requests / minute
        Rate(limit=10, period=1, burst=20)      # 10 req/s sustained, bursts of 20
    """

    limit: int
    period: float
    burst: int | None = None

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("Rate.limit must be > 0")
        if self.period <= 0:
            raise ValueError("Rate.period must be > 0")
        if self.burst is not None and self.burst <= 0:
            raise ValueError("Rate.burst must be > 0")

    @property
    def per_second(self) -> float:
        """Steady refill / leak rate in events per second."""
        return self.limit / self.period

    @property
    def capacity(self) -> int:
        """Bucket capacity for token / leaky bucket (burst, or limit if unset)."""
        return self.burst if self.burst is not None else self.limit

    @classmethod
    def per_minute(cls, limit: int, burst: int | None = None) -> Rate:
        return cls(limit=limit, period=60.0, burst=burst)

    @classmethod
    def per_hour(cls, limit: int, burst: int | None = None) -> Rate:
        return cls(limit=limit, period=3600.0, burst=burst)


@dataclass(frozen=True)
class RateLimitResult:
    """
    Outcome of one `try_acquire`.

    Attributes:
        allowed: whether the request may proceed.
        limit: the ceiling for the current window / bucket (for `X-RateLimit-Limit`).
        remaining: units still available after this call (never negative).
        reset_after: seconds until the quota is fully replenished.
        retry_after: seconds to wait before this request would succeed;
            `0.0` when allowed.
    """

    allowed: bool
    limit: int
    remaining: int
    reset_after: float
    retry_after: float = 0.0

    @property
    def headers(self) -> dict[str, str]:
        """Standard rate-limit response headers."""
        out = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_after) + 1),
        }
        if not self.allowed:
            out["Retry-After"] = str(int(self.retry_after) + 1)
        return out


class RateLimiter(ABC):
    """
    Common base: holds the Redis client, the namespace and the `Rate`, and
    turns an identity into a concrete Redis key.

    Subclasses implement `try_acquire`. Everything is atomic server-side (Lua),
    so concurrent requests for the same identity cannot over-admit.
    """

    #: Short algorithm id, used in the key namespace and for logging.
    algorithm: str = "base"

    def __init__(self, redis: Redis, keys: KeyBuilder, rate: Rate) -> None:
        self._redis = redis
        self._keys = keys
        self.rate = rate

    def _key(self, identity: str, *extra: object) -> str:
        return self._keys.build(identity, *extra)

    @staticmethod
    def _now_ms() -> int:
        return int(time.time() * 1000)

    @abstractmethod
    async def try_acquire(self, identity: str, cost: int = 1) -> RateLimitResult:
        """
        Attempt to consume *cost* units for *identity* without blocking.

        Returns a `RateLimitResult`; never raises on a plain over-limit — check
        `result.allowed`. Use `acquire` if you want an exception instead.
        """

    async def acquire(self, identity: str, cost: int = 1) -> RateLimitResult:
        """Like `try_acquire`, but raise `RateLimitExceededError` when denied."""
        result = await self.try_acquire(identity, cost)
        if not result.allowed:
            raise RateLimitExceededError(
                identity,
                limit=result.limit,
                remaining=result.remaining,
                retry_after=result.retry_after,
                reset_after=result.reset_after,
            )
        return result

    @abstractmethod
    async def reset(self, identity: str) -> None:
        """Drop all state for *identity* (e.g. after a manual unblock or in tests)."""

    async def peek(self, identity: str) -> RateLimitResult:
        """
        Report the current state without consuming (cost=0).

        Every algorithm here treats cost=0 as a pure read that still refreshes
        time-based state (refill / leak / window roll-over) but admits nothing.
        """
        return await self.try_acquire(identity, cost=0)
