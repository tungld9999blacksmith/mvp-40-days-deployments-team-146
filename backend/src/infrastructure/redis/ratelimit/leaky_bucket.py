"""
Leaky bucket (as a meter).

Think of a bucket that leaks at a constant `rate.per_second`. Each request pours
in `cost` units of water; it is admitted only if the water stays at or below
`capacity`. Unlike the token bucket, the *outflow* is perfectly smooth — this is
the algorithm to protect a downstream that must be fed at a steady pace.

State is a hash `{level, ts}` drained lazily on each call (no background worker),
all inside one Lua script. Equivalent to GCRA / the classic "leaky bucket as a
meter" formulation.
"""

from __future__ import annotations

from redis.asyncio import Redis

from ..keys import KeyBuilder
from .base import Rate, RateLimiter, RateLimitResult

# KEYS[1] = bucket hash
# ARGV = capacity, leak_per_sec, now_ms, cost, ttl_ms
# Returns {allowed, level_after(str), retry_after_s(str), reset_after_s(str)}
_LUA = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local leak     = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])
local cost     = tonumber(ARGV[4])
local ttl      = tonumber(ARGV[5])

local state = redis.call('HMGET', key, 'level', 'ts')
local level = tonumber(state[1])
local ts    = tonumber(state[2])
if level == nil then
  level = 0.0
  ts = now
end

-- Lazy leak for the time elapsed since the last touch.
local elapsed = math.max(0, now - ts) / 1000.0
level = math.max(0.0, level - elapsed * leak)

local allowed = 0
if level + cost <= capacity then
  allowed = 1
  level = level + cost
end

redis.call('HSET', key, 'level', level, 'ts', now)
redis.call('PEXPIRE', key, ttl)

local retry = 0.0
if allowed == 0 and leak > 0 then
  -- Wait until enough has leaked to fit this request.
  retry = (level + cost - capacity) / leak
end
local reset = 0.0
if leak > 0 then
  reset = level / leak
end
return {allowed, tostring(level), tostring(retry), tostring(reset)}
"""


class LeakyBucketLimiter(RateLimiter):
    algorithm = "lb"

    def __init__(self, redis: Redis, keys: KeyBuilder, rate: Rate) -> None:
        super().__init__(redis, keys, rate)
        self._script = redis.register_script(_LUA)
        self._ttl_ms = max(1000, int(self.rate.capacity / self.rate.per_second * 2 * 1000))

    async def try_acquire(self, identity: str, cost: int = 1) -> RateLimitResult:
        capacity = self.rate.capacity
        allowed, level, retry, reset = await self._script(
            keys=[self._key(identity)],
            args=[capacity, self.rate.per_second, self._now_ms(), cost, self._ttl_ms],
        )
        level_after = float(level)
        return RateLimitResult(
            allowed=bool(allowed),
            limit=capacity,
            remaining=max(0, int(capacity - level_after)),
            reset_after=float(reset),
            retry_after=float(retry),
        )

    async def reset(self, identity: str) -> None:
        await self._redis.delete(self._key(identity))
