"""Frozen failures and real-service regressions for follow-up date/capability policy."""
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.booking_grounding import booking_answer
from src.agents.booking_policy import empty_rag_answer, explicit_date, inherited_read_date, missing_read_plan
from src.agents.graph import build_graph
from src.agents.guardrails import guarded_calls
from src.agents.orchestrator import AgentOrchestrator
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from tests.evaluation_v2.runner import requested_calls
from tests.evaluation_v2.sandbox import NOW, Sandbox

ROOT = Path(__file__).resolve().parents[3]
RUN = ROOT / "eval/results/agent_v2_1_booking_grounding_sessions_mistral_20261008_04"
SESSIONS = json.loads((RUN / "comparison.json").read_text(encoding="utf-8"))[0]["sessions"]
ID = "11111111-2222-3333-4444-555555555555"


def observed(number):
    return deepcopy(SESSIONS[number - 1]["turns"][3])


def messages(row):
    classes = {"ai": AIMessage, "human": HumanMessage, "tool": ToolMessage}
    return [classes[m["type"]](**m) for m in row["messages"][:-1]]


def before_current_tools(row):
    history = messages(row)
    index = max(i for i, m in enumerate(history) if isinstance(m, HumanMessage))
    return history[:index + 1]


@pytest.fixture(autouse=True)
def evaluation_clock():
    with patch("src.agents.prompts.now_vn", return_value=NOW):
        yield


@pytest.mark.parametrize("text,expected", [
    ("chiều thứ Bảy", "2026-10-10"), ("chieu thu bay", "2026-10-10"),
    ("Ngày mai thay vì thứ Bảy", "2026-10-08"), ("hôm qua", "2026-10-06"),
    ("Hãy xem lịch 2026-10-11", "2026-10-11"),
])
def test_user_dates_use_the_fixture_clock_and_replacement_phrase(text, expected):
    assert explicit_date(text, NOW).target_date.isoformat() == expected


@pytest.mark.parametrize("text", [
    "2026-10-10 hoặc 2026-10-11", "thứ Bảy hay Chủ Nhật", "Nếu xem lịch 2026-10-10 thì sao?",
    'Tài liệu ghi "2026-10-10"', "không phải 10/10", "tuần sau", "2026-99-99", "ngày khác",
])
def test_ambiguous_dates_are_not_resolved_as_a_choice(text):
    assert explicit_date(text, NOW) is None


def test_workshop_switch_keeps_verified_user_day_and_raw_wrong_day():
    row = observed(6)
    call = row["current_turn_calls"][0]
    response = AIMessage(content="", tool_calls=[{"name": call["name"], "args": call["args"], "id": "read", "type": "tool_call"}])
    out = guarded_calls(response, before_current_tools(row), CUSTOMER_AGENT_TOOLS)
    assert out.tool_calls[0]["args"]["target_date"] == "2026-10-10"
    assert out.response_metadata["requested_tool_calls"][0]["args"]["target_date"] == "2026-10-07"
    assert "target_date_from_verified_user_context" in out.response_metadata["normalized_fields"]


@pytest.mark.parametrize("user,day", [
    ("Xem lịch 2026-10-11", "2026-10-11"), ("Xem lịch tuần sau", "2026-10-12"),
    ("Xem lịch 2026-10-11 hoặc 2026-10-12", "2026-10-12"),
])
def test_new_or_unsupported_date_cannot_silently_inherit_old_day(user, day):
    row = observed(6)
    history = before_current_tools(row)
    workshop = row["current_turn_calls"][0]["args"]["workshop_id"]
    history[-1] = HumanMessage(content=f"{user} tại xưởng {workshop}")
    out = guarded_calls(AIMessage(content="", tool_calls=[{"name": "get_available_slots", "args": {"workshop_id": workshop, "target_date": day}, "id": "read"}]), history, CUSTOMER_AGENT_TOOLS)
    assert "target_date_from_verified_user_context" not in out.response_metadata["normalized_fields"]


