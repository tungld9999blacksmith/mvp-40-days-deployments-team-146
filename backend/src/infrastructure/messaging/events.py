"""Wire DTOs for chat messages (camelCase, JSON-friendly).

``MessageDto`` is the client-facing projection of a ``ChatMessage`` row, shared
by REST, SSE (F4) and the WebSocket. ``MessageEventDto`` is what real-time
subscribers receive (``MessageDto`` + ``conversationId``); it round-trips through
Redis Pub/Sub. Internal-only fields (chunk/document ids, tool_calls, trace_id)
are intentionally dropped here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.common.core.conversation import ChatMessage, MessageRole

# Citation keys exposed to clients (trimmed snapshot); the rest stay server-side.
_CITATION_CLIENT_KEYS = ("title", "version", "documentType", "pageNumber", "snippet")


def _client_citations(citations: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        {k: c.get(k) for k in _CITATION_CLIENT_KEYS if k in c}
        for c in (citations or [])
    ]


class MessageDto(BaseModel):
    id: UUID
    seq: int | None = None
    role: MessageRole
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    refs: dict[str, Any] = Field(default_factory=dict)
    card: dict[str, Any] | None = None
    createdAt: datetime

    @classmethod
    def from_message(cls, message: ChatMessage) -> MessageDto:
        return cls(
            id=message.id,
            seq=message.seq,
            role=message.role,
            content=message.content,
            citations=_client_citations(message.citations),
            refs=message.refs or {},
            card=message.card,
            createdAt=message.created_at,
        )


class MessageEventDto(MessageDto):
    conversationId: UUID

    @classmethod
    def from_message(cls, message: ChatMessage) -> MessageEventDto:
        return cls(
            id=message.id,
            seq=message.seq,
            role=message.role,
            content=message.content,
            citations=_client_citations(message.citations),
            refs=message.refs or {},
            card=message.card,
            createdAt=message.created_at,
            conversationId=message.conversation_id,
        )


def conversation_channel(conversation_id: UUID | str) -> str:
    """Pub/Sub topic carrying one conversation's message stream."""
    return f"conversation.{conversation_id}"
