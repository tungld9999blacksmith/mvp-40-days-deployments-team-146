# Regression: ISSUE-007 — answers about an existing booking's price lines were replaced by
# "Tôi chưa có kết quả xác nhận đặt lịch…" because they mention the booking code (EVC-…)
# Found by /qa on 2026-10-10
# Report: .gstack/qa-reports/run-20261010T080327Z/qa-report-localhost-2026-10-10.md
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agents.guardrails import guarded_calls
from src.agents.tools import CUSTOMER_AGENT_TOOLS

LINES = {
    "booking": {"booking_id": "b1", "booking_code": "EVC-2BECBE9F", "status": "IN_PROGRESS", "pricing_flow": "two_tier"},
    "package": [],
    "pending_decisions": [],
    "current_total": 550000.0,
    "total_if_all_approved": 550000.0,
}
CANNED = "Tôi chưa có kết quả xác nhận đặt lịch"


def _turn(answer: str) -> str:
    messages = [
        HumanMessage(content="Xưởng đề xuất gì thêm cho xe tôi?"),
        ToolMessage(content=json.dumps(LINES, ensure_ascii=False), name="get_booking_lines", tool_call_id="read"),
    ]
    return str(guarded_calls(AIMessage(content=answer), messages, CUSTOMER_AGENT_TOOLS).content)


def test_answer_about_the_booking_just_read_is_kept():
    answer = "Lịch hẹn EVC-2BECBE9F: bạn đã đồng ý Kiểm tra hệ thống treo 250.000 ₫. Tổng hiện tại 550.000 ₫."
    assert _turn(answer) == answer


def test_an_invented_booking_is_still_rejected():
    assert _turn("Tôi đã đặt lịch cho bạn, mã EVC-9999AAAA.").startswith(CANNED)