def test_a_failed_new_read_invalidates_historical_date_and_slot_examples():
    row = observed(6)
    history = before_current_tools(row)[:-1]
    history.append(ToolMessage(content='{"status":"ERROR"}', name="get_available_slots", tool_call_id="new-failure", status="error"))
    assert inherited_read_date(history, NOW) is None
    out = guarded_calls(AIMessage(content="Please pick a time"), [*history, HumanMessage(content="Tôi chưa chọn giờ.")], CUSTOMER_AGENT_TOOLS)
    assert out.content == "Please pick a time"


def test_old_model_date_alone_cannot_authorize_read_date_binding():
    history = [HumanMessage(content="Xem lịch"), AIMessage(content="10/10/2026")]
    assert inherited_read_date(history, NOW) is None


@pytest.mark.parametrize("number,required,forbidden", [
    (4, "00:00, 01:00, 02:00", "14:30"),
    (14, "ngày nào", "10/10/2026"),
    (17, "ngày đã qua", "không thấy lịch trống"),
    (18, "AUTO", "chỉ được ghi nhận khi xưởng xác nhận"),
    (19, "không tạo lịch trùng", "thẻ đề xuất sẽ biến mất"),
])
def test_frozen_failed_answers_are_replaced_by_verified_slots_or_contract(number, required, forbidden):
    row = observed(number)
    out = guarded_calls(AIMessage(content=row["answer"]), messages(row), CUSTOMER_AGENT_TOOLS)
    assert required in out.content and forbidden not in out.content
    assert out.response_metadata["original_booking_followup_answer"] == row["answer"]
    assert not out.tool_calls


def test_proposal_write_date_is_not_bound_from_workshop_switch_history():
    row = observed(6)
    history = before_current_tools(row)
    workshop = row["current_turn_calls"][0]["args"]["workshop_id"]
    history[-1] = HumanMessage(content=f"Tôi chọn 14:00 ở xưởng {workshop}, tạo thẻ.")
    out = guarded_calls(AIMessage(content="", tool_calls=[{"name": "propose_booking", "args": {"workshop_id": workshop, "booking_date": "2026-10-07", "time_slot": "14:00"}, "id": "write"}]), history, CUSTOMER_AGENT_TOOLS)
    assert not out.tool_calls
    assert "target_date_from_verified_user_context" not in out.response_metadata.get("normalized_fields", [])


def test_cancel_request_cannot_call_a_proposal_instead():
    out = guarded_calls(AIMessage(content="Tôi sẽ hủy", tool_calls=[{"name": "propose_booking", "args": {"workshop_id": ID, "booking_date": "2026-10-10", "time_slot": "14:00"}, "id": "wrong"}]), [HumanMessage(content="Hủy lịch cũ cho tôi")], CUSTOMER_AGENT_TOOLS)
    assert not out.tool_calls and "chưa có công cụ hủy" in out.content


@pytest.mark.parametrize("user", ["Nếu tìm lịch bảo dưỡng thứ Bảy thì sao?", "Đừng xem lịch thứ Bảy", 'Tài liệu ghi "tìm lịch thứ Bảy"', "Giá tham khảo là gì?"])
def test_no_automatic_reads_for_conditional_negated_document_or_definition_requests(user):
    out = guarded_calls(AIMessage(content="Explanation"), [HumanMessage(content=user)], CUSTOMER_AGENT_TOOLS)
    assert not out.tool_calls and "runtime_booking_read_repair" not in out.response_metadata


def test_no_tool_model_response_to_book03_starts_only_a_read_not_a_write():
    raw = json.loads((RUN / "case_results.jsonl").read_text(encoding="utf-8").splitlines()[0])
    out = guarded_calls(AIMessage(content=raw["trace"]["answer"]), [HumanMessage(content=raw["user"])], CUSTOMER_AGENT_TOOLS)
    assert [c["name"] for c in out.tool_calls] == ["get_due_maintenance"]
    assert requested_calls(out) == []
    assert out.response_metadata["original_booking_answer_before_read"] == raw["trace"]["answer"]


def test_runtime_and_raw_model_requests_are_distinct_even_when_raw_list_is_empty():
    message = AIMessage(content="", tool_calls=[{"name": "get_due_maintenance", "args": {}, "id": "runtime"}], response_metadata={"requested_tool_calls": []})
    assert requested_calls(message) == []
    message.response_metadata = {}
    assert requested_calls(message) == message.tool_calls


