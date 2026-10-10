from typing import Any

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from src.agents.graph import build_graph


class ScriptedChat(FakeListChatModel):
    turn: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, *args, **kwargs):
        self.turn += 1
        if self.turn == 1:
            return AIMessage(content="", tool_calls=[{
                "name": "get_due_maintenance", "args": {}, "id": "due-call",
            }])
        return AIMessage(content="Done")


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_prefill_follows_actual_tool_schema(legacy):
    calls: list[dict[str, Any]] = []

    if legacy:
        @tool
        def get_due_maintenance(model: str, current_odometer_km: int, months_since_last_service: int):
            """Legacy maintenance tool with explicit vehicle inputs."""
            calls.append({"model": model, "odo": current_odometer_km, "months": months_since_last_service})
            return {"due_status": "NORMAL"}
    else:
        @tool
        def get_due_maintenance(config: RunnableConfig):
            """Main maintenance tool reads its caller from trusted config."""
            calls.append({"caller": config["configurable"]["trusted_caller"]})
            return {"due_status": "NORMAL"}

    graph = build_graph(
        ScriptedChat(responses=["unused"]), [get_due_maintenance], MemorySaver(),
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Maintenance status")], "vehicle_context": {
            "model": "VF5", "current_odo": 5000, "months_since_last": 3,
        }},
        {"configurable": {"thread_id": f"prefill-{legacy}", "trusted_caller": "server-owner"}},
    )
    assert calls == ([{"model": "VF5", "odo": 5000, "months": 3}] if legacy else [{"caller": "server-owner"}])
    tool_call = next(m.tool_calls[0] for m in result["messages"] if isinstance(m, AIMessage) and m.tool_calls)
    assert tool_call["args"] == (
        {"model": "VF5", "current_odometer_km": 5000, "months_since_last_service": 3}
        if legacy else {}
    )


class UpstreamErrorChat(FakeListChatModel):
    """Replies like OpenRouter when the provider fails mid-answer, ``failures`` times."""

    failures: int = 1
    calls: int = 0

    def bind_tools(self, tools, **kwargs):
        return self

    async def ainvoke(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            return AIMessage(content="", response_metadata={"finish_reason": "error"})
        return AIMessage(content="Answer", response_metadata={"finish_reason": "stop"})


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [1, 2])
async def test_upstream_error_reply_is_retried_once_then_raised(failures):
    model = UpstreamErrorChat(responses=["unused"], failures=failures)
    graph = build_graph(model, [], MemorySaver())
    run = graph.ainvoke(
        {"messages": [HumanMessage(content="Book maintenance")]},
        {"configurable": {"thread_id": f"upstream-{failures}"}},
    )
    if failures == 1:
        result = await run
        assert result["messages"][-1].content == "Answer"
    else:
        with pytest.raises(RuntimeError, match="upstream error"):
            await run
    assert model.calls == 2
