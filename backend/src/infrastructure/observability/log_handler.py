"""OTLP log handler that only ships PII-redacted content."""

from __future__ import annotations

import logging

from opentelemetry.instrumentation.logging.handler import LoggingHandler

# Loggers whose records must not loop back into the exporter that produced them.
_SELF_LOGGERS = ("opentelemetry",)


class RedactedOtlpLogHandler(LoggingHandler):
    """``LoggingHandler`` whose body is the formatted (redacted) line, nothing raw.

    The stock handler copies every ``LogRecord`` extra and the raw exception
    message / stacktrace into attributes, bypassing ``PiiRedactor``. Here the
    body comes from the structlog formatter set on the handler (exception
    included, already redacted) and attributes keep only code location + the
    exception type. Trace / span ids are attached by the SDK from the active span.
    """

    def __init__(self, level: int = logging.NOTSET, logger_provider=None) -> None:
        super().__init__(level=level, logger_provider=logger_provider)
        self.addFilter(lambda record: not record.name.startswith(_SELF_LOGGERS))

    def _get_attributes(self, record: logging.LogRecord) -> tuple[dict[str, str | int], str | None]:
        attributes: dict[str, str | int] = {
            "code.file.path": record.pathname,
            "code.function.name": record.funcName,
            "code.line.number": record.lineno,
            "logger.name": record.name,
        }
        if record.exc_info and record.exc_info[0] is not None:
            attributes["exception.type"] = record.exc_info[0].__name__
        # (attributes, event_name): plain log lines are not named events.
        return attributes, None
