"""Agent composition root, shared by HTTP chat and standalone agent callers."""

from __future__ import annotations

from functools import lru_cache, partial
from typing import Any

from src.config import get_settings

from .graph import build_graph, get_agent_llm, get_checkpointer
from .orchestrator import AgentOrchestrator, fetch_vehicle_context
from .tool_review import review_tool_call
from .tools.dependency import get_agent_tool_services, get_agent_tools


@lru_cache
def get_agent_graph() -> Any:
    """Build once on demand; normal turns and confirmation use the same graph."""
    return build_graph(
        llm=get_agent_llm(),
        tools=get_agent_tools(),
        checkpointer=get_checkpointer(),
        use_llm_fallback=True,
        tool_call_reviewer=review_tool_call if get_settings().llm_booking_check_enabled else None,
    )


@lru_cache
def get_agent_orchestrator() -> AgentOrchestrator:
    services = get_agent_tool_services()
    return AgentOrchestrator(
        graph=get_agent_graph(),
        vehicle_context_loader=partial(fetch_vehicle_context, session_factory=services.open_session),
    )
