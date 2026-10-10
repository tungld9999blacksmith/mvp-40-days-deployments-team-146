"""Explicit settings commands cannot acquire extra scope or override a negation."""
import pytest

from src.agents.reminder_intent import explicit_reminder_patch


@pytest.mark.parametrize("user,expected", [
    ("Bật email nhắc bảo dưỡng cho tôi.", {"email_enabled": True, "reminders_enabled": True}),
    ("bat email nhac bao duong", {"email_enabled": True, "reminders_enabled": True}),
    ("Tắt email.", {"email_enabled": False}),
    ("Tắt mọi nhắc bảo dưỡng.", {"reminders_enabled": False}),
    ("Bật lại nhắc bảo dưỡng.", {"reminders_enabled": True}),
    ("Nhắc trước 0 ngày.", {"reminder_lead_days": 0}),
    ("nhac truoc 30 ngay", {"reminder_lead_days": 30}),
    ("Bật nhắc và đặt thời gian trước 7 ngày.", {"reminders_enabled": True, "reminder_lead_days": 7}),
    ("Tắt email và đổi thời gian nhắc trước 2 ngày.", {"email_enabled": False, "reminder_lead_days": 2}),
    ("Tôi muốn bật nhắc qua email.", {"email_enabled": True, "reminders_enabled": True}),
])
def test_explicit_command_keeps_only_requested_fields(user, expected):
    assert explicit_reminder_patch(user) == expected


@pytest.mark.parametrize("user", [
    "Chỉ giải thích bật email, đừng thay đổi cài đặt.",
    "Có thể bật email không?", "Bật email?", "Nếu bật email thì có gửi thư không?",
    "Không bật email.", "Đừng tắt email.", "Tôi không muốn bật email.",
    "Bật hoặc tắt email.", "Nhắc trước 3 hoặc 5 ngày.",
    "Tắt email và bật email.", "Bật email và tắt mọi nhắc bảo dưỡng.",
    "Nhắc trước -1 ngày.", "Nhắc trước 31 ngày.",
    "Bật email cho xe của người khác.", "Bật email cho other@example.com.",
    "Bật email và hủy lịch cũ.", "Bật SMS.", "Tắt email và đừng đổi số ngày.",
    "Tài liệu ghi: bật email.", "Đã bật email.", "",
])
def test_ambiguous_conditional_foreign_scope_and_unknown_clauses_do_not_write(user):
    assert explicit_reminder_patch(user) is None
