"""
Distributed work queue on Redis Streams + consumer groups.

Guarantees at-least-once delivery across any number of worker processes:

- `enqueue` appends to a stream; each message is delivered to exactly one consumer of the group.
- A message stays in the group's pending list until `ack`. If a worker dies mid-message, the
  message becomes visible again after `visibility_timeout` and another worker reclaims it.
- `nack` (or a handler exception in `consume`) re-enqueues with an optional delay; after
  `max_attempts` deliveries the message goes to the dead-letter stream instead.
- Delayed messages wait in a sorted set (score = due time) and are promoted atomically.

Handlers must be idempotent: at-least-once means a message can be processed twice
(e.g. a worker finishes the work but crashes before acking).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from . import _envelope
from .errors import QueueError
from .keys import KeyBuilder
from .serializers import Serializer, serializer_for

logger = logging.getLogger(__name__)

T = TypeVar("T")

_FIELD = b"m"

# KEYS: delayed zset, delayed payload hash, stream; ARGV: now, limit
_PROMOTE_LUA = """
local ids = redis.call('zrangebyscore', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
for _, id in ipairs(ids) do
  local env = redis.call('hget', KEYS[2], id)
  if env then
    redis.call('xadd', KEYS[3], '*', 'm', env)
  end
  redis.call('zrem', KEYS[1], id)
  redis.call('hdel', KEYS[2], id)
end
return #ids
"""


@dataclass
class QueueMessage(Generic[T]):
    id: str
    data: T
    attempt: int
    """1 on first delivery, incremented on every redelivery (nack, crash, timeout)."""
    enqueued_at: datetime
    headers: dict[str, str] = field(default_factory=dict)
    last_error: str | None = None
    _raw: bytes = field(default=b"", repr=False)


RetryDelay = float | Callable[[int], float] | None


def exponential_backoff(base: float = 1.0, cap: float = 300.0) -> Callable[[int], float]:
    """Retry delay factory: base * 2^(attempt-1), capped."""
    return lambda attempt: min(cap, base * 2 ** (attempt - 1))


class DistributedQueue(Generic[T]):
    def __init__(
        self,
        redis: Redis,
        keys: KeyBuilder,
        name: str,
        item_type: Any = None,
        *,
        serializer: Serializer[T] | None = None,
        group: str = "workers",
        consumer: str | None = None,
        visibility_timeout: float = 30.0,
        max_attempts: int = 5,
        maxlen: int | None = None,
    ) -> None:
        """
        Args:
            name: queue name (stream key <prefix>:queue:<name>).
            item_type: payload type hint; drives the default serializer.
            group: consumer group — every group gets its own copy of the stream (fan-out);
                consumers inside one group share the work.
            consumer: this worker's name; unique per process by default.
            visibility_timeout: seconds a delivered, un-acked message stays invisible before
                another worker may reclaim it. Must exceed your longest handler run.
            max_attempts: deliveries before a message is dead-lettered.
            maxlen: approximate cap on stream length (oldest entries trimmed).
        """
        self._redis = redis
        self.name = name
        self.group = group
        self.consumer = consumer or f"consumer-{uuid.uuid4().hex[:12]}"
        self.visibility_timeout = visibility_timeout
        self.max_attempts = max_attempts
        self.maxlen = maxlen
        self.serializer: Serializer[T] = serializer or serializer_for(item_type)

        qkeys = keys.child("queue", name)
        self.stream_key = qkeys.prefix
        self.delayed_key = qkeys.build("delayed")
        self.delayed_data_key = qkeys.build("delayed", "data")
        self.dead_key = qkeys.build("dead")
        self._group_ready = False
        self._promote = redis.register_script(_PROMOTE_LUA)

    # ------------------------------------------------------------------ setup
    async def ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self._redis.xgroup_create(self.stream_key, self.group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise QueueError(f"Cannot create consumer group {self.group!r}: {exc}") from exc
        self._group_ready = True

    # ---------------------------------------------------------------- produce
    def _pack(self, data: T, headers: dict[str, str] | None, attempts: int = 0, error: str | None = None) -> bytes:
        meta: dict[str, Any] = {"ts": time.time(), "attempts": attempts, "headers": headers or {}}
        if error:
            meta["error"] = error
        return _envelope.pack(meta, self.serializer.dumps(data))

    async def _push(self, raw: bytes, delay: float | None) -> str:
        if delay and delay > 0:
            delayed_id = uuid.uuid4().hex
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.hset(self.delayed_data_key, delayed_id, raw)  # type: ignore
                pipe.zadd(self.delayed_key, {delayed_id: time.time() + delay})
                await pipe.execute()
            return f"delayed:{delayed_id}"
        msg_id = await self._redis.xadd(
            self.stream_key, {_FIELD: raw}, maxlen=self.maxlen, approximate=self.maxlen is not None
        )
        return msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)

    async def enqueue(self, data: T, *, delay: float | None = None, headers: dict[str, str] | None = None) -> str:
        """Add a message; with *delay* (seconds) it becomes visible only after that time."""
        return await self._push(self._pack(data, headers), delay)

    async def enqueue_many(self, items: Iterable[T], *, headers: dict[str, str] | None = None) -> list[str]:
        async with self._redis.pipeline(transaction=False) as pipe:
            for item in items:
                pipe.xadd(
                    self.stream_key,
                    {_FIELD: self._pack(item, headers)},
                    maxlen=self.maxlen,
                    approximate=self.maxlen is not None,
                )
            ids = await pipe.execute()
        return [i.decode() if isinstance(i, bytes) else str(i) for i in ids]

    async def promote_due(self, limit: int = 100) -> int:
        """Move delayed messages whose time has come into the stream (atomic; safe from many workers)."""
        return int(
            await self._promote(
                keys=[self.delayed_key, self.delayed_data_key, self.stream_key], args=[time.time(), limit]
            )
        )

    # ---------------------------------------------------------------- consume
    def _decode(self, msg_id: bytes | str, fields: dict[bytes, bytes], deliveries: int) -> QueueMessage[T]:
        raw = fields[_FIELD]
        meta, payload = _envelope.unpack(raw)
        return QueueMessage(
            id=msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
            data=self.serializer.loads(payload),
            attempt=int(meta.get("attempts", 0)) + deliveries,
            enqueued_at=datetime.fromtimestamp(meta.get("ts", time.time()), tz=UTC),
            headers=meta.get("headers") or {},
            last_error=meta.get("error"),
            _raw=raw,
        )

    async def receive(self, count: int = 10, block: float | None = 1.0) -> list[QueueMessage[T]]:
        """
        Fetch up to *count* messages for this consumer: stale ones reclaimed from dead/slow
        workers first, then new ones. Blocks up to *block* seconds when the queue is empty
        (None = don't block).
        """
        await self.ensure_group()
        await self.promote_due()
        reclaimed = await self._reclaim_stale(count)
        if reclaimed:
            return reclaimed

        response = await self._redis.xreadgroup(
            self.group,
            self.consumer,
            {self.stream_key: ">"},
            count=count,
            block=int(block * 1000) if block else None,
        )
        messages: list[QueueMessage[T]] = []
        for _stream, entries in response or []:
            for msg_id, fields in entries:
                if fields:
                    messages.append(self._decode(msg_id, fields, deliveries=1))
        return messages

    async def _reclaim_stale(self, count: int) -> list[QueueMessage[T]]:
        idle_ms = int(self.visibility_timeout * 1000)
        pending = await self._redis.xpending_range(
            self.stream_key, self.group, min="-", max="+", count=count, idle=idle_ms
        )
        if not pending:
            return []
        deliveries = {p["message_id"]: int(p["times_delivered"]) for p in pending}
        claimed = await self._redis.xclaim(
            self.stream_key, self.group, self.consumer, min_idle_time=idle_ms, message_ids=list(deliveries)
        )
        messages: list[QueueMessage[T]] = []
        for msg_id, fields in claimed:
            if not fields:  # entry was trimmed/deleted while pending
                await self._redis.xack(self.stream_key, self.group, msg_id)
                continue
            message = self._decode(msg_id, fields, deliveries=deliveries.get(msg_id, 0) + 1)
            if message.attempt > self.max_attempts:
                await self.dead_letter(message, reason="visibility timeout exceeded too many times")
                continue
            messages.append(message)
        return messages

    async def ack(self, *messages: QueueMessage[T]) -> None:
        """Mark messages done (removes them from the pending list and the stream)."""
        if not messages:
            return
        ids = [m.id for m in messages]
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.xack(self.stream_key, self.group, *ids)
            pipe.xdel(self.stream_key, *ids)
            await pipe.execute()

    async def nack(self, message: QueueMessage[T], *, delay: float | None = None, error: str | None = None) -> None:
        """Processing failed: retry later (after *delay* seconds) or dead-letter once attempts run out."""
        if message.attempt >= self.max_attempts:
            await self.dead_letter(message, reason=error or "max attempts reached")
            return
        meta, payload = _envelope.unpack(message._raw)
        meta["attempts"] = message.attempt
        if error:
            meta["error"] = error
        await self._push(_envelope.pack(meta, payload), delay)
        await self.ack(message)

    async def dead_letter(self, message: QueueMessage[T], reason: str) -> None:
        meta, payload = _envelope.unpack(message._raw)
        meta.update(attempts=message.attempt, error=reason, dead_at=time.time(), original_id=message.id)
        await self._redis.xadd(self.dead_key, {_FIELD: _envelope.pack(meta, payload)})
        await self.ack(message)

    # ------------------------------------------------------------- worker loop
    async def consume(
        self,
        handler: Callable[[QueueMessage[T]], Awaitable[Any]],
        *,
        batch_size: int = 10,
        block: float = 1.0,
        concurrency: int = 1,
        retry_delay: RetryDelay = None,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        """
        Worker loop: receive -> handler -> ack, or nack on exception. Runs until *stop_event*
        is set (or the task is cancelled).

        Args:
            concurrency: max messages handled at once by this worker.
            retry_delay: seconds before a failed message is retried — a number, a function of
                the attempt number (see `exponential_backoff`), or None for immediate retry.
        """
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(message: QueueMessage[T]) -> None:
            async with semaphore:
                try:
                    await handler(message)
                except Exception as exc:
                    logger.exception("Queue %s: message %s failed (attempt %d)", self.name, message.id, message.attempt)
                    delay = retry_delay(message.attempt) if callable(retry_delay) else retry_delay
                    await self.nack(message, delay=delay, error=f"{type(exc).__name__}: {exc}")
                else:
                    await self.ack(message)

        while stop_event is None or not stop_event.is_set():
            try:
                messages = await self.receive(count=batch_size, block=block)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Queue %s: receive failed; retrying", self.name)
                await asyncio.sleep(1.0)
                continue
            if messages:
                await asyncio.gather(*(run_one(m) for m in messages))
            else:
                # Always yield to the event loop: a receive that completes without suspending
                # (e.g. fakeredis ignoring `block`) would otherwise starve every other task.
                await asyncio.sleep(0)

    # --------------------------------------------------------------- inspect
    async def size(self) -> int:
        """Messages in the stream (waiting + in flight). Excludes delayed and dead messages."""
        return int(await self._redis.xlen(self.stream_key))

    async def pending_count(self) -> int:
        """Messages delivered but not yet acked."""
        await self.ensure_group()
        info = await self._redis.xpending(self.stream_key, self.group)
        return int(info["pending"])

    async def delayed_count(self) -> int:
        return int(await self._redis.zcard(self.delayed_key))

    async def dead_count(self) -> int:
        return int(await self._redis.xlen(self.dead_key))

    async def dead_letters(self, count: int = 100) -> list[QueueMessage[T]]:
        entries = await self._redis.xrange(self.dead_key, count=count)
        return [self._decode(msg_id, fields, deliveries=0) for msg_id, fields in entries]

    async def requeue_dead(self, count: int = 100) -> int:
        """Move dead-lettered messages back to the queue with a fresh attempt counter."""
        moved = 0
        for message in await self.dead_letters(count):
            meta, payload = _envelope.unpack(message._raw)
            meta["attempts"] = 0
            meta.pop("error", None)
            await self._push(_envelope.pack(meta, payload), delay=None)
            await self._redis.xdel(self.dead_key, message.id)
            moved += 1
        return moved

    async def purge(self) -> None:
        """Delete the queue, its delayed set and its dead letters."""
        await self._redis.delete(self.stream_key, self.delayed_key, self.delayed_data_key, self.dead_key)
        self._group_ready = False


@contextlib.asynccontextmanager
async def running_consumer(queue: DistributedQueue[Any], handler: Callable[..., Awaitable[Any]], **kwargs: Any):
    """Run `queue.consume(handler)` in a background task for the duration of the block (e.g. app lifespan)."""
    stop = asyncio.Event()
    task = asyncio.create_task(queue.consume(handler, stop_event=stop, **kwargs))
    try:
        yield task
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
