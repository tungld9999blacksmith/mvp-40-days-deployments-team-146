"""
Access-identity resolution.

A rate limiter needs a stable string that names *who* is being limited. Which
signal to key on differs per endpoint:

    - public/anonymous endpoints  -> client IP,
    - authenticated API traffic   -> the API token (or the resolved user id),
    - trusted service-to-service  -> an explicit `X-RateLimit-Key` header.

An `IdentityResolver` maps a request to an `Identity` (or `None` when the signal
is absent). Resolvers are composable: `first_of(...)` tries several in order,
so an endpoint can prefer a token but fall back to IP.

Each `Identity` carries a *scope* so values from different signals never collide
in Redis: the IP `1.2.3.4` and an API key that happens to be `1.2.3.4` produce
the distinct keys `ip:1.2.3.4` and `token:...`. API tokens are hashed before
they reach a key, so no secret is ever stored in Redis.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from starlette.requests import Request

RATE_LIMIT_KEY_HEADER = "X-RateLimit-Key"


@dataclass(frozen=True)
class Identity:
    """A scoped rate-limit subject, e.g. `Identity("ip", "1.2.3.4")`."""

    scope: str
    value: str

    def __str__(self) -> str:
        return f"{self.scope}:{self.value}"


IdentityResolver = Callable[[Request], Identity | None]


def _hash(secret: str) -> str:
    """Short, non-reversible fingerprint so raw tokens never land in a key."""
    return hashlib.sha256(secret.encode()).hexdigest()[:32]


def by_ip(*, trust_forwarded: bool = False, scope: str = "ip") -> IdentityResolver:
    """
    Key on the client IP.

    `trust_forwarded=True` reads the first hop of `X-Forwarded-For` — only enable
    it when a trusted proxy sets that header, otherwise clients can spoof it.
    """

    def resolve(request: Request) -> Identity | None:
        if trust_forwarded:
            forwarded = request.headers.get("X-Forwarded-For")
            if forwarded:
                return Identity(scope, forwarded.split(",")[0].strip())
        client = request.client
        return Identity(scope, client.host) if client else None

    return resolve


def by_header(header: str, *, scope: str | None = None) -> IdentityResolver:
    """Key on an arbitrary header, e.g. `by_header(RATE_LIMIT_KEY_HEADER)`."""
    resolved_scope = scope or header.lower()

    def resolve(request: Request) -> Identity | None:
        value = request.headers.get(header)
        return Identity(resolved_scope, value) if value else None

    return resolve


def by_api_token(
    *, header: str = "Authorization", scheme: str | None = "Bearer", scope: str = "token"
) -> IdentityResolver:
    """
    Key on the API token in an auth header (hashed).

    With `scheme="Bearer"` the `"Bearer "` prefix is stripped; pass
    `scheme=None` to treat the whole header value as the token.
    """

    def resolve(request: Request) -> Identity | None:
        raw = request.headers.get(header)
        if not raw:
            return None
        token = raw
        if scheme:
            prefix = f"{scheme} "
            if not raw.lower().startswith(prefix.lower()):
                return None
            token = raw[len(prefix) :].strip()
        return Identity(scope, _hash(token)) if token else None

    return resolve


def by_state(attribute: str, *, scope: str = "user") -> IdentityResolver:
    """
    Key on a value set on `request.state` by upstream auth middleware
    (e.g. `request.state.user_id`). Returns `None` if unset.
    """

    def resolve(request: Request) -> Identity | None:
        value = getattr(request.state, attribute, None)
        return Identity(scope, str(value)) if value is not None else None

    return resolve


def first_of(*resolvers: IdentityResolver) -> IdentityResolver:
    """
    Try each resolver in order, returning the first non-`None` identity.

    Typical per-endpoint policy: prefer the authenticated subject, fall back to
    IP for anonymous callers::

        first_of(by_state("user_id"), by_api_token(), by_ip())
    """

    def resolve(request: Request) -> Identity | None:
        for resolver in resolvers:
            identity = resolver(request)
            if identity is not None:
                return identity
        return None

    return resolve
