"""Inbound M2M (Machine-to-Machine) authentication for mock-ev-system.

Specification: ``docs/specs/mock-system/m2m_authentication_spec.md`` (SPEC-SEC-OEM-M2M-001 v2.0).

EV Care exchanges a client assertion for an access token at ``POST /oauth/token``
(see ``routers/oauth.py``), then sends that access token on every business call.
This module holds the shared config, the assertion replay cache and the
``require_access_token`` dependency that protects the business routers.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated

from ev_contracts import (
    ACCESS_TOKEN_TTL_SECONDS,
    M2MAuthError,
    clean_pem,
    public_key_from_private,
    verify_access_token,
)
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthConfig:
    evcare_public_key: str
    private_key: str
    auth_required: bool
    access_token_ttl_seconds: int

    @property
    def enforced(self) -> bool:
        # Bypass only in dev/test: no EV Care key configured and auth not forced.
        return bool(self.evcare_public_key) or self.auth_required


def load_auth_config() -> AuthConfig:
    return AuthConfig(
        evcare_public_key=clean_pem(os.getenv("EVCARE_PUBLIC_KEY", "")),
        private_key=clean_pem(os.getenv("MOCK_PRIVATE_KEY", "")),
        auth_required=os.getenv("MOCK_AUTH_REQUIRED", "").lower() in {"1", "true", "yes"},
        access_token_ttl_seconds=int(os.getenv("MOCK_ACCESS_TOKEN_TTL_SECONDS", str(ACCESS_TOKEN_TTL_SECONDS))),
    )


@lru_cache(maxsize=4)
def own_public_key(private_key_pem: str) -> str:
    """Public half of MOCK_PRIVATE_KEY: the mock verifies the access tokens it issued."""
    return public_key_from_private(private_key_pem)


class AssertionReplayCache:
    """Remembers client-assertion ``jti`` values until they expire (single-process mock)."""

    def __init__(self) -> None:
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def remember(self, jti: str, expires_at: float) -> bool:
        """Record ``jti``; False when it was already used."""
        now = time.time()
        with self._lock:
            self._seen = {k: exp for k, exp in self._seen.items() if exp > now}
            if jti in self._seen:
                return False
            self._seen[jti] = expires_at
            return True


assertion_replay_cache = AssertionReplayCache()


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_access_token(authorization: Annotated[str | None, Header(alias="Authorization")] = None) -> dict | None:
    """FastAPI dependency: accept only access tokens this mock issued (``typ=at+jwt``)."""
    config = load_auth_config()
    if not config.enforced:
        return None
    if not config.private_key:
        logger.error("MOCK_PRIVATE_KEY is not configured; cannot verify access tokens")
        raise _unauthorized("M2M_CONFIG_ERROR", "M2M authentication configuration error: MOCK_PRIVATE_KEY not set")
    try:
        return verify_access_token(authorization, own_public_key(config.private_key))
    except M2MAuthError as exc:
        logger.warning("M2M access token rejected (%s): %s", exc.code, exc)
        raise _unauthorized(exc.code, str(exc)) from exc
