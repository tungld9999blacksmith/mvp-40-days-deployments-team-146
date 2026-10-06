"""Conversation module — dependency injection and guards (US-025).

REST callers are identified by their Firebase ID token (Q-621). Outside
production, a request without ``Authorization`` may still pass ``X-User-Id``
for local tooling. WebSocket callers always require a verified token.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import UserStatus, VehicleUser
from src.config import get_settings
from src.infrastructure.messaging import get_message_service
from src.infrastructure.redis.dependency import get_redis_toolkit
from src.infrastructure.supabase.db import engine, get_session

from . import errors
from .service import ChatService

logger = logging.getLogger(__name__)
_bearer = HTTPBearer(auto_error=False)
# Same tolerance as the other Firebase guards (host clock drift).
_CLOCK_SKEW_SECONDS = 10


@lru_cache
def get_chat_service() -> ChatService:
    return ChatService(
        engine=engine,
        message_service=get_message_service(),
        toolkit=get_redis_toolkit(),
        llm=None,
        knowledge_store=None,
        vector_store=None,
        settings=get_settings(),
        orchestrator=None,
    )


def get_current_user_id(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    # "function" scope: close before the SSE answer streams, so a chat turn does not
    # hold a pooler connection idle in transaction for the whole LLM call.
    session: Annotated[Session, Depends(get_session, scope="function")],
    x_user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
) -> int:
    """``user_id`` of the signed-in vehicle owner (Firebase ID token, Q-621)."""
    if cred is not None:
        return user_id_from_token(cred.credentials, session)

    # Local tooling only (Swagger, scripts): never trusted in production.
    if x_user_id is not None and get_settings().app_env != "production":
        return x_user_id
    raise errors.Unauthorized()


def user_id_from_token(token: str, session: Session) -> int:
    """Shared HTTP/WebSocket token verification and active-owner guard."""
    from firebase_admin import auth

    try:
        claims = auth.verify_id_token(token, check_revoked=True, clock_skew_seconds=_CLOCK_SKEW_SECONDS)
    except (
        auth.RevokedIdTokenError,
        auth.InvalidIdTokenError,
        auth.UserDisabledError,
        auth.UserNotFoundError,
        ValueError,
    ) as exc:
        raise errors.Unauthorized("Invalid or expired Firebase token.") from exc
    except Exception as exc:  # noqa: BLE001 — Firebase unreachable (the revocation check needs a call)
        logger.warning("Firebase token check failed: %s", exc)
        raise errors.AuthProviderUnavailable() from exc
    user = session.exec(select(VehicleUser).where(VehicleUser.firebase_uid == claims.get("uid"))).first()
    if user is None or user.user_id is None:
        raise errors.Forbidden("This account is not a vehicle owner.")
    if user.status != UserStatus.ACTIVE:
        raise errors.Forbidden("The account is not allowed to use this feature.")
    return user.user_id


def get_websocket_user_id(token: str) -> int:
    with Session(engine) as session:
        return user_id_from_token(token, session)
