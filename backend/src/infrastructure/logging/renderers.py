"""Final-stage structlog renderers for the file outputs (``.log`` and ``.csv``).

JSON uses ``structlog.processors.JSONRenderer`` directly.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from structlog.types import EventDict, WrappedLogger

# Rendered in this order as dedicated fields; everything else goes to "extra".
_HEAD_FIELDS = ("timestamp", "level", "logger", "correlation_id", "trace_id", "event")


def _pop_head(event_dict: EventDict) -> tuple[dict[str, Any], dict[str, Any]]:
    rest = dict(event_dict)
    head = {name: rest.pop(name, None) for name in _HEAD_FIELDS}
    return head, rest


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, ensure_ascii=False)


class LogLineRenderer:
    """Classic one-line text format for ``.log`` files::

        2026-09-30T03:54:18Z WARNING  [audit] [cid=demo-1 trace=4bf9...] http_request status_code=401 ...

    A traceback (``exception`` key, from ``format_exc_info``) follows on the next lines.
    """

    def __call__(self, logger: WrappedLogger, method_name: str, event_dict: EventDict) -> str:
        head, rest = _pop_head(event_dict)
        exception = rest.pop("exception", None)

        parts = [
            _scalar(head["timestamp"]),
            f"{_scalar(head['level']).upper():<8}",
            f"[{_scalar(head['logger']) or '-'}]",
        ]
        if head["correlation_id"] or head["trace_id"]:
            parts.append(f"[cid={_scalar(head['correlation_id']) or '-'} trace={_scalar(head['trace_id']) or '-'}]")
        parts.append(_scalar(head["event"]))
        parts.extend(f"{key}={self._value(value)}" for key, value in rest.items())

        line = " ".join(p for p in parts if p)
        if exception:
            line = f"{line}\n{_scalar(exception)}"
        return line

    @staticmethod
    def _value(value: Any) -> str:
        text = _scalar(value)
        if not text:
            return '""'
        if any(c.isspace() for c in text) or '"' in text or "=" in text:
            return json.dumps(text, ensure_ascii=False)
        return text


CSV_COLUMNS: tuple[str, ...] = (*_HEAD_FIELDS, "exception", "extra")


class CsvRenderer:
    """One CSV row per record; columns = ``CSV_COLUMNS``, other keys JSON-packed in ``extra``."""

    def __call__(self, logger: WrappedLogger, method_name: str, event_dict: EventDict) -> str:
        head, rest = _pop_head(event_dict)
        exception = rest.pop("exception", None)
        row = [_scalar(head[name]) for name in _HEAD_FIELDS]
        row.append(_scalar(exception))
        row.append(json.dumps(rest, default=str, ensure_ascii=False) if rest else "")
        return csv_line(row)


def csv_line(values: list[str] | tuple[str, ...]) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator="").writerow(values)
    return buf.getvalue()
