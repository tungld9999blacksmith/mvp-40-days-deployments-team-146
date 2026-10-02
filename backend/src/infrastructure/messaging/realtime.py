"""Chat message persistence + real-time fan-out (SVC-MSG-001).

``MessageService`` is the single writer of ``chat_message`` (FF F4 BR-602). Every
turn:

    1. validate the role shape (BR-ENT-466),
    2. persist to Postgres and bump ``conversation.last_message_at`` in one
       transaction (the durable source of truth),
    3. publish a ``MessageEventDto`` on the conversation's Redis Pub/Sub channel
       *after commit* (so a subscriber can always read the row back), and
    4. optionally hand the message id to Celery for vector indexing — gated by
       ``settings.conversation_semantic_index_enabled`` (Q-604, default off).

Ordering is fixed: commit → publish → index. Persistence is synchronous
(repositories are sync) and runs in a worker thread so the async publish/stream
path never blocks the event loop. Publish/index failures are logged, never
raised: the message is already durable and clients can catch up over REST.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

import anyio
from sqlmodel import Session

from src.common.core.conversation import (
    ChatMessage,
    ChatMessageRepository,
    ConversationRepository,
    MessageRole,
)
from src.common.data_access import eq

from ..redis.pubsub import PubSubBroker
from .events import MessageEventDto, conversation_channel

logger = logging.getLogger(__name__)

_TITLE_MAX = 60


class ConversationNotFoundError(Exception):
    """Raised by the writer when the target conversation does not exist."""


class InvalidMessageError(ValueError):
    """Raised when a message violates its role shape (BR-ENT-466)."""


@dataclass
class NewMessage:
    """One message for ``append_many`` (persisted in insertion order)."""

    role: MessageRole
    content: str = ""
    client_message_id: UUID | None = None
    citations: list = field(default_factory=list)
    tool_calls: list = field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None
    refs: dict = field(default_factory=dict)
    card: dict | None = None
    intent: str | None = None
    agent_run_id: UUID | None = None
    trace_id: str | None = None


@dataclass
class AppendResult:
    message: ChatMessage
    created: bool


def _validate(item: NewMessage) -> None:
    role = item.role
    if role == MessageRole.USER:
        if not item.content or item.citations or item.tool_calls:
            raise InvalidMessageError("user message must have content and no citations/tool_calls")
    elif role == MessageRole.ASSISTANT:
        if not item.content and not item.tool_calls:
            raise InvalidMessageError("assistant message must have content or tool_calls")
    elif role == MessageRole.TOOL:
        if not item.tool_call_id or not item.tool_name:
            raise InvalidMessageError("tool message must carry tool_call_id and tool_name")


def _to_values(item: NewMessage, conversation_id: UUID) -> dict:
    return {
        "conversation_id": conversation_id,
        "role": item.role,
        "content": item.content,
        "client_message_id": item.client_message_id,
        "citations": item.citations,
        "tool_calls": item.tool_calls,
        "tool_call_id": item.tool_call_id,
        "tool_name": item.tool_name,
        "refs": item.refs,
        "card": item.card,
        "intent": item.intent,
        "agent_run_id": item.agent_run_id,
        "trace_id": item.trace_id,
    }


class MessageService:
    def __init__(
        self,
        db_engine,
        pubsub: PubSubBroker,
        *,
        index_dispatch: Callable[[str], None] | None = None,
        semantic_index_enabled: bool = False,
    ) -> None:
        self._db_engine = db_engine
        self._pubsub = pubsub
        self._index_dispatch = index_dispatch
        self._semantic_index_enabled = semantic_index_enabled

    def _topic(self, conversation_id: UUID):
        return self._pubsub.topic(conversation_channel(conversation_id), MessageEventDto)

    # -- write ------------------------------------------------------------
    async def append(
        self,
        conversation_id: UUID,
        role: MessageRole,
        content: str = "",
        *,
        publish: bool = True,
        **kwargs,
    ) -> AppendResult:
        """Persist one message, then publish + index it (see module docstring)."""
        result = await self.append_many(
            conversation_id, [NewMessage(role=role, content=content, **kwargs)], publish=publish
        )
        return result[0]

    async def append_many(
        self,
        conversation_id: UUID,
        items: Sequence[NewMessage],
        *,
        publish: bool = True,
    ) -> list[AppendResult]:
        for item in items:
            _validate(item)
        results: list[AppendResult] = await anyio.to_thread.run_sync(self._persist_many, conversation_id, list(items))

        for result in results:
            if not result.created:
                continue
            message = result.message
            if publish and message.role in (MessageRole.USER, MessageRole.ASSISTANT):
                await self._safe_publish(conversation_id, message)
            if self._semantic_index_enabled and message.role in (
                MessageRole.USER,
                MessageRole.ASSISTANT,
            ):
                self._safe_dispatch_index(message)
        return results

    def _persist_many(self, conversation_id: UUID, items: list[NewMessage]) -> list[AppendResult]:
        with Session(self._db_engine) as session:
            conv_repo = ConversationRepository(session)
            conversation = conv_repo.get(conversation_id)
            if conversation is None:
                raise ConversationNotFoundError(str(conversation_id))

            msg_repo = ChatMessageRepository(session)
            results: list[AppendResult] = []
            title_set = bool(conversation.title)
            for item in items:
                existing = self._find_duplicate(msg_repo, conversation_id, item)
                if existing is not None:
                    results.append(AppendResult(existing, created=False))
                    continue
                message = msg_repo.create(_to_values(item, conversation_id))
                results.append(AppendResult(message, created=True))
                if not title_set and item.role == MessageRole.USER and item.content:
                    conversation.title = item.content[:_TITLE_MAX]
                    title_set = True

            if any(r.created for r in results):
                conversation.last_message_at = datetime.now(UTC)
                session.add(conversation)

            session.commit()
            for result in results:
                session.refresh(result.message)
            return results

    @staticmethod
    def _find_duplicate(repo: ChatMessageRepository, conversation_id: UUID, item: NewMessage) -> ChatMessage | None:
        if item.role != MessageRole.USER or item.client_message_id is None:
            return None
        return repo.find_one(
            filters=[
                eq("conversation_id", conversation_id),
                eq("client_message_id", item.client_message_id),
            ]
        )

    # -- realtime ---------------------------------------------------------
    async def subscribe(self, conversation_id: UUID) -> AsyncIterator[MessageEventDto]:
        """Yield live message events for a conversation until the caller stops."""
        async for message in self._topic(conversation_id).subscribe():
            yield message.data

    async def _safe_publish(self, conversation_id: UUID, message: ChatMessage) -> None:
        try:
            await self._topic(conversation_id).publish(MessageEventDto.from_message(message))
        except Exception:  # noqa: BLE001 — durable already; catch-up via REST
            logger.exception("Failed to publish message %s", message.id)

    def _safe_dispatch_index(self, message: ChatMessage) -> None:
        if self._index_dispatch is None:
            return
        try:
            self._index_dispatch(str(message.id))
        except Exception:  # noqa: BLE001 — indexing is best-effort
            logger.exception("Failed to enqueue indexing for message %s", message.id)
