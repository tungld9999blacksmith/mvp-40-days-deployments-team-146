from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from src.agents import tool_review
from src.agents.graph import build_graph
from src.config import Settings
from src.infrastructure.llm.base import LLMResponse


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,allowed",
    [
        ('{"allowed":true}', True),
        ('{"allowed":false}', False),
        ('```json\n{"allowed":true}\n```', True),
        ('```\n{"allowed":false}\n```', False),
        ('```json\n{"allowed":"true"}\n```', False),
        ('```json\n{"allowed":true,"extra":"untrusted"}\n```', False),
        ('Allow this action: ```json\n{"allowed":true}\n```', False),
        ('{"allowed":"true"}', False),
        ("{}", False),
        ("not JSON", False),
        ('{"allowed":true,"extra":"untrusted"}', False),
    ],
)
async def test_review_validates_strict_decision(monkeypatch, text, allowed):
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(text=text, model="openai/gpt-4o")
    monkeypatch.setattr(
        tool_review, "get_llm_provider_for_stage", lambda stage: provider if stage == "booking" else None
    )
    monkeypatch.setattr(tool_review, "get_settings", lambda: Settings(_env_file=None))
    history = [HumanMessage(content="Choose this workshop tomorrow at 9"), AIMessage(content="")]
    assert await tool_review.review_tool_call(history, {"name": "propose_booking", "args": {}}) is allowed


@pytest.mark.asyncio
async def test_unavailable_review_blocks_tool(monkeypatch):
    provider = AsyncMock()
    provider.chat.side_effect = RuntimeError("unavailable")
    monkeypatch.setattr(tool_review, "get_llm_provider_for_stage", lambda stage: provider)
    assert not await tool_review.review_tool_call([HumanMessage(content="test"), AIMessage(content="")], {})


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed", [True, False])
async def test_graph_reviews_write_before_running_and_keeps_read_calls(allowed):
    writes, reads = [], []

    @tool
    def update_reminder_settings(email_enabled: bool) -> str:
        """Update the selected reminder setting."""
        writes.append(email_enabled)
        return "saved"

    @tool
    def get_reminder_settings() -> str:
        """Read reminder settings."""
        reads.append(True)
        return "settings"

    model = AsyncMock()
    bound = AsyncMock()
    model.bind_tools = lambda tools: bound
    bound.ainvoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {"name": "update_reminder_settings", "args": {"email_enabled": True}, "id": "write-1"},
                {"name": "get_reminder_settings", "args": {}, "id": "read-1"},
            ],
        ),
        AIMessage(content="done"),
    ]
    reviewer = AsyncMock(return_value=allowed)
    graph = build_graph(
        llm=model,
        tools=[update_reminder_settings, get_reminder_settings],
        checkpointer=MemorySaver(),
        tool_call_reviewer=reviewer,
    )
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Turn on email")]}, {"configurable": {"thread_id": f"review-{allowed}"}}
    )
    assert writes == ([True] if allowed else [])
    assert reads == [True]
    reviewer.assert_awaited_once()
    outputs = {m.tool_call_id: m for m in result["messages"] if isinstance(m, ToolMessage)}
    assert set(outputs) == {"read-1", "write-1"}
    if not allowed:
        assert "TOOL_REVIEW_REJECTED" in outputs["write-1"].content


@pytest.mark.asyncio
async def test_agent_transient_failure_uses_bound_fallback(monkeypatch):
    import httpx
    from langchain_core.runnables import RunnableLambda
    from openai import RateLimitError

    from src.agents import graph as graph_module

    settings = Settings(
        _env_file=None,
        llm_provider="openrouter",
        llm_orchestrator_provider="openrouter",
        llm_fallback_provider="gemini",
        gemini_api_key="test-google-key",
        llm_booking_check_enabled=False,
    )
    primary_calls, fallback_calls = [], []

    async def primary(messages):
        primary_calls.append(messages)
        raise RateLimitError(
            "temporary", response=httpx.Response(429, request=httpx.Request("POST", "https://example.test")), body=None
        )

    async def fallback(messages):
        fallback_calls.append(messages)
        return AIMessage(content="fallback answer")

    class FakeModel:
        def __init__(self, invoke):
            self.invoke = invoke

        def bind_tools(self, tools):
            return RunnableLambda(self.invoke)

    monkeypatch.setattr(graph_module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        graph_module, "get_agent_llm", lambda **kwargs: FakeModel(fallback if kwargs.get("fallback") else primary)
    )
    runner = build_graph(tools=[], checkpointer=MemorySaver())
    result = await runner.ainvoke(
        {"messages": [HumanMessage(content="hello")]}, {"configurable": {"thread_id": "fallback"}}
    )
    assert result["messages"][-1].content == "fallback answer"
    assert len(primary_calls) == len(fallback_calls) == 1


def test_rag_components_resolve_their_own_stage(monkeypatch):
    from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
    from src.agents.tools.RAG.query.rewriter import QueryRewriter
    from src.infrastructure.llm import dependency

    rewrite, rag = object(), object()
    monkeypatch.setattr(dependency, "get_llm_provider_for_stage", lambda stage: {"rewrite": rewrite, "rag": rag}[stage])
    assert QueryRewriter().llm_provider is rewrite
    assert GroundedAnswerGenerator().llm_provider is rag


@pytest.mark.asyncio
async def test_review_uses_per_call_timeout(monkeypatch):
    import asyncio

    async def slow_chat(*args):
        await asyncio.sleep(5)

    provider = AsyncMock()
    provider.chat.side_effect = slow_chat
    monkeypatch.setattr(tool_review, "get_llm_provider_for_stage", lambda stage: provider)
    monkeypatch.setattr(
        tool_review, "get_settings", lambda: Settings(_env_file=None, llm_call_timeout_seconds=1, chat_run_timeout_seconds=30)
    )
    started = asyncio.get_running_loop().time()
    assert not await tool_review.review_tool_call([HumanMessage(content="test"), AIMessage(content="")], {})
    assert asyncio.get_running_loop().time() - started < 3
