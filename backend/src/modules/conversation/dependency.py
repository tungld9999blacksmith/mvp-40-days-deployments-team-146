"""Conversation module — dependency injection and guards (US-025).

REST callers are identified by their Firebase ID token (Q-621). Outside
production, a request without ``Authorization`` may still pass ``X-User-Id``
for local tooling. The WebSocket stream (``ws.py``) keeps its dev handshake.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import UserStatus, VehicleUser

from src.config import get_settings
from src.infrastructure.llm.dependency import get_llm_provider
from src.infrastructure.messaging import get_message_service
from src.infrastructure.redis.dependency import get_redis_toolkit
from src.infrastructure.supabase.db import engine, get_session
from src.infrastructure.vectorstore.dependency import (
    get_knowledge_vector_store,
    get_vector_store,
)

from . import errors
from .service import ChatService

_bearer = HTTPBearer(auto_error=False)
# Same tolerance as the other Firebase guards (host clock drift).
_CLOCK_SKEW_SECONDS = 10


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        engine=engine,
        message_service=get_message_service(),
        toolkit=get_redis_toolkit(),
        llm=get_llm_provider(),
        knowledge_store=get_knowledge_vector_store(),
        vector_store=get_vector_store(),
        settings=get_settings(),
    )


def get_current_user_id(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
    x_user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
) -> int:
    """``user_id`` of the signed-in vehicle owner (Firebase ID token, Q-621)."""
    if cred is not None:
        from firebase_admin import auth

        try:
            claims = auth.verify_id_token(cred.credentials, clock_skew_seconds=_CLOCK_SKEW_SECONDS)
        except Exception as exc:  # noqa: BLE001 — any verification failure is a 401
            raise errors.Unauthorized("Invalid or expired Firebase token.") from exc
        user = session.exec(
            select(VehicleUser).where(VehicleUser.firebase_uid == claims.get("uid"))
        ).first()
        if user is None or user.user_id is None:
            raise errors.Forbidden("This account is not a vehicle owner.")
        if user.status != UserStatus.ACTIVE:
            raise errors.Forbidden("The account is not allowed to use this feature.")
        return user.user_id

    # Local tooling only (Swagger, scripts): never trusted in production.
    if x_user_id is not None and get_settings().app_env != "production":
        return x_user_id
    raise errors.Unauthorized()
