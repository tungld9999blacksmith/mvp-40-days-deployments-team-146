"""Notification module - request / response schemas (camelCase JSON, ``{"data": ...}`` envelope).

Shapes follow ``docs/specs/sprint-2/api/us-021-sprint-2-spec.api.md`` §C.5, API-NOTI-002.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class NotificationChannel(StrEnum):
    DISCORD = "DISCORD"
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
