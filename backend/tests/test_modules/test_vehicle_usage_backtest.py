from datetime import timedelta

from src.modules.vehicle_usage.backtest import evaluate_series
from src.modules.vehicle_usage.domain import Reading
from tests.test_modules.test_vehicle_usage import NOW, history


def run(readings):
    return evaluate_series(
        readings, milestone_km=12000, official_due_date=(NOW + timedelta(days=80)).date(), cutoffs=[NOW]
    )


def test_future_changes_affect_only_labels_not_training_predictions():
    slow_future = history() + [Reading(10800 + 200 * day, NOW + timedelta(days=day)) for day in range(1, 8)]
    fast_future = history() + [Reading(12000, NOW + timedelta(days=1))]
    slow, fast = run(slow_future), run(fast_future)
    assert slow["evaluations"][0]["predictedKmDate"] == fast["evaluations"][0]["predictedKmDate"]
    assert slow["medianAbsoluteErrorDays"] == 0 and fast["medianAbsoluteErrorDays"] == 5


def test_unobserved_crossing_is_unscored_and_never_assumed_zero_error():
    report = run(history())
    assert report["evaluationCount"] == 1 and report["scoredCount"] == 0
    assert report["medianAbsoluteErrorDays"] is None
