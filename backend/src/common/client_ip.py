"""Client IP of the request being handled, for limits that cannot key on the account.

The shared demo account (modules/demo_account) is one ``user_id`` for every visitor, so
its chat limits key on the caller's IP instead. Routers that need it add the
``remember_client_ip`` dependency; services read ``current_client_ip()``.
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar

from starlette.requests import Request

from src.config import get_settings

_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)


def resolve_client_ip(request: Request, *, trust_forwarded: bool) -> str | None:
    """First ``X-Forwarded-For`` hop behind a trusted proxy (spoofable otherwise), else the peer address."""
    if trust_forwarded:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded and forwarded.split(",")[0].strip():
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def remember_client_ip(request: Request) -> None:
    """Router dependency (async, so the value is visible to the endpoint)."""
    _client_ip.set(resolve_client_ip(request, trust_forwarded=get_settings().rate_limit_trust_forwarded))


def current_client_ip() -> str | None:
    return _client_ip.get()


def client_key(ip: str | None) -> str:
    """Short, non-reversible key for an IP (rate-limit keys never hold the raw address)."""
    return hashlib.sha256((ip or "unknown").encode()).hexdigest()[:16]
