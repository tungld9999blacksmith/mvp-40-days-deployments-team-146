"""
Generic, typed Pub/Sub.

A `Topic[T]` is a typed channel: whatever you publish is serialized with the topic's
Serializer and comes back to subscribers as `Message[T]` with the payload already decoded.

    vehicle_events = toolkit.pubsub.topic("vehicle.updated", VehicleEvent)

    await vehicle_events.publish(VehicleEvent(id=42, status="parked"))

    async for message in vehicle_events.subscribe():      # ad-hoc consumer
        print(message.data.status)

    @vehicle_events.on                                     # long-running handler
    async def handle(message: Message[VehicleEvent]) -> None: ...
    await toolkit.pubsub.start()

Pattern topics (`topic("vehicle.*", VehicleEvent, pattern=True)`) subscribe with PSUBSCRIBE;
`message.channel` then holds the concrete channel name.

Redis Pub/Sub is fire-and-forget: subscribers that are offline miss messages.
Use `DistributedQueue` when every message must be processed.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Generic, TypeVar

from redis.asyncio import Redis

from . import _envelope
from .keys import KeyBuilder
from .serializers import Serializer, serializer_for

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class Message(Generic[T]):
    topic: str
    channel: str
    data: T
    id: str
    published_at: datetime
    headers: dict[str, str] = field(default_factory=dict)


Handler = Callable[[Message[Any]], Awaitable[Any] | Any]


class Topic(Generic[T]):
    def __init__(
        self,
        broker: PubSubBroker,
        name: str,
        payload_type: Any = None,
        *,
        serializer: Serializer[T] | None = None,
        pattern: bool = False,
    ) -> None:
        self.broker = broker
        self.name = name
        self.pattern = pattern
        self.serializer: Serializer[T] = serializer or serializer_for(payload_type)

    @property
    def redis_channel(self) -> str:
        return self.broker.channel_key(self.name)

    async def publish(self, data: T, headers: dict[str, str] | None = None, channel: str | None = None) -> int:
        """Publish *data*; returns how many subscribers received it. Pattern topics need a concrete *channel*."""
        return await self.broker.publish(self, data, headers=headers, channel=channel)

    def subscribe(self) -> AsyncIterator[Message[T]]:
        return self.broker.subscribe(self)

    def on(self, handler: Handler) -> Handler:
        """Decorator: register a long-running handler (dispatched once `broker.start()` runs)."""
        self.broker.add_handler(self, handler)
        return handler

    def decode(self, channel: str, raw: bytes) -> Message[T]:
        meta, payload = _envelope.unpack(raw)
        return Message(
            topic=self.name,
            channel=channel,
            data=self.serializer.loads(payload),
            id=meta.get("id", ""),
            published_at=datetime.fromtimestamp(meta.get("ts", time.time()), tz=UTC),
            headers=meta.get("headers") or {},
        )


class PubSubBroker:
    def __init__(self, redis: Redis, keys: KeyBuilder) -> None:
        self._redis = redis
        self._keys = keys.child("pubsub")
        self._handlers: dict[tuple[str, bool], tuple[Topic[Any], list[Handler]]] = {}
        self._task: asyncio.Task[None] | None = None

    def channel_key(self, name: str) -> str:
        return self._keys.build(name)

    def _strip(self, redis_channel: bytes | str) -> str:
        name = redis_channel.decode() if isinstance(redis_channel, bytes) else redis_channel
        prefix = self._keys.prefix + ":"
        return name[len(prefix) :] if name.startswith(prefix) else name

    def topic(
        self,
        name: str,
        payload_type: Any = None,
        *,
        serializer: Serializer[Any] | None = None,
        pattern: bool = False,
    ) -> Topic[Any]:
        return Topic(self, name, payload_type, serializer=serializer, pattern=pattern)

    # ---------------------------------------------------------------- publish
    async def publish(
        self,
        topic: Topic[T],
        data: T,
        *,
        headers: dict[str, str] | None = None,
        channel: str | None = None,
    ) -> int:
        if topic.pattern and channel is None:
            raise ValueError(f"Pattern topic {topic.name!r} needs a concrete channel to publish to")
        meta = {"id": uuid.uuid4().hex, "ts": time.time(), "headers": headers or {}}
        raw = _envelope.pack(meta, topic.serializer.dumps(data))
        return int(await self._redis.publish(self.channel_key(channel or topic.name), raw))

    # -------------------------------------------------------------- subscribe
    async def subscribe(self, *topics: Topic[Any], poll_timeout: float = 1.0) -> AsyncIterator[Message[Any]]:
        """Async iterator over messages of *topics*; the connection closes when the iterator is closed."""
        if not topics:
            raise ValueError("subscribe needs at least one topic")
        channels = {t.redis_channel: t for t in topics if not t.pattern}
        patterns = {t.redis_channel: t for t in topics if t.pattern}

        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        try:
            if channels:
                await pubsub.subscribe(*channels)
            if patterns:
                await pubsub.psubscribe(*patterns)
            while True:
                raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll_timeout)
                if raw is None:
                    continue
                message = self._decode(raw, channels, patterns)
                if message is not None:
                    yield message
        finally:
            with contextlib.suppress(Exception):
                await pubsub.aclose()

    def _decode(
        self,
        raw: dict[str, Any],
        channels: dict[str, Topic[Any]],
        patterns: dict[str, Topic[Any]],
    ) -> Message[Any] | None:
        channel = raw["channel"].decode() if isinstance(raw["channel"], bytes) else raw["channel"]
        if raw["type"] == "pmessage":
            pattern = raw["pattern"].decode() if isinstance(raw["pattern"], bytes) else raw["pattern"]
            topic = patterns.get(pattern)
        else:
            topic = channels.get(channel)
        if topic is None:
            return None
        try:
            return topic.decode(self._strip(channel), raw["data"])
        except Exception:
            logger.exception("Dropping undecodable message on %s", channel)
            return None

    # --------------------------------------------------------------- handlers
    def add_handler(self, topic: Topic[Any], handler: Handler) -> None:
        entry = self._handlers.setdefault((topic.name, topic.pattern), (topic, []))
        entry[1].append(handler)
        if self.running:
            # restart the listener so it subscribes to the new topic too
            self._restart()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """Start dispatching messages to registered handlers in a background task."""
        if not self.running and self._handlers:
            self._task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def _restart(self) -> None:
        if self._task is not None:
            self._task.cancel()
        self._task = asyncio.create_task(self._listen())

    async def _listen(self) -> None:
        backoff = 0.5
        while True:
            topics = [topic for topic, _ in self._handlers.values()]
            try:
                async for message in self.subscribe(*topics):
                    backoff = 0.5
                    await self._dispatch(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Pub/Sub listener disconnected; reconnecting in %.1fs", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 10.0)

    async def _dispatch(self, message: Message[Any]) -> None:
        for key in ((message.topic, False), (message.topic, True)):
            entry = self._handlers.get(key)
            if entry is None:
                continue
            for handler in entry[1]:
                try:
                    result = handler(message)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    logger.exception("Pub/Sub handler %r failed for message %s", handler, message.id)
