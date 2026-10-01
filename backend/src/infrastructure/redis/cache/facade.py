"""
CacheFacade — the single entry point for caching (Facade pattern over CacheStore,
the CacheStrategy family, the WriteBackBuffer and the stampede locks).

Direct calls:
    await cache.read("vehicle:42", loader=lambda: repo.get(42), strategy="cache_aside", ttl=600)
    await cache.write("vehicle:42", vehicle, writer=repo.save, strategy="write_through")

Decorators (for repository / service coroutines, e.g. Supabase queries):
    @cache.cached("vehicle:{vehicle_id}", ttl=600, tags=["vehicles"])
    @cache.cache_write("vehicle:{vehicle.id}", strategy="write_through")
    @cache.cache_evict(tags=["vehicles"])
"""

from __future__ import annotations

import functools
import inspect
import types
import typing
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Generic, ParamSpec, TypeVar

from redis.asyncio import Redis

from .._templating import bind_arguments, build_key, render_template, require_async
from ..errors import CacheError
from ..keys import KeyBuilder
from ..lock import LockManager
from ..serializers import serializer_for
from .options import CacheOptions
from .store import MISS, CacheStore
from .strategies import (
    CacheAsideStrategy,
    CacheStrategy,
    KeyLoader,
    Loader,
    ReadThroughStrategy,
    WriteAroundStrategy,
    WriteBackStrategy,
    Writer,
    WriteThroughStrategy,
)
from .write_back import WriteBackBuffer

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")

KeySpec = str | Callable[..., str] | None


