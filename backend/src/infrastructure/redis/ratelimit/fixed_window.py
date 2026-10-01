"""
Fixed window counter.

Time is chopped into fixed windows of `rate.period` seconds. Each window is a
single counter (one Redis key per identity per window); a request is admitted
while the counter stays at or below `rate.limit`. Cheapest algorithm — O(1)
memory and one integer per window — but allows up to `2 * limit` requests across
a window boundary (a burst at the end of one window plus a burst at the start of
the next). Use it when that edge burst is acceptable.
"""

from __future__ import annotations

from redis.asyncio import Redis

from ..keys import KeyBuilder
from .base import Rate, RateLimiter, RateLimitResult

# KEYS[1] = counter key for the current window
# ARGV = limit, cost, window_ms
# Returns {allowed, count_after}
_LUA = """
local key    = KEYS[1]
local limit  = tonumber(ARGV[1])
local cost   = tonumber(ARGV[2])
local ttl    = tonumber(ARGV[3])

local current = tonumber(redis.call('GET', key)) or 0
local allowed = 0
if current + cost <= limit then
  allowed = 1
  current = redis.call('INCRBY', key, cost)
  redis.call('PEXPIRE', key, ttl)
end
return {allowed, current}
"""


class FixedWindowLimiter(RateLimiter):
    algorithm = "fw"

    def __init__(self, redis: Redis, keys: KeyBuilder, rate: Rate) -> None:
        super().__init__(redis, keys, rate)
        self._script = redis.register_script(_LUA)
        self._window_ms = int(self.rate.period * 1000)

    async def try_acquire(self, identity: str, cost: int = 1) -> RateLimitResult:
        now = self._now_ms()
        window_id = now // self._window_ms
        window_end = (window_id + 1) * self._window_ms
        reset_after = (window_end - now) / 1000.0

        allowed, count = await self._script(
            keys=[self._key(identity, window_id)],
            args=[self.rate.limit, cost, self._window_ms],
        )
        return RateLimitResult(
            allowed=bool(allowed),
            limit=self.rate.limit,
            remaining=max(0, self.rate.limit - int(count)),
            reset_after=reset_after,
            # Denied requests can only succeed once the window rolls over.
            retry_after=0.0 if allowed else reset_after,
        )

    async def reset(self, identity: str) -> None:
        now = self._now_ms()
        window_id = now // self._window_ms
        await self._redis.delete(self._key(identity, window_id))
