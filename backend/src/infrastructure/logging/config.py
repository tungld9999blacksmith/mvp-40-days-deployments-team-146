"""structlog configuration shared by the API process and the Celery worker.

Pipeline::

    structlog logger ─┐
                      ├─> shared processors (contextvars, level, logger, timestamp)
    stdlib logger ────┘        │
                               ├─> [stdout]      exc -> PII redact -> JSON | console
                               ├─> [app.log]     exc -> PII redact -> LogLineRenderer
                               ├─> [app.jsonl]   exc -> PII redact -> JSONRenderer
                               ├─> [app.csv]     exc -> PII redact -> CsvRenderer
                               └─> [OTLP]        exc -> PII redact -> JSON body
                                                 (only when an OTel LoggerProvider is passed)

Stdlib records (``logging.getLogger(__name__)``, uvicorn, libraries) go through
the same ``foreign_pre_chain`` so they are rendered the same way and also carry
the bound context (``correlation_id``, ``trace_id``, ...). While an OpenTelemetry
span is active, ``trace_id`` / ``span_id`` are the span's, so log lines and traces
join up in Grafana.

PII redaction runs per output, *after* tracebacks are formatted, so exception
messages are scrubbed too. File outputs are opt-in via ``file_formats``.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, TextIO

import structlog
from structlog.types import Processor

from src.infrastructure.observability.context import current_trace_ids

from .handlers import rotating_file_handler
from .pii import PiiRedactor
from .renderers import CsvRenderer, LogLineRenderer

FileFormat = Literal["log", "json", "csv"]
FILE_FORMATS: tuple[FileFormat, ...] = ("log", "json", "csv")
_FILE_SUFFIX: dict[FileFormat, str] = {"log": ".log", "json": ".jsonl", "csv": ".csv"}

# uvicorn.access duplicates AuditLogMiddleware (and lacks the request context).
_SILENCED_LOGGERS = ("uvicorn.access",)
_PROPAGATED_LOGGERS = ("uvicorn", "uvicorn.error")

# Marks handlers created here so a re-configure closes them (releases files).
_MANAGED_ATTR = "_structlog_managed"


def add_otel_trace_context(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Set ``trace_id`` / ``span_id`` from the active OpenTelemetry span, if any.

    Runs after ``merge_contextvars`` so the span (the source of truth for traces)
    wins over ids bound earlier; without a span the bound ids stay untouched.
    """
    ids = current_trace_ids()
    if ids is not None:
        event_dict["trace_id"], event_dict["span_id"] = ids
    return event_dict


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        add_otel_trace_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
    ]


def _formatter(
    renderer: Processor,
    *,
    shared: list[Processor],
    structured_exc: bool,
    redactor: Processor | None,
) -> structlog.stdlib.ProcessorFormatter:
    processors: list[Processor] = [structlog.stdlib.ProcessorFormatter.remove_processors_meta]
    if structured_exc:
        # Request objects contain entire dependency graphs. Serializing every
        # local on a client disconnect makes a single traceback enormous.
        processors.append(
            structlog.processors.ExceptionRenderer(structlog.tracebacks.ExceptionDictTransformer(show_locals=False))
        )
    else:
        processors.append(structlog.processors.format_exc_info)
    if redactor is not None:
        processors.append(redactor)
    processors.append(renderer)
    return structlog.stdlib.ProcessorFormatter(foreign_pre_chain=shared, processors=processors)


def parse_file_formats(value: str | Iterable[str] | None) -> tuple[FileFormat, ...]:
    """``"log, json"`` / ``["log"]`` -> ``("log", "json")``; unknown names raise."""
    if not value:
        return ()
    items = value.split(",") if isinstance(value, str) else value
    formats: list[FileFormat] = []
    for item in items:
        name = item.strip().lower()
        if not name:
            continue
        if name not in FILE_FORMATS:
            raise ValueError(f"Unknown log file format {name!r}; expected one of {FILE_FORMATS}")
        if name not in formats:
            formats.append(name)  # type: ignore[arg-type]
    return tuple(formats)


def configure_logging(
    *,
    level: str = "INFO",
    json_logs: bool = True,
    stream: TextIO | None = None,
    redact_pii: bool = True,
    file_formats: str | Iterable[str] | None = None,
    log_dir: str | Path = "logs",
    file_name: str = "app",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    otel_logger_provider: Any | None = None,
) -> None:
    """Configure structlog + the stdlib root logger. Safe to call more than once.

    ``file_formats`` picks the file exports among ``log`` / ``json`` / ``csv``
    (e.g. ``"log"`` or ``["log", "csv"]``); each is written to
    ``<log_dir>/<file_name>.<ext>`` with size-based rotation.

    ``otel_logger_provider`` (from ``setup_telemetry``) adds an OTLP handler whose
    body is the same redacted JSON line as stdout.
    """
    shared = _shared_processors()
    redactor = PiiRedactor() if redact_pii else None

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    console = logging.StreamHandler(stream or sys.stdout)
    console.setFormatter(
        _formatter(
            structlog.processors.JSONRenderer(ensure_ascii=False)
            if json_logs
            else structlog.dev.ConsoleRenderer(colors=True),
            shared=shared,
            structured_exc=json_logs,
            redactor=redactor,
        )
    )
    handlers: list[logging.Handler] = [console]

    renderers: dict[FileFormat, tuple[Processor, bool]] = {
        # format -> (renderer, structured traceback)
        "log": (LogLineRenderer(), False),
        "json": (structlog.processors.JSONRenderer(ensure_ascii=False), True),
        "csv": (CsvRenderer(), False),
    }
    formats = parse_file_formats(file_formats)
    # An unwritable directory (Railway: root-owned volume, app runs as uid 1000) would fail
    # every record; keep stdout only and say so once below.
    file_export_disabled = bool(formats) and not _writable_dir(Path(log_dir))
    for fmt in () if file_export_disabled else formats:
        renderer, structured_exc = renderers[fmt]
        handler = rotating_file_handler(
            Path(log_dir) / f"{file_name}{_FILE_SUFFIX[fmt]}",
            csv=fmt == "csv",
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
        handler.setFormatter(_formatter(renderer, shared=shared, structured_exc=structured_exc, redactor=redactor))
        handlers.append(handler)

    if otel_logger_provider is not None:
        from src.infrastructure.observability.log_handler import RedactedOtlpLogHandler

        otlp = RedactedOtlpLogHandler(logger_provider=otel_logger_provider)
        otlp.setFormatter(
            _formatter(
                structlog.processors.JSONRenderer(ensure_ascii=False),
                shared=shared,
                structured_exc=True,
                redactor=redactor,
            )
        )
        handlers.append(otlp)

    for handler in handlers:
        setattr(handler, _MANAGED_ATTR, True)

    root = logging.getLogger()
    for old in root.handlers:
        if getattr(old, _MANAGED_ATTR, False):
            old.close()
    root.handlers = handlers
    root.setLevel(level)

    for name in _PROPAGATED_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    for name in _SILENCED_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = False

    if file_export_disabled:
        get_logger(__name__).warning("logging.file_export_disabled", log_dir=str(log_dir))


def _writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(path, os.W_OK)


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name, **initial_values)
