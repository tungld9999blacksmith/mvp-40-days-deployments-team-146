"""Offline regression coverage for agent dependency composition and streaming."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage

from src.agents import dependency, graph
from src.agents.orchestrator import AgentOrchestrator, fetch_vehicle_context, run_agent_turn
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from src.agents.tools.dependency import AgentToolServices, build_customer_agent_tools
from tests._maintenance import make_session
from tests._user_vehicle import add_odometer, add_owner, add_vehicle


class EventGraph:
    def __init__(self, events, error=None):
        self.events = events
        self.error = error
        self.calls = []

    async def astream_events(self, state, *, config, version):
        self.calls.append((state, config, version))
        for event in self.events:
            yield event
        if self.error:
            raise self.error


@pytest.mark.asyncio
async def test_orchestrator_uses_injected_graph_loader_and_trusted_identity():
    vehicle_id, conversation_id, message_id = uuid4(), uuid4(), uuid4()
    loader = AsyncMock(return_value={"vehicle_id": str(vehicle_id), "current_odo": 11_500})
    citations = [{"title": "Manual"}]
    runner = EventGraph(
        [
            {"event": "on_tool_start", "name": "get_due_maintenance", "data": {"input": {}}},
            {"event": "on_tool_end", "name": "get_due_maintenance", "data": {"output": {"due": True}}},
            {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="Answer")}},
            {"event": "on_chain_end", "data": {"output": {"citations": citations}}},
        ]
    )
    orchestrator = AgentOrchestrator(runner, loader)

    events = [
        event
        async for event in orchestrator.run_agent_turn(
            conversation_id, 42, vehicle_id, "Question", source_message_id=message_id, operation_key="request-1"
        )
    ]

    loader.assert_awaited_once_with(vehicle_id)
    assert [event["type"] for event in events] == ["tool_start", "tool_end", "token", "completed"]
    assert events[-1]["message_data"]["content"] == "Answer"
    assert events[-1]["message_data"]["citations"] == citations
    state, config, version = runner.calls[0]
    assert isinstance(state["messages"][-1], HumanMessage)
    assert state["vehicle_context"]["current_odo"] == 11_500
    assert version == "v2"
    caller = config["configurable"]
    assert (caller["thread_id"], caller["user_id"], caller["user_vehicle_id"]) == (
        str(conversation_id),
        42,
        str(vehicle_id),
    )
    assert caller["ctx"].source_message_id == message_id
    assert caller["ctx"].operation_key == "request-1"

    runner.calls.clear()
    await anext(orchestrator.confirm_booking_turn(conversation_id, 42, True, vehicle_id))
    assert runner.calls[0][0].resume == {"confirmed": True}
    assert runner.calls[0][1]["configurable"]["thread_id"] == str(conversation_id)
    loader.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_failure_never_reexecutes_the_graph():
    runner = EventGraph([], error=RuntimeError("Stream interrupted after side effect"))
    loader = AsyncMock()
    orchestrator = AgentOrchestrator(runner, loader)

    events = [
        event
        async for event in orchestrator.run_agent_turn(
            uuid4(), 42, uuid4(), "Question", vehicle_context={"model": "VF6"}
        )
    ]

    assert len(runner.calls) == 1
    loader.assert_not_awaited()
    assert [event["type"] for event in events] == ["token", "completed"]
    assert events[-1]["message_data"]["content"]


def test_tool_bundles_keep_dependencies_isolated_and_out_of_tool_schema():
    unused = Mock(side_effect=AssertionError("Unexpected business-service access"))
    pipeline_a = Mock()
    pipeline_a.query_sync.return_value = SimpleNamespace(answer="A", citations=[])
    pipeline_b = Mock()
    pipeline_b.query_sync.return_value = SimpleNamespace(answer="B", citations=[])
    services = AgentToolServices(unused, unused, unused, unused, unused, lambda: pipeline_a)
    tools_a = build_customer_agent_tools(services)
    tools_b = build_customer_agent_tools(replace(services, rag_pipeline=lambda: pipeline_b))

    assert [tool.name for tool in tools_a] == [tool.name for tool in CUSTOMER_AGENT_TOOLS]
    for tool in tools_a:
        assert not (
            {"services", "provider", "pipeline_provider", "config", "user_id", "user_vehicle_id"} & tool.args.keys()
        )
    rag_a, rag_b = tools_a[-1], tools_b[-1]
    assert rag_a.invoke({"query": "Warranty"}) == "A"
    assert rag_b.invoke({"query": "Warranty"}) == "B"
    assert rag_a.invoke({"query": "Warranty"}) == "A"
    unused.assert_not_called()


@pytest.mark.asyncio
async def test_context_loader_reads_injected_database():
    from contextlib import contextmanager

    for session in make_session():
        user = add_owner(session)
        vehicle = add_vehicle(session, user)
        add_odometer(session, vehicle, 11_500)

        @contextmanager
        def session_factory():
            yield session

        context = await fetch_vehicle_context(vehicle.id, session_factory=session_factory)
        assert context["vehicle_id"] == str(vehicle.id)
        assert context["user_id"] == user.user_id
        assert context["current_odo"] == 11_500
        assert context["last_service_odo"] is None


@pytest.mark.asyncio
async def test_default_entrypoint_and_legacy_export_use_dependency_graph(monkeypatch):
    import src.agents as agents

    runner = EventGraph([])
    orchestrator = AgentOrchestrator(runner, AsyncMock(return_value={}))
    monkeypatch.setattr(dependency, "get_agent_orchestrator", lambda: orchestrator)
    monkeypatch.setattr(dependency, "get_agent_graph", lambda: runner)

    assert graph.agent is runner
    assert agents.agent is runner
    events = [event async for event in run_agent_turn(uuid4(), 42)]
    assert events[-1]["type"] == "completed"
    assert len(runner.calls) == 1


def test_graph_composition_is_cached_and_respects_empty_tool_list(monkeypatch):
    llm, checkpointer, runner = Mock(), Mock(), Mock()
    build = Mock(return_value=runner)
    monkeypatch.setattr(dependency, "get_agent_llm", lambda: llm)
    monkeypatch.setattr(dependency, "get_agent_tools", lambda: [])
    monkeypatch.setattr(dependency, "get_checkpointer", lambda: checkpointer)
    monkeypatch.setattr(dependency, "build_graph", build)
    dependency.get_agent_graph.cache_clear()
    try:
        assert dependency.get_agent_graph() is dependency.get_agent_graph()
        build.assert_called_once_with(llm=llm, tools=[], checkpointer=checkpointer)
    finally:
        dependency.get_agent_graph.cache_clear()

    graph.build_graph(llm=llm, tools=[], checkpointer=False)
    llm.bind_tools.assert_called_once_with([])
