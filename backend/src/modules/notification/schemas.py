"""Notification module - request / response schemas (camelCase JSON, ``{"data": ...}`` envelope).

Shapes follow ``docs/specs/sprint-2/api/us-021-sprint-2-spec.api.md`` §C.5, API-NOTI-002.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator, model_validator
from pydantic.alias_generators import to_camel

from src.common.money import Money


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


class QuietHours(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    start: str
    end: str

    @field_validator("start", "end", mode="before")
    @classmethod
    def valid_time(cls, value):
        if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
            raise ValueError("Time must be HH:mm")
        return value

    @model_validator(mode="after")
    def nonempty_window(self):
        if self.start == self.end:
            raise ValueError("Quiet hours cannot cover the whole day")
        return self


class NotificationSettingsOut(CamelModel):
    send_schedule_available: bool = False
    preferred_send_time: str | None = None
    quiet_hours: QuietHours | None = None
    timezone: str = "Asia/Ho_Chi_Minh"
    personalized_reminders_enabled: bool = False
    personalization_available: bool = True
    personalization_mode: str = "shadow"
    personalization_policy_version: str = "driving-usage-2026-10-v1"
    personalization_consent_at: datetime | None = None
    reminders_enabled: bool
    reminder_lead_days: int
    default_reminder_lead_days: int
    channels: list[ChannelSettingOut]
    email_recipient: str | None = None
    email_verified: bool = False
    email_suppressed: bool = False
    email_transport: str = "off"
    email_scope: str = "MAINTENANCE_REMINDER"
    scope: str = "ALL_OWNED_VEHICLES"


class NotificationSettingsEnvelope(CamelModel):
    data: NotificationSettingsOut


class ChannelChangeIn(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    channel: NotificationChannel
    enabled: StrictBool


class NotificationSettingsUpdateIn(CamelModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    reminders_enabled: StrictBool | None = None
    # Range is checked in the service so the error code is INVALID_LEAD_DAYS (API-NOTI-002).
    reminder_lead_days: StrictInt | None = None
    channels: list[ChannelChangeIn] | None = None
    personalized_reminders_enabled: StrictBool | None = None
    personalization_policy_version: str | None = None
    preferred_send_time: str | None = None
    quiet_hours: QuietHours | None = None
    timezone: str | None = None

    @field_validator("preferred_send_time", mode="before")
    @classmethod
    def validate_send_time(cls, value):
        return None if value is None else QuietHours.valid_time(value)

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_timezone(cls, value):
        if not isinstance(value, str) or len(value) > 64:
            raise ValueError("Timezone must be an IANA name")
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Timezone must be an IANA name") from exc
        return value


# ── API-NOTI-003 in-app feed (derived, no notification table) ──
class ReminderRefOut(CamelModel):
    user_vehicle_id: UUID
    level: str  # EARLY | WARNING | URGENT | EXPIRED
    odo_milestone_km: int
    resolved: bool
    resolution_reason: str | None = None


class QuoteRefOut(CamelModel):
    quote_id: UUID
    status: str  # APPROVED | REJECTED
    approved_total: Money | None = None
    workshop_name: str | None = None


class BookingRefOut(CamelModel):
    booking_id: UUID
    booking_code: str
    status: str  # CONFIRMED | CANCELLED | COMPLETED
    reason_code: str | None = None
    booking_date: date
    time_slot: time
    workshop_name: str | None = None


class BookingReminderRefOut(CamelModel):
    booking_id: UUID
    booking_code: str
    booking_date: date
    time_slot: time
    workshop_name: str | None = None


class FollowUpRefOut(CamelModel):
    follow_up_id: UUID
    booking_id: UUID
    workshop_name: str | None = None


class BookingLineRefOut(CamelModel):
    """A two-tier price line waiting for the owner, a reference price the workshop confirmed,
    or a decision the workshop recorded by phone."""

    booking_id: UUID
    booking_code: str
    line_id: UUID
    kind: str  # PACKAGE | EXTRA
    status: str  # PROPOSED | CONFIRMED | APPROVED / DECLINED (phone decision)
    item_name: str
    price: Money
    is_safety_critical: bool = False
    workshop_name: str | None = None
    decided_via: str | None = None  # PHONE when the workshop recorded the owner's answer
    phone_confirmed_by: str | None = None


class NotificationOut(CamelModel):
    """One feed entry; exactly one of the ``*Ref`` blocks matches ``kind``.

    ``unread`` is true only for a reviewed quote not opened yet, a survey waiting
    for an answer, an appointment reminder the owner has not acted on and a price
    line waiting for the owner's decision — the other kinds have no read state.
    """

    id: str
    kind: str  # MAINTENANCE_REMINDER | QUOTE_RESULT | BOOKING_UPDATE | BOOKING_REMINDER | FOLLOW_UP | BOOKING_LINE
    occurred_at: datetime
    unread: bool
    reminder: ReminderRefOut | None = None
    quote: QuoteRefOut | None = None
    booking: BookingRefOut | None = None
    booking_reminder: BookingReminderRefOut | None = None
    follow_up: FollowUpRefOut | None = None
    booking_line: BookingLineRefOut | None = None


class NotificationFeedOut(CamelModel):
    items: list[NotificationOut]
    unread_count: int


class NotificationFeedEnvelope(CamelModel):
    data: NotificationFeedOut
