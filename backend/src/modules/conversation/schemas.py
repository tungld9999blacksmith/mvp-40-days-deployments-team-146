"""Conversation module — request/response schemas (US-025 API)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.infrastructure.messaging import MessageDto


class CreateConversationRequest(BaseModel):
    userVehicleId: UUID
    title: str | None = Field(default=None, max_length=255)


class ConversationDto(BaseModel):
    id: UUID
    userVehicleId: UUID
    title: str | None = None
    lastMessageAt: datetime
    createdAt: datetime
    lastMessagePreview: str | None = None


class ConversationEnvelope(BaseModel):
    data: ConversationDto


class PageInfo(BaseModel):
    nextCursor: str | None = None
    hasMore: bool = False


class ConversationListEnvelope(BaseModel):
    data: list[ConversationDto]
    page: PageInfo


class MessageListEnvelope(BaseModel):
    data: list[MessageDto]
    page: PageInfo


class SendMessageRequest(BaseModel):
    clientMessageId: UUID
    content: str = Field(min_length=1)


class SearchHit(BaseModel):
    conversationId: UUID
    conversationTitle: str | None = None
    messageId: UUID
    seq: int | None = None
    role: str
    snippet: str
    createdAt: datetime


class SearchEnvelope(BaseModel):
    data: list[SearchHit]
    page: PageInfo


class SemanticHit(BaseModel):
    messageId: UUID
    seq: int | None = None
    role: str
    snippet: str
    score: float
    createdAt: datetime


class SemanticSearchEnvelope(BaseModel):
    data: list[SemanticHit]


class ExcerptSource(BaseModel):
    type: str
    id: UUID
    confirmedMessageId: UUID


class ExcerptMessage(BaseModel):
    id: UUID
    seq: int | None = None
    role: str
    content: str
    createdAt: datetime


class ExcerptData(BaseModel):
    source: ExcerptSource
    messages: list[ExcerptMessage]


class ExcerptEnvelope(BaseModel):
    data: ExcerptData


# ---- SSE event payloads (data of each `event:` frame) ----------------------


class AcceptedEvent(BaseModel):
    userMessage: MessageDto
    replayed: bool = False


class StatusEvent(BaseModel):
    stage: str
    tool: str | None = None


class TokenEvent(BaseModel):
    delta: str


class CompletedEvent(BaseModel):
    message: MessageDto


class ErrorEvent(BaseModel):
    code: str
    message: str
    traceId: str | None = None


class SseFrame(BaseModel):
    """Internal helper: one SSE frame (event name + JSON data)."""

    event: str
    data: dict[str, Any]
