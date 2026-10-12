"""Agent-specific telemetry: the turn summary and the guardrail records.

Built on ``infrastructure.observability.step`` — Grafana gets attributes, LangSmith
gets content. See docs/observability/OBSERVABILITY_SETUP.md ("Agent telemetry").
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..infrastructure.observability import Step, get_agent_metrics

logger = logging.getLogger(__name__)

OUTCOMES = ("answered", "fallback", "error", "cancelled")


@dataclass
class TurnRecorder:
    """What happened during one agent turn; summarized on ``agent.turn`` at the end."""

    started: float = field(default_factory=time.monotonic)
    tools: list[str] = field(default_factory=list)
    outcome: str = "answered"
    error_type: str | None = None
    message_data: dict[str, Any] | None = None

    def tool_started(self, name: str) -> None:
        self.tools.append(name)

    def failed(self, exc: BaseException) -> None:
        self.outcome, self.error_type = "error", type(exc).__name__

    def cancelled(self) -> None:
        self.outcome = "cancelled"

    def completed(self, message_data: dict[str, Any]) -> None:
        self.message_data = message_data
        if self.outcome == "answered" and message_data.get("fallback_required"):
            self.outcome = "fallback"

    def finish(self, current: Step) -> None:
        duration_ms = round((time.monotonic() - self.started) * 1000)
        current.set(
            **{
                "agent.outcome": self.outcome,
                "agent.tool_calls": len(self.tools),
                "agent.tools": sorted(set(self.tools)),
                "error.type": self.error_type,
            }
        )
        current.metadata(outcome=self.outcome, tools=self.tools)
        data = self.message_data or {}
        current.outputs(
            {
                "content": data.get("content", ""),
                "citations": data.get("citations", []),
                "confidence": data.get("confidence"),
                "fallback_required": data.get("fallback_required"),
            }
        )
        if self.outcome == "error":
            current.fail(self.error_type or "agent error")
        # Loki: one summary line per turn, joined to the trace by trace_id. No content.
        logger.info(
            "Agent turn finished: %s",
            self.outcome,
            extra={
                "agent_outcome": self.outcome,
                "agent_tool_calls": len(self.tools),
                "agent_tools": ",".join(self.tools),
                "duration_ms": duration_ms,
            },
        )


def record_input_guard(current: Step, report: Any) -> None:
    """Input guard result: flag reasons on the span + counter, full report to LangSmith."""
    pii_types = sorted(report.pii_found)
    reasons = (["injection"] if report.has_injection else []) + (["pii"] if report.has_pii else [])
    current.set(
        **{
            "guard.decision": "flag" if reasons else "pass",
            "guard.injection": report.has_injection,
            "guard.pii_types": pii_types,
        }
    )
    current.outputs({"injection_hits": len(report.injection_hits), "pii_found": dict(report.pii_found)})
    decisions = get_agent_metrics().guardrail_decisions
    for reason in reasons or ["none"]:
        decisions.add(
            1, {"guard.stage": "input", "guard.decision": "flag" if reasons else "pass", "guard.reason": reason}
        )


def tool_call_signature(response: Any) -> list[dict[str, Any]]:
    return [{"name": tc.get("name"), "args": tc.get("args")} for tc in getattr(response, "tool_calls", None) or []]


def record_tool_call_guard(current: Step, before: list[dict[str, Any]], response: Any) -> None:
    """Tool-call guardrails (schema / authorization / repair): pass or modify."""
    after = tool_call_signature(response)
    modified = before != after
    current.set(
        **{
            "guard.decision": "modify" if modified else "pass",
            "guard.calls_in": len(before),
            "guard.calls_out": len(after),
        }
    )
    current.outputs({"tool_calls": after})
    if before or after:  # plain answers without tool calls are not a guard decision
        get_agent_metrics().guardrail_decisions.add(
            1,
            {
                "guard.stage": "tool_calls",
                "guard.decision": "modify" if modified else "pass",
                "guard.reason": "tool_call_rewrite" if modified else "none",
            },
        )
