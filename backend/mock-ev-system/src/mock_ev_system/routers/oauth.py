"""OAuth2 token endpoint: client_credentials + private_key_jwt (RFC 7523 §2.2).

EV Care posts a client assertion signed with EVCARE_PRIVATE_KEY; the mock verifies it with
EVCARE_PUBLIC_KEY, rejects a reused ``jti`` and returns an access token signed with
MOCK_PRIVATE_KEY (SPEC-SEC-OEM-M2M-001 v2.0 §5).
"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs

from ev_contracts import (
    CLIENT_ASSERTION_TYPE,
    CLIENT_CREDENTIALS_GRANT,
    EVCARE_CLIENT_ID,
    M2M_CLOCK_SKEW_SECONDS,
    OAUTH_TOKEN_PATH,
    M2MAuthError,
    create_access_token,
    verify_client_assertion,
)
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..auth import assertion_replay_cache, load_auth_config

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OAuth"])

_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _error(status_code: int, error: str, description: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": error, "error_description": description},
        headers=_NO_STORE,
    )


@router.post(OAUTH_TOKEN_PATH, summary="Exchange a signed client assertion for an access token")
async def issue_token(request: Request) -> JSONResponse:
    config = load_auth_config()
    if not config.evcare_public_key or not config.private_key:
        logger.error("Token endpoint needs EVCARE_PUBLIC_KEY and MOCK_PRIVATE_KEY")
        return _error(503, "server_error", "M2M keys are not configured on the manufacturer system")

    form = {k: v[0] for k, v in parse_qs((await request.body()).decode("utf-8")).items()}
    if form.get("grant_type") != CLIENT_CREDENTIALS_GRANT:
        return _error(400, "unsupported_grant_type", "grant_type must be client_credentials")
    if form.get("client_assertion_type") != CLIENT_ASSERTION_TYPE or not form.get("client_assertion"):
        return _error(400, "invalid_request", "client_assertion and its jwt-bearer type are required")
    if form.get("client_id") not in (None, EVCARE_CLIENT_ID):
        return _error(401, "invalid_client", "Unknown client_id")

    try:
        claims = verify_client_assertion(form["client_assertion"], config.evcare_public_key)
    except M2MAuthError as exc:
        logger.warning("Client assertion rejected (%s): %s", exc.code, exc)
        return _error(401, "invalid_client", f"{exc.code}: {exc}")
    # Remember the jti as long as the verifier would still accept the assertion (exp + leeway).
    if not assertion_replay_cache.remember(str(claims["jti"]), float(claims["exp"]) + M2M_CLOCK_SKEW_SECONDS):
        logger.warning("Client assertion replay rejected: jti=%s", claims["jti"])
        return _error(401, "invalid_client", "M2M_TOKEN_REPLAYED: client assertion was already used")

    access_token = create_access_token(
        config.private_key,
        subject=str(claims["sub"]),
        expires_in_seconds=config.access_token_ttl_seconds,
    )
    return JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": config.access_token_ttl_seconds,
        },
        headers=_NO_STORE,
    )
