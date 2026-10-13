"""Agent metrics for Grafana (OpenTelemetry).

Numbers only, no content: tool health and latency, guardrail decisions, RAG, and per
LLM call / per turn latency, tokens and cost (docs/observability/OBSERVABILITY_SETUP.md,
"Chia vai Grafana / LangSmith"). Prompts and answers stay in LangSmith.

Every label below has a small, fixed value set — the free tier allows 10k series.
Never label with user / vehicle / conversation ids or free text.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from opentelemetry import metrics
from opentelemetry.metrics import Counter, Histogram, Meter, MeterProvider, NoOpMeterProvider

from .switch import agent_telemetry_enabled

METER_NAME = "evcare.agent"

# The OTel default buckets are millisecond-sized; these fit LLM / tool latencies in seconds.
SECOND_BUCKETS = [0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 12, 20, 30, 60]


@dataclass(frozen=True)
class AgentMetrics:
    tool_calls: Counter
    guardrail_decisions: Counter
    rag_queries: Counter
    rag_stage_duration: Histogram
    tool_duration: Histogram
    llm_call_duration: Histogram
    llm_tokens: Counter
    llm_cost: Counter
    llm_unpriced_calls: Counter
    turn_duration: Histogram
    turn_cost: Histogram

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
            tool_duration=meter.create_histogram(
                "evcare.agent.tool.duration",
                unit="s",
                description="Agent tool execution time by tool and outcome.",
                explicit_bucket_boundaries_advisory=SECOND_BUCKETS,
            ),
            llm_call_duration=meter.create_histogram(
                "evcare.llm.call.duration",
                unit="s",
                description="One LLM call, by model, graph node and status (ok, error).",
                explicit_bucket_boundaries_advisory=SECOND_BUCKETS,
            ),
            llm_tokens=meter.create_counter(
                "evcare.llm.tokens",
                unit="{token}",
                description="LLM tokens by model, graph node and type (input, output).",
            ),
            llm_cost=meter.create_counter(
                "evcare.llm.cost.usd",
                description="Estimated LLM cost in USD (token counts x model_prices.json).",
            ),
            llm_unpriced_calls=meter.create_counter(
                "evcare.llm.unpriced.calls",
                unit="{call}",
                description="LLM calls whose model has no price in model_prices.json (cost not counted).",
            ),
            turn_duration=meter.create_histogram(
                "evcare.agent.turn.duration",
                unit="s",
                description="Whole agent turn (one user message to the final answer) by outcome.",
                explicit_bucket_boundaries_advisory=SECOND_BUCKETS,
            ),
            turn_cost=meter.create_histogram(
                "evcare.agent.turn.cost.usd",
                description="Estimated LLM cost of one agent turn in USD.",
                explicit_bucket_boundaries_advisory=[0.0001, 0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
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


@lru_cache(maxsize=1)
def _noop_metrics() -> AgentMetrics:
    return AgentMetrics.from_meter(NoOpMeterProvider().get_meter(METER_NAME))


def get_agent_metrics() -> AgentMetrics:
    """Instruments on the global meter provider (or the test override); no-ops when
    ``OTEL_AGENT_ENABLED`` is off."""
    if not agent_telemetry_enabled():
        return _noop_metrics()
    return _override or _global_metrics()
