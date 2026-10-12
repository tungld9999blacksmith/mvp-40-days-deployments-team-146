"""Forecast boundaries using explicit observations, no future data or providers."""

from datetime import UTC, date, datetime, timedelta

import pytest

from src.common.core.maintenance.reminder import ReminderLevel
from src.modules.notification.policy_service import decide_reminder
from src.modules.user_vehicle.domain import DueResult, DueStatus, NextMilestone, Odometer
from src.modules.vehicle_usage.domain import Reading, calculate_forecast

NOW = datetime(2026, 10, 11, 2, tzinfo=UTC)


def due(km=10800, at=NOW, days=80, status=DueStatus.NORMAL):
    return DueResult(
        status,
        next_milestone=NextMilestone(12000, 12, NOW.date() + timedelta(days=days), False),
        remaining_km=12000 - km,
        remaining_days=days,
        odometer=Odometer(km, at),
    )


def history(speed=200, age=0):
    anchor = NOW - timedelta(days=age)
    return [Reading(10800 - speed * delta, anchor - timedelta(days=delta)) for delta in range(28, -1, -1)]


def test_high_usage_extends_reminder_window_without_changing_observed_status():
    observed = due()
    forecast = calculate_forecast(history(), observed, now=NOW)
    assert forecast.avg_km_per_day == 200
    assert forecast.km_forecast_date == date(2026, 10, 17)
    assert forecast.projected_due_date == date(2026, 10, 17)
    assert observed.due_status == DueStatus.NORMAL
    decision = decide_reminder(
        observed, lead_days=7, due_soon_km=500, today=NOW.date(), forecast=forecast, predictive_enabled=True
    )
    assert decision.level == ReminderLevel.EARLY
    assert decision.trigger_reasons == ("PREDICTED_KM_WINDOW",)
    assert decide_reminder(observed, lead_days=7, due_soon_km=500, today=NOW.date(), forecast=forecast).level is None


def test_low_usage_and_official_time_deadline():
    forecast = calculate_forecast(history(20), due(days=5), now=NOW)
    assert forecast.km_forecast_date == date(2026, 12, 10)
    assert forecast.projected_due_date == date(2026, 10, 16)
    assert forecast.basis == "TIME_ONLY"
    decision = decide_reminder(
        due(days=5), lead_days=7, due_soon_km=500, today=NOW.date(), forecast=forecast, predictive_enabled=True
    )
    assert decision.trigger_reasons == ("TIME_WINDOW",)


def test_forecast_is_anchored_to_measurement_not_calculation_time():
    forecast = calculate_forecast(history(age=3), due(at=NOW - timedelta(days=3)), now=NOW)
    assert forecast.km_forecast_date == date(2026, 10, 14)


def test_zero_usage_uses_time_without_division_by_zero():
    forecast = calculate_forecast(history(0), due(), now=NOW)
    assert forecast.status == "AVAILABLE" and forecast.avg_km_per_day == 0
    assert forecast.km_forecast_date is None
    assert forecast.projected_due_date == due().next_milestone.due_date


def test_sparse_samples_are_weighted_by_elapsed_time():
    rows = [Reading(9000, NOW - timedelta(days=14)), Reading(9600, NOW - timedelta(days=7)), Reading(10800, NOW)]
    forecast = calculate_forecast(rows, due(), now=NOW)
    assert forecast.avg_km_per_day == round(1800 / 14, 2)
    assert forecast.sample_days == 3


@pytest.mark.parametrize(
    "rows,result,status",
    [
        ([Reading(10800, NOW)], due(), "INSUFFICIENT_DATA"),
        (history(age=8), due(at=NOW - timedelta(days=8)), "STALE_DATA"),
        (history() + [Reading(11000, NOW + timedelta(days=1))], due(), "ANOMALOUS_DATA"),
        (history(), due(km=11000), "ANOMALOUS_DATA"),
        ([Reading(100, NOW - timedelta(days=14)), Reading(10800, NOW)], due(), "ANOMALOUS_DATA"),
        (
            [Reading(100, NOW - timedelta(days=14)), Reading(11000, NOW - timedelta(days=7)), Reading(10800, NOW)],
            due(),
            "ANOMALOUS_DATA",
        ),
    ],
)
def test_unsafe_or_missing_data_cannot_predict(rows, result, status):
    forecast = calculate_forecast(rows, result, now=NOW)
    assert forecast.status == status
    assert forecast.avg_km_per_day is None and forecast.km_forecast_date is None


def test_multiple_measurements_in_one_day_do_not_change_average():
    rows = history()
    rows.extend(Reading(10800 - 200 * d - 1, NOW - timedelta(days=d, minutes=1)) for d in range(20))
    forecast = calculate_forecast(rows, due(), now=NOW)
    assert forecast.avg_km_per_day == 200 and forecast.sample_days == 29


def test_intraday_decrease_is_not_hidden_by_daily_downsampling():
    rows = history()
    rows.extend(
        [
            Reading(10500, NOW - timedelta(minutes=30)),
            Reading(10700, NOW - timedelta(minutes=15)),
        ]
    )
    assert calculate_forecast(rows, due(), now=NOW).status == "ANOMALOUS_DATA"


def test_long_forecast_horizon_has_no_precise_km_date():
    forecast = calculate_forecast(history(1), due(), now=NOW)
    assert forecast.status == "AVAILABLE" and forecast.km_forecast_date is None


def test_recent_standstill_is_low_confidence():
    rows = [Reading(8000 + 200 * d if d < 14 else 10800, NOW - timedelta(days=28 - d)) for d in range(29)]
    assert calculate_forecast(rows, due(), now=NOW).status == "LOW_CONFIDENCE"


def test_possibly_reached_does_not_assert_observed_overdue():
    observed = due(at=NOW - timedelta(days=7))
    forecast = calculate_forecast(history(age=7), observed, now=NOW)
    assert forecast.possibly_reached
    assert (
        decide_reminder(
            observed, lead_days=0, due_soon_km=500, today=NOW.date(), forecast=forecast, predictive_enabled=True
        ).level
        == ReminderLevel.EARLY
    )
    assert observed.due_status == DueStatus.NORMAL


def test_observed_overdue_always_wins():
    decision = decide_reminder(
        due(km=12001, status=DueStatus.OVERDUE), lead_days=0, due_soon_km=500, today=NOW.date(), predictive_enabled=True
    )
    assert decision.level == ReminderLevel.EXPIRED
    assert decision.trigger_reasons == ("OBSERVED_OVERDUE",)
