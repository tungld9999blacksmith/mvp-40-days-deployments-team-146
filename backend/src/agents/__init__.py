"""EV Care AI Agent Module."""

from typing import Any

from .graph import build_graph
from .orchestrator import AgentOrchestrator, run_agent_turn
from .state import AgentState
from .tools import CUSTOMER_AGENT_TOOLS

__all__ = [
    "agent",
    "build_graph",
    "AgentOrchestrator",
    "AgentState",
    "run_agent_turn",
    "CUSTOMER_AGENT_TOOLS",
]


def __getattr__(name: str) -> Any:
    if name == "agent":
        from .dependency import get_agent_graph

        return get_agent_graph()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
