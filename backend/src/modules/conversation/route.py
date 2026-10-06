"""Conversation module — HTTP + SSE endpoints (US-025).

Covers the platform CRUD (API-CONV-001..006) and the F4-specific send-with-SSE
(API-CHAT-004) and workshop excerpt (API-CHAT-007/008). The WebSocket
(API-MSG-001) lives in ``ws.py``.

Owner routes identify the caller by Firebase ID token (``get_current_user_id``;
``X-User-Id`` only as a non-production fallback). Workshop excerpts use the
authenticated workshop owner's scope.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from src.common.core.maintenance import Booking
from src.infrastructure.supabase.db import engine
from src.infrastructure.vectorstore import mask_pii
from src.modules.workshop_board.dependency import OwnerWorkshop, get_owner_workshop

from . import errors, schemas
from .dependency import ChatService, get_chat_service, get_current_user_id

router = APIRouter(prefix="/conversations", tags=["conversations"])
workshop_router = APIRouter(prefix="/workshop", tags=["conversations"])


# ── API-CONV-001 — create ───────────────────────────────────────────────
@router.post("", response_model=schemas.ConversationEnvelope, status_code=201)
def create_conversation(
    body: schemas.CreateConversationRequest,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> schemas.ConversationEnvelope:
    conversation = service.create_conversation(user_id, body.userVehicleId, body.title)
    return schemas.ConversationEnvelope(data=_conversation_dto(conversation))


# ── API-CONV-002 — list ─────────────────────────────────────────────────
@router.get("", response_model=schemas.ConversationListEnvelope)
def list_conversations(
    service: Annotated[ChatService, Depends(get_chat_service)],
    user_id: Annotated[int, Depends(get_current_user_id)],
    user_vehicle_id: Annotated[UUID | None, Query(alias="userVehicleId")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
) -> schemas.ConversationListEnvelope:
    items, next_cursor, has_more = service.list_conversations(user_id, user_vehicle_id, limit, cursor)
    previews = service.last_message_previews([c.id for c in items])
    data = [_conversation_dto(c, preview=previews.get(c.id)) for c in items]
    return schemas.ConversationListEnvelope(data=data, page=schemas.PageInfo(nextCursor=next_cursor, hasMore=has_more))


# ── API-CONV-004 — keyword search (must precede /{id} routes) ────────────
@router.get("/search", response_model=schemas.SearchEnvelope)
def search_conversations(
    service: Annotated[ChatService, Depends(get_chat_service)],
    user_id: Annotated[int, Depends(get_current_user_id)],
    q: Annotated[str, Query(min_length=2, max_length=100)],
    user_vehicle_id: Annotated[UUID | None, Query(alias="userVehicleId")] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    cursor: str | None = None,
) -> schemas.SearchEnvelope:
    before_seq = int(cursor) if cursor and cursor.isdigit() else None
    hits, next_cursor, has_more = service.search_messages(user_id, q, user_vehicle_id, limit, before_seq)
    data = [
        schemas.SearchHit(
            conversationId=m.conversation_id,
            conversationTitle=title,
            messageId=m.id,
            seq=m.seq,
            role=m.role.value,
            snippet=snippet or m.content[:200],
            createdAt=m.created_at,
        )
        for m, title, snippet in hits
    ]
    return schemas.SearchEnvelope(
        data=data,
        page=schemas.PageInfo(nextCursor=str(next_cursor) if next_cursor is not None else None, hasMore=has_more),
    )


# ── API-CONV-003 — messages ──────────────────────────────────────────────
@router.get("/{conversationId}/messages", response_model=schemas.MessageListEnvelope)
def list_messages(
    conversation_id: Annotated[UUID, Path(alias="conversationId")],
    service: Annotated[ChatService, Depends(get_chat_service)],
    user_id: Annotated[int, Depends(get_current_user_id)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    before: int | None = None,
    after: int | None = None,
) -> schemas.MessageListEnvelope:
    service.get_owned_conversation(user_id, conversation_id)  # 404 if not owner
    rows, next_cursor, has_more = service.list_messages(conversation_id, limit, before, after)
    return schemas.MessageListEnvelope(
        data=service.to_dtos(rows),
        page=schemas.PageInfo(nextCursor=next_cursor, hasMore=has_more),
    )


# ── API-CHAT-004 — send a message, stream the answer (SSE) ───────────────
@router.post("/{conversationId}/messages")
async def send_message(
    conversation_id: Annotated[UUID, Path(alias="conversationId")],
    body: schemas.SendMessageRequest,
    request: Request,
    service: Annotated[ChatService, Depends(get_chat_service)],
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> Response:
    # TODO(observability): source from a trace middleware once added.
    trace_id = request.headers.get("x-trace-id") or uuid4().hex

    async def is_disconnected() -> bool:
        return await request.is_disconnected()

    agen = service.stream_turn(
        user_id,
        conversation_id,
        body.clientMessageId,
        body.content,
        trace_id=trace_id,
        is_disconnected=is_disconnected,
    )
    # Pull the first frame eagerly so pre-stream errors (rate limit, busy, not
    # found, invalid) map to real HTTP status codes before the stream starts.
    first = await anext(agen, None)
    if first is None:  # the client disconnected before the turn produced a frame
        return Response(status_code=204)

    async def event_stream() -> AsyncIterator[bytes]:
        async with aclosing(agen):
            yield _sse(first.event, first.data)
            async for frame in agen:
                yield _sse(frame.event, frame.data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Trace-Id": trace_id or "",
        },
    )


# ── API-CONV-006 — semantic search within a conversation (optional) ──────
@router.get("/{conversationId}/semantic-search", response_model=schemas.SemanticSearchEnvelope)
def semantic_search(
    conversation_id: Annotated[UUID, Path(alias="conversationId")],
    service: Annotated[ChatService, Depends(get_chat_service)],
    user_id: Annotated[int, Depends(get_current_user_id)],
    q: Annotated[str, Query(min_length=2, max_length=500)],
    k: Annotated[int, Query(ge=1, le=20)] = 5,
) -> schemas.SemanticSearchEnvelope:
    service.get_owned_conversation(user_id, conversation_id)
    hits = service.semantic_search(conversation_id, q, k)
    return schemas.SemanticSearchEnvelope(
        data=[
            schemas.SemanticHit(
                messageId=m.id,
                seq=m.seq,
                role=m.role.value,
                snippet=m.content[:200],
                score=score,
                createdAt=m.created_at,
            )
            for m, score in hits
        ]
    )


# ── API-CONV-005 — delete ────────────────────────────────────────────────
@router.delete("/{conversationId}", status_code=204)
def delete_conversation(
    conversation_id: Annotated[UUID, Path(alias="conversationId")],
    service: Annotated[ChatService, Depends(get_chat_service)],
    user_id: Annotated[int, Depends(get_current_user_id)],
) -> Response:
    service.delete_conversation(user_id, conversation_id)
    return Response(status_code=204)


# ── API-CHAT-007 — workshop conversation excerpt ───────────────────
@workshop_router.get("/bookings/{bookingId}/conversation-excerpt", response_model=schemas.ExcerptEnvelope)
def booking_excerpt(
    booking_id: Annotated[UUID, Path(alias="bookingId")],
    service: Annotated[ChatService, Depends(get_chat_service)],
    scope: Annotated[OwnerWorkshop, Depends(get_owner_workshop)],
) -> schemas.ExcerptEnvelope:
    with Session(engine) as session:
        booking = session.get(Booking, booking_id)
        source_id = booking.source_message_id if booking else None
        owned = booking is not None and booking.workshop_id == scope.workshop.id
    if not owned:
        raise errors.ConversationNotFound()  # 404 – never reveal other workshops' records
    if source_id is None:
        raise errors.ExcerptNotAvailable()
    return _excerpt_envelope(service.excerpt_for_source("booking", source_id, booking_id))


# ── helpers ───────────────────────────────────────────────────────────────
def _conversation_dto(conversation, preview: str | None = None) -> schemas.ConversationDto:
    return schemas.ConversationDto(
        id=conversation.id,
        userVehicleId=conversation.user_vehicle_id,
        title=conversation.title,
        lastMessageAt=conversation.last_message_at,
        createdAt=conversation.created_at,
        lastMessagePreview=preview,
    )


def _excerpt_envelope(excerpt: dict) -> schemas.ExcerptEnvelope:
    src = excerpt["source"]
    messages = [
        schemas.ExcerptMessage(
            id=m.id,
            seq=m.seq,
            role=m.role.value,
            content=mask_pii(m.content),
            createdAt=m.created_at,
        )
        for m in excerpt["messages"]
    ]
    return schemas.ExcerptEnvelope(
        data=schemas.ExcerptData(
            source=schemas.ExcerptSource(type=src["type"], id=src["id"], confirmedMessageId=src["confirmedMessageId"]),
            messages=messages,
        )
    )


def _sse(event: str, data: dict) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n".encode()
