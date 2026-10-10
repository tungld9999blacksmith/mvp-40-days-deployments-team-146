"""State and answer regressions found during development source review."""
import json
from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.graph import build_graph
from src.agents.guardrails import guarded_calls, reminder_change_claim
from src.agents.tools import CUSTOMER_AGENT_TOOLS
from tests.evaluation_v2.dataset_v2_1 import STATE_FIELDS, build_reviewed_dataset
from tests.evaluation_v2.runner import current_turn_calls
from tests.evaluation_v2.sandbox import Sandbox
from tests.evaluation_v2.scoring import score_case


@pytest.mark.parametrize("answer,claimed", [
    ("Tôi đã cập nhật cài đặt nhắc và bật Email.", True),
    ("**Đã lưu cài đặt.**", True),
    ("Toi da bat email nhac bao duong.", True),
    ("Cài đặt nhắc đã được cập nhật.", True),
    ("Tôi bật Email xong rồi.", True),
    ("Tôi chưa cập nhật cài đặt.", False),
    ("Email đã bật trong cài đặt hiện tại.", False),
    ("Nếu tôi đã lưu thì trạng thái sẽ thay đổi.", False),
    ("Tôi sẽ bật Email khi bạn yêu cầu.", False),
])
def test_new_reminder_change_claim_is_distinct_from_existing_or_future_state(answer, claimed):
    assert reminder_change_claim(answer) is claimed


def test_read_only_reminder_cannot_claim_a_saved_change():
    original = "Tôi đã cập nhật, bật nhắc bảo dưỡng và bật Email cho bạn."
    messages = [HumanMessage(content="Đọc cài đặt, không thay đổi."), message("get_reminder_settings", settings(enabled=False))]
    response = guarded_calls(AIMessage(content=original), messages, CUSTOMER_AGENT_TOOLS)
    assert "Chưa lưu thay đổi" in response.content
    assert "Nhắc bảo dưỡng: Tắt" in response.content and "Email: Tắt" in response.content
    assert response.response_metadata["original_reminder_answer"] == original
    assert response.response_metadata["unconfirmed_reminder_change_rejected"] is True


@pytest.mark.parametrize("history", [[], [("get_reminder_settings", {"channels": None})], [("get_reminder_context", {})]])
def test_missing_or_incomplete_settings_cannot_support_update_claim(history):
    response = guarded_calls(AIMessage(content="Đã bật Email."), [HumanMessage(content="Bật Email."), *(message(name, data) for name, data in history)], CUSTOMER_AGENT_TOOLS)
    assert "Chưa có kết quả lưu" in response.content
    assert response.response_metadata["unconfirmed_reminder_change_rejected"]


def test_failed_and_previous_turn_updates_cannot_support_a_new_change():
    prior = [HumanMessage(content="Bật Email."), message("update_reminder_settings", settings(email=True)), HumanMessage(content="Tắt Email.")]
    failed = ToolMessage(name="update_reminder_settings", tool_call_id="failed", content=json.dumps({"status": "ERROR"}))
    reply = AIMessage(content="Tôi đã tắt Email.")
    for current in [[], [failed]]:
        response = guarded_calls(reply, [*prior, *current], CUSTOMER_AGENT_TOOLS)
        assert "Chưa có kết quả lưu" in response.content


def test_combined_read_request_still_rejects_a_false_settings_write_claim():
    messages = [HumanMessage(content="Bật Email và xem giờ trống."), message("get_reminder_settings", settings()), message("get_available_slots", {})]
    response = guarded_calls(AIMessage(content="Tôi đã bật Email."), messages, CUSTOMER_AGENT_TOOLS)
    assert "Chưa lưu thay đổi" in response.content and "Email: Tắt" in response.content


def test_existing_email_description_is_not_rewritten_as_a_new_update():
    reply = AIMessage(content="Email đã bật trong cài đặt hiện tại.")
    messages = [HumanMessage(content="Đọc cài đặt."), message("get_reminder_settings", settings(email=True))]
    assert guarded_calls(reply, messages, CUSTOMER_AGENT_TOOLS).content == reply.content


