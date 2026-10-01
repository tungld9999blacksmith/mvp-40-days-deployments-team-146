"""Structured logging (structlog) — JSON logs with request-scoped context.

- ``configure_logging`` — route stdlib *and* structlog loggers through one
  structlog pipeline: stdout (JSON or console) + optional file exports
  (``log`` / ``json`` / ``csv``), all PII-redacted.
- ``get_logger``        — structlog logger; ``logging.getLogger(__name__)`` keeps working.
- ``PiiRedactor``       — the redaction processor (secrets, emails, phones, personal data).

Context bound with ``structlog.contextvars.bind_contextvars`` (e.g. the
correlation / trace ids bound by ``CorrelationIdMiddleware``) is merged into
every log line emitted while it is bound, from either logger kind.
"""

from .config import FILE_FORMATS, configure_logging, get_logger, parse_file_formats
from .pii import REDACTED, PiiRedactor, mask_email, mask_phone, redact_text
from .renderers import CSV_COLUMNS, CsvRenderer, LogLineRenderer

__all__ = [
    "CSV_COLUMNS",
    "FILE_FORMATS",
    "REDACTED",
    "CsvRenderer",
    "LogLineRenderer",
    "PiiRedactor",
    "configure_logging",
    "get_logger",
    "mask_email",
    "mask_phone",
    "parse_file_formats",
    "redact_text",
]