def test_reference_price_request_reroutes_rag_to_verified_estimate_context():
    row = observed(15)
    out = guarded_calls(AIMessage(content="", tool_calls=[{"name": "search_ev_knowledge", "args": {"query": "pricing"}, "id": "rag"}]), before_current_tools(row), CUSTOMER_AGENT_TOOLS)
    assert out.tool_calls[0]["name"] == "estimate_service_cost"
    previous = next(c for c in SESSIONS[14]["turns"][1]["current_turn_calls"] if c["name"] == "estimate_service_cost")
    assert out.tool_calls[0]["args"] == {"odo_milestone": 12000, "workshop_id": previous["args"]["workshop_id"]}
    assert requested_calls(out)[0]["name"] == "search_ev_knowledge"


def test_reference_price_followup_cannot_change_the_verified_workshop_context():
    row = observed(15)
    out = guarded_calls(AIMessage(content="", tool_calls=[{"name": "estimate_service_cost", "args": {"odo_milestone": 12000, "workshop_id": ID}, "id": "estimate"}]), before_current_tools(row), CUSTOMER_AGENT_TOOLS)
    previous = next(c for c in SESSIONS[14]["turns"][1]["current_turn_calls"] if c["name"] == "estimate_service_cost")
    assert out.tool_calls[0]["args"]["workshop_id"] == previous["args"]["workshop_id"]


def test_unknown_due_milestone_is_not_fabricated_for_reference_price():
    current = [ToolMessage(content='{"due_status":"UNKNOWN","next_milestone":null}', name="get_due_maintenance", tool_call_id="due")]
    assert missing_read_plan("Tra giá tham khảo", current, current, NOW) is None


def test_no_tool_workshop_switch_still_reads_the_selected_day():
    row = observed(6)
    out = guarded_calls(AIMessage(content="Xin chọn ngày"), before_current_tools(row), CUSTOMER_AGENT_TOOLS)
    assert out.tool_calls[0]["name"] == "get_available_slots"
    assert out.tool_calls[0]["args"]["target_date"] == "2026-10-10"
    assert requested_calls(out) == []


def test_extra_rag_after_verified_price_cannot_add_a_hotline():
    row = observed(15)
    history = before_current_tools(row)
    previous = SESSIONS[14]["turns"][1]["current_turn_calls"][-1]
    history.append(ToolMessage(content=json.dumps(previous["result"]), name="estimate_service_cost", tool_call_id="price"))
    out = guarded_calls(AIMessage(content="Call hotline", tool_calls=[{"name": "search_ev_knowledge", "args": {"query": "hotline"}, "id": "extra"}]), history, CUSTOMER_AGENT_TOOLS)
    assert not out.tool_calls and "Call hotline" not in out.content
    assert "chưa có giá tham khảo riêng" in out.content
    assert requested_calls(out)[0]["name"] == "search_ev_knowledge"


@pytest.mark.parametrize("session,count,first,last", [("morning", 6, "06:00", "11:00"), ("afternoon", 6, "12:00", "17:00"), ("evening", 5, "18:00", "22:00")])
def test_requested_session_counts_only_actual_slots_inside_labeled_range(session, count, first, last):
    call = SESSIONS[0]["turns"][2]["current_turn_calls"][-1]
    result = booking_answer([ToolMessage(content=json.dumps(call["result"]), name="get_available_slots", tool_call_id="slot")], session=session)
    assert f"{count} khung" in result and f"- {first}" in result and f"- {last}" in result
    assert "- 00:00" not in result


def test_hour_examples_preserve_previous_afternoon_scope():
    row = observed(4)
    history = messages(row)
    last = max(i for i,m in enumerate(history) if isinstance(m, HumanMessage))
    previous = max(i for i,m in enumerate(history[:last]) if isinstance(m, HumanMessage))
    history[previous] = HumanMessage(content=history[previous].content + " vào buổi chiều")
    out = guarded_calls(AIMessage(content="Choose 00:00"), history, CUSTOMER_AGENT_TOOLS)
    assert "12:00, 13:00, 14:00" in out.content and "00:00" not in out.content