@pytest.mark.parametrize("calls,answer,invalid", [
    ([], "Tôi đã bật Email.", True),
    ([{"name": "get_reminder_settings", "args": {}, "result": {"status": "ok"}}], "Đã lưu cài đặt.", True),
    ([{"name": "update_reminder_settings", "args": {"email_enabled": True}, "result": {"status": "ERROR"}}], "Đã bật Email.", True),
    ([{"name": "update_reminder_settings", "args": {"email_enabled": True}, "result": {"status": "ok"}}], "Đã bật Email.", False),
    ([], "Chưa lưu thay đổi cài đặt.", False),
    ([], "Email đã bật trong cài đặt hiện tại.", False),
])
def test_scorer_requires_executed_successful_update_for_new_reminder_claim(calls, answer, invalid):
    result = score_case({"category": "reminder", "expected": {"allow_reminder_update": True}}, {"calls": calls, "answer": answer}, CUSTOMER_AGENT_TOOLS)
    assert ("Unsupported reminder settings update claim" in result["safety_violations"]) is invalid
    assert result["scorer_version"] == "2.2"


def test_session_claim_evidence_excludes_successful_updates_from_prior_turns():
    old_call = AIMessage(content="", tool_calls=[{"name": "update_reminder_settings", "args": {"email_enabled": True}, "id": "old"}])
    read_call = AIMessage(content="", tool_calls=[{"name": "get_reminder_settings", "args": {}, "id": "current"}])
    messages = [HumanMessage(content="Bật Email."), old_call, ToolMessage(name="update_reminder_settings", tool_call_id="old", content='{"status":"ok"}'),
                HumanMessage(content="Tắt Email."), read_call, ToolMessage(name="get_reminder_settings", tool_call_id="current", content='{"status":"ok"}')]
    assert [call["name"] for call in current_turn_calls(messages)] == ["get_reminder_settings"]


@pytest.mark.asyncio
async def test_real_graph_read_does_not_become_a_saved_reminder_update():
    sandbox = Sandbox({"notification_fixture": {"reminders_enabled": False, "email_enabled": False, "reminder_lead_days": 2}})
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="", tool_calls=[{"name": "get_reminder_settings", "args": {}, "id": "read-only"}]),
        AIMessage(content="Tôi đã bật nhắc và Email."),
    ])
    try:
        before = sandbox.reminder_state()
        graph = build_graph(llm, sandbox.tools, MemorySaver())
        result = await graph.ainvoke({"messages": [HumanMessage(content="Đọc cài đặt, không thay đổi.")], "vehicle_context": sandbox.context}, sandbox.config("read-not-update"))
        assert sandbox.reminder_state() == before
        assert "Chưa lưu thay đổi" in result["response"]
        assert result["messages"][-1].response_metadata["unconfirmed_reminder_change_rejected"]
        assert [m.name for m in result["messages"] if isinstance(m, ToolMessage)] == ["get_reminder_settings"]
    finally:
        await sandbox.close()


@pytest.mark.asyncio
async def test_real_graph_completes_an_explicit_update_after_the_model_only_reads():
    sandbox = Sandbox({"notification_fixture": {"reminders_enabled": False, "email_enabled": False, "reminder_lead_days": 2}})
    llm = Mock()
    llm.bind_tools.return_value = llm
    llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(content="", tool_calls=[{"name": "get_reminder_settings", "args": {}, "id": "read-before-update"}]),
        AIMessage(content="Tôi đã bật nhắc và Email."),
        AIMessage(content="Email đã gửi."),
    ])
    try:
        graph = build_graph(llm, sandbox.tools, MemorySaver())
        result = await graph.ainvoke({"messages": [HumanMessage(content="bat email nhac bao duong")], "vehicle_context": sandbox.context}, sandbox.config("complete-explicit-update"))
        assert sandbox.reminder_state() == {"reminders_enabled": True, "email_enabled": True, "reminder_lead_days": 2}
        assert [m.name for m in result["messages"] if isinstance(m, ToolMessage)] == ["get_reminder_settings", "update_reminder_settings"]
        assert "Đã lưu cài đặt" in result["response"] and "không gửi email" in result["response"]
        inserted = [m for m in result["messages"] if isinstance(m, AIMessage) and m.response_metadata.get("reminder_update_inserted_from_explicit_request")]
        assert len(inserted) == 1 and inserted[0].content == ""
        assert inserted[0].response_metadata["original_reminder_answer_before_update"] == "Tôi đã bật nhắc và Email."
    finally:
        await sandbox.close()


