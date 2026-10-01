"""Auth module — dependency injection (composition root, FEAT-AUTH-002).

Wires the DB session and the Celery-backed session revoker into
``AuthService``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.infrastructure.supabase.db import get_session

from .revoker import CelerySessionRevoker
from .service import AuthService


def get_session_revoker() -> CelerySessionRevoker:
    return CelerySessionRevoker()


def get_auth_service(
    session: Annotated[Session, Depends(get_session)],
    revoker: Annotated[CelerySessionRevoker, Depends(get_session_revoker)],
) -> AuthService:
    return AuthService(session, revoker)
