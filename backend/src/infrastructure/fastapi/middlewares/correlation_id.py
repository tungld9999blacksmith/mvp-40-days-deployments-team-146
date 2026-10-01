"""Correlation id / trace middleware — binds request context into structlog.

- Correlation id: incoming ``X-Request-ID`` (falls back to ``X-Correlation-ID``),
  generated when missing or malformed; echoed back as ``X-Request-ID``.
- Trace id: taken from a W3C ``traceparent`` header when present (so ids line up
  with an upstream tracer), otherwise equal to the correlation id.
- Both, plus the HTTP method and path, are bound with
  ``structlog.contextvars.bound_contextvars`` for the whole request, so every log
  line emitted while handling it carries them. Also stored on
  ``request.state.correlation_id`` / ``request.state.trace_id``.

Pure ASGI (not ``BaseHTTPMiddleware``) so streaming / SSE responses are not
buffered. WebSocket connections get the context but no header echo.
"""

from __future__ import annotations

import re
import uuid

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_HEADERS = ("x-request-id", "x-correlation-id")

# Matches the audit trace_id column size (see common.request_context).
_MAX_LENGTH = 64
_VALID_ID = re.compile(rf"^[A-Za-z0-9._:\-]{{1,{_MAX_LENGTH}}}$")
# W3C Trace Context: version-traceid-parentid-flags
_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")
_ZERO_TRACE = "0" * 32
_ZERO_SPAN = "0" * 16


def get_correlation_id() -> str | None:
    """Correlation id of the request being handled, or ``None`` outside one."""
    return structlog.contextvars.get_contextvars().get("correlation_id")


def get_trace_id() -> str | None:
    """Trace id of the request being handled, or ``None`` outside one."""
    return structlog.contextvars.get_contextvars().get("trace_id")


def _headers(scope: Scope) -> dict[str, str]:
    return {
        k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
    }


def _extract_request_id(headers: dict[str, str]) -> str | None:
    for name in _REQUEST_ID_HEADERS:
        value = (headers.get(name) or "").strip()
        # Reject client-supplied values that could pollute logs (newlines, huge ids).
        if value and _VALID_ID.match(value):
            return value
    return None


def _extract_traceparent(headers: dict[str, str]) -> tuple[str, str] | None:
    match = _TRACEPARENT.match((headers.get("traceparent") or "").strip().lower())
    if not match:
        return None
    trace_id, parent_span_id = match.groups()
    if trace_id == _ZERO_TRACE or parent_span_id == _ZERO_SPAN:
        return None
    return trace_id, parent_span_id


class CorrelationIdMiddleware:
    """Bind correlation / trace context for every HTTP / WebSocket request."""

    def __init__(self, app: ASGIApp, *, header_name: str = REQUEST_ID_HEADER) -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = _headers(scope)
        correlation_id = _extract_request_id(headers) or uuid.uuid4().hex
        context: dict[str, str] = {"correlation_id": correlation_id}
        traceparent = _extract_traceparent(headers)
        if traceparent:
            context["trace_id"], context["parent_span_id"] = traceparent
        else:
            context["trace_id"] = correlation_id

        state = scope.setdefault("state", {})
        state["correlation_id"] = correlation_id
        state["trace_id"] = context["trace_id"]

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[self.header_name] = correlation_id
            await send(message)

        with structlog.contextvars.bound_contextvars(
            **context,
            http_method=scope.get("method", "WEBSOCKET"),
            http_path=scope["path"],
        ):
            await self.app(scope, receive, send_with_header)
