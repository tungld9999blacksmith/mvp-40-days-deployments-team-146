"""Demo account module — HTTP endpoint.

``POST /api/v1/auth/demo-session`` (no auth): returns a Firebase custom token for the
shared demo account; the client signs in with ``signInWithCustomToken`` and then calls
``POST /oauth/sign-in`` like after a Google sign-in. 404 when ``DEMO_LOGIN_ENABLED`` is off.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from . import schemas
from .dependency import get_demo_service, limit_demo_sessions, require_demo_login_enabled
from .service import DemoAccountService

router = APIRouter(prefix="/auth", tags=["demo account"])


@router.post(
    "/demo-session",
    response_model=schemas.DemoSessionEnvelope,
    summary="Custom token for the shared demo account (Dùng thử ngay)",
    dependencies=[Depends(require_demo_login_enabled), Depends(limit_demo_sessions)],
)
async def open_demo_session(
    service: Annotated[DemoAccountService, Depends(get_demo_service)],
) -> schemas.DemoSessionEnvelope:
    token = await service.open_session()
    return schemas.DemoSessionEnvelope(data=schemas.DemoSessionData(custom_token=token))
