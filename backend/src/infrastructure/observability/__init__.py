"""Observability: OpenTelemetry (traces / metrics / logs -> OTel Collector) and LangSmith.

- ``setup_telemetry`` / ``instrument_fastapi`` / ``shutdown_telemetry`` — process
  lifecycle; no-ops unless ``OTEL_ENABLED=true`` (never under ``APP_ENV=test``).
- ``current_trace_ids`` — W3C ids of the active span (log / LangSmith correlation).
- ``configure_langsmith`` — copy LangSmith settings into ``os.environ`` (+ PII anonymizer).
- ``step`` — one unit of agent work: thin OTel span (Grafana) + full LangSmith run.
- ``get_agent_metrics`` — Grafana-side agent metrics (tools, guardrails, RAG).
- ``agent_callbacks`` / ``instrument_tools`` — LangChain LLM and tool calls on the Grafana side.

Setup & usage: docs/observability/OBSERVABILITY_SETUP.md, OBSERVABILITY_USAGE.md.
"""

from .agent_hooks import agent_callbacks, instrument_tools
from .context import current_trace_ids
from .langsmith import configure_langsmith, jobs_project
from .metrics import AgentMetrics, get_agent_metrics
from .telemetry import (
    BACKEND_SERVICE,
    WORKER_SERVICE,
    Telemetry,
    build_telemetry,
    get_telemetry,
    instrument_fastapi,
    is_enabled,
    setup_telemetry,
    shutdown_telemetry,
)
from .tracing import Step, step

__all__ = [
    "AgentMetrics",
    "BACKEND_SERVICE",
    "WORKER_SERVICE",
    "Telemetry",
    "build_telemetry",
    "Step",
    "agent_callbacks",
    "configure_langsmith",
    "current_trace_ids",
    "get_agent_metrics",
    "get_telemetry",
    "instrument_fastapi",
    "instrument_tools",
    "is_enabled",
    "jobs_project",
    "setup_telemetry",
    "shutdown_telemetry",
    "step",
]
