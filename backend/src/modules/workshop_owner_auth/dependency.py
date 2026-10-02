"""Workshop-owner auth — dependency injection (FEAT-AUTH-004)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.supabase.db import get_session

from . import errors
from .domain import RequestContext
from .ports import WorkshopSessionRevoker
from .revoker import CeleryWorkshopSessionRevoker
from .service import WorkshopAuthService

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def get_workshop_session_revoker() -> WorkshopSessionRevoker:
    return CeleryWorkshopSessionRevoker()


def build_workshop_auth_service(session: Session, revoker: WorkshopSessionRevoker | None = None) -> WorkshopAuthService:
    settings = get_settings()
    return WorkshopAuthService(
        session,
        revoker,
        onboarding_retention_days=settings.onboarding_retention_days,
        event_retention_days=settings.workshop_auth_event_retention_days,
    )


def get_workshop_auth_service(
    session: Annotated[Session, Depends(get_session)],
    revoker: Annotated[WorkshopSessionRevoker, Depends(get_workshop_session_revoker)],
) -> WorkshopAuthService:
    return build_workshop_auth_service(session, revoker)


def request_context(request: Request) -> RequestContext:
    """IP / user agent / trace id recorded on every audit event."""
    return RequestContext(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        trace_id=request.headers.get("X-Request-ID"),
    )


def verify_firebase_token_check_revoked(
    cred: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """Verify the ID token **and** that its session was not revoked (API-302, BR-307)."""
    if cred is None:
        raise errors.WorkshopAuthError("Cần đăng nhập.", code="UNAUTHORIZED")
    from firebase_admin import auth

    try:
        return auth.verify_id_token(cred.credentials, check_revoked=True, clock_skew_seconds=10)
    except auth.RevokedIdTokenError as exc:
        raise errors.WorkshopAuthError(
            "Phiên đăng nhập đã bị thu hồi. Vui lòng đăng nhập lại.", code="TOKEN_REVOKED"
        ) from exc
    except (auth.InvalidIdTokenError, auth.UserDisabledError, ValueError) as exc:
        raise errors.WorkshopAuthError("Token không hợp lệ hoặc đã hết hạn.", code="INVALID_TOKEN") from exc
    except Exception as exc:  # noqa: BLE001 — Firebase unreachable (revoke check needs a call)
        logger.warning("revocation check failed: %s", exc)
        raise errors.AuthProviderUnavailableError("Không kiểm tra được phiên lúc này. Vui lòng thử lại.") from exc
