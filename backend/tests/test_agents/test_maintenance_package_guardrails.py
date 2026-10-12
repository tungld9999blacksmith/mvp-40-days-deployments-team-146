"""Prerequisite regression tests for optimal maintenance package advice."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.business_grounding import business_answer
from src.agents.guardrails import guarded_calls
from src.agents.tools import CUSTOMER_AGENT_TOOLS


def _call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{
            "name": "recommend_maintenance_packages",
            "args": {"budget_vnd": 1_000_000, "priority": "BALANCED"},
            "id": "package",
        }],
    )


def _result(name: str, data: dict) -> ToolMessage:
    return ToolMessage(content=json.dumps(data), name=name, tool_call_id=name)


DUE = {
    "due_status": "DUE_SOON",
    "due_reason": "KM",
    "remaining_km": 500,
    "remaining_days": 30,
    "next_milestone": {
        "odo_milestone_km": 12_000,
        "month_milestone": 12,
        "items": [{"item_code": "BRAKE_INSPECTION", "item_name": "Kiểm tra phanh"}],
    },
}


def test_package_request_first_reads_due_maintenance():
    output = guarded_calls(_call(), [HumanMessage(content="Gợi ý gói tối ưu")], CUSTOMER_AGENT_TOOLS)
    assert [call["name"] for call in output.tool_calls] == ["get_due_maintenance"]


def test_package_request_then_reads_service_history():
    messages = [HumanMessage(content="Gợi ý gói tối ưu"), _result("get_due_maintenance", DUE)]
    output = guarded_calls(_call(), messages, CUSTOMER_AGENT_TOOLS)
    assert [call["name"] for call in output.tool_calls] == ["get_service_history"]


def test_package_optimizer_runs_after_due_and_history_without_duplicate_estimate():
    messages = [
        HumanMessage(content="Gợi ý gói tối ưu"),
        _result("get_due_maintenance", DUE),
        _result("get_service_history", {"status": "READY", "records": []}),
    ]
    output = guarded_calls(_call(), messages, CUSTOMER_AGENT_TOOLS)
    assert [call["name"] for call in output.tool_calls] == ["recommend_maintenance_packages"]


def test_package_answer_is_rendered_from_backend_result_not_llm_numbers():
    packages = {
        "status": "READY",
        "has_reference_price": True,
        "recommended_package_code": "BALANCED",
        "disclaimer": "Xưởng xác nhận giá cuối cùng.",
        "packages": [
            {
                "package_code": "ESSENTIAL",
                "name": "Thiết yếu",
                "items": [{"item_name": "Kiểm tra phanh"}],
                "estimated_total": "350000",
                "estimated_duration_minutes": 30,
                "constraint_status": "FITS",
            }
        ],
    }

    answer = business_answer([_result("recommend_maintenance_packages", packages)])

    assert "350,000 VND" in answer
    assert "BALANCED" in answer
    assert "giá tham khảo" in answer


def test_due_answer_never_invents_optimizer_tiers():
    answer = business_answer([_result("get_due_maintenance", DUE)])

    assert "Kiểm tra phanh" in answer
    assert "REQUIRED" not in answer
    assert "RECOMMENDED" not in answer
    assert "OPTIONAL" not in answer


def test_guardrail_replaces_llm_tiers_before_optimizer_runs():
    messages = [HumanMessage(content="Xe cần làm gì?"), _result("get_due_maintenance", DUE)]
    response = AIMessage(content="REQUIRED: Kiểm tra phanh. OPTIONAL: vệ sinh.")

    output = guarded_calls(response, messages, CUSTOMER_AGENT_TOOLS)

    assert "REQUIRED" not in output.content
    assert "OPTIONAL" not in output.content
    assert output.response_metadata["premature_package_tiers_rejected"] is True
