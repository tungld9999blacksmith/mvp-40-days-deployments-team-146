"""structlog configuration shared by the API process.

Pipeline::

    structlog logger ─┐
                      ├─> shared processors (contextvars, level, logger, timestamp)
    stdlib logger ────┘        │
                               ├─> [stdout]      exc -> PII redact -> JSON | console
                               ├─> [app.log]     exc -> PII redact -> LogLineRenderer
                               ├─> [app.jsonl]   exc -> PII redact -> JSONRenderer
                               └─> [app.csv]     exc -> PII redact -> CsvRenderer

Stdlib records (``logging.getLogger(__name__)``, uvicorn, libraries) go through
the same ``foreign_pre_chain`` so they are rendered the same way and also carry
the bound context (``correlation_id``, ``trace_id``, ...).

PII redaction runs per output, *after* tracebacks are formatted, so exception
messages are scrubbed too. File outputs are opt-in via ``file_formats``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Literal, TextIO

import structlog
from structlog.types import Processor

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


def _shared_processors() -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
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
) -> None:
    """Configure structlog + the stdlib root logger. Safe to call more than once.

    ``file_formats`` picks the file exports among ``log`` / ``json`` / ``csv``
    (e.g. ``"log"`` or ``["log", "csv"]``); each is written to
    ``<log_dir>/<file_name>.<ext>`` with size-based rotation.
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
            structlog.processors.JSONRenderer(ensure_ascii=False) if json_logs else structlog.dev.ConsoleRenderer(),
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
    for fmt in parse_file_formats(file_formats):
        renderer, structured_exc = renderers[fmt]
        handler = rotating_file_handler(
            Path(log_dir) / f"{file_name}{_FILE_SUFFIX[fmt]}",
            csv=fmt == "csv",
            max_bytes=max_bytes,
            backup_count=backup_count,
        )
        handler.setFormatter(_formatter(renderer, shared=shared, structured_exc=structured_exc, redactor=redactor))
        handlers.append(handler)

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


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name, **initial_values)
