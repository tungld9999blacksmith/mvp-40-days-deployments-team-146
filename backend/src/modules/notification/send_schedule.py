"""Owner-selected delivery windows; UTC persistence, local calendar decisions."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.modules.vehicle_usage.domain import utc


def active(prefs) -> bool:
    return bool(prefs.preferred_send_time or prefs.quiet_hours_start)


def in_quiet(value: time, start: time, end: time) -> bool:
    return start <= value < end if start < end else value >= start or value < end


def local_instant(day, value, zone, earliest):
    # Round-trip normalizes a missing DST hour forward. Both folds are considered
    # so an ambiguous time never schedules an instant earlier than requested.
    local = datetime.combine(day, value, tzinfo=zone)
    candidates = sorted({utc(local.replace(fold=fold)) for fold in (0, 1)})
    valid = [
        at
        for at in candidates
        if at.astimezone(zone).replace(tzinfo=None) >= local.replace(tzinfo=None) and at >= earliest
    ]
    return min(valid) if valid else utc(local + timedelta(days=1))


def next_allowed_at(earliest: datetime, prefs, *, initial: bool = False) -> datetime:
    candidate = utc(earliest)
    zone = ZoneInfo(prefs.timezone)
    preferred = time.fromisoformat(prefs.preferred_send_time) if prefs.preferred_send_time else None
    start = time.fromisoformat(prefs.quiet_hours_start) if prefs.quiet_hours_start else None
    end = time.fromisoformat(prefs.quiet_hours_end) if prefs.quiet_hours_end else None
    # A selected time inside quiet hours moves to their end, consistently every day.
    if preferred and start and in_quiet(preferred, start, end):
        preferred = end
    if initial and preferred:
        local = candidate.astimezone(zone)
        if (local.hour, local.minute) != (preferred.hour, preferred.minute):
            candidate = local_instant(local.date(), preferred, zone, candidate)
    for _ in range(8):
        local = candidate.astimezone(zone)
        wall = local.timetz().replace(tzinfo=None)
        if preferred and wall < preferred:
            candidate = local_instant(local.date(), preferred, zone, candidate)
            continue
        if start and in_quiet(wall, start, end):
            day = local.date() + timedelta(days=int(start > end and wall >= start))
            candidate = local_instant(day, end, zone, candidate)
            continue
        return candidate
    raise ValueError("No valid delivery window")


def eligible_at(now, prefs, due_at):
    """Allow the dispatcher tick just after midnight for a late-night slot.

    This bounded grace never overrides quiet hours or a future due instant.
    """
    now = utc(now)
    allowed = next_allowed_at(now, prefs)
    if due_at and timedelta(0) <= now - utc(due_at) <= timedelta(minutes=15):
        wall = now.astimezone(ZoneInfo(prefs.timezone)).timetz().replace(tzinfo=None)
        if not prefs.quiet_hours_start or not in_quiet(
            wall, time.fromisoformat(prefs.quiet_hours_start), time.fromisoformat(prefs.quiet_hours_end)
        ):
            return now
    return allowed