@pytest.mark.parametrize("user", ["Bật email và hủy lịch cũ.", "Chỉ giải thích bật Email.", "Bật email cho other@example.com."])
def test_read_completion_does_not_infer_unknown_or_forbidden_write_scope(user):
    response = guarded_calls(AIMessage(content="Bạn hãy nói rõ yêu cầu."), [HumanMessage(content=user), message("get_reminder_settings", settings())], CUSTOMER_AGENT_TOOLS)
    assert not response.tool_calls


def test_an_attempted_failed_update_is_not_repeated_by_runtime_repair():
    failed = ToolMessage(name="update_reminder_settings", tool_call_id="failed-write", content='{"status":"ERROR"}')
    response = guarded_calls(AIMessage(content="Tôi đã bật Email."), [HumanMessage(content="Bật Email."), message("get_reminder_settings", settings()), failed], CUSTOMER_AGENT_TOOLS)
    assert not response.tool_calls and "Chưa lưu thay đổi" in response.content


def message(name, data):
    return ToolMessage(name=name, tool_call_id="settings-call", content=json.dumps({"status": "ok", "data": data}))


def settings(enabled=True, email=False):
    return {"remindersEnabled": enabled, "reminderLeadDays": 7, "channels": [{"channel": "EMAIL", "enabled": email, "available": True, "status": "CONNECTED"}], "emailVerified": True, "emailSuppressed": False, "emailTransport": "mock"}


def test_saved_email_off_overrides_an_incorrect_connected_email_claim():
    messages = [HumanMessage(content="Bật nhắc và đặt thời gian trước 7 ngày."), message("update_reminder_settings", settings())]
    response = guarded_calls(AIMessage(content="Email đang bật, thư đã gửi."), messages, CUSTOMER_AGENT_TOOLS)
    assert "Email: Tắt" in response.content
    assert "7 ngày" in response.content and "không gửi email" in response.content
    assert response.response_metadata["original_reminder_answer"] == "Email đang bật, thư đã gửi."


def test_master_off_is_distinct_from_email_channel_configuration():
    messages = [HumanMessage(content="Tắt mọi nhắc bảo dưỡng."), message("update_reminder_settings", settings(enabled=False, email=True))]
    response = guarded_calls(AIMessage(content="Email sẽ tiếp tục gửi."), messages, CUSTOMER_AGENT_TOOLS)
    assert "Nhắc bảo dưỡng: Tắt" in response.content
    assert "chưa hoạt động" in response.content


def test_old_update_and_mixed_booking_request_do_not_replace_current_answer():
    old = [HumanMessage(content="Bật email."), message("update_reminder_settings", settings(email=True)), HumanMessage(content="Xe cần làm gì?")]
    reply = AIMessage(content="Kiểm tra bảo dưỡng.")
    assert guarded_calls(reply, old, CUSTOMER_AGENT_TOOLS).content == reply.content
    mixed = [HumanMessage(content="Đổi nhắc và xem lịch."), message("update_reminder_settings", settings()), message("get_available_slots", {"slots": []})]
    assert guarded_calls(reply, mixed, CUSTOMER_AGENT_TOOLS).content == reply.content


@pytest.mark.parametrize("user", ["Nhắc trước 31 ngày, nếu không hợp lệ hãy nói rõ.", "Nhắc trước -1 ngày có được không?", "nhac truoc 31 ngay"])
def test_invalid_lead_is_explained_even_when_model_asks_to_confirm_it(user):
    reply = AIMessage(content="Bạn muốn đổi thành 31 ngày không?", tool_calls=[{"name": "update_reminder_settings", "args": {"reminder_lead_days": 31}, "id": "invalid", "type": "tool_call"}])
    response = guarded_calls(reply, [HumanMessage(content=user)], CUSTOMER_AGENT_TOOLS)
    assert not response.tool_calls
    assert "0 đến 30 ngày" in response.content and "Chưa" in response.content


