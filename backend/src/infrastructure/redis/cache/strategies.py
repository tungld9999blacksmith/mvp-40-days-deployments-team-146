"""
Cache strategies (Strategy pattern). Every strategy exposes the same three operations:

    read(key, loader, options)          -> value | None
    write(key, value, writer, options)  -> writer result
    invalidate(key, options)

`loader()` fetches the value from the source of truth (e.g. a Supabase query) and
`writer(value)` persists it. How and when the cache is touched is what differs:

| strategy      | read on miss                                   | write                                              |
|---------------|------------------------------------------------|----------------------------------------------------|
| cache_aside   | caller-supplied loader, then populate          | DB write, then delete cache key (+ double delete)  |
| read_through  | cache's own bound loader, stampede-protected   | DB write, then delete cache key                    |
| write_through | populate on miss                               | DB write, then set cache to the new value (sync)   |
| write_around  | populate on miss                               | DB write only; cache ages out via (short) TTL      |
| write_back    | pending buffer first, then loader              | cache now, DB later in batches (WriteBackBuffer)   |
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from ..errors import CacheError, LockNotOwnedError
from ..lock import LockManager
from .options import CacheOptions
from .store import MISS, CacheStore
from .write_back import WriteBackBuffer

logger = logging.getLogger(__name__)

Loader = Callable[[], Awaitable[Any]]
KeyLoader = Callable[[str], Awaitable[Any]]
Writer = Callable[[Any], Awaitable[Any]]


class CacheStrategy(ABC):
    name: ClassVar[str]

    def __init__(self, store: CacheStore, locks: LockManager) -> None:
        self.store = store
        self.locks = locks

    # ------------------------------------------------------------------ read
    async def read(self, key: str, loader: Loader | None, options: CacheOptions) -> Any:
        cached = await self.store.get(key, options)
        if cached is not MISS:
            return cached
        loader = self._resolve_loader(key, loader)
        if loader is None:
            return None
        if options.stampede_lock:
            return await self._load_single_flight(key, loader, options)
        return await self._load_and_store(key, loader, options)

    def _resolve_loader(self, key: str, loader: Loader | None) -> Loader | None:
        return loader

    async def _load_and_store(self, key: str, loader: Loader, options: CacheOptions) -> Any:
        value = await loader()
        await self.store.set(key, value, options)
        return value

    async def _load_single_flight(self, key: str, loader: Loader, options: CacheOptions) -> Any:
        lock = self.locks.critical_section(
            f"cache-fill:{self.store.full_key(key, options)}",
            ttl=options.stampede_lock_ttl,
            wait_timeout=options.stampede_wait,
        )
        if not await lock.acquire():
            # fail open: waited long enough, load ourselves rather than error out
            return await self._load_and_store(key, loader, options)
        try:
            cached = await self.store.get(key, options)
            if cached is not MISS:
                return cached
            return await self._load_and_store(key, loader, options)
        finally:
            with contextlib.suppress(LockNotOwnedError):
                await lock.release()

    # ----------------------------------------------------------------- write
    async def write(self, key: str, value: Any, writer: Writer | None, options: CacheOptions) -> Any:
        result = await self._require(writer)(value)
        await self.invalidate(key, options)
        return result

    async def invalidate(self, key: str, options: CacheOptions) -> None:
        await self.store.delete(key, options=options)

    @staticmethod
    def _require(writer: Writer | None) -> Writer:
        if writer is None:
            raise CacheError("This strategy writes to the source of truth and needs a writer")
        return writer


class CacheAsideStrategy(CacheStrategy):
    """Lazy loading: the application reads cache, loads from DB on miss, and invalidates on write."""

    name = "cache_aside"

    def __init__(self, store: CacheStore, locks: LockManager) -> None:
        super().__init__(store, locks)
        self._background: set[asyncio.Task[None]] = set()

    async def write(self, key: str, value: Any, writer: Writer | None, options: CacheOptions) -> Any:
        result = await super().write(key, value, writer, options)
        if options.double_delete_delay:
            task = asyncio.create_task(self._delayed_delete(key, options))
            self._background.add(task)
            task.add_done_callback(self._background.discard)
        return result

    async def _delayed_delete(self, key: str, options: CacheOptions) -> None:
        await asyncio.sleep(options.double_delete_delay or 0)
        try:
            await self.store.delete(key, options=options)
        except Exception:
            logger.exception("Delayed cache delete of %s failed", key)


class ReadThroughStrategy(CacheStrategy):
    """
    The cache owns the loading logic: it is built with a `key_loader(key)` and callers just
    `read(key)`. Stampede protection is on by default since every miss goes through one place.
    """

    name = "read_through"

    def __init__(self, store: CacheStore, locks: LockManager, key_loader: KeyLoader | None = None) -> None:
        super().__init__(store, locks)
        self.key_loader = key_loader

    async def read(self, key: str, loader: Loader | None, options: CacheOptions) -> Any:
        if not options.stampede_lock:
            options = options.merge(stampede_lock=True)
        return await super().read(key, loader, options)

    def _resolve_loader(self, key: str, loader: Loader | None) -> Loader | None:
        if loader is not None:
            return loader
        if self.key_loader is None:
            raise CacheError("read_through strategy needs a key_loader (or a loader per call)")
        key_loader = self.key_loader
        return lambda: key_loader(key)


class WriteThroughStrategy(CacheStrategy):
    """Every write goes to the DB and then synchronously to the cache — reads right after a write are warm."""

    name = "write_through"

    async def write(self, key: str, value: Any, writer: Writer | None, options: CacheOptions) -> Any:
        result = await self._require(writer)(value)
        # DB first: if it fails the cache keeps the previous (still correct) value
        cached_value = result if options.cache_writer_result and result is not None else value
        await self.store.set(key, cached_value, options)
        return result


class WriteAroundStrategy(CacheStrategy):
    """
    Writes bypass the cache entirely; entries refresh only when they expire. Use with a short
    TTL for write-heavy data that is rarely re-read right after being written.
    """

    name = "write_around"

    async def write(self, key: str, value: Any, writer: Writer | None, options: CacheOptions) -> Any:
        return await self._require(writer)(value)


class WriteBackStrategy(CacheStrategy):
    """
    Writes land in the cache immediately and are persisted to the DB later, in batches,
    by the `WriteBackBuffer` (queue = `options.write_back_queue`). Fastest writes; the DB
    lags behind by up to one flush interval. Register the queue's writer before writing.
    """

    name = "write_back"

    def __init__(self, store: CacheStore, locks: LockManager, buffer: WriteBackBuffer) -> None:
        super().__init__(store, locks)
        self.buffer = buffer

    async def read(self, key: str, loader: Loader | None, options: CacheOptions) -> Any:
        cached = await self.store.get(key, options)
        if cached is not MISS:
            return cached
        # cache entry expired before flush: the pending buffer still has the newest value
        pending = await self.buffer.pending(options.write_back_queue, self.store.full_key(key, options))
        if pending is not None:
            value = self.store.serializer(options).loads(pending)
            await self.store.set(key, value, options)
            return value
        return await super().read(key, loader, options)

    async def write(self, key: str, value: Any, writer: Writer | None, options: CacheOptions) -> Any:
        if value is None:
            raise CacheError("write_back cannot buffer None; use invalidate() to drop an entry")
        queue = options.write_back_queue
        if writer is not None and not self.buffer.is_registered(queue):
            self.buffer.register(queue, writer, self.store.serializer(options))
        await self.store.set(key, value, options)
        await self.buffer.mark_dirty(queue, self.store.full_key(key, options), self.store.encode(value, options))
        return None


STRATEGIES: dict[str, type[CacheStrategy]] = {
    cls.name: cls
    for cls in (
        CacheAsideStrategy,
        ReadThroughStrategy,
        WriteThroughStrategy,
        WriteAroundStrategy,
        WriteBackStrategy,
    )
}
