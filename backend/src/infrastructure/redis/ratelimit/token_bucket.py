"""
Token bucket.

A bucket holds up to `capacity` tokens and refills at `rate.per_second`. Each
request removes `cost` tokens; if fewer than `cost` remain, it is denied. Lets
callers burst up to `capacity` after an idle period, then settles to the steady
rate — the friendliest algorithm for bursty-but-well-behaved clients.

State is a hash `{tokens, ts}` refilled lazily on each call, so no background
worker is needed. The whole read-refill-consume cycle runs in one Lua script.
"""

from __future__ import annotations

from redis.asyncio import Redis

from ..keys import KeyBuilder
from .base import Rate, RateLimiter, RateLimitResult

# KEYS[1] = bucket hash
# ARGV = capacity, refill_per_sec, now_ms, cost, ttl_ms
# Returns {allowed, tokens_left(str), retry_after_s(str), reset_after_s(str)}
_LUA = """
local key      = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate     = tonumber(ARGV[2])
local now      = tonumber(ARGV[3])
local cost     = tonumber(ARGV[4])
local ttl      = tonumber(ARGV[5])

local state  = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts     = tonumber(state[2])
if tokens == nil then
  tokens = capacity
  ts = now
end

-- Lazy refill for the time elapsed since the last touch.
local elapsed = math.max(0, now - ts) / 1000.0
tokens = math.min(capacity, tokens + elapsed * rate)

local allowed = 0
if tokens >= cost then
  allowed = 1
  tokens = tokens - cost
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', key, ttl)

local retry = 0.0
if allowed == 0 and rate > 0 then
  retry = (cost - tokens) / rate
end
local reset = 0.0
if rate > 0 then
  reset = (capacity - tokens) / rate
end
return {allowed, tostring(tokens), tostring(retry), tostring(reset)}
"""


class TokenBucketLimiter(RateLimiter):
    algorithm = "tb"

    def __init__(self, redis: Redis, keys: KeyBuilder, rate: Rate) -> None:
        super().__init__(redis, keys, rate)
        self._script = redis.register_script(_LUA)
        # Keep a bucket around for a few refill periods of idleness, then let it expire.
        self._ttl_ms = max(1000, int(self.rate.capacity / self.rate.per_second * 2 * 1000))

    async def try_acquire(self, identity: str, cost: int = 1) -> RateLimitResult:
        capacity = self.rate.capacity
        allowed, tokens, retry, reset = await self._script(
            keys=[self._key(identity)],
            args=[capacity, self.rate.per_second, self._now_ms(), cost, self._ttl_ms],
        )
        tokens_left = float(tokens)
        return RateLimitResult(
            allowed=bool(allowed),
            limit=capacity,
            remaining=max(0, int(tokens_left)),
            reset_after=float(reset),
            retry_after=float(retry),
        )

    async def reset(self, identity: str) -> None:
        await self._redis.delete(self._key(identity))
