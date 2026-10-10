"""Real LangGraph memory reducer tests: three turns, restart and recovery."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.checkpoint import postgres_dsn
from src.agents.graph import build_graph
from src.agents.orchestrator import AgentOrchestrator
from src.config import Settings


class FakeChat(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class FailingChat(FakeChat):
    async def ainvoke(self, *args, **kwargs):
        raise RuntimeError("model disconnected")


class SlowChat(FakeChat):
    started: asyncio.Event

    async def ainvoke(self, *args, **kwargs):
        self.started.set()
        await asyncio.Event().wait()


def test_checkpoint_uses_derived_database_fields_and_raw_psycopg_dsn():
    cfg = Settings(
        _env_file=None,
        database_password="password@with/slash",
        database_user="test",
        database_host="localhost",
        database_name="test_db",
        database_url=None,
    )
    dsn = postgres_dsn(cfg)
    assert dsn.startswith("postgresql://") and "+psycopg" not in dsn
    assert "password%40with%2Fslash" in dsn and "connect_timeout=" in dsn


@pytest.mark.asyncio
async def test_three_turns_database_ids_confirmation_and_graph_rebuild_do_not_duplicate():
    saver = MemorySaver()
    model = FakeChat(responses=["answer-1", "answer-2", "answer-3"])
    graph = build_graph(model, [], saver)
    runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    cid = uuid4()
    history = []
    for n in range(3):
        mid, aid = uuid4(), uuid4()
        events = [
            e
            async for e in runner.run_agent_turn(
                cid, 1, message=f"question-{n}", history_messages=list(history), source_message_id=mid
            )
        ]
        answer = events[-1]["message_data"]["content"]
        assert answer == f"answer-{n + 1}"
        await runner.record_committed_answer(cid, aid, answer)
        history += [HumanMessage(content=f"question-{n}", id=str(mid)), AIMessage(content=answer, id=str(aid))]
        if n == 0:
            history += [AIMessage(content="Booking confirmed through API", id="booking-confirmation")]
        if n == 1:
            # New graph/orchestrator with the same saver, equivalent to reopening
            # the persistent saver after a process restart.
            graph = build_graph(model, [], saver)
            runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    state = await graph.aget_state({"configurable": {"thread_id": str(cid)}})
    messages = state.values["messages"]
    assert len(messages) == 7
    assert len({m.id for m in messages}) == 7
    assert sum(m.id == "booking-confirmation" for m in messages) == 1
    assert messages[-1].id == str(aid)


@pytest.mark.asyncio
async def test_failed_turn_clears_partial_checkpoint_and_recovers_from_committed_history():
    saver = MemorySaver()
    bad = FailingChat(responses=["bad"])
    graph = build_graph(bad, [], saver)
    runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    cid = uuid4()
    events = [e async for e in runner.run_agent_turn(cid, 1, message="first", source_message_id="user-1")]
    assert events[-1]["type"] == "completed"
    config = {"configurable": {"thread_id": str(cid)}}
    assert await saver.aget_tuple(config) is None
    good = build_graph(FakeChat(responses=["recovered"]), [], saver)
    runner = AgentOrchestrator(good, AsyncMock(return_value={}))
    history = [HumanMessage(content="first", id="user-1"), AIMessage(content="fallback", id="assistant-1")]
    result = [
        e
        async for e in runner.run_agent_turn(
            cid, 1, message="second", history_messages=history, source_message_id="user-2"
        )
    ]
    assert result[-1]["message_data"]["content"] == "recovered"
    assert len((await good.aget_state(config)).values["messages"]) == 4


@pytest.mark.asyncio
async def test_cancelled_turn_does_not_leave_orphan_checkpoint():
    saver = MemorySaver()
    started = asyncio.Event()
    slow = SlowChat(responses=["slow"], started=started)
    graph = build_graph(slow, [], saver)
    runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    cid = uuid4()

    async def consume():
        return [e async for e in runner.run_agent_turn(cid, 1, message="first", source_message_id="user-1")]

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await saver.aget_tuple({"configurable": {"thread_id": str(cid)}}) is None
