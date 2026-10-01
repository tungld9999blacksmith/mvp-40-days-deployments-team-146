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


def channel_rows(session: Session, user_id: int) -> dict[ReminderChannel, bool]:
    rows = session.exec(
        select(UserNotificationChannel).where(UserNotificationChannel.user_id == user_id)
    ).all()
    return {row.channel: row.is_enabled for row in rows}


def effective_channels(rows: dict[ReminderChannel, bool]) -> frozenset[ReminderChannel]:
    """No rows -> the default (Discord only); otherwise the enabled ones."""
    if not rows:
        return DEFAULT_CHANNELS
    return frozenset(channel for channel, enabled in rows.items() if enabled)


def load_preferences(session: Session, user_id: int, *, default_lead_days: int) -> Preferences:
    setting = session.get(UserNotificationSetting, user_id)
    rows = channel_rows(session, user_id)
    return Preferences(
        reminders_enabled=setting.reminders_enabled if setting else True,
        lead_days=setting.reminder_lead_days if setting else default_lead_days,
        channels=effective_channels(rows),
        has_channel_rows=bool(rows),
    )
