"""Observed booking errors: counts, current-user read IDs and proposal scope."""
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.booking_grounding import booking_answer, explicit_workshop_id
from src.agents.graph import build_graph
from src.agents.guardrails import guarded_calls
from src.agents.orchestrator import AgentOrchestrator
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from tests.evaluation_v2.sandbox import Sandbox

ROOT = Path(__file__).resolve().parents[3]
SESSIONS = json.loads((ROOT / "eval/results/agent_v2_1_business_sessions_mistral_20261008_03/comparison.json").read_text(encoding="utf-8"))[0]["sessions"]
ID = "11111111-2222-3333-4444-555555555555"
OTHER = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def message(call):
    return ToolMessage(content=json.dumps(call["result"]), name=call["name"], tool_call_id="read", artifact=call.get("artifact"))


def observed(session, turn):
    return deepcopy(next(s for s in SESSIONS if s["session_id"] == session)["turns"][turn - 1])


@pytest.mark.parametrize("user", [f"Tra dự toán xưởng {ID}.", f"xem lich xuong {ID}", f"Xưởng ID: {ID.upper()}", f"Hãy xem lịch xưởng {ID}"])
def test_direct_current_user_workshop_id(user):
    assert explicit_workshop_id(user) == ID


@pytest.mark.parametrize("user", [
    f"Xưởng {ID} hoặc xưởng {OTHER}", f"Không tra xưởng {ID}", f"Đừng xem xưởng {ID}",
    f"Nếu tra xưởng {ID} thì sao?", f"Tài liệu ghi xưởng {ID}", f"Ví dụ xưởng {ID}",
    f"Xe {ID}", f"Xưởng {ID} của xe {OTHER}", f"Xưởng {ID}-extra", "Xưởng not-a-uuid", "Đặt lịch đó.",
    f"Chưa tra xưởng {ID}", f'Đoạn "xưởng {ID}" nghĩa là gì?',
])
def test_read_id_is_not_guessed_from_ambiguous_negated_or_document_text(user):
    assert explicit_workshop_id(user) is None


@pytest.mark.parametrize("name", ["get_available_slots", "estimate_service_cost"])
def test_read_uuid_repair_keeps_raw_request_for_scoring(name):
    args = {"workshop_id": "copied-wrong"}
    args.update({"target_date": "2026-10-10"} if name == "get_available_slots" else {"odo_milestone": 12000})
    original = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "read"}])
    due = ToolMessage(content='{"due_status":"OVERDUE"}', name="get_due_maintenance", tool_call_id="due")
    answer = guarded_calls(original, [HumanMessage(content=f"Tra xưởng {ID} ngày 2026-10-10"), due], CUSTOMER_AGENT_TOOLS)
    assert answer.tool_calls[0]["args"]["workshop_id"] == ID
    assert answer.response_metadata["requested_tool_calls"][0]["args"]["workshop_id"] == "copied-wrong"
    assert "workshop_id_from_explicit_user" in answer.response_metadata["normalized_fields"]