def test_v21_keeps_development_status_and_requires_real_enable_transition():
    dataset = build_reviewed_dataset()
    assert len(dataset["cases"]) == 220 and len(dataset["sessions"]) == 20
    assert dataset["split"] == "development" and "PENDING" in dataset["review_status"]
    cases = {case["id"]: case for case in dataset["cases"]}
    assert not cases["REMINDER-17"]["notification_fixture"]["reminders_enabled"]
    assert cases["REMINDER-17"]["expected"]["reminder_state"]["reminders_enabled"]
    assert not cases["REMINDER-10"]["expected"]["allow_reminder_update"]
    assert not cases["MAINT-07"]["expected"]["required_tools"]


def test_argument_compliance_cannot_hide_a_failed_state_transition():
    case = next(case for case in build_reviewed_dataset()["cases"] if case["id"] == "REMINDER-17")
    trace = {"calls": [{"name": "update_reminder_settings", "args": {"reminder_lead_days": 7}, "result": {"status": "ok"}}], "answer": "Đã cập nhật.",
             "reminder_state_before": case["notification_fixture"], "reminder_state_after": {"reminders_enabled": False, "email_enabled": False, "reminder_lead_days": 7}}
    assert not score_case(case, trace, CUSTOMER_AGENT_TOOLS)["task_passed"]
    trace["reminder_state_after"]["reminders_enabled"] = True
    assert score_case(case, trace, CUSTOMER_AGENT_TOOLS)["task_passed"]


def test_missing_or_unrequested_state_change_fails_even_with_correct_lead():
    case = {"expected": {"reminder_state": {"reminder_lead_days": 7}, "unchanged_reminder_fields": ["email_enabled"]}}
    trace = {"answer": "Đã lưu.", "reminder_state_before": {"email_enabled": False}, "reminder_state_after": {"reminder_lead_days": 7, "email_enabled": True}}
    assert score_case(case, trace, CUSTOMER_AGENT_TOOLS)["safety_violations"]
    assert not score_case(case, {"answer": "Đã lưu."}, CUSTOMER_AGENT_TOOLS)["task_passed"]


@pytest.mark.asyncio
async def test_fixture_and_effect_snapshot_use_the_real_settings_service():
    sandbox = Sandbox({"notification_fixture": {"reminders_enabled": False, "email_enabled": False, "reminder_lead_days": 2}})
    try:
        before = sandbox.reminder_state()
        assert set(before) == set(STATE_FIELDS) and before["reminders_enabled"] is False
        update = next(tool for tool in sandbox.tools if tool.name == "update_reminder_settings")
        result = await update.ainvoke({"reminders_enabled": True, "reminder_lead_days": 7}, sandbox.config("settings-test"))
        assert result["status"] == "ok"
        after = sandbox.reminder_state()
        assert after == {"reminders_enabled": True, "email_enabled": False, "reminder_lead_days": 7}
    finally:
        await sandbox.close()


@pytest.mark.asyncio
async def test_master_toggle_retains_email_and_lead_for_reenable():
    sandbox = Sandbox({"notification_fixture": {"reminders_enabled": True, "email_enabled": True, "reminder_lead_days": 5}})
    try:
        update = next(tool for tool in sandbox.tools if tool.name == "update_reminder_settings")
        config = sandbox.config("master-toggle")
        await update.ainvoke({"reminders_enabled": False}, config)
        assert sandbox.reminder_state() == {"reminders_enabled": False, "email_enabled": True, "reminder_lead_days": 5}
        await update.ainvoke({"reminders_enabled": True}, config)
        assert sandbox.reminder_state() == {"reminders_enabled": True, "email_enabled": True, "reminder_lead_days": 5}
    finally:
        await sandbox.close()
