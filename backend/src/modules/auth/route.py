"""Auth module — HTTP endpoints (FEAT-AUTH-002).

API-101 ``POST /api/v1/oauth/logout``. The route only reads request context and
delegates to the service; business rules and DB access live in the service.

Login (API-001) and the session check (API-102 ``GET /oauth/profile``) live in
the onboarding and oauth modules respectively and are not re-declared here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from src.modules.oauth.dependency import verify_firebase_token

from .dependency import get_auth_service
from .service import AuthService

# Logout lives under /oauth, next to sign-in and profile.
oauth_router = APIRouter(prefix="/oauth", tags=["auth"])


@oauth_router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Sign out: record the logout and revoke the session in the background",
)
async def logout(
    request: Request,
    response: Response,
    claims: Annotated[dict, Depends(verify_firebase_token)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> Response:
    service.logout(
        claims,
        trace_id=x_request_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
