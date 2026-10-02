"""Conversation module — WebSocket (API-MSG-001).

Receive-only realtime channel: pushes newly-persisted messages of a conversation
to every connected device (the chatbot-realtime / multi-device backbone). Token
streaming of a live turn goes over SSE (API-CHAT-004), not here.

TODO(auth Q-621): dev auth — the first ``auth`` frame carries ``userId`` instead
of a Firebase token. Swap for token verification before prod.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, WebSocket, WebSocketDisconnect

from src.config import get_settings
from src.infrastructure.messaging import get_message_service
from src.infrastructure.redis.dependency import get_redis_toolkit

from . import errors
from .dependency import get_chat_service

logger = logging.getLogger(__name__)

ws_router = APIRouter(prefix="/conversations", tags=["conversations"])

# Close codes (API-MSG-001 §4).
_CLOSE_BAD_FRAME = 4400
_CLOSE_UNAUTH = 4401
_CLOSE_NOT_FOUND = 4404
_CLOSE_TOO_MANY = 4429
_CLOSE_ERROR = 4500


@ws_router.websocket("/{conversationId}/stream")
async def stream(
    websocket: WebSocket,
    conversation_id: Annotated[UUID, Path(alias="conversationId")],
) -> None:
    settings = get_settings()
    service = get_chat_service()
    messages = get_message_service()
    toolkit = get_redis_toolkit()

    await websocket.accept()

    # 1) Authenticate via the first frame (dev: {"type":"auth","userId":N}).
    try:
        auth = await asyncio.wait_for(websocket.receive_json(), timeout=settings.conversation_ws_auth_timeout_seconds)
    except (TimeoutError, WebSocketDisconnect):
        await websocket.close(code=_CLOSE_UNAUTH)
        return
    if not isinstance(auth, dict) or auth.get("type") != "auth" or "userId" not in auth:
        await websocket.close(code=_CLOSE_BAD_FRAME)
        return
    try:
        user_id = int(auth["userId"])
    except (TypeError, ValueError):
        await websocket.close(code=_CLOSE_UNAUTH)
        return

    # 2) Ownership (never reveal other owners' conversations — AC-605).
    try:
        service.get_owned_conversation(user_id, conversation_id)
    except errors.ConversationNotFound:
        await websocket.close(code=_CLOSE_NOT_FOUND)
        return

    # 3) Per-user connection cap.
    conn_key = toolkit.keys.build("chat", "ws", str(user_id))
    count = await toolkit.redis.incr(conn_key)
    await toolkit.redis.expire(conn_key, 3600)
    if count > settings.conversation_ws_max_per_user:
        await toolkit.redis.decr(conn_key)
        await websocket.close(code=_CLOSE_TOO_MANY)
        return

    try:
        rows, _, _ = service.list_messages(conversation_id, 1, None, None)
        last_seq = rows[0].seq if rows else None
        await websocket.send_json({"type": "ready", "lastSeq": last_seq})

        async def pump_out() -> None:
            async for event in messages.subscribe(conversation_id):
                await websocket.send_json({"type": "message", "data": event.model_dump(mode="json")})

        async def pump_ping() -> None:
            while True:
                await asyncio.sleep(settings.conversation_ws_ping_seconds)
                await websocket.send_json({"type": "ping"})

        async def pump_in() -> None:
            # Only `pong` (and re-`auth`) are expected; ignore the rest.
            while True:
                await websocket.receive_json()

        tasks = [asyncio.create_task(c()) for c in (pump_out, pump_ping, pump_in)]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.exception("WebSocket error on conversation %s", conversation_id)
        with contextlib.suppress(Exception):
            await websocket.close(code=_CLOSE_ERROR)
    finally:
        await toolkit.redis.decr(conn_key)
