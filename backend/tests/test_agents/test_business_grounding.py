"""Regression against observed tool/answer contradictions and streaming exposure."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import tool

from src.agents.business_grounding import business_answer
from src.agents.guardrails import guarded_calls
from src.agents.orchestrator import AgentOrchestrator

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = json.loads((ROOT / "eval/results/provider_recheck_mistral_20261008_01/semantic_followup_samples.json").read_text(encoding="utf-8"))


@tool
def get_due_maintenance() -> str:
    """Read current maintenance from the authorized vehicle."""
    return "{}"


def result(name, data, **kwargs):
    return ToolMessage(content=json.dumps(data), name=name, tool_call_id="read", **kwargs)


def sample_data(index):
    return deepcopy(SAMPLES[index]["current_turn_calls"][0]["result"])


def test_observed_positive_days_and_purchase_date_are_not_overdue_or_last_service():
    row = SAMPLES[0]
    output = guarded_calls(AIMessage(content=row["answer"]), [HumanMessage(content=row["user"]), result("get_due_maintenance", sample_data(0))], [get_due_maintenance])
    assert "quá hạn 500 km" in output.content
    assert "còn 182 ngày đến hạn" in output.content
    assert "quá hạn 182 ngày" not in output.content
    assert "07/04/2027" in output.content
    assert "đây không phải bản ghi lần bảo dưỡng gần nhất" in output.content
    assert output.response_metadata["original_business_answer"] == row["answer"]


@pytest.mark.parametrize("km,days,status,reason,expected", [
    (500, -2, "OVERDUE", "TIME", ("còn 500 km", "quá hạn 2 ngày")),
    (-500, -2, "OVERDUE", "BOTH", ("quá hạn 500 km", "quá hạn 2 ngày")),
    (0, 182, "DUE_SOON", "KM", ("còn 0 km", "còn 182 ngày")),
    (500, 0, "DUE_SOON", "BOTH", ("còn 500 km", "còn 0 ngày")),
    (None, -2, "OVERDUE", "TIME", ("theo thời gian", "quá hạn 2 ngày")),
])
def test_signed_distances_are_interpreted_independently(km, days, status, reason, expected):
    data = sample_data(0)
    data.update(remaining_km=km, remaining_days=days, due_status=status, due_reason=reason)
    answer = business_answer([result("get_due_maintenance", data)])
    assert all(text in answer for text in expected)
    if km is None:
        assert "Theo km:" not in answer


def test_unknown_maintenance_does_not_reuse_old_milestone():
    answer = business_answer([result("get_due_maintenance", {"due_status": "UNKNOWN", "unknown_reason": "NO_MAINTENANCE_RULE"})])
    assert "Chưa đủ dữ liệu" in answer and "12,000" not in answer


def test_observed_vat_and_warranty_claims_use_verified_fields():
    row = SAMPLES[1]
    output = guarded_calls(AIMessage(content=row["answer"]), [HumanMessage(content=row["user"]), result("estimate_service_cost", sample_data(1))], [get_due_maintenance])
    assert "chưa xác định giá đã bao gồm VAT hay chưa" in output.content
    assert "Giá đã bao gồm VAT theo quy định xưởng" not in output.content
    assert "Bảo hành xe: chưa xác định" in output.content
    assert "100,000 VND (giá của xưởng)" in output.content
    assert "giá tham khảo" not in output.content
    assert output.response_metadata["original_business_answer"] == row["answer"]


def test_mixed_reference_and_workshop_prices_preserve_source_and_fractional_total():
    data = sample_data(1)
    data["items"].append({"item_name": "Additional service", "price": 10.25, "covered": False, "price_source": "REFERENCE_PRICE"})
    data.update(chargeable_total=100010.25, has_reference_price=True)
    answer = business_answer([result("estimate_service_cost", data)])
    assert "100,000 VND (giá của xưởng)" in answer
    assert "10.25 VND (giá tham khảo)" in answer
    assert "100,010.25 VND" in answer
    assert "xưởng có thể báo giá khác" in answer


def test_expired_warranty_never_renders_a_free_warranty_item():
    data = sample_data(1)
    data["warranty_status"] = "EXPIRED"
    answer = business_answer([result("estimate_service_cost", data)])
    assert "Chưa có dữ liệu" in answer
    assert "công cụ tính 0" not in answer


def test_all_covered_zero_estimate_does_not_invent_a_workshop_price_source():
    data = sample_data(1)
    for item in data["items"]:
        item.update(covered=True, price=0, price_source=None)
    data.update(chargeable_total=0, covered_count=len(data["items"]))
    answer = business_answer([result("estimate_service_cost", data)])
    assert "Tổng chi phí ước tính: 0 VND" in answer
    assert "giá xưởng" not in answer and "giá của xưởng" not in answer and "giá tham khảo" not in answer
    assert "Bảo hành xe: chưa xác định" in answer


@pytest.mark.parametrize("field,value", [("chargeable_total", 1), ("chargeable_total", float("nan")), ("chargeable_total", True), ("has_reference_price", True), ("currency", "USD"), ("items", None)])
def test_invalid_estimates_fail_closed(field, value):
    data = sample_data(1)
    data[field] = value
    answer = business_answer([result("estimate_service_cost", data)])
    assert "Chưa có dữ liệu dự toán chi phí hợp lệ" in answer
    assert "100,000" not in answer


@pytest.mark.parametrize("price", [-1, True, float("inf"), None])
def test_invalid_item_price_is_not_rendered(price):
    data = sample_data(1)
    data["items"][1]["price"] = price
    assert "Chưa có dữ liệu" in business_answer([result("estimate_service_cost", data)])


def test_new_error_blocks_earlier_success_in_same_turn():
    messages = [result("estimate_service_cost", sample_data(1)), result("estimate_service_cost", {"status": "ERROR"}, status="error")]
    answer = business_answer(messages)
    assert "Chưa có dữ liệu" in answer and "100,000" not in answer


def test_old_turn_data_and_intermediate_tool_calls_are_not_rewritten():
    response = AIMessage(content="Please provide current data")
    messages = [HumanMessage(content="old"), result("get_due_maintenance", sample_data(0)), HumanMessage(content="new")]
    assert guarded_calls(response, messages, [get_due_maintenance]).content == response.content
    calling = AIMessage(content="", tool_calls=[{"name": "get_due_maintenance", "args": {}, "id": "new"}])
    output = guarded_calls(calling, messages, [get_due_maintenance])
    assert output.tool_calls and "business_answer_grounded_in_tool_results" not in output.response_metadata


@pytest.mark.parametrize("other", ["retrieve_knowledge", "propose_booking", "get_reminder_settings"])
def test_mixed_tool_flows_keep_their_own_answer_and_artifact(other):
    assert business_answer([result("get_due_maintenance", sample_data(0)), result(other, {})]) is None


class EventGraph:
    checkpointer = None

    def __init__(self, events):
        self.events = events

    async def astream_events(self, *args, **kwargs):
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


@pytest.mark.asyncio
async def test_business_raw_tokens_never_reach_client_before_guarded_answer():
    answer = business_answer([result("get_due_maintenance", sample_data(0))])
    graph = EventGraph([
        {"event": "on_tool_start", "name": "get_due_maintenance", "data": {"input": {}}},
        {"event": "on_tool_end", "name": "get_due_maintenance", "data": {"output": sample_data(0)}},
        {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="quá hạn 182 ngày; đã gồm VAT")}},
        {"event": "on_chain_end", "data": {"output": {"response": answer}}},
    ])
    runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    events = [event async for event in runner.run_agent_turn("test", 1, message="maintenance")]
    assert [e["type"] for e in events] == ["tool_start", "tool_end", "token", "completed"]
    assert events[2]["delta"] == answer == events[3]["message_data"]["content"]
    assert "quá hạn 182 ngày" not in "".join(e.get("delta", "") for e in events)


@pytest.mark.asyncio
async def test_nonbusiness_tokens_keep_streaming():
    graph = EventGraph([{"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="hello")}}])
    runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    events = [event async for event in runner.run_agent_turn("test", 1, message="hello")]
    assert events[0] == {"type": "token", "delta": "hello"}
    assert events[-1]["message_data"]["content"] == "hello"


@pytest.mark.asyncio
@pytest.mark.parametrize("introduction", [False, True])
async def test_business_stream_failure_emits_one_fallback_and_never_partial_model_text(introduction):
    intro_events = [{"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="I will check.")}}] if introduction else []
    graph = EventGraph(intro_events + [
        {"event": "on_tool_start", "name": "estimate_service_cost"},
        {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="VAT included")}},
        RuntimeError("disconnected"),
    ])
    runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
    events = [event async for event in runner.run_agent_turn("test", 1, message="cost")]
    tokens = [e["delta"] for e in events if e["type"] == "token"]
    assert len(tokens) == 1 + int(introduction)
    assert tokens[-1] == events[-1]["message_data"]["content"]
    assert "VAT included" not in tokens[-1]
    assert "I will check." != tokens[-1]


@pytest.mark.asyncio
async def test_real_graph_services_and_orchestrator_ground_cost_without_writes():
    from langgraph.checkpoint.memory import MemorySaver

    from src.agents.graph import build_graph
    from tests.evaluation_v2.sandbox import Sandbox

    sandbox = Sandbox({})
    model = Mock()
    model.bind_tools.return_value = model
    model.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="", tool_calls=[{"name": "get_due_maintenance", "args": {}, "id": "due"}]),
        AIMessage(content="", tool_calls=[{"name": "estimate_service_cost", "args": {"odo_milestone": 12000, "workshop_id": sandbox.workshop_a}, "id": "cost"}]),
        AIMessage(content="Quá hạn 182 ngày. Giá đã bao gồm VAT. Bảo hành đã hết nhưng vẫn miễn phí."),
    ])
    try:
        before = sandbox.reminder_state()
        graph = build_graph(model, sandbox.tools, MemorySaver())
        runner = AgentOrchestrator(graph, AsyncMock(return_value={}))
        events = [event async for event in runner.run_agent_turn(sandbox.conversation_id, sandbox.user_id, sandbox.vehicle_id, "Tra hạn và chi phí", vehicle_context=sandbox.context)]
        answer = events[-1]["message_data"]["content"]
        assert "còn 182 ngày" in answer and "quá hạn 500 km" in answer
        assert "100,000 VND" in answer and "chưa xác định giá đã bao gồm VAT hay chưa" in answer
        assert "giá tham khảo" not in answer
        assert "Bảo hành đã hết" not in answer
        assert "".join(e["delta"] for e in events if e["type"] == "token") == answer
        assert sandbox.side_effects() == {"booking_count_before_confirm": 0, "proposal_count": 0}
        assert sandbox.reminder_state() == before
        assert model.ainvoke.await_count == 3  # No extra LLM call by the renderer.
        state = await graph.aget_state({"configurable": {"thread_id": str(sandbox.conversation_id)}})
        assert state.values["messages"][-1].response_metadata["original_business_answer"].startswith("Quá hạn 182 ngày")
    finally:
        await sandbox.close()
