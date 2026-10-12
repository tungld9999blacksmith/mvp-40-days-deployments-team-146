"""Temporal validation: forecast inputs stop at the cutoff, labels come after it."""

from collections import Counter
from datetime import date, datetime, timedelta
from math import ceil
from statistics import median

from src.modules.user_vehicle.domain import DueResult, DueStatus, NextMilestone, Odometer, today_vn

from .domain import Reading, calculate_forecast, utc


def evaluate_series(readings: list[Reading], *, milestone_km: int, official_due_date: date, cutoffs: list[datetime]):
    ordered = sorted(readings, key=lambda row: utc(row.recorded_at))
    rows = []
    for cutoff in cutoffs:
        training = [row for row in ordered if utc(row.recorded_at) <= utc(cutoff)]
        if not training or training[-1].odo_km >= milestone_km:
            continue
        anchor = training[-1]
        due = DueResult(
            DueStatus.NORMAL,
            next_milestone=NextMilestone(milestone_km, 12, official_due_date, False),
            remaining_km=milestone_km - anchor.odo_km,
            remaining_days=(official_due_date - today_vn(cutoff)).days,
            odometer=Odometer(anchor.odo_km, anchor.recorded_at),
        )
        forecast = calculate_forecast(training, due, now=cutoff)
        future = [row for row in ordered if utc(cutoff) < utc(row.recorded_at) <= utc(cutoff) + timedelta(days=90)]
        observed = next((row for row in future if row.odo_km >= milestone_km), None)
        # Daily OEM samples label the first observed crossing, not its exact time.
        error = (
            abs((forecast.km_forecast_date - today_vn(observed.recorded_at)).days)
            if observed and forecast.km_forecast_date
            else None
        )
        rows.append(
            {
                "cutoff": utc(cutoff).isoformat(),
                "forecastStatus": forecast.status,
                "predictedKmDate": forecast.km_forecast_date.isoformat() if forecast.km_forecast_date else None,
                "observedCrossingDate": today_vn(observed.recorded_at).isoformat() if observed else None,
                "absoluteErrorDays": error,
            }
        )
    errors = sorted(row["absoluteErrorDays"] for row in rows if row["absoluteErrorDays"] is not None)
    return {
        "evaluationCount": len(rows),
        "scoredCount": len(errors),
        "forecastStatuses": dict(Counter(row["forecastStatus"] for row in rows)),
        "medianAbsoluteErrorDays": median(errors) if errors else None,
        "p90AbsoluteErrorDays": errors[ceil(len(errors) * 0.9) - 1] if errors else None,
        "evaluations": rows,
    }
