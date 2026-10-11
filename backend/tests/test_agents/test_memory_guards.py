"""Regressions observed in the paid production-prompt memory evaluation."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

from src.agents.guardrails import guarded_calls
from src.agents.memory_context import build_memory_context
from src.agents.memory_guard import verified_memory_response
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from src.config import Settings
from src.modules.agent_memory.preferences import Window


def request(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": "test", "type": "tool_call"}])


def test_memory_tool_exposes_period_enum_and_parses_typed_value():
    memory = next(t for t in CUSTOMER_AGENT_TOOLS if t.name == "remember_preference")
    with pytest.raises(ValidationError):
        memory.args_schema.model_validate({"key": "preferred_service_window", "value": {"day": "saturday", "period": "any"}})
    parsed = memory.args_schema.model_validate({"key": "preferred_service_window", "value": {"day": "saturday", "period": "afternoon"}})
    assert isinstance(parsed.value, Window)


def test_format_only_request_does_not_insert_maintenance_prerequisite():
    question = "Lần này tôi chỉ muốn xem tổng tiền. Chỉ nhắc định dạng cho lần này, không tra giá hay ghi nhớ lại."
    response = guarded_calls(request("estimate_service_cost", odo_milestone=12000), [HumanMessage(content=question)], CUSTOMER_AGENT_TOOLS)
    assert response.tool_calls == []
    assert "tổng tiền" in response.content and "Chưa lưu" in response.content


@pytest.mark.parametrize("question", [
    "Chỉ nhắc sở thích của tôi và tra dự toán mốc 12000 giúp tôi.",
    "Chỉ nhắc sở thích của tôi. Hãy tra dự toán mốc 12000 giúp tôi.",
    "Tra dự toán mốc 12000 rồi chỉ nhắc lựa chọn hiện tại của tôi.",
])
def test_mixed_preference_and_business_request_still_requires_maintenance(question):
    response = guarded_calls(request("estimate_service_cost", odo_milestone=12000), [HumanMessage(content=question)], CUSTOMER_AGENT_TOOLS)
    assert response.tool_calls[0]["name"] == "get_due_maintenance"


@pytest.mark.parametrize("question", ["Tôi thích sáng thứ Hai cho lần này.", "Đừng ghi nhớ sáng thứ Hai."])
def test_one_time_and_negated_requests_cannot_call_remember(question):
    response = guarded_calls(request("remember_preference", key="preferred_service_window", value={"day": "monday", "period": "morning"}), [HumanMessage(content=question)], CUSTOMER_AGENT_TOOLS)
    assert response.tool_calls == []


def test_explicit_consent_retains_remember_tool():
    response = guarded_calls(request("remember_preference", key="preferred_service_window", value={"day": "saturday", "period": "afternoon"}), [HumanMessage(content="Hãy nhớ tôi thích chiều thứ Bảy.")], CUSTOMER_AGENT_TOOLS)
    assert response.tool_calls[0]["name"] == "remember_preference"


@pytest.mark.parametrize("answer", ["Tôi đã ghi nhớ sở thích sáng thứ Hai.", "Tôi đã lưu sở thích sáng thứ Hai."])
def test_nonconsented_reply_cannot_claim_a_memory_save(answer):
    response = verified_memory_response(AIMessage(content=answer), [HumanMessage(content="Đừng ghi nhớ sở thích mới.")])
    assert "chưa lưu" in response.content


def test_empty_recall_is_explicit_data_in_context():
    result = build_memory_context([HumanMessage(content="Bạn nhớ sở thích nào?")], "System", Settings(_env_file=None), preferences=[])
    assert '"preferences": []' in result.messages[1].content
