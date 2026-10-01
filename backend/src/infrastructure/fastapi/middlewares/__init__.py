"""FastAPI / ASGI middlewares.

- ``CorrelationIdMiddleware`` — per-request ``X-Request-ID`` + trace id, bound into
  ``structlog.contextvars`` (``get_correlation_id()`` / ``get_trace_id()``)
- ``AuditLogMiddleware``      — one structlog audit record per HTTP request

Register order (``add_middleware`` wraps outermost last)::

    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

Call ``infrastructure.logging.configure_logging()`` first so records render as JSON.
"""

from .audit_log import AUDIT_EVENT, AUDIT_LOGGER_NAME, DEFAULT_EXCLUDED_PATHS, AuditLogMiddleware
from .correlation_id import (
    REQUEST_ID_HEADER,
    CorrelationIdMiddleware,
    get_correlation_id,
    get_trace_id,
)

__all__ = [
    "AUDIT_EVENT",
    "AUDIT_LOGGER_NAME",
    "DEFAULT_EXCLUDED_PATHS",
    "REQUEST_ID_HEADER",
    "AuditLogMiddleware",
    "CorrelationIdMiddleware",
    "get_correlation_id",
    "get_trace_id",
]
