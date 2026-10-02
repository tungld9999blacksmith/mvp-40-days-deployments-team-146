"""Unit tests for the reminder rules (FEAT-NOTI-001 BR-501, BR-509)."""

from __future__ import annotations

from datetime import date

import pytest

from src.common.core.maintenance.reminder import ReminderLevel
from src.modules.notification.domain import build_message, decide_level, mask_plate
from src.modules.user_vehicle.domain import (
    DueResult,
    DueStatus,
    MilestoneItem,
    NextMilestone,
)


def _result(status: DueStatus, *, days: int | None, km: int | None, milestone: bool = True) -> DueResult:
    return DueResult(
        due_status=status,
        next_milestone=(
            NextMilestone(12_000, 12, date(2026, 10, 15), False, [MilestoneItem("X", "X", False)])
            if milestone
            else None
        ),
        remaining_days=days,
        remaining_km=km,
    )


@pytest.mark.parametrize(
    "status, days, km, lead, expected",
    [
        (DueStatus.NORMAL, 3, 5_000, 2, None),
        (DueStatus.NORMAL, 2, 5_000, 2, ReminderLevel.EARLY),  # on the lead day
        (DueStatus.NORMAL, 0, 5_000, 0, ReminderLevel.EARLY),  # lead 0 -> due day
        (DueStatus.NORMAL, 1, 5_000, 0, None),
        (DueStatus.DUE_SOON, 10, 500, 2, ReminderLevel.EARLY),  # km threshold, inclusive
        (DueStatus.DUE_SOON, 10, 501, 2, None),
        (DueStatus.NORMAL, 3, None, 2, None),  # no odometer: days only
        (DueStatus.OVERDUE, -3, 200, 2, ReminderLevel.EXPIRED),
        (DueStatus.OVERDUE, 20, -100, 2, ReminderLevel.EXPIRED),  # overdue by km only
    ],
)
def test_decide_level(status, days, km, lead, expected):
    result = _result(status, days=days, km=km)

    assert decide_level(result, lead_days=lead, due_soon_km=500) is expected


def test_unknown_or_missing_milestone_never_reminds():
    unknown = DueResult(due_status=DueStatus.UNKNOWN)
    no_milestone = _result(DueStatus.NORMAL, days=0, km=0, milestone=False)

    assert decide_level(unknown, lead_days=30, due_soon_km=500) is None
    assert decide_level(no_milestone, lead_days=30, due_soon_km=500) is None


def test_mask_plate_hides_the_middle():
    assert mask_plate("30A12345") == "30****45"
    assert mask_plate("1234") == "1234"


def test_message_is_safe_and_has_link():
    message = build_message(
        model_name="VF6",
        license_plate="30A12345",
        result=_result(DueStatus.NORMAL, days=2, km=5_000),
        level=ReminderLevel.EARLY,
        app_url="https://app.example.com/",
    )

    assert "30A12345" not in message.body and "30****45" in message.body
    assert "12,000 km / 12 months" in message.body and "2 days" in message.body
    assert message.link == "https://app.example.com/booking"
    assert message.body.endswith("https://app.example.com/booking")


def test_expired_message_states_how_late():
    message = build_message(
        model_name="VF6",
        license_plate="30A12345",
        result=_result(DueStatus.OVERDUE, days=-3, km=-300),
        level=ReminderLevel.EXPIRED,
    )

    assert "overdue by 3 days and 300 km" in message.body
    assert message.link is None
