"""A named workshop switch must read that workshop's slots before a proposal."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents import prompts
from src.agents.guardrails import guarded_calls, tool_failure
from src.agents.tools import CUSTOMER_AGENT_TOOLS

NEW = "c40f7f12-e5a2-4d52-a2f4-89aa6b7aa0e2"
OLD = "e18893e3-b098-4f9a-b43c-7d36a521a169"
DAY = "2026-10-09"
USER = "Tôi chọn xưởng EV Care Hà Nội, ngày 09/10/2026 lúc 14:00. Hãy tìm xưởng, kiểm tra giờ trống và tạo thẻ đề xuất bảo dưỡng để tôi xác nhận trên giao diện."


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(prompts, "now_vn", lambda: datetime(2026, 10, 9, 9, tzinfo=timezone(timedelta(hours=7))))


def tool(name, value, status="success"):
    return ToolMessage(name=name, tool_call_id=name, content=json.dumps(value), status=status)


def found(entries=None):
    return tool("find_workshops", {"workshops": entries if entries is not None else [
        {"workshop_id": NEW, "name": "EV Care Hà Nội"},
    ]})


def slots(workshop=OLD, day=DAY, available=True):
    return tool("get_available_slots", {"workshop_id": workshop, "date": day,
        "slots": [{"time_slot": "14:00:00", "available": available, "remaining": 3 if available else 0}]})


def proposal(workshop=NEW):
    return AIMessage(content="", tool_calls=[{"name": "propose_booking", "args": {
        "workshop_id": workshop, "booking_date": DAY, "time_slot": "14:00", "odo_milestone": 10000,
    }, "id": "model-proposal"}])


def messages(user=USER):
    return [HumanMessage(content=user), tool("get_due_maintenance", {"due_status": "OVERDUE"}), found(), slots()]


def test_observed_old_workshop_read_is_recovered_as_read_of_named_workshop():
    raw = proposal()
    output = guarded_calls(raw, messages(), CUSTOMER_AGENT_TOOLS)
    assert len(output.tool_calls) == 1
    assert output.tool_calls[0]["name"] == "get_available_slots"
    assert output.tool_calls[0]["args"] == {"workshop_id": NEW, "target_date": DAY}
    assert output.response_metadata["requested_tool_calls"] == raw.tool_calls
    assert output.response_metadata["runtime_booking_read_repair"] == "selected_workshop_slot_prerequisite"


def test_proposal_still_requires_verified_available_slot_at_selected_workshop():
    raw = proposal()
    output = guarded_calls(raw, messages() + [slots(NEW)], CUSTOMER_AGENT_TOOLS)
    assert output.tool_calls == raw.tool_calls
    assert "runtime_booking_read_repair" not in output.response_metadata


def test_full_slot_does_not_trigger_repeated_reads_or_proposal():
    output = guarded_calls(proposal(), messages() + [slots(NEW, available=False)], CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls
    assert "kiểm tra lại đúng xưởng" in output.content


@pytest.mark.parametrize("user", [
    USER.replace("Tôi chọn", "Nếu tôi chọn"),
    USER.replace("Tôi chọn", "Tôi không chọn"),
    USER.replace("EV Care Hà Nội,", "EV Care Hà Nội hoặc VinFast Thăng Long,"),
    USER.replace("EV Care Hà Nội,", '"EV Care Hà Nội",'),
    USER.replace("14:00", "15:00"),
])
def test_ambiguous_negated_or_mismatched_selection_does_not_authorize_recovery(user):
    output = guarded_calls(proposal(), messages(user), CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls


def test_model_workshop_not_selected_by_user_is_not_repaired():
    # Multiple matches make the name ambiguous, even though the model supplied a UUID.
    current = messages()
    current[2] = found([{"workshop_id": NEW, "name": "EV Care Hà Nội"},
                        {"workshop_id": OLD, "name": "EV Care Hà Nội"}])
    output = guarded_calls(proposal(), current, CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls


def test_recovery_uses_user_selected_day_and_keeps_raw_model_day():
    raw = proposal()
    output = guarded_calls(raw, messages(USER.replace("09/10/2026", "10/10/2026")), CUSTOMER_AGENT_TOOLS)
    assert output.tool_calls[0]["name"] == "get_available_slots"
    assert output.tool_calls[0]["args"] == {"workshop_id": NEW, "target_date": "2026-10-10"}
    assert output.response_metadata["requested_tool_calls"][0]["args"]["booking_date"] == DAY


def test_newest_failed_lookup_invalidates_earlier_success():
    current = messages() + [tool("find_workshops", {"status": "ERROR"}, "error")]
    assert not guarded_calls(proposal(), current, CUSTOMER_AGENT_TOOLS).tool_calls


def test_historical_lookup_cannot_bind_new_named_choice():
    history = [HumanMessage(content="Tìm xưởng"), found(), AIMessage(content="Đã tra")]
    current = messages()
    del current[2]
    assert not guarded_calls(proposal(), history + current, CUSTOMER_AGENT_TOOLS).tool_calls


def test_lookup_of_another_name_cannot_bind_proposal_id():
    current = messages()
    current[2] = found([{"workshop_id": NEW, "name": "VinFast Thăng Long"}])
    assert not guarded_calls(proposal(), current, CUSTOMER_AGENT_TOOLS).tool_calls


def test_open_booking_error_explains_next_action_without_claiming_new_booking():
    answer = tool_failure([tool("propose_booking", {"status": "ERROR", "error_code": "OPEN_BOOKING_EXISTS"}, "error")])
    assert "Xe đang có một lịch hẹn" in answer and "Lịch hẹn" in answer
    assert "Chưa có lịch hẹn mới" in answer


@pytest.mark.asyncio
async def test_real_graph_switches_slot_read_and_creates_one_proposal_without_booking():
    from unittest.mock import AsyncMock, Mock

    from langgraph.checkpoint.memory import MemorySaver

    from src.agents.graph import build_graph
    from tests.evaluation_v2.sandbox import Sandbox

    sandbox = Sandbox({})
    model = Mock()
    model.bind_tools.return_value = model

    def call(name, args, call_id):
        return {"name": name, "args": args, "id": call_id}

    proposed = {"workshop_id": sandbox.workshop_b, "booking_date": DAY, "time_slot": "14:00"}
    model.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="", tool_calls=[call("get_due_maintenance", {}, "due")]),
        AIMessage(content="", tool_calls=[
            call("find_workshops", {"area_or_address": "Hà Nội", "limit": 1}, "find"),
            call("get_available_slots", {"workshop_id": sandbox.workshop_a, "target_date": DAY}, "old-slots"),
        ]),
        AIMessage(content="", tool_calls=[call("propose_booking", proposed, "before-read")]),
        AIMessage(content="", tool_calls=[call("propose_booking", proposed, "after-read")]),
        AIMessage(content="Xem thẻ đề xuất."),
    ])
    try:
        graph = build_graph(model, sandbox.tools, MemorySaver())
        result = await graph.ainvoke({"messages": [HumanMessage(content=USER.replace("EV Care Hà Nội", "VinFast Ha Dong"))],
                                     "vehicle_context": sandbox.context}, sandbox.config("named-workshop-recovery"))
        reads = [json.loads(m.content) for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "get_available_slots"]
        assert [r["workshop_id"] for r in reads] == [sandbox.workshop_a, sandbox.workshop_b]
        cards = [m.artifact for m in result["messages"] if isinstance(m, ToolMessage) and isinstance(m.artifact, dict) and m.artifact.get("type") == "BOOKING_PROPOSAL"]
        assert len(cards) == 1 and cards[0]["primary"]["workshopId"] == sandbox.workshop_b
        assert cards[0]["primary"]["date"] == DAY and cards[0]["primary"]["timeSlot"] == "14:00"
        assert sandbox.side_effects() == {"booking_count_before_confirm": 0, "proposal_count": 1}
    finally:
        await sandbox.close()