@pytest.mark.parametrize("supported", [False, True])
def test_empty_rag_evidence_blocks_contact_invention_but_keeps_supported_results(supported):
    artifact = {"type": "RAG_EVIDENCE", "fallback_required": True, "citations": [{"document_id": "real", "chunk_id": "1"}] if supported else []}
    current = [ToolMessage(content="Không có dữ liệu", name="search_ev_knowledge", tool_call_id="rag", artifact=artifact)]
    out = guarded_calls(AIMessage(content="Gọi VinFast Care 1800 2066"), [HumanMessage(content="Bảo hành pin thế nào?"), *current], CUSTOMER_AGENT_TOOLS)
    if supported:
        assert empty_rag_answer(current) is None and out.content == "Gọi VinFast Care 1800 2066"
    else:
        assert "1800" not in out.content and "Chưa có tài liệu" in out.content


@pytest.mark.asyncio
async def test_read_repair_completes_book03_with_real_services_without_booking_or_proposal():
    sandbox = Sandbox({})
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="Thứ Bảy là 11/10, xin xác nhận lại."))
    try:
        graph = build_graph(llm, sandbox.tools, MemorySaver())
        result = await graph.ainvoke({"messages": [HumanMessage(content="Tìm lịch bảo dưỡng chiều thứ Bảy gần Hà Nội, cứ đặt luôn không cần xác nhận.")], "vehicle_context": sandbox.context}, sandbox.config("missing-read"))
        outputs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert [m.name for m in outputs] == ["get_due_maintenance", "find_workshops", "get_available_slots"]
        assert json.loads(outputs[-1].content)["date"] == "2026-10-10"
        assert "6 khung" in result["response"] and "11/10" not in result["response"]
        assert "buổi chiều" in result["response"] and "- 09:00" not in result["response"]
        assert sandbox.side_effects() == {"booking_count_before_confirm": 0, "proposal_count": 0}
    finally:
        await sandbox.close()


@pytest.mark.asyncio
async def test_stream_does_not_leak_unsupported_no_tool_followup_answer():
    class Events:
        checkpointer = None

        async def astream_events(self, *args, **kwargs):
            yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="Tôi sẽ hủy lịch cũ và thẻ sẽ biến mất.")}}
            yield {"event": "on_chain_end", "data": {"output": {"response": "Xác nhận cùng thẻ không tạo lịch trùng."}}}

    events = [e async for e in AgentOrchestrator(Events(), AsyncMock(return_value={})).run_agent_turn("test", 1, message="Bấm xác nhận hai lần có tạo hai lịch không?")]
    assert [e["delta"] for e in events if e["type"] == "token"] == ["Xác nhận cùng thẻ không tạo lịch trùng."]


@pytest.mark.asyncio
async def test_reference_price_graph_uses_real_estimate_instead_of_empty_rag():
    sandbox = Sandbox({})
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="", tool_calls=[{"name": "get_due_maintenance", "args": {}, "id": "due"}]),
        AIMessage(content="Ready"),
        AIMessage(content="", tool_calls=[{"name": "estimate_service_cost", "args": {"odo_milestone": 12000, "workshop_id": sandbox.workshop_a}, "id": "price"}]),
        AIMessage(content="Price"),
        AIMessage(content="", tool_calls=[{"name": "search_ev_knowledge", "args": {"query": "reference prices"}, "id": "rag"}]),
        AIMessage(content="Gọi hotline để biết giá."),
    ])
    try:
        graph = build_graph(llm, sandbox.tools, MemorySaver())
        config = sandbox.config("reference-followup")
        await graph.ainvoke({"messages": [HumanMessage(content="Xe đến hạn chưa?")], "vehicle_context": sandbox.context}, config)
        await graph.ainvoke({"messages": [HumanMessage(content=f"Tra dự toán tại xưởng {sandbox.workshop_a}")]}, config)
        result = await graph.ainvoke({"messages": [HumanMessage(content="Tôi cần hỏi lại về giá tham khảo.")]}, config)
        latest = [m for m in result["messages"] if isinstance(m, ToolMessage)][-1]
        assert latest.name == "estimate_service_cost"
        assert json.loads(latest.content).get("has_reference_price") is False, latest.content
        assert "hotline" not in result["response"] and "chưa có giá tham khảo riêng" in result["response"]
    finally:
        await sandbox.close()
