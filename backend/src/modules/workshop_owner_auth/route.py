"""Workshop-owner auth — HTTP endpoints (FEAT-AUTH-004).

- API-301 ``POST /api/v1/workshop-owner/oauth/logout``
- API-302 ``GET  /api/v1/workshop-owner/oauth/session``

Sign-in (API-201) lives in ``workshop_owner_onboarding``; it writes its audit
events through that module's ``SignInAuditor`` port, implemented here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from src.modules.oauth.dependency import verify_firebase_token

from . import schemas
from .dependency import (
    get_workshop_auth_service,
    request_context,
    verify_firebase_token_check_revoked,
)
from .domain import RequestContext
from .service import WorkshopAuthService

router = APIRouter(prefix="/workshop-owner/oauth", tags=["workshop-owner-auth"])


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Workshop owner: sign out — audit + revoke the session in the background",
)
async def logout(
    claims: Annotated[dict, Depends(verify_firebase_token)],
    context: Annotated[RequestContext, Depends(request_context)],
    service: Annotated[WorkshopAuthService, Depends(get_workshop_auth_service)],
) -> Response:
    service.logout(claims, context)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/session",
    response_model=schemas.SessionEnvelope,
    summary="Workshop owner: session check (detects revoked sessions)",
)
async def session_check(
    claims: Annotated[dict, Depends(verify_firebase_token_check_revoked)],
    service: Annotated[WorkshopAuthService, Depends(get_workshop_auth_service)],
) -> schemas.SessionEnvelope:
    return schemas.SessionEnvelope(data=service.session(claims))
