"""Read the active OpenTelemetry span context (API only — no SDK import)."""

from __future__ import annotations

from opentelemetry import trace


def current_trace_ids() -> tuple[str, str] | None:
    """``(trace_id, span_id)`` as W3C hex of the active span, or ``None`` when there is none.

    With telemetry disabled no span is ever recording, so this returns ``None``.
    """
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x"), format(context.span_id, "016x")
