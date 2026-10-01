"""
Sliding window log.

Every admitted request is appended to a ZSET as a member scored by its arrival
timestamp (an event log). On each call the log is trimmed to the last
`rate.period` seconds and its size compared against `rate.limit`. This is the
*exact* sliding window: no boundary burst, no approximation — at the price of
O(admitted) memory per identity, so reserve it for low-limit, high-value
endpoints (login, payment, OTP).

Trim + count + append run in one Lua script for atomicity. Members are made
unique with a per-call token so requests landing on the same millisecond do not
collide.
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from ..keys import KeyBuilder
from .base import Rate, RateLimiter, RateLimitResult

# KEYS[1] = log zset
# ARGV = now_ms, window_ms, limit, cost, ttl_ms, token
# Returns {allowed, count_after, oldest_score(str), newest_score(str)}
_LUA = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local cost   = tonumber(ARGV[4])
local ttl    = tonumber(ARGV[5])
local token  = ARGV[6]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

local allowed = 0
if count + cost <= limit then
  allowed = 1
  for i = 1, cost do
    redis.call('ZADD', key, now, token .. '-' .. i)
  end
  count = count + cost
end
redis.call('PEXPIRE', key, ttl)

local oldest = -1
local newest = -1
local lo = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
if lo[2] then oldest = tonumber(lo[2]) end
local hi = redis.call('ZRANGE', key, -1, -1, 'WITHSCORES')
if hi[2] then newest = tonumber(hi[2]) end
return {allowed, count, tostring(oldest), tostring(newest)}
"""


class SlidingWindowLogLimiter(RateLimiter):
    algorithm = "swl"

    def __init__(self, redis: Redis, keys: KeyBuilder, rate: Rate) -> None:
        super().__init__(redis, keys, rate)
        self._script = redis.register_script(_LUA)
        self._window_ms = int(self.rate.period * 1000)

    async def try_acquire(self, identity: str, cost: int = 1) -> RateLimitResult:
        now = self._now_ms()
        allowed, count, oldest, newest = await self._script(
            keys=[self._key(identity)],
            args=[now, self._window_ms, self.rate.limit, cost, self._window_ms, uuid.uuid4().hex],
        )
        oldest_ms = float(oldest)
        newest_ms = float(newest)
        # A slot frees when the oldest entry leaves the window.
        retry_after = 0.0
        if not allowed and oldest_ms >= 0:
            retry_after = max(0.0, (oldest_ms + self._window_ms - now) / 1000.0)
        # Fully replenished when the newest entry leaves the window.
        reset_after = 0.0 if newest_ms < 0 else max(0.0, (newest_ms + self._window_ms - now) / 1000.0)
        return RateLimitResult(
            allowed=bool(allowed),
            limit=self.rate.limit,
            remaining=max(0, self.rate.limit - int(count)),
            reset_after=reset_after,
            retry_after=retry_after,
        )

    async def reset(self, identity: str) -> None:
        await self._redis.delete(self._key(identity))
