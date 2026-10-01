"""
Distributed lock on one or more Redis keys (single-instance Redlock-style).

- Acquire is all-or-nothing across every key, in one Lua script (no partial locks, no deadlock
  from acquisition order).
- Each holder gets a random token; release / extend only touch keys still holding that token,
  so a holder whose TTL expired can never delete someone else's lock.
- Each successful acquire also returns a monotonically increasing *fencing token*. Pass it to the
  storage layer (e.g. `WHERE version < :fence`) to reject writes from a holder that stalled past its TTL.
- Not re-entrant: acquiring the same lock twice from the same task waits for itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable, Sequence
from types import TracebackType
from typing import Any

from redis.asyncio import Redis

from ..errors import LockAcquireError, LockNotOwnedError

logger = logging.getLogger(__name__)

# KEYS[1..n-1] = lock keys, KEYS[n] = fencing counter; ARGV = token, ttl_ms
_ACQUIRE_LUA = """
for i = 1, #KEYS - 1 do
  if redis.call('exists', KEYS[i]) == 1 then return 0 end
end
for i = 1, #KEYS - 1 do
  redis.call('set', KEYS[i], ARGV[1], 'PX', ARGV[2])
end
return redis.call('incr', KEYS[#KEYS])
"""

# KEYS = lock keys; ARGV = token. Returns how many keys were still ours.
_RELEASE_LUA = """
local released = 0
for i = 1, #KEYS do
  if redis.call('get', KEYS[i]) == ARGV[1] then
    redis.call('del', KEYS[i])
    released = released + 1
  end
end
return released
"""

# KEYS = lock keys; ARGV = token, ttl_ms. All-or-nothing.
_EXTEND_LUA = """
for i = 1, #KEYS do
  if redis.call('get', KEYS[i]) ~= ARGV[1] then return 0 end
end
for i = 1, #KEYS do
  redis.call('pexpire', KEYS[i], ARGV[2])
end
return 1
"""

WAIT_FOREVER = None


class DistributedLock:
    def __init__(
        self,
        redis: Redis,
        keys: Sequence[str],
        fence_key: str,
        *,
        ttl: float = 30.0,
        wait_timeout: float | None = 10.0,
        retry_interval: float = 0.05,
        max_retry_interval: float = 0.5,
        auto_renew: bool = False,
        token: str | None = None,
    ) -> None:
        """
        Args:
            keys: Redis keys to lock together.
            ttl: lock lifetime in seconds; the lock auto-expires if the holder crashes.
            wait_timeout: seconds to wait for the lock. 0 = try once, None = wait forever.
            retry_interval / max_retry_interval: exponential backoff (with jitter) between attempts.
            auto_renew: run a watchdog that extends the TTL every ttl/3 while held — for work
                whose duration is unknown. The lock still expires if the process dies.
            token: holder identity; random by default.
        """
        if not keys:
            raise ValueError("DistributedLock needs at least one key")
        if ttl <= 0:
            raise ValueError("ttl must be > 0")
        self._redis = redis
        self._keys = sorted(set(keys))
        self._fence_key = fence_key
        self.ttl = ttl
        self.wait_timeout = wait_timeout
        self._retry_interval = retry_interval
        self._max_retry_interval = max_retry_interval
        self._auto_renew = auto_renew
        self.token = token or uuid.uuid4().hex
        self.fencing_token: int | None = None
        self._lost = False
        self._watchdog: asyncio.Task[None] | None = None

        self._acquire_script = redis.register_script(_ACQUIRE_LUA)
        self._release_script = redis.register_script(_RELEASE_LUA)
        self._extend_script = redis.register_script(_EXTEND_LUA)

    @property
    def keys(self) -> list[str]:
        return list(self._keys)

    @property
    def acquired(self) -> bool:
        return self.fencing_token is not None

    @property
    def lost(self) -> bool:
        """True if the auto-renew watchdog found the lock expired or taken over."""
        return self._lost

    @property
    def _ttl_ms(self) -> int:
        return max(1, int(self.ttl * 1000))

    async def _try_acquire(self) -> bool:
        fence = await self._acquire_script(keys=[*self._keys, self._fence_key], args=[self.token, self._ttl_ms])
        if not fence:
            return False
        self.fencing_token = int(fence)
        self._lost = False
        if self._auto_renew:
            self._watchdog = asyncio.create_task(self._renew_loop())
        return True

    async def acquire(self, blocking: bool = True, wait_timeout: float | None | object = ...) -> bool:
        """Try to take the lock. Returns False if not acquired within the timeout."""
        if self.acquired:
            raise RuntimeError("Lock instance already acquired; create a new instance per holder")
        timeout = self.wait_timeout if wait_timeout is ... else wait_timeout
        if not blocking:
            timeout = 0

        deadline = None if timeout is None else time.monotonic() + float(timeout)  # type: ignore[arg-type]
        delay = self._retry_interval
        while True:
            if await self._try_acquire():
                return True
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                sleep_for = min(delay, remaining)
            else:
                sleep_for = delay
            await asyncio.sleep(sleep_for * random.uniform(0.5, 1.0))
            delay = min(delay * 2, self._max_retry_interval)

    async def release(self) -> None:
        """Release every key still held. Raises LockNotOwnedError if any key had already expired."""
        await self._stop_watchdog()
        if not self.acquired:
            return
        released = await self._release_script(keys=self._keys, args=[self.token])
        self.fencing_token = None
        if int(released) != len(self._keys):
            raise LockNotOwnedError(
                f"Lock {self._keys} expired before release ({released}/{len(self._keys)} keys still owned); "
                "the protected section outlived the TTL"
            )

    async def extend(self, ttl: float | None = None) -> None:
        """Reset the TTL (to *ttl* seconds, or the original ttl). Raises LockNotOwnedError if lost."""
        if not self.acquired:
            raise LockNotOwnedError("Cannot extend a lock that is not acquired")
        if ttl is not None:
            self.ttl = ttl
        if not await self._extend_script(keys=self._keys, args=[self.token, self._ttl_ms]):
            self._lost = True
            raise LockNotOwnedError(f"Lock {self._keys} is no longer owned by this holder")

    async def is_owned(self) -> bool:
        if not self.acquired:
            return False
        values = await self._redis.mget(self._keys)
        return all(v is not None and v.decode() == self.token for v in values)

    async def _renew_loop(self) -> None:
        interval = self.ttl / 3
        while True:
            await asyncio.sleep(interval)
            try:
                await self.extend()
            except LockNotOwnedError:
                logger.warning("Distributed lock %s lost while held (auto-renew failed)", self._keys)
                return
            except Exception:  # transient network error: keep trying until the TTL runs out
                logger.exception("Auto-renew of lock %s failed; retrying", self._keys)

    async def _stop_watchdog(self) -> None:
        if self._watchdog is not None:
            self._watchdog.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog
            self._watchdog = None

    async def __aenter__(self) -> DistributedLock:
        if not await self.acquire():
            raise LockAcquireError(f"Could not acquire lock {self._keys} within {self.wait_timeout}s")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self.release()
        except LockNotOwnedError:
            if exc_type is None:
                raise
            # don't mask the body's own exception
            logger.warning("Lock %s had expired before release", self._keys)


Hook = Callable[[], Awaitable[Any] | Any]


class TransactionLock(DistributedLock):
    """
    Locks every resource touched by one system/business transaction, as a unit.

    - `transaction_id` is the lock token, so `LockManager.holder(resource)` tells you which
      transaction currently owns a resource.
    - `after_commit` hooks run when the block exits normally, `after_rollback` hooks when it
      raises — both *before* the locks are released, so e.g. cache invalidation happens while
      no other transaction can touch the same rows.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._on_commit: list[Hook] = []
        self._on_rollback: list[Hook] = []

    @property
    def transaction_id(self) -> str:
        return self.token

    def after_commit(self, hook: Hook) -> Hook:
        self._on_commit.append(hook)
        return hook

    def after_rollback(self, hook: Hook) -> Hook:
        self._on_rollback.append(hook)
        return hook

    async def _run_hooks(self, hooks: list[Hook]) -> None:
        for hook in hooks:
            try:
                result = hook()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Transaction %s hook %r failed", self.transaction_id, hook)

    async def __aenter__(self) -> TransactionLock:
        await super().__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            await self._run_hooks(self._on_rollback if exc_type else self._on_commit)
        finally:
            await super().__aexit__(exc_type, exc, tb)
