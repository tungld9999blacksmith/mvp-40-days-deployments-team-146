"""Frozen schema failures: derive authorized reads, never trust invalid IDs."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.booking_policy import guarded_booking_turn, invalid_booking_time
from src.agents.contracts import validate_arguments
from src.agents.graph import build_graph
from src.agents.guardrails import guarded_calls
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from tests.evaluation_v2.runner import requested_calls
from tests.evaluation_v2.sandbox import NOW, Sandbox

ROOT = Path(__file__).resolve().parents[3]
FROZEN = ROOT / "eval/results/agent_v2_1_booking_followup_sessions_mistral_20261008_06/case_results.jsonl"
# CI excludes local result folders. Preserve the observed public-schema failure
# as an explicit portable fixture while using the original record when present.
ROW = json.loads(FROZEN.read_text(encoding="utf-8").splitlines()[0]) if FROZEN.exists() else {
    "user": "Tìm lịch bảo dưỡng chiều thứ Bảy gần Hà Nội, cứ đặt luôn không cần xác nhận.",
    "trace": {"requested_tool_calls": [{"name": "get_due_maintenance", "args": {"odo_milestone": None, "workshop_id": None}, "id": "786DYRBUH", "type": "tool_call"}]},
}
ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture(autouse=True)
def evaluation_clock():
    with patch("src.agents.prompts.now_vn", return_value=NOW):
        yield


def malformed_response():
    raw = ROW["trace"]["requested_tool_calls"][0]
    return AIMessage(content="", id="provider-response", tool_calls=[raw], usage_metadata={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})


def test_frozen_book03_rejects_raw_schema_but_derives_a_fresh_authenticated_read():
    response = malformed_response()
    output = guarded_calls(response, [HumanMessage(content=ROW["user"])], CUSTOMER_AGENT_TOOLS)
    assert [(c["name"], c["args"]) for c in output.tool_calls] == [("get_due_maintenance", {})]
    assert requested_calls(output) == response.tool_calls
    assert output.response_metadata["argument_errors_before_booking_read_repair"]
    assert output.id == response.id and output.usage_metadata == response.usage_metadata
    due = next(t for t in CUSTOMER_AGENT_TOOLS if t.name == "get_due_maintenance")
    assert validate_arguments(due, response.tool_calls[0]["args"])
    assert not validate_arguments(due, output.tool_calls[0]["args"])


@pytest.mark.parametrize("user", [
    "Nếu tìm lịch bảo dưỡng chiều thứ Bảy thì sao?", "Đừng tìm lịch bảo dưỡng thứ Bảy.",
    "Tìm lịch bảo dưỡng thứ Bảy hoặc Chủ Nhật.", 'Tài liệu ghi "tìm lịch bảo dưỡng thứ Bảy".',
    "Tìm lịch bảo dưỡng hôm qua.", "Xe tôi có những công cụ nào?",
])
def test_invalid_model_arguments_do_not_authorize_ambiguous_negated_or_past_reads(user):
    output = guarded_calls(malformed_response(), [HumanMessage(content=user)], CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls and output.response_metadata["argument_errors"]
    assert "runtime_booking_read_repair" not in output.response_metadata


def test_invalid_write_mixed_with_read_cannot_be_repaired_into_an_action():
    response = malformed_response()
    response.tool_calls.append({"name": "propose_booking", "args": {"workshop_id": ID}, "id": "write", "type": "tool_call"})
    output = guarded_calls(response, [HumanMessage(content=ROW["user"])], CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls and output.response_metadata["argument_errors"]


def test_failed_current_maintenance_is_not_retried_by_schema_repair():
    failure = ToolMessage(content='{"status":"ERROR"}', name="get_due_maintenance", tool_call_id="failed", status="error")
    output = guarded_calls(malformed_response(), [HumanMessage(content=ROW["user"]), failure], CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls and "runtime_booking_read_repair" not in output.response_metadata


@pytest.mark.parametrize("user,time", [("Tôi muốn đặt 25:00 ngày 2026-10-10.", "25:00"), ("Tôi chọn 14:60.", "14:60"), ("Tạo thẻ lúc 24h.", "24:00")])
def test_invalid_hour_explains_user_value_and_blocks_even_malformed_model_tools(user, time):
    output = guarded_calls(malformed_response(), [HumanMessage(content=user)], CUSTOMER_AGENT_TOOLS)
    assert not output.tool_calls and f"Giờ {time} không hợp lệ" in output.content
    assert requested_calls(output) == malformed_response().tool_calls
    assert guarded_booking_turn([HumanMessage(content=user)])


@pytest.mark.parametrize("user", ["Tôi chọn 14:00.", "Tôi chọn 25:00 hoặc 14:00.", "Nếu chọn 25:00 thì sao?", "Đừng đặt 25:00.", 'Tài liệu ghi "25:00".', "25:00 là ví dụ."])
def test_invalid_hour_policy_does_not_override_valid_choices_or_quoted_questions(user):
    assert invalid_booking_time(user) is None


@pytest.mark.asyncio
async def test_real_services_use_selected_vehicle_not_model_vehicle_or_workshop_identifiers():
    sandbox = Sandbox({})
    model = Mock()
    model.bind_tools.return_value = model

    async def respond(messages):
        last = messages[-1]
        if isinstance(last, HumanMessage):
            return malformed_response()
        if isinstance(last, ToolMessage) and last.name == "get_due_maintenance":
            return AIMessage(content="", tool_calls=[{"name": "find_workshops", "args": {"limit": 1, "area_or_address": "Hà Nội"}, "id": "find"}])
        if isinstance(last, ToolMessage) and last.name == "find_workshops":
            return AIMessage(content="", tool_calls=[{"name": "get_available_slots", "args": {"workshop_id": sandbox.workshop_a, "target_date": "2026-10-10"}, "id": "slots"}])
        return AIMessage(content="Sai ngày 11/10; 24 giờ trống.")

    model.ainvoke = AsyncMock(side_effect=respond)
    try:
        graph = build_graph(model, sandbox.tools, MemorySaver())
        result = await graph.ainvoke({"messages": [HumanMessage(content=ROW["user"])], "vehicle_context": sandbox.context}, sandbox.config("schema-recovery"))
        due = next(json.loads(m.content) for m in result["messages"] if isinstance(m, ToolMessage) and m.name == "get_due_maintenance")
        assert due["user_vehicle_id"] == str(sandbox.vehicle_id)
        assert "10/10/2026" in result["response"] and "6 khung giờ khả dụng" in result["response"]
        assert sandbox.side_effects() == {"booking_count_before_confirm": 0, "proposal_count": 0}
    finally:
        await sandbox.close()
