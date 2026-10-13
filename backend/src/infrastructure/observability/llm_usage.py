"""Latency, token and cost accounting for LLM calls, per call and per agent turn.

Every LLM call — LangChain chat models (``OtelLLMCallbackHandler``) and providers
used outside LangChain (``TracedLLMProvider``) — goes through ``record_llm_call``:
it feeds the Grafana metrics and adds to the ``TurnUsage`` bound to the running turn,
which ``agent.turn`` reports as its total. Numbers only; never message content.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from dataclasses import dataclass

from .metrics import get_agent_metrics
from .pricing import estimate_cost

logger = logging.getLogger(__name__)

_warned_unpriced: set[str] = set()


@dataclass
class TurnUsage:
    """Everything the LLM calls of one agent turn consumed."""

    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    unpriced_calls: int = 0
    llm_seconds: float = 0.0


_current: ContextVar[TurnUsage | None] = ContextVar("evcare_turn_usage", default=None)


def bind_turn_usage(usage: TurnUsage | None) -> None:
    """Make ``usage`` collect the LLM calls of the current turn; ``None`` stops collecting."""
    _current.set(usage)


def record_llm_call(
    *,
    model: str,
    node: str | None,
    duration_s: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    status: str = "ok",
) -> float | None:
    """Record one LLM call; returns its cost in USD (``None`` when the model is unpriced)."""
    metrics = get_agent_metrics()
    labels = {"gen_ai.request.model": model, "agent.node": node or "none"}
    metrics.llm_call_duration.record(duration_s, {**labels, "llm.status": status})
    for kind, count in (("input", input_tokens), ("output", output_tokens)):
        if count:
            metrics.llm_tokens.add(count, {**labels, "gen_ai.token.type": kind})

    cost = estimate_cost(model, input_tokens, output_tokens) if status == "ok" else 0.0
    if cost is None:
        metrics.llm_unpriced_calls.add(1, labels)
        if model not in _warned_unpriced:
            _warned_unpriced.add(model)
            logger.warning("No price for model %r in model_prices.json; its cost is not reported", model)
    elif cost:
        metrics.llm_cost.add(cost, labels)

    usage = _current.get()
    if usage is not None:
        usage.llm_calls += 1
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.llm_seconds += duration_s
        if cost is None:
            usage.unpriced_calls += 1
        else:
            usage.cost_usd += cost
    return cost
