"""Agent metrics for Grafana (OpenTelemetry).

Token usage, cost, LLM latency and agent error rate are LangSmith-only by design
(docs/observability/OBSERVABILITY_SETUP.md, "Chia vai Grafana / LangSmith"). Grafana
gets what LangSmith cannot alert on: tool health, guardrail decisions and RAG.

Every label below has a small, fixed value set — the free tier allows 10k series.
Never label with user / vehicle / conversation ids or free text.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, Meter, MeterProvider

METER_NAME = "evcare.agent"


@dataclass(frozen=True)
class AgentMetrics:
    tool_calls: Counter
    guardrail_decisions: Counter
    rag_queries: Counter
    rag_stage_duration: Histogram

    @classmethod
    def from_meter(cls, meter: Meter) -> AgentMetrics:
        return cls(
            tool_calls=meter.create_counter(
                "evcare.agent.tool.calls",
                unit="{call}",
                description="Agent tool executions by tool and outcome (ok, empty, error, exception).",
            ),
            guardrail_decisions=meter.create_counter(
                "evcare.agent.guardrail.decisions",
                unit="{decision}",
                description="Guardrail checks by stage, decision (pass, flag, modify) and reason.",
            ),
            rag_queries=meter.create_counter(
                "evcare.rag.queries",
                unit="{query}",
                description="RAG queries by outcome (answered, fallback, empty, out_of_scope, error) and cache.",
            ),
            rag_stage_duration=meter.create_histogram(
                "evcare.rag.stage.duration",
                unit="s",
                description="Duration of the non-LLM RAG stages (retrieve, rerank).",
            ),
        )


_override: AgentMetrics | None = None


def use_meter_provider(provider: MeterProvider | None) -> None:
    """Record agent metrics on ``provider`` instead of the global one (tests); ``None`` resets."""
    global _override
    _override = AgentMetrics.from_meter(provider.get_meter(METER_NAME)) if provider is not None else None


@lru_cache(maxsize=1)
def _global_metrics() -> AgentMetrics:
    # Created through the API proxy: instruments made before ``setup_telemetry``
    # start recording once the SDK provider is installed.
    return AgentMetrics.from_meter(metrics.get_meter(METER_NAME))


def get_agent_metrics() -> AgentMetrics:
    """Instruments on the global meter provider (or the test override)."""
    return _override or _global_metrics()
