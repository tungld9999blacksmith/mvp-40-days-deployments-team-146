"""
LockManager — facade over DistributedLock for the three locking styles:

    locks.lock_data(LockKey(data_type="vehicle", data_id=42))   # lock by data (row / entity)
    locks.critical_section("recompute-leaderboard")               # lock a code section, cluster-wide
    locks.transaction(key_a, key_b, "billing")                    # lock everything a transaction touches

Each returns an async context manager; the decorator forms are `@locks.data_locked(...)`
and `@locks.synchronized(...)`.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, ParamSpec, TypeVar

from redis.asyncio import Redis

from .._templating import bind_arguments, render_template, require_async
from ..keys import KeyBuilder
from .lock import DistributedLock, TransactionLock
from .models import LockKey

P = ParamSpec("P")
R = TypeVar("R")

Resource = LockKey | str
_UNSET: Any = ...


class LockManager:
    def __init__(
        self,
        redis: Redis,
        keys: KeyBuilder,
        *,
        default_ttl: float = 30.0,
        default_wait_timeout: float | None = 10.0,
    ) -> None:
        self._redis = redis
        self._keys = keys.child("lock")
        self.default_ttl = default_ttl
        self.default_wait_timeout = default_wait_timeout

    # ------------------------------------------------------------------ keys
    def key_for(self, resource: Resource) -> str:
        """LockKey -> <prefix>:lock:data:<type>:<id>; str -> <prefix>:lock:cs:<name>."""
        if isinstance(resource, LockKey):
            return self._keys.build("data", resource.data_type, resource.data_id)
        return self._keys.build("cs", resource)

    @property
    def _fence_key(self) -> str:
        return self._keys.build("fence")

    def _make(
        self,
        cls: type[DistributedLock],
        resources: Iterable[Resource],
        ttl: float | None,
        wait_timeout: float | None,
        auto_renew: bool,
    ) -> Any:
        return cls(
            self._redis,
            [self.key_for(r) for r in resources],
            self._fence_key,
            ttl=ttl or self.default_ttl,
            wait_timeout=self.default_wait_timeout if wait_timeout is _UNSET else wait_timeout,
            auto_renew=auto_renew,
        )

    # --------------------------------------------------------------- factories
    def lock_data(
        self,
        *keys: LockKey,
        ttl: float | None = None,
        wait_timeout: float | None = _UNSET,
        auto_renew: bool = False,
    ) -> DistributedLock:
        """Lock one or more data records (all-or-nothing)."""
        if not keys:
            raise ValueError("lock_data needs at least one LockKey")
        return self._make(DistributedLock, keys, ttl, wait_timeout, auto_renew)

    def critical_section(
        self,
        name: str,
        *,
        ttl: float | None = None,
        wait_timeout: float | None = _UNSET,
        auto_renew: bool = False,
    ) -> DistributedLock:
        """Mutual exclusion for a named section of code across every process/instance."""
        return self._make(DistributedLock, [name], ttl, wait_timeout, auto_renew)

    def transaction(
        self,
        *resources: Resource,
        ttl: float | None = None,
        wait_timeout: float | None = _UNSET,
        auto_renew: bool = True,
    ) -> TransactionLock:
        """
        Lock every resource a system transaction touches, atomically, for the whole transaction.
        Mix data keys and section names freely. `auto_renew` defaults to True because
        transaction duration is rarely known up front.
        """
        if not resources:
            raise ValueError("transaction needs at least one resource")
        return self._make(TransactionLock, resources, ttl, wait_timeout, auto_renew)

    # ------------------------------------------------------------- inspection
    async def is_locked(self, resource: Resource) -> bool:
        return bool(await self._redis.exists(self.key_for(resource)))

    async def holder(self, resource: Resource) -> str | None:
        """Token (= transaction_id for TransactionLock) of whoever holds *resource*."""
        value = await self._redis.get(self.key_for(resource))
        return value.decode() if value is not None else None

    async def force_release(self, resource: Resource) -> bool:
        """Admin escape hatch: delete a lock regardless of owner."""
        return bool(await self._redis.delete(self.key_for(resource)))

    # -------------------------------------------------------------- decorators
    def synchronized(
        self,
        name: str | None = None,
        *,
        ttl: float | None = None,
        wait_timeout: float | None = _UNSET,
        auto_renew: bool = False,
    ) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
        """
        Run the decorated coroutine as a cluster-wide critical section.
        *name* may be a template over the arguments ("sync-user:{user_id}"); default is the function path.
        """

        def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
            require_async(func)
            section = name or f"{func.__module__}.{func.__qualname__}"

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                resolved = render_template(section, bind_arguments(func, args, kwargs))
                async with self.critical_section(resolved, ttl=ttl, wait_timeout=wait_timeout, auto_renew=auto_renew):
                    return await func(*args, **kwargs)

            return wrapper

        return decorator

    def data_locked(
        self,
        data_type: str | None = None,
        data_id: str | None = None,
        *,
        key: Callable[..., LockKey | Iterable[LockKey]] | None = None,
        ttl: float | None = None,
        wait_timeout: float | None = _UNSET,
        auto_renew: bool = False,
    ) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
        """
        Lock the data the decorated coroutine works on:

            @locks.data_locked("vehicle", "{vehicle_id}")
            async def update_vehicle(vehicle_id: int, ...): ...

            @locks.data_locked(key=lambda src, dst, **_: [LockKey(data_type="wallet", data_id=src),
                                                          LockKey(data_type="wallet", data_id=dst)])
            async def transfer(src: int, dst: int, amount: int): ...
        """
        if key is None and (data_type is None or data_id is None):
            raise ValueError("data_locked needs (data_type, data_id template) or key=callable")

        def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
            require_async(func)

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                if key is not None:
                    produced = key(*args, **kwargs)
                    lock_keys = [produced] if isinstance(produced, LockKey) else list(produced)
                else:
                    rendered = render_template(str(data_id), bind_arguments(func, args, kwargs))
                    lock_keys = [LockKey(data_type=str(data_type), data_id=rendered)]
                async with self.lock_data(*lock_keys, ttl=ttl, wait_timeout=wait_timeout, auto_renew=auto_renew):
                    return await func(*args, **kwargs)

            return wrapper

        return decorator
