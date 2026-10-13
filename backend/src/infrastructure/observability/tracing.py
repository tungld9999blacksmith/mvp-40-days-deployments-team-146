"""Agent tracing on both backends from one call site.

- Grafana (OpenTelemetry): a *thin* span — name, duration, status and low-cardinality
  attributes. Never prompt, answer, tool argument or document text.
- LangSmith: the full run — inputs / outputs (anonymized when ``LANGCHAIN_REDACT_PII``),
  tokens and cost.

``step`` opens both and cross-links them: the LangSmith run carries ``otel_trace_id``
in its metadata, the span carries ``langsmith.run_id`` / ``langsmith.trace_id``.
Both sides are no-ops when their backend is off (``OTEL_ENABLED`` /
``LANGCHAIN_TRACING_V2``), so call sites never branch on configuration.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, nullcontext
from typing import Any

import langsmith
from opentelemetry import trace
from opentelemetry.trace import INVALID_SPAN, Span, Status, StatusCode

from .context import current_trace_ids
from .switch import agent_telemetry_enabled

logger = logging.getLogger(__name__)

TRACER_NAME = "evcare.agent"

AttributeValue = str | bool | int | float | Sequence[str]


_tracer_provider: trace.TracerProvider | None = None


def use_tracer_provider(provider: trace.TracerProvider | None) -> None:
    """Route agent spans to ``provider`` instead of the global one (tests); ``None`` resets."""
    global _tracer_provider
    _tracer_provider = provider


def get_tracer() -> trace.Tracer:
    """Tracer of the global provider (no-op until ``setup_telemetry``)."""
    return (_tracer_provider or trace.get_tracer_provider()).get_tracer(TRACER_NAME)


def _clean(attributes: Mapping[str, Any] | None) -> dict[str, AttributeValue]:
    """Drop ``None``; OTel rejects it and the attribute is simply unknown."""
    cleaned: dict[str, AttributeValue] = {}
    for key, value in (attributes or {}).items():
        if value is None:
            continue
        if isinstance(value, list | tuple | set | frozenset):
            value = [str(item) for item in value]
        cleaned[key] = value
    return cleaned


class Step:
    """Handle of an open ``step``: annotate the span and finish the LangSmith run."""

    def __init__(self, span: Span, run: Any | None) -> None:
        self.span = span
        self.run = run

    def set(self, **attributes: Any) -> None:
        """Grafana-side attributes. Keep them low-cardinality and free of user content."""
        cleaned = _clean(attributes)
        if cleaned:
            self.span.set_attributes(cleaned)

    def metadata(self, **values: Any) -> None:
        """LangSmith-side metadata (filterable in the UI)."""
        if self.run is not None:
            self.run.add_metadata({k: v for k, v in values.items() if v is not None})

    def outputs(self, outputs: Mapping[str, Any], *, usage: Mapping[str, int] | None = None) -> None:
        """LangSmith outputs (+ token usage for ``run_type="llm"``); ignored on the Grafana side."""
        if self.run is None:
            return
        if usage:
            self.run.set(usage_metadata=dict(usage))
        self.run.end(outputs=dict(outputs))

    def fail(self, reason: str) -> None:
        """Mark the step failed without an exception (e.g. a handled error path)."""
        self.span.set_status(Status(StatusCode.ERROR, reason))
        if self.run is not None:
            self.run.end(error=reason)


@contextmanager
def step(
    name: str,
    *,
    run_type: str = "chain",
    attributes: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    tags: Sequence[str] | None = None,
    langsmith_run: bool = True,
) -> Iterator[Step]:
    """One unit of agent work, traced on Grafana (thin) and LangSmith (full).

    ``langsmith_run=False`` for work LangChain already reports to LangSmith (tool
    calls): only the Grafana span is created. An exception marks both as failed
    and propagates. With ``OTEL_AGENT_ENABLED`` off the Grafana span is skipped and the
    LangSmith run is unaffected.
    """
    grafana_span = (
        get_tracer().start_as_current_span(name, attributes=_clean(attributes))
        if agent_telemetry_enabled()
        else nullcontext(INVALID_SPAN)
    )
    with grafana_span as span:
        if not langsmith_run:
            yield Step(span, None)
            return
        run_metadata = {k: v for k, v in (metadata or {}).items() if v is not None}
        ids = current_trace_ids()
        if ids:
            run_metadata["otel_trace_id"], run_metadata["otel_span_id"] = ids
        with langsmith.trace(
            name,
            run_type=run_type,  # type: ignore[arg-type]
            inputs=dict(inputs or {}),
            metadata=run_metadata,
            tags=list(tags or []),
        ) as run:
            if run is not None:
                span.set_attributes({"langsmith.run_id": str(run.id), "langsmith.trace_id": str(run.trace_id)})
            yield Step(span, run)
            if run is not None and run.end_time is None:
                run.end()
