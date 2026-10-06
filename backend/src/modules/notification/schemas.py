"""Notification module - request / response schemas (camelCase JSON, ``{"data": ...}`` envelope).

Shapes follow ``docs/specs/sprint-2/api/us-021-sprint-2-spec.api.md`` §C.5, API-NOTI-002.
"""

from __future__ import annotations

from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NotificationChannel(StrEnum):
    ZALO = "ZALO"
    TELEGRAM = "TELEGRAM"
    SMS = "SMS"
    EMAIL = "EMAIL"


class ChannelStatus(StrEnum):
    CONNECTED = "CONNECTED"
    NOT_CONNECTED = "NOT_CONNECTED"
    COMING_SOON = "COMING_SOON"


class ChannelSettingOut(CamelModel):
    channel: NotificationChannel
    enabled: bool
    available: bool
    status: ChannelStatus


class NotificationSettingsOut(CamelModel):
    reminders_enabled: bool
    reminder_lead_days: int
    default_reminder_lead_days: int
    channels: list[ChannelSettingOut]


class NotificationSettingsEnvelope(CamelModel):
    data: NotificationSettingsOut


class ChannelChangeIn(CamelModel):
    channel: NotificationChannel
    enabled: bool


class NotificationSettingsUpdateIn(CamelModel):
    reminders_enabled: bool | None = None
    # Range is checked in the service so the error code is INVALID_LEAD_DAYS (API-NOTI-002).
    reminder_lead_days: int | None = None
    channels: list[ChannelChangeIn] | None = None


# ── API-NOTI-003 in-app feed (derived, no notification table) ──
class ReminderRefOut(CamelModel):
    user_vehicle_id: UUID
    level: str  # EARLY | WARNING | URGENT | EXPIRED
    odo_milestone_km: int
    resolved: bool


class BookingRefOut(CamelModel):
    booking_id: UUID
    booking_code: str
    status: str  # CONFIRMED | CANCELLED | COMPLETED
    reason_code: str | None = None
    booking_date: date
    time_slot: time
    workshop_name: str | None = None


class FollowUpRefOut(CamelModel):
    follow_up_id: UUID
    booking_id: UUID
    workshop_name: str | None = None


class NotificationOut(CamelModel):
    """One feed entry; exactly one of the ``*Ref`` blocks matches ``kind``.

    ``unread`` is true only for a survey waiting for an answer — the other
    kinds have no read state.
    """

    id: str
    kind: str  # MAINTENANCE_REMINDER | BOOKING_UPDATE | FOLLOW_UP
    occurred_at: datetime
    unread: bool
    reminder: ReminderRefOut | None = None
    booking: BookingRefOut | None = None
    follow_up: FollowUpRefOut | None = None


class NotificationFeedOut(CamelModel):
    items: list[NotificationOut]
    unread_count: int


class NotificationFeedEnvelope(CamelModel):
    data: NotificationFeedOut
