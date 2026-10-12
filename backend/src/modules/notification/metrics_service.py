"""Aggregate local reporting and durable shadow telemetry, never a global owner API."""

from datetime import datetime, timedelta

from sqlmodel import Session, select

from src.common.core.identity import VehicleUser
from src.common.core.notification import ReminderPolicyEvaluation
from src.modules.user_vehicle.domain import today_vn

from .policy_service import ReminderDecision
from .preferences import load_preferences


def record_policy_evaluation(db, vehicle, forecast, baseline, candidate, actual, *, mode, lead_days, duration_ms, now):
    if mode not in {"on", "shadow"}:
        return
    # Erasure locks the same owner and deletes these derived evaluation rows.
    db.exec(select(VehicleUser).where(VehicleUser.user_id == vehicle.user_id).with_for_update()).one()
    if not load_preferences(db, vehicle.user_id, default_lead_days=lead_days).personalized_reminders_enabled:
        db.commit()
        return
    day = today_vn(now)
    existing = db.exec(
        select(ReminderPolicyEvaluation).where(
            ReminderPolicyEvaluation.user_vehicle_id == vehicle.id,
            ReminderPolicyEvaluation.evaluation_day == day,
            ReminderPolicyEvaluation.mode == mode,
        )
    ).first()
    if existing is None:

        def level(decision: ReminderDecision):
            return decision.level.name if decision.level else None

        db.add(
            ReminderPolicyEvaluation(
                user_id=vehicle.user_id,
                user_vehicle_id=vehicle.id,
                evaluation_day=day,
                mode=mode,
                forecast_status=forecast.status,
                baseline_level=level(baseline),
                candidate_level=level(candidate),
                actual_level=level(actual),
                lead_days=lead_days,
                duration_ms=max(0, duration_ms),
                calculated_at=now,
            )
        )
    db.commit()


def aggregate_metrics(db: Session, *, now: datetime, days: int = 30) -> dict:
    from collections import Counter
    from math import ceil

    from src.common.core.maintenance import Booking
    from src.common.core.notification import ReminderBookingAttribution, ReminderDelivery, ReminderPersonalizationEvent
    from src.common.core.notification.email import EmailOutbox

    since = now - timedelta(days=days)
    rows = db.exec(
        select(ReminderPolicyEvaluation).where(
            ReminderPolicyEvaluation.calculated_at >= since, ReminderPolicyEvaluation.calculated_at <= now
        )
    ).all()
    statuses = Counter(row.forecast_status for row in rows)
    latest_by_vehicle = {}
    for row in sorted(rows, key=lambda item: item.calculated_at):
        latest_by_vehicle[row.user_vehicle_id] = row
    available_vehicles = sum(row.forecast_status == "AVAILABLE" for row in latest_by_vehicle.values())
    durations = sorted(row.duration_ms for row in rows)
    shadow = [row for row in rows if row.mode == "shadow"]
    confirmed = db.exec(
        select(ReminderBookingAttribution, Booking.status)
        .join(Booking, Booking.id == ReminderBookingAttribution.booking_id)
        .where(ReminderBookingAttribution.confirmed_at >= since, ReminderBookingAttribution.confirmed_at <= now)
    ).all()
    events = db.exec(
        select(ReminderPersonalizationEvent.action).where(
            ReminderPersonalizationEvent.occurred_at >= since, ReminderPersonalizationEvent.occurred_at <= now
        )
    ).all()
    delivery_states = db.exec(
        select(EmailOutbox.delivery_state).where(EmailOutbox.created_at >= since, EmailOutbox.created_at <= now)
    ).all()
    from src.common.core.maintenance.reminder import ReminderChannel

    attempts = db.exec(
        select(ReminderDelivery.attempts).where(
            ReminderDelivery.last_attempt_at >= since,
            ReminderDelivery.last_attempt_at <= now,
            ReminderDelivery.channel == ReminderChannel.EMAIL,
        )
    ).all()
    return {
        "generatedAt": now.isoformat(),
        "windowDays": days,
        "evaluationCount": len(rows),
        "forecastStatuses": dict(statuses),
        "evaluatedVehicleCount": len(latest_by_vehicle),
        "availableVehicleCount": available_vehicles,
        "forecastCoverage": available_vehicles / len(latest_by_vehicle) if latest_by_vehicle else None,
        "evaluationForecastCoverage": statuses["AVAILABLE"] / len(rows) if rows else None,
        "forecastP95Ms": durations[ceil(len(durations) * 0.95) - 1] if durations else None,
        "shadowCount": len(shadow),
        "shadowChangedDecisions": sum(row.baseline_level != row.candidate_level for row in shadow),
        "confirmedBookings": len(confirmed),
        "directConfirmedBookings": sum(row.match_method == "DIRECT" for row, _ in confirmed),
        "recentReminderConfirmedBookings": sum(row.match_method == "RECENT_REMINDER" for row, _ in confirmed),
        "confirmedBookingCurrentStatuses": dict(Counter(status.name for _, status in confirmed)),
        "consentEvents": dict(Counter(events)),
        "emailStates": dict(Counter(delivery_states)),
        "recordedProviderAttempts": sum(attempts),
        "notes": [
            "One evaluation per opted-in vehicle/day/mode; not a count of HTTP reads.",
            "Coverage uses each evaluated vehicle's latest result in this window; not all registered vehicles.",
            "RECENT_REMINDER is correlation, not proof the reminder caused the booking.",
            "Confirmed counts exclude holds and CTA clicks; email accepted is not delivered.",
            "Seven-day attribution uses booking creation time; confirmation may occur later.",
            "Provider attempts are cumulative per email delivery whose latest attempt falls in this window.",
        ],
    }
