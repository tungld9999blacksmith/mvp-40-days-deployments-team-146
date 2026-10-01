"""Unit tests for the due-status calculation (FEAT-VEH-001 RM-401, BR-001..BR-007)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from src.modules.user_vehicle.domain import (
    CalculationBasis,
    DueConfig,
    DueReason,
    DueStatus,
    LastService,
    LastServiceType,
    Odometer,
    RuleItem,
    UnknownReason,
    add_months,
    calculate_due_status,
    today_vn,
)

PURCHASE = date(2025, 10, 15)  # milestone 1 due 2026-10-15, milestone 2 due 2027-10-15
TODAY = date(2026, 9, 28)
CONFIG = DueConfig()

RULES = [
    RuleItem(12_000, 12, "BRAKE_INSPECTION", "Brake system inspection", False),
    RuleItem(12_000, 12, "BATTERY_CHECK", "High-voltage battery check", True),
    RuleItem(24_000, 24, "BRAKE_FLUID", "Replace brake fluid", False),
]


def _odo(km: int) -> Odometer:
    return Odometer(odo_km=km, recorded_at=datetime(2026, 9, 28, tzinfo=UTC))


def _calc(*, odo: int | None = None, last: LastService | None = None, today: date = TODAY):
    return calculate_due_status(
        rules=RULES,
        purchase_date=PURCHASE,
        odometer=_odo(odo) if odo is not None else None,
        last_service=last,
        today=today,
        config=CONFIG,
    )


def _service(day: date, km: int | None) -> LastService:
    return LastService(LastServiceType.OEM_SERVICE_RECORD, day, km)


def test_due_soon_by_km_ac001():
    result = _calc(odo=11_600)

    assert result.due_status is DueStatus.DUE_SOON
    assert result.due_reason is DueReason.KM
    assert result.calculation_basis is CalculationBasis.KM_AND_TIME
    assert result.remaining_km == 400
    assert result.remaining_days == 17
    milestone = result.next_milestone
    assert (milestone.odo_milestone_km, milestone.month_milestone) == (12_000, 12)
    assert milestone.due_date == date(2026, 10, 15)
    assert milestone.label == "12,000 km / 12 months"
    assert {i.item_code for i in milestone.items} == {"BRAKE_INSPECTION", "BATTERY_CHECK"}
    assert result.last_service.type is LastServiceType.PURCHASE_DATE


def test_time_only_without_odometer_ac002():
    result = _calc(odo=None, today=date(2026, 3, 1))

    assert result.calculation_basis is CalculationBasis.TIME_ONLY
    assert result.remaining_km is None
    assert result.due_status is DueStatus.NORMAL


def test_overdue_by_time_ac004():
    result = _calc(odo=8_000, today=date(2026, 10, 25))

    assert result.due_status is DueStatus.OVERDUE
    assert result.due_reason is DueReason.TIME
    assert result.remaining_days == -10


def test_overdue_by_km_ac003():
    result = _calc(odo=12_300)

    assert result.due_status is DueStatus.OVERDUE
    assert result.due_reason is DueReason.KM
    assert result.remaining_km == -300


def test_both_conditions_report_both():
    result = _calc(odo=12_100, today=date(2026, 10, 20))

    assert result.due_status is DueStatus.OVERDUE
    assert result.due_reason is DueReason.BOTH


def test_worse_condition_wins_edge309():
    # Far from the km milestone but 10 days past the date -> OVERDUE by time.
    result = _calc(odo=3_000, today=date(2026, 10, 25))

    assert result.due_status is DueStatus.OVERDUE
    assert result.due_reason is DueReason.TIME


@pytest.mark.parametrize(
    "odo, today, expected",
    [
        (11_500, date(2026, 3, 1), DueStatus.DUE_SOON),  # exactly 500 km left
        (11_499, date(2026, 3, 1), DueStatus.NORMAL),
        (5_000, date(2026, 10, 1), DueStatus.DUE_SOON),  # exactly 14 days left
        (5_000, date(2026, 9, 30), DueStatus.NORMAL),
        (12_000, date(2026, 3, 1), DueStatus.DUE_SOON),  # at the milestone, not past it
    ],
)
def test_thresholds_are_inclusive(odo, today, expected):
    assert _calc(odo=odo, today=today).due_status is expected


def test_next_milestone_after_service_ac007():
    result = _calc(odo=12_500, last=_service(date(2026, 9, 1), 12_100))

    assert result.next_milestone.odo_milestone_km == 24_000
    assert result.due_status is DueStatus.NORMAL
    assert result.last_service.odo_km == 12_100


def test_service_on_or_after_due_date_completes_milestone():
    result = _calc(odo=9_500, last=_service(date(2026, 10, 15), 9_000))

    assert result.next_milestone.odo_milestone_km == 24_000


def test_early_service_does_not_complete_milestone_q302_deferred():
    # No early-service window yet (Q-302 deferred): 100 km / 1 day short is not "done".
    by_km = _calc(odo=12_500, last=_service(date(2026, 9, 1), 11_900))
    by_date = _calc(odo=9_500, last=_service(date(2026, 10, 14), 9_000))

    assert by_km.next_milestone.odo_milestone_km == 12_000
    assert by_date.next_milestone.odo_milestone_km == 12_000


def test_late_service_skips_missed_milestones_edge308():
    rules = RULES + [RuleItem(36_000, 36, "COOLANT", "Replace coolant", False)]
    result = calculate_due_status(
        rules=rules,
        purchase_date=PURCHASE,
        odometer=_odo(25_500),
        last_service=_service(date(2027, 9, 1), 25_000),
        today=date(2027, 9, 10),
        config=CONFIG,
    )

    assert result.next_milestone.odo_milestone_km == 36_000


def test_recurring_milestone_after_table_end_br007():
    result = calculate_due_status(
        rules=RULES,
        purchase_date=PURCHASE,
        odometer=_odo(24_500),
        last_service=_service(date(2027, 10, 1), 24_100),
        today=date(2027, 10, 5),
        config=CONFIG,
    )

    milestone = result.next_milestone
    assert milestone.is_recurring is True
    assert (milestone.odo_milestone_km, milestone.month_milestone) == (36_000, 36)
    assert milestone.due_date == date(2028, 10, 15)
    assert {i.item_code for i in milestone.items} == {"BRAKE_INSPECTION", "BATTERY_CHECK"}


def test_recurring_step_is_configurable_q301():
    result = calculate_due_status(
        rules=RULES,
        purchase_date=PURCHASE,
        odometer=_odo(24_500),
        last_service=_service(date(2027, 10, 1), 24_100),
        today=date(2027, 10, 5),
        config=DueConfig(recurring_km=10_000, recurring_months=6),
    )

    assert (result.next_milestone.odo_milestone_km, result.next_milestone.month_milestone) == (
        34_000,
        30,
    )


def test_no_rules_is_unknown_ef003():
    result = calculate_due_status(
        rules=[],
        purchase_date=PURCHASE,
        odometer=_odo(5_200),
        last_service=None,
        today=TODAY,
        config=CONFIG,
    )

    assert result.due_status is DueStatus.UNKNOWN
    assert result.unknown_reason is UnknownReason.NO_MAINTENANCE_RULE
    assert result.next_milestone is None
    assert result.odometer.odo_km == 5_200


@pytest.mark.parametrize(
    "start, months, expected",
    [
        (date(2025, 1, 31), 1, date(2025, 2, 28)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2025, 10, 15), 12, date(2026, 10, 15)),
        (date(2025, 11, 30), 3, date(2026, 2, 28)),
    ],
)
def test_add_months_clamps_to_month_end(start, months, expected):
    assert add_months(start, months) == expected


def test_today_uses_vietnam_calendar_day():
    # 2026-09-27 18:00 UTC is already 2026-09-28 in Vietnam.
    assert today_vn(datetime(2026, 9, 27, 18, 0, tzinfo=UTC)) == date(2026, 9, 28)
    assert today_vn(datetime(2026, 9, 27, 16, 0)) == date(2026, 9, 27)
