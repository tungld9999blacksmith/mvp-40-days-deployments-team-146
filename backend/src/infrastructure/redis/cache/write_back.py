"""
Write-back (write-behind) buffer.

A write-back write updates the cache immediately and records the value in a Redis hash
`<prefix>:cache:_wb:<queue>` (field = cache key). A flush — periodic via `start()`, or manual
via `flush()` — calls the queue's registered writer for each pending value and removes the entry
only if it hasn't been overwritten meanwhile, so a newer value written during the flush is never lost.

Pending values live in Redis, not in process memory, so they survive an app restart and any
instance can flush them. A cluster-wide lock per queue keeps two instances from flushing
the same queue at once.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis

from ..keys import KeyBuilder
from ..lock import LockManager
from ..serializers import Serializer

logger = logging.getLogger(__name__)

WriteBackWriter = Callable[[Any], Awaitable[Any]]

# KEYS[1] = pending hash; ARGV = field, value-seen-at-flush
_COMPARE_AND_HDEL_LUA = """
if redis.call('hget', KEYS[1], ARGV[1]) == ARGV[2] then
  return redis.call('hdel', KEYS[1], ARGV[1])
end
return 0
"""


@dataclass(frozen=True)
class _Registration:
    writer: WriteBackWriter
    serializer: Serializer[Any]


@dataclass
class FlushResult:
    flushed: int = 0
    failed: int = 0
    skipped_locked: bool = False


class WriteBackBuffer:
    def __init__(self, redis: Redis, keys: KeyBuilder, locks: LockManager) -> None:
        self._redis = redis
        self._keys = keys.child("cache", "_wb")
        self._locks = locks
        self._writers: dict[str, _Registration] = {}
        self._task: asyncio.Task[None] | None = None
        self._cas_hdel = redis.register_script(_COMPARE_AND_HDEL_LUA)

    def register(self, queue: str, writer: WriteBackWriter, serializer: Serializer[Any]) -> None:
        """`writer(value)` persists one value to the database; `serializer` decodes pending bytes."""
        self._writers[queue] = _Registration(writer, serializer)

    def is_registered(self, queue: str) -> bool:
        return queue in self._writers

    def _pending_key(self, queue: str) -> str:
        return self._keys.build(queue)

    async def mark_dirty(self, queue: str, cache_key: str, payload: bytes) -> None:
        if queue not in self._writers:
            raise KeyError(f"No write-back writer registered for queue {queue!r}")
        await self._redis.hset(self._pending_key(queue), cache_key, payload)

    async def pending(self, queue: str, cache_key: str) -> bytes | None:
        """Not-yet-flushed payload for a key (read path falls back to it on a cache miss)."""
        return await self._redis.hget(self._pending_key(queue), cache_key)

    async def pending_count(self, queue: str | None = None) -> int:
        queues = [queue] if queue else list(self._writers)
        return sum([int(await self._redis.hlen(self._pending_key(q))) for q in queues])

    async def flush(self, queue: str | None = None, batch_size: int = 100) -> FlushResult:
        """Persist pending values of *queue* (or all registered queues). Failed writes stay pending."""
        total = FlushResult()
        for name in [queue] if queue else list(self._writers):
            result = await self._flush_queue(name, batch_size)
            total.flushed += result.flushed
            total.failed += result.failed
            total.skipped_locked = total.skipped_locked or result.skipped_locked
        return total

    async def _flush_queue(self, queue: str, batch_size: int) -> FlushResult:
        registration = self._writers[queue]
        pending_key = self._pending_key(queue)
        result = FlushResult()
        lock = self._locks.critical_section(f"write-back-flush:{queue}", ttl=60, wait_timeout=0, auto_renew=True)
        if not await lock.acquire():
            result.skipped_locked = True
            return result
        try:
            async for field, payload in self._redis.hscan_iter(pending_key, count=batch_size):
                try:
                    await registration.writer(registration.serializer.loads(payload))
                except Exception:
                    result.failed += 1
                    logger.exception("Write-back flush of %s (queue %s) failed; will retry", field, queue)
                    continue
                await self._cas_hdel(keys=[pending_key], args=[field, payload])
                result.flushed += 1
        finally:
            with contextlib.suppress(Exception):
                await lock.release()
        return result

    # ------------------------------------------------------------ background
    def start(self, interval: float = 5.0) -> None:
        """Flush every *interval* seconds in a background task (call from the app lifespan)."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(interval))

    async def stop(self, final_flush: bool = True) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        if final_flush:
            await self.flush()

    async def _run(self, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                await self.flush()
            except Exception:
                logger.exception("Write-back flush loop error")
