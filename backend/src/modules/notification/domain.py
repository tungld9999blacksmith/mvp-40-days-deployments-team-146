"""Notification module - reminder rules as pure functions (FEAT-NOTI-001 BR-501, BR-509).

No FastAPI, no Session: the service loads the inputs and calls these functions.
"""

from __future__ import annotations

from src.common.core.maintenance.reminder import ReminderChannel, ReminderLevel
from src.modules.user_vehicle.domain import DueResult, DueStatus

from .channels import NotificationMessage

# External channels, in the order used everywhere the channel list is shown.
# Reminders are always shown in the in-app feed, whatever is enabled here.
ALL_CHANNELS: tuple[ReminderChannel, ...] = (
    ReminderChannel.ZALO,
    ReminderChannel.TELEGRAM,
    ReminderChannel.SMS,
    ReminderChannel.EMAIL,
)
DEFAULT_CHANNELS: frozenset[ReminderChannel] = frozenset()

MIN_LEAD_DAYS = 0
MAX_LEAD_DAYS = 30


def decide_level(result: DueResult, *, lead_days: int, due_soon_km: int) -> ReminderLevel | None:
    """BR-501: which reminder level (if any) the vehicle has reached."""
    milestone = result.next_milestone
    if result.due_status is DueStatus.UNKNOWN or milestone is None:
        return None
    if result.due_status is DueStatus.OVERDUE:
        return ReminderLevel.EXPIRED
    if result.remaining_days is not None and result.remaining_days <= lead_days:
        return ReminderLevel.EARLY
    if result.remaining_km is not None and result.remaining_km <= due_soon_km:
        return ReminderLevel.EARLY
    return None


def mask_plate(plate: str) -> str:
    """Keep the first and last two characters (``30A12345`` -> ``30****45``)."""
    if len(plate) <= 4:
        return plate
    return plate[:2] + "*" * (len(plate) - 4) + plate[-2:]


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def build_message(
    *,
    model_name: str,
    license_plate: str,
    result: DueResult,
    level: ReminderLevel,
    app_url: str = "",
) -> NotificationMessage:
    """BR-509: no VIN / phone / email / national id; plate partly masked; link to the app."""
    milestone = result.next_milestone
    vehicle = f"{model_name} ({mask_plate(license_plate)})"
    days = result.remaining_days or 0
    km = result.remaining_km

    if level is ReminderLevel.EXPIRED:
        overdue: list[str] = []
        if days < 0:
            overdue.append(_plural(-days, "day"))
        if km is not None and km < 0:
            overdue.append(f"{-km:,} km")
        how_late = " and ".join(overdue) if overdue else "just now"
        subject = "Maintenance overdue"
        body = (
            f"Your {vehicle} is overdue for the {milestone.label} maintenance "
            f"(due {milestone.due_date.isoformat()}, overdue by {how_late})."
        )
    else:
        left: list[str] = []
        if days >= 0:
            left.append(_plural(days, "day") if days else "today")
        if km is not None and km >= 0:
            left.append(f"{km:,} km")
        remaining = " / ".join(left) if left else "very soon"
        subject = "Maintenance coming up"
        body = (
            f"Your {vehicle} is approaching the {milestone.label} maintenance "
            f"(due {milestone.due_date.isoformat()}, remaining: {remaining})."
        )

    link = f"{app_url.rstrip('/')}/booking" if app_url else None
    if link:
        body += f" Book a visit: {link}"
    return NotificationMessage(subject=subject, body=body, link=link)
