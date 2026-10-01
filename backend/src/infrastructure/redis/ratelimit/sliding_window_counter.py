"""
Sliding window counter.

A pragmatic middle ground between the fixed window (cheap, bursty at edges) and
the log (exact, memory-hungry). It keeps just two counters — the current window
and the previous one — and estimates the rolling count as::

    estimate = current + previous * (fraction of the previous window still in view)

That weighted blend smooths the fixed-window boundary burst using O(1) memory
(one small hash per identity). It slightly over- or under-counts under uneven
traffic, but is the usual default for high-throughput HTTP rate limiting.

The read / roll-over / consume cycle runs in one Lua script.
"""

from __future__ import annotations

import math

from redis.asyncio import Redis

from ..keys import KeyBuilder
from .base import Rate, RateLimiter, RateLimitResult

# KEYS[1] = state hash {win, cur, prev}
# ARGV = now_ms, window_ms, limit, cost, ttl_ms
# Returns {allowed, cur(str), prev(str), estimate(str), elapsed_ms(str)}
_LUA = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local cost   = tonumber(ARGV[4])
local ttl    = tonumber(ARGV[5])

local cur_win = math.floor(now / window)
local d    = redis.call('HMGET', key, 'win', 'cur', 'prev')
local win  = tonumber(d[1])
local cur  = tonumber(d[2]) or 0
local prev = tonumber(d[3]) or 0

if win == nil then
  win = cur_win; cur = 0; prev = 0
elseif cur_win == win then
  -- still in the same window
elseif cur_win == win + 1 then
  prev = cur; cur = 0; win = cur_win
else
  prev = 0; cur = 0; win = cur_win
end

local elapsed  = now - cur_win * window
local weight   = (window - elapsed) / window
local estimate = cur + prev * weight

local allowed = 0
if estimate + cost <= limit then
  allowed = 1
  cur = cur + cost
  estimate = estimate + cost
end

redis.call('HSET', key, 'win', win, 'cur', cur, 'prev', prev)
redis.call('PEXPIRE', key, ttl)
return {allowed, tostring(cur), tostring(prev), tostring(estimate), tostring(elapsed)}
"""


class SlidingWindowCounterLimiter(RateLimiter):
    algorithm = "swc"

    def __init__(self, redis: Redis, keys: KeyBuilder, rate: Rate) -> None:
        super().__init__(redis, keys, rate)
        self._script = redis.register_script(_LUA)
        self._window_ms = int(self.rate.period * 1000)

    async def try_acquire(self, identity: str, cost: int = 1) -> RateLimitResult:
        limit = self.rate.limit
        allowed, cur, prev, estimate, elapsed = await self._script(
            keys=[self._key(identity)],
            args=[self._now_ms(), self._window_ms, limit, cost, 2 * self._window_ms],
        )
        cur_f, prev_f, estimate_f = float(cur), float(prev), float(estimate)
        remaining_in_win_ms = self._window_ms - float(elapsed)

        reset_after = self._reset_after(cur_f, prev_f, remaining_in_win_ms)
        retry_after = 0.0
        if not allowed:
            retry_after = self._retry_after(cur_f, prev_f, remaining_in_win_ms, limit, cost)

        return RateLimitResult(
            allowed=bool(allowed),
            limit=limit,
            remaining=max(0, limit - math.ceil(estimate_f)),
            reset_after=reset_after,
            retry_after=retry_after,
        )

    def _reset_after(self, cur: float, prev: float, remaining_in_win_ms: float) -> float:
        """Seconds until both counters have fully rolled out of view."""
        if prev > 0:
            # prev fully leaves at the end of this window; cur becomes prev and
            # leaves one window later.
            return (remaining_in_win_ms + (self._window_ms if cur > 0 else 0)) / 1000.0
        if cur > 0:
            return remaining_in_win_ms / 1000.0
        return 0.0

    def _retry_after(
        self, cur: float, prev: float, remaining_in_win_ms: float, limit: int, cost: int
    ) -> float:
        """
        Estimate when the request would fit, exploiting that the previous
        window's weighted contribution decays linearly to 0 by window end.
        """
        headroom = limit - cost - cur
        if prev > 0 and headroom >= 0:
            # estimate(dt) = cur + prev * (remaining_in_win - dt) / window == limit - cost
            dt_ms = remaining_in_win_ms - headroom * self._window_ms / prev
            if 0 <= dt_ms <= remaining_in_win_ms:
                return dt_ms / 1000.0
        # Current window itself is saturated: earliest relief is the next window.
        return max(0.0, remaining_in_win_ms) / 1000.0

    async def reset(self, identity: str) -> None:
        await self._redis.delete(self._key(identity))
