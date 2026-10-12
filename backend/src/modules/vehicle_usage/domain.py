"""Deterministic forecasts from OEM observations; never writes estimated ODO."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from src.modules.user_vehicle.domain import DueResult, today_vn

from .schemas import MaintenanceForecast


@dataclass(frozen=True)
class UsageConfig:
    window_days: int = 30
    min_sample_days: int = 3
    min_observation_days: int = 14
    max_gap_days: int = 7
    max_age_days: int = 7
    horizon_days: int = 90
    max_daily_km: float = 1000
    trend_ratio: float = 2
    max_readings: int = 6000


@dataclass(frozen=True)
class Reading:
    odo_km: int
    recorded_at: datetime


def utc(at: datetime) -> datetime:
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


def calculate_forecast(
    readings: list[Reading], result: DueResult, *, now: datetime, config: UsageConfig = UsageConfig()
) -> MaintenanceForecast:
    """Use the latest continuous valid segment and elapsed calendar time.

    Invalid intervals reset the segment. Daily sampling avoids poll-frequency
    weighting; a missing observation is never interpreted as zero usage.
    """
    now = utc(now)
    out = MaintenanceForecast(status="INSUFFICIENT_DATA", calculated_at=now)
    if result.next_milestone is None or result.odometer is None:
        return out
    out.official_time_due_date = result.next_milestone.due_date
    readings = sorted(readings, key=lambda row: utc(row.recorded_at))
    if any(utc(row.recorded_at) > now for row in readings):
        out.status = "ANOMALOUS_DATA"
        return out
    daily: dict = {}
    cutoff = now - timedelta(days=config.window_days)
    previous_reading = None
    invalid = False
    for row in readings:
        if utc(row.recorded_at) >= cutoff:
            if previous_reading is not None and (
                row.odo_km < previous_reading.odo_km
                or (utc(row.recorded_at) == utc(previous_reading.recorded_at) and row.odo_km != previous_reading.odo_km)
            ):
                # A dip that recovers within one day must not disappear when
                # downsampling. Start a new segment after that source anomaly.
                daily.clear()
                invalid = True
            daily[today_vn(row.recorded_at)] = row
            previous_reading = row
    points = list(daily.values())
    if not points:
        return out
    anchor = points[-1]
    if anchor.odo_km != result.odometer.odo_km or utc(anchor.recorded_at) != utc(result.odometer.recorded_at):
        out.status = "ANOMALOUS_DATA"
        return out
    if now - utc(anchor.recorded_at) > timedelta(days=config.max_age_days):
        out.status = "STALE_DATA"
        return out
    segment = [points[0]]
    for point in points[1:]:
        previous = segment[-1]
        elapsed = (utc(point.recorded_at) - utc(previous.recorded_at)).total_seconds() / 86400
        delta = point.odo_km - previous.odo_km
        if elapsed <= 0 or elapsed > config.max_gap_days or delta < 0 or delta / elapsed > config.max_daily_km:
            segment = [point]
            invalid = True
        else:
            segment.append(point)
    span = (utc(anchor.recorded_at) - utc(segment[0].recorded_at)).total_seconds() / 86400
    if len(segment) < config.min_sample_days or span < config.min_observation_days:
        out.status = "ANOMALOUS_DATA" if invalid else "INSUFFICIENT_DATA"
        return out
    speed = (anchor.odo_km - segment[0].odo_km) / span
    recent = [point for point in segment if utc(point.recorded_at) >= utc(anchor.recorded_at) - timedelta(days=14)]
    if len(recent) >= 2:
        recent_span = (utc(anchor.recorded_at) - utc(recent[0].recorded_at)).total_seconds() / 86400
        recent_speed = (anchor.odo_km - recent[0].odo_km) / recent_span
        if (
            recent_span >= 7
            and speed > 0
            and (recent_speed > speed * config.trend_ratio or recent_speed < speed / config.trend_ratio)
        ):
            out.status = "LOW_CONFIDENCE"
            return out
    out.status, out.quality = "AVAILABLE", "SUFFICIENT"
    out.avg_km_per_day = round(speed, 2)
    out.observation_days, out.sample_days = round(span, 2), len(segment)
    out.anchor_recorded_at = utc(anchor.recorded_at)
    out.projected_due_date = result.next_milestone.due_date
    out.basis = "TIME_ONLY"
    if speed > 0:
        days_to_km = max(0, result.next_milestone.odo_milestone_km - anchor.odo_km) / speed
        if days_to_km <= config.horizon_days:
            km_at = utc(anchor.recorded_at) + timedelta(days=days_to_km)
            out.km_forecast_date = today_vn(km_at)
            out.possibly_reached = km_at < now
            if out.km_forecast_date <= out.projected_due_date:
                out.projected_due_date = out.km_forecast_date
                out.basis = "KM_FORECAST"
    return out