def test_proposal_uuid_is_not_repaired_and_history_cannot_bind_a_new_read():
    response = AIMessage(content="", tool_calls=[{"name": "propose_booking", "args": {"workshop_id": "wrong", "booking_date": "2026-10-10", "time_slot": "14:00"}, "id": "proposal"}])
    output = guarded_calls(response, [HumanMessage(content=f"Đặt 14:00 tại xưởng {ID}")], CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls and output.response_metadata["argument_errors"]
    read = AIMessage(content="", tool_calls=[{"name": "get_available_slots", "args": {"workshop_id": "wrong", "target_date": "2026-10-10"}, "id": "read"}])
    output = guarded_calls(read, [HumanMessage(content=f"Xưởng {ID}"), AIMessage(content="old"), HumanMessage(content="Xem lịch giúp tôi")], CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls and output.response_metadata["argument_errors"]


def test_observed_24_slots_claim_is_replaced_with_23_verified_slots():
    row = observed("SESSION-01", 3)
    output = guarded_calls(AIMessage(content=row["answer"]), [HumanMessage(content=row["user"]), *map(message, row["current_turn_calls"])], CUSTOMER_AGENT_TOOLS)
    assert "23 khung giờ khả dụng" in output.content and "24 khung" not in output.content
    assert "00:00: còn 4 chỗ" in output.content and "22:00: còn 4 chỗ" in output.content
    assert "23:00" not in output.content
    assert output.response_metadata["original_booking_answer"] == row["answer"]


def test_non_contiguous_mixed_capacity_slots_do_not_become_an_invented_range():
    call = {"name": "get_available_slots", "result": {"workshop_id": ID, "date": "2026-10-10", "slots": [
        {"time_slot": "08:00:00", "available": True, "remaining": 2},
        {"time_slot": "09:00:00", "available": False, "remaining": 0},
        {"time_slot": "14:30:00", "available": True, "remaining": 1},
    ]}}
    answer = booking_answer([message(call)])
    assert "2 khung giờ khả dụng" in answer
    assert "08:00: còn 2 chỗ" in answer and "14:30: còn 1 chỗ" in answer
    assert "không khả dụng: 09:00" in answer
    assert "mỗi giờ" not in answer


@pytest.mark.parametrize("slots,phrase", [([], "0 khung giờ khả dụng"), ([{"time_slot": "08:00", "available": False, "remaining": 0}], "không khả dụng: 08:00")])
def test_empty_and_full_availability_do_not_offer_a_booking(slots, phrase):
    answer = booking_answer([message({"name": "get_available_slots", "result": {"workshop_id": ID, "date": "2026-10-10", "slots": slots}})])
    assert phrase in answer
    assert "Bạn hãy chọn" not in answer


@pytest.mark.parametrize("change", ["negative", "duplicate", "invalid_time", "invalid_bool"])
def test_malformed_slot_result_fails_closed(change):
    row = observed("SESSION-01", 3)
    slots = row["current_turn_calls"][0]["result"]["slots"]
    if change == "negative":
        slots[0]["remaining"] = -1
    if change == "duplicate":
        slots.append(deepcopy(slots[0]))
    if change == "invalid_time":
        slots[0]["time_slot"] = "25:00"
    if change == "invalid_bool":
        slots[0]["available"] = "true"
    assert "Chưa có dữ liệu" in booking_answer(list(map(message, row["current_turn_calls"])))


def test_observed_proposal_email_promise_uses_matching_card_without_email_claim():
    row = observed("SESSION-01", 4)
    tool_message = message(row["current_turn_calls"][0])
    output = guarded_calls(AIMessage(content=row["answer"]), [HumanMessage(content=row["user"]), tool_message], CUSTOMER_AGENT_TOOLS)
    assert "14:00" in output.content and "10/10/2026" in output.content
    assert 'bấm "Xác nhận đặt lịch"' in output.content
    assert "email" not in output.content.casefold() and "[**Xác nhận" not in output.content
    assert "chưa giữ chỗ" in output.content
    assert tool_message.artifact == row["current_turn_calls"][0]["artifact"]
    assert output.response_metadata["original_booking_answer"] == row["answer"]


@pytest.mark.parametrize("failure", ["missing_card", "id_mismatch", "new_error"])
def test_missing_or_mismatched_proposal_card_and_new_error_cannot_prove_success(failure):
    row = observed("SESSION-01", 4)
    tool_message = message(row["current_turn_calls"][0])
    if failure == "missing_card":
        tool_message.artifact = None
    if failure == "id_mismatch":
        tool_message.artifact["proposalId"] = OTHER
    messages = [tool_message]
    if failure == "new_error":
        messages.append(ToolMessage(content='{"status":"ERROR"}', name="propose_booking", tool_call_id="failure", status="error"))
    assert "Chưa có dữ liệu" in booking_answer(messages)


def test_old_slot_result_and_unsupported_mixed_tool_do_not_replace_current_answer():
    row = observed("SESSION-01", 3)
    response = AIMessage(content="Please clarify")
    output = guarded_calls(response, [HumanMessage(content="old"), message(row["current_turn_calls"][0]), HumanMessage(content="new")], CUSTOMER_AGENT_TOOLS)
    assert output.content == response.content
    assert booking_answer([message(row["current_turn_calls"][0]), ToolMessage(content="{}", name="search_ev_knowledge", tool_call_id="rag")]) is None


@pytest.mark.asyncio
async def test_real_graph_repairs_explicit_read_id_and_creates_only_a_proposal():
    sandbox = Sandbox({})
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="", tool_calls=[{"name": "get_available_slots", "args": {"workshop_id": "malformed", "target_date": "2026-10-10"}, "id": "slots"}]),
        AIMessage(content="24 slots"),
        AIMessage(content="", tool_calls=[{"name": "propose_booking", "args": {"workshop_id": sandbox.workshop_a, "booking_date": "2026-10-10", "time_slot": "14:00"}, "id": "p1"}]),
        AIMessage(content="", tool_calls=[{"name": "propose_booking", "args": {"workshop_id": sandbox.workshop_a, "booking_date": "2026-10-10", "time_slot": "14:00"}, "id": "p2"}]),
        AIMessage(content="Thẻ đã tạo, bạn sẽ nhận email sau xác nhận."),
    ])
    try:
        before = sandbox.reminder_state()
        graph = build_graph(llm, sandbox.tools, MemorySaver())
        config = sandbox.config("booking-grounding")
        first = await graph.ainvoke({"messages": [HumanMessage(content=f"Xem lịch 2026-10-10 tại xưởng {sandbox.workshop_a}.")], "vehicle_context": sandbox.context}, config)
        assert "23 khung giờ khả dụng" in first["response"]
        second = await graph.ainvoke({"messages": [HumanMessage(content="Tôi chọn 14:00; tạo thẻ đề xuất.")]}, config)
        assert "email" not in second["response"].casefold()
        assert sandbox.side_effects() == {"booking_count_before_confirm": 0, "proposal_count": 1}
        assert sandbox.reminder_state() == before
        assert any(isinstance(m, ToolMessage) and isinstance(m.artifact, dict) and m.artifact.get("type") == "BOOKING_PROPOSAL" for m in second["messages"])
    finally:
        await sandbox.close()


@pytest.mark.asyncio
async def test_booking_raw_tokens_after_tool_never_reach_client():
    class Events:
        checkpointer = None

        async def astream_events(self, *args, **kwargs):
            yield {"event": "on_tool_start", "name": "propose_booking"}
            yield {"event": "on_chat_model_stream", "data": {"chunk": AIMessageChunk(content="You will receive booking email.")}}
            yield {"event": "on_chain_end", "data": {"output": {"response": "Lịch chưa được đặt. Bấm xác nhận trên thẻ."}}}

    runner = AgentOrchestrator(Events(), AsyncMock(return_value={}))
    events = [event async for event in runner.run_agent_turn("test", 1, message="proposal")]
    tokens = [event["delta"] for event in events if event["type"] == "token"]
    assert tokens == [events[-1]["message_data"]["content"]]
    assert "email" not in tokens[0]
