"""Transparent planning projection; never modifies the observed due status."""

from datetime import timedelta

from src.modules.user_vehicle.domain import DueStatus

from .schemas import TripAdvice


def advise_trip(trip, result, *, today, forecast=None):
    if trip.departure_date < today:
        return TripAdvice(status="DEPARTED")
    milestone = result.next_milestone
    if milestone is None or result.due_status == DueStatus.UNKNOWN:
        return TripAdvice(status="UNKNOWN")
    until_departure = (trip.departure_date - today).days
    before = 0
    if until_departure <= 90 and forecast and forecast.status == "AVAILABLE" and forecast.avg_km_per_day is not None:
        before = forecast.avg_km_per_day * until_departure
    projection = (
        result.odometer.odo_km + before + trip.distance_km if result.odometer and not result.odometer.is_stale else None
    )
    reasons = []
    if result.due_status == DueStatus.OVERDUE:
        reasons.append("OBSERVED_OVERDUE")
    if projection is not None and projection >= milestone.odo_milestone_km:
        reasons.append("TRIP_KM_MILESTONE")
    if milestone.due_date <= (trip.return_date or trip.departure_date):
        reasons.append("TRIP_TIME_DEADLINE")
    return TripAdvice(
        status="MAINTENANCE_RECOMMENDED"
        if reasons
        else "ODO_UNAVAILABLE"
        if projection is None
        else "NO_MILESTONE_CROSSING",
        reasons=reasons,
        milestone_km=milestone.odo_milestone_km,
        projected_trip_end_km=projection,
        projected_usage_before_departure_km=before,
        prepare_by=max(today, trip.departure_date - timedelta(days=1)) if reasons else None,
    )
