"""Single reminder policy for creation and last-moment channel eligibility."""

from dataclasses import dataclass
from datetime import date, timedelta

from src.common.core.maintenance.reminder import ReminderLevel
from src.modules.user_vehicle.domain import DueResult, DueStatus
from src.modules.vehicle_usage.schemas import MaintenanceForecast

from .domain import decide_level


@dataclass(frozen=True)
class ReminderDecision:
    level: ReminderLevel | None
    trigger_reasons: tuple[str, ...] = ()
    policy_version: str = "reminder-usage-v1"
    trip: dict | None = None


def decide_reminder(
    result: DueResult,
    *,
    lead_days: int,
    due_soon_km: int,
    today: date,
    forecast: MaintenanceForecast | None = None,
    predictive_enabled: bool = False,
    trip: dict | None = None,
) -> ReminderDecision:
    level = decide_level(result, lead_days=lead_days, due_soon_km=due_soon_km)
    if result.due_status == DueStatus.UNKNOWN or result.next_milestone is None:
        return ReminderDecision(None)
    if level == ReminderLevel.EXPIRED:
        return ReminderDecision(level, ("OBSERVED_OVERDUE",))
    reasons = []
    if result.remaining_days is not None and result.remaining_days <= lead_days:
        reasons.append("TIME_WINDOW")
    if result.remaining_km is not None and result.remaining_km <= due_soon_km:
        reasons.append("FIXED_KM_WINDOW")
    if (
        predictive_enabled
        and forecast
        and forecast.status == "AVAILABLE"
        and forecast.km_forecast_date is not None
        and forecast.km_forecast_date <= today + timedelta(days=lead_days)
    ):
        reasons.append("PREDICTED_KM_WINDOW")
        level = ReminderLevel.EARLY
    if trip:
        reasons.extend(trip["reasons"])
        level = ReminderLevel.EARLY
    return ReminderDecision(level, tuple(reasons), trip=trip)