class CacheFacade:
    def __init__(
        self,
        redis: Redis,
        keys: KeyBuilder,
        locks: LockManager,
        *,
        default_ttl: float = 300.0,
        default_options: CacheOptions | None = None,
    ) -> None:
        self.store = CacheStore(redis, keys, default_ttl=default_ttl)
        self.locks = locks
        self.write_back_buffer = WriteBackBuffer(redis, keys, locks)
        self.defaults = default_options or CacheOptions()
        self._strategies: dict[str, CacheStrategy] = {}
        for strategy in (
            CacheAsideStrategy(self.store, locks),
            ReadThroughStrategy(self.store, locks),
            WriteThroughStrategy(self.store, locks),
            WriteAroundStrategy(self.store, locks),
            WriteBackStrategy(self.store, locks, self.write_back_buffer),
        ):
            self.register_strategy(strategy)

    # -------------------------------------------------------------- strategies
    def register_strategy(self, strategy: CacheStrategy, name: str | None = None) -> None:
        """Plug in a custom CacheStrategy (or replace a built-in one)."""
        self._strategies[name or strategy.name] = strategy

    def strategy(self, name: str) -> CacheStrategy:
        try:
            return self._strategies[name]
        except KeyError:
            raise CacheError(f"Unknown cache strategy {name!r}; available: {sorted(self._strategies)}") from None

    @property
    def strategies(self) -> list[str]:
        return sorted(self._strategies)

    def options(self, options: CacheOptions | None = None, **overrides: Any) -> CacheOptions:
        return (options or self.defaults).merge(**overrides)

    # --------------------------------------------------------- plain key/value
    async def get(self, key: str, default: Any = None, **overrides: Any) -> Any:
        value = await self.store.get(key, self.options(**overrides))
        return default if value is MISS else value

    async def set(self, key: str, value: Any, **overrides: Any) -> None:
        await self.store.set(key, value, self.options(**overrides))

    async def delete(self, *keys: str, namespace: str | None = None) -> int:
        return await self.store.delete(*keys, options=self.options(namespace=namespace))

    async def exists(self, key: str, namespace: str | None = None) -> bool:
        return await self.store.exists(key, self.options(namespace=namespace))

    async def ttl(self, key: str, namespace: str | None = None) -> float | None:
        return await self.store.ttl(key, self.options(namespace=namespace))

    async def invalidate_tags(self, *tags: str) -> int:
        return await self.store.invalidate_tags(*tags)

    async def invalidate_pattern(self, pattern: str, namespace: str | None = None) -> int:
        return await self.store.invalidate_pattern(pattern, namespace=namespace)

    # ------------------------------------------------------ strategy-driven ops
    async def read(
        self,
        key: str,
        loader: Loader | None = None,
        *,
        strategy: str = "cache_aside",
        options: CacheOptions | None = None,
        **overrides: Any,
    ) -> Any:
        """Read *key* through *strategy*; on a miss the value comes from `loader()`."""
        return await self.strategy(strategy).read(key, loader, self.options(options, **overrides))

    async def write(
        self,
        key: str,
        value: Any,
        writer: Writer | None = None,
        *,
        strategy: str = "write_through",
        options: CacheOptions | None = None,
        **overrides: Any,
    ) -> Any:
        """Persist *value* with `writer(value)` and update the cache as *strategy* dictates."""
        return await self.strategy(strategy).write(key, value, writer, self.options(options, **overrides))

    async def invalidate(self, key: str, *, strategy: str = "cache_aside", **overrides: Any) -> None:
        await self.strategy(strategy).invalidate(key, self.options(**overrides))

    def read_through(self, key_loader: KeyLoader, value_type: Any = None, **overrides: Any) -> ReadThroughCache[Any]:
        """
        A cache bound to its own loader — callers only ever pass keys:

            vehicles = cache.read_through(lambda key: repo.get(int(key)), Vehicle | None, namespace="vehicle")
            await vehicles.get("42")

        *value_type* builds the serializer, so cache hits come back as the same type the loader returns.
        """
        opts = self.options(**overrides)
        if opts.serializer is None and value_type is not None:
            opts = opts.merge(serializer=serializer_for(value_type))
        return ReadThroughCache(ReadThroughStrategy(self.store, self.locks, key_loader), opts)

    # -------------------------------------------------------------- write-back
    def register_write_back(self, queue: str, writer: Writer, **overrides: Any) -> None:
        """Register the DB writer that flushes queue *queue* (must happen on every instance that flushes)."""
        self.write_back_buffer.register(queue, writer, self.store.serializer(self.options(**overrides)))

    # ------------------------------------------------------------- decorators
    def cached(
        self,
        key: KeySpec = None,
        *,
        strategy: str = "cache_aside",
        condition: Callable[..., bool] | None = None,
        **overrides: Any,
    ) -> Callable[[Callable[P, Awaitable[R]]], CachedFunction[P, R]]:
        """
        Cache the result of a read coroutine (e.g. a Supabase query).

        Args:
            key: template over the arguments ("vehicle:{vehicle_id}", "user:{user.id}:vehicles"),
                a callable(*args, **kwargs) -> str, or None for an automatic key from the arguments.
            strategy: read strategy — "cache_aside" (default), "read_through" (stampede-protected),
                "write_back" (also serves not-yet-flushed values).
            condition: callable(*args, **kwargs) -> bool; when False the call bypasses the cache.
            **overrides: any CacheOptions field — ttl, serializer, namespace, tags, ttl_jitter,
                cache_none, none_ttl, stampede_lock, cache_if, ...
                The serializer defaults to one built from the function's return annotation,
                so `-> Vehicle | None` / `-> list[Vehicle]` come back as models, not dicts.
        """

        def decorator(func: Callable[P, Awaitable[R]]) -> CachedFunction[P, R]:
            require_async(func)
            opts = self.options(**overrides)
            if opts.serializer is None:
                opts = opts.merge(serializer=serializer_for(_return_type(func)))
            return CachedFunction(self, func, key, self.strategy(strategy), opts, condition)

        return decorator

    def cache_write(
        self,
        key: KeySpec,
        *,
        strategy: str = "write_through",
        value_arg: str | None = None,
        queue: str | None = None,
        **overrides: Any,
    ) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R | None]]]:
        """
        Turn a DB-write coroutine into a cached write under *strategy*:

            @cache.cache_write("vehicle:{vehicle.id}", strategy="write_through")
            async def save_vehicle(vehicle: Vehicle, session: Session) -> Vehicle: ...

        - The decorated function is the writer; the cached value is its `value_arg` argument
          (default: first parameter), or its return value with `cache_writer_result=True`.
        - write_through: DB then cache.  cache_aside: DB then evict.  write_around: DB only.
        - write_back: the call returns None immediately; the function runs later in a flush,
          called as `func(<value_arg>=value)` — so its other parameters need defaults.
          *queue* defaults to the function's dotted path.
        """

        def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R | None]]:
            require_async(func)
            params = [p for p in inspect.signature(func).parameters if p not in ("self", "cls")]
            arg_name = value_arg or (params[0] if params else None)
            if arg_name is None:
                raise CacheError(f"{func.__qualname__} has no argument to cache; pass value_arg=")
            chosen = self.strategy(strategy)
            opts = self.options(**overrides)
            if strategy == "write_back":
                opts = opts.merge(write_back_queue=queue or f"{func.__module__}.{func.__qualname__}")
            if opts.serializer is None:
                hints = _type_hints(func)
                hint = hints.get("return") if opts.cache_writer_result else hints.get(arg_name)
                opts = opts.merge(serializer=serializer_for(hint))
            if strategy == "write_back":

                async def flush_writer(value: Any) -> Any:
                    return await func(**{arg_name: value})  # type: ignore[call-arg]

                self.write_back_buffer.register(opts.write_back_queue, flush_writer, self.store.serializer(opts))

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
                bound = bind_arguments(func, args, kwargs)
                cache_key = build_key(func, args, kwargs, key)

                async def writer(_: Any) -> R:
                    return await func(*args, **kwargs)

                return await chosen.write(cache_key, bound[arg_name], writer, opts)

            return wrapper

        return decorator

    def cache_evict(
        self,
        *keys: KeySpec,
        tags: Iterable[str] = (),
        pattern: str | None = None,
        namespace: str | None = None,
        before: bool = False,
    ) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
        """
        Invalidate cache entries when the decorated coroutine runs (after it succeeds, or
        `before=True` to evict first). *keys* and *pattern* may be argument templates.

            @cache.cache_evict("vehicle:{vehicle_id}", tags=["vehicles"])
            async def delete_vehicle(vehicle_id: int) -> None: ...
        """
        tag_list = list(tags)

        def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
            require_async(func)

            async def evict(args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
                resolved = [build_key(func, args, kwargs, k) for k in keys]
                if resolved:
                    await self.delete(*resolved, namespace=namespace)
                if tag_list:
                    await self.invalidate_tags(*tag_list)
                if pattern:
                    rendered = render_template(pattern, bind_arguments(func, args, kwargs))
                    await self.invalidate_pattern(rendered, namespace=namespace)

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                if before:
                    await evict(args, kwargs)
                result = await func(*args, **kwargs)
                if not before:
                    await evict(args, kwargs)
                return result

            return wrapper

        return decorator


class CachedFunction(Generic[P, R]):
    """The callable returned by `@cache.cached` — plus `invalidate`, `refresh` and `key_for` helpers."""

    def __init__(
        self,
        facade: CacheFacade,
        func: Callable[P, Awaitable[R]],
        key: KeySpec,
        strategy: CacheStrategy,
        options: CacheOptions,
        condition: Callable[..., bool] | None,
    ) -> None:
        functools.update_wrapper(self, func)
        self._facade = facade
        self._func = func
        self._key = key
        self._strategy = strategy
        self.options = options
        self._condition = condition

    def key_for(self, *args: P.args, **kwargs: P.kwargs) -> str:
        return build_key(self._func, args, kwargs, self._key)

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        if self._condition is not None and not self._condition(*args, **kwargs):
            return await self._func(*args, **kwargs)
        return await self._strategy.read(
            self.key_for(*args, **kwargs),
            lambda: self._func(*args, **kwargs),
            self.options,
        )

    async def invalidate(self, *args: P.args, **kwargs: P.kwargs) -> None:
        """Drop the cached entry for these arguments."""
        await self._strategy.invalidate(self.key_for(*args, **kwargs), self.options)

    async def refresh(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """Reload from the source and overwrite the cached entry."""
        value = await self._func(*args, **kwargs)
        await self._facade.store.set(self.key_for(*args, **kwargs), value, self.options)
        return value

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        # support decorating methods: bind `self` like a normal function would
        if instance is None:
            return self
        return types.MethodType(self, instance)


class ReadThroughCache(Generic[T]):
    """A read-through cache bound to one loader; returned by `CacheFacade.read_through`."""

    def __init__(self, strategy: ReadThroughStrategy, options: CacheOptions) -> None:
        self._strategy = strategy
        self.options = options

    async def get(self, key: str) -> T | None:
        return await self._strategy.read(key, None, self.options)

    async def invalidate(self, key: str) -> None:
        await self._strategy.invalidate(key, self.options)

    async def refresh(self, key: str) -> T | None:
        await self.invalidate(key)
        return await self.get(key)


def _type_hints(func: Callable[..., Any]) -> dict[str, Any]:
    try:
        return typing.get_type_hints(func)
    except Exception:  # unresolved forward refs — fall back to untyped JSON
        return {}


def _return_type(func: Callable[..., Any]) -> Any:
    return _type_hints(func).get("return")
