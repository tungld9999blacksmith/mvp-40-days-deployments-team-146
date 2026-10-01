"""Audit log middleware — one structured (structlog) record per HTTP request.

Each record is emitted on the ``audit`` logger as event ``http_request`` with:
method, path, query, status code, duration, client IP, user agent, the caller's
``user_id`` when an auth dependency set ``request.state.user_id``, and the
exception type if the request crashed. ``correlation_id`` / ``trace_id`` are
merged in from ``structlog.contextvars`` (bound by ``CorrelationIdMiddleware``).

Request / response bodies are never logged (PII, tokens, uploads).

Pure ASGI (not ``BaseHTTPMiddleware``) so streaming / SSE responses are not
buffered; the duration of a streamed response covers the whole stream.
Register it *inside* ``CorrelationIdMiddleware`` so the context is bound.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

AUDIT_LOGGER_NAME = "audit"
AUDIT_EVENT = "http_request"

DEFAULT_EXCLUDED_PATHS: tuple[str, ...] = (
    "/health",
    "/api/v1/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)

_USER_AGENT_MAX = 512


class AuditLogMiddleware:
    """Write an audit record for every HTTP request that is not excluded."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        logger: Any | None = None,
        excluded_paths: Iterable[str] = DEFAULT_EXCLUDED_PATHS,
        excluded_methods: Iterable[str] = ("OPTIONS",),
        trust_forwarded: bool = False,
    ) -> None:
        self.app = app
        self.logger = logger or structlog.stdlib.get_logger(AUDIT_LOGGER_NAME)
        self.excluded_paths = tuple(excluded_paths)
        self.excluded_methods = {m.upper() for m in excluded_methods}
        # Only enable behind a trusted proxy — X-Forwarded-For is client-controlled.
        self.trust_forwarded = trust_forwarded

    def _is_excluded(self, scope: Scope) -> bool:
        if scope["method"].upper() in self.excluded_methods:
            return True
        path = scope["path"]
        return any(path == p or path.startswith(p.rstrip("/") + "/") for p in self.excluded_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._is_excluded(scope):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code: int | None = None

        async def send_capturing_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        error: BaseException | None = None
        try:
            await self.app(scope, receive, send_capturing_status)
        except BaseException as exc:
            error = exc
            raise
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            self._write(scope, status_code, duration_ms, error)

    def _write(
        self,
        scope: Scope,
        status_code: int | None,
        duration_ms: float,
        error: BaseException | None,
    ) -> None:
        # An unhandled exception reaches us before Starlette's ServerErrorMiddleware
        # renders the 500, so no response status has been captured yet.
        if status_code is None:
            status_code = 500

        headers = _headers(scope)
        state = scope.get("state") or {}
        fields: dict[str, Any] = {
            "http_method": scope["method"],
            "http_path": scope["path"],
            "query": scope.get("query_string", b"").decode("latin-1") or None,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "client_ip": self._client_ip(scope, headers),
            "user_agent": (headers.get("user-agent") or "")[:_USER_AGENT_MAX] or None,
            "user_id": state.get("user_id"),
        }
        if error is not None:
            fields["error"] = type(error).__name__

        self.logger.log(_level_for(status_code), AUDIT_EVENT, **fields)

    def _client_ip(self, scope: Scope, headers: dict[str, str]) -> str | None:
        if self.trust_forwarded:
            forwarded = headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip() or None
        client = scope.get("client")
        return client[0] if client else None


def _level_for(status_code: int) -> int:
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


def _headers(scope: Scope) -> dict[str, str]:
    return {
        k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
    }
