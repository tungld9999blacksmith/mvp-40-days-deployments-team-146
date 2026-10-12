"""Notification module - reads an owner's effective preferences (BR-504, BR-505, BR-ENT-451)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import UserNotificationChannel, UserNotificationSetting

from .domain import DEFAULT_CHANNELS


@dataclass(frozen=True)
class Preferences:
    reminders_enabled: bool
    lead_days: int
    channels: frozenset[ReminderChannel]  # channels the owner turned on
    has_channel_rows: bool
    personalized_reminders_enabled: bool = False
    preferred_send_time: str | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    timezone: str = "Asia/Ho_Chi_Minh"


def channel_rows(session: Session, user_id: int) -> dict[ReminderChannel, bool]:
    rows = session.exec(
        select(UserNotificationChannel)
        .where(UserNotificationChannel.user_id == user_id)
        .execution_options(populate_existing=True)
    ).all()
    return {row.channel: row.is_enabled for row in rows}


def effective_channels(rows: dict[ReminderChannel, bool]) -> frozenset[ReminderChannel]:
    """No rows -> the default (no external channel); otherwise the enabled ones."""
    if not rows:
        return DEFAULT_CHANNELS
    return frozenset(channel for channel, enabled in rows.items() if enabled)


def load_preferences(session: Session, user_id: int, *, default_lead_days: int) -> Preferences:
    from src.modules.vehicle_usage.service import consent_enabled

    setting = session.exec(
        select(UserNotificationSetting)
        .where(UserNotificationSetting.user_id == user_id)
        .execution_options(populate_existing=True)
    ).first()
    rows = channel_rows(session, user_id)
    return Preferences(
        reminders_enabled=setting.reminders_enabled if setting else True,
        lead_days=setting.reminder_lead_days if setting else default_lead_days,
        channels=effective_channels(rows),
        has_channel_rows=bool(rows),
        personalized_reminders_enabled=consent_enabled(setting),
        preferred_send_time=setting.preferred_send_time if setting else None,
        quiet_hours_start=setting.quiet_hours_start if setting else None,
        quiet_hours_end=setting.quiet_hours_end if setting else None,
        timezone=setting.timezone if setting else "Asia/Ho_Chi_Minh",
    )
