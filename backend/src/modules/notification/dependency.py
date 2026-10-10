"""Notification module - dependency injection (composition root)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import Settings, get_settings
from src.infrastructure.supabase.db import get_session

from .adapters import EsmsConfig, EsmsSmsAdapter
from .channels import NotificationChannelAdapter, NotificationService
from .email_service import MaintenanceEmailAdapter, email_configuration_ready
from .feed_service import NotificationFeedService
from .settings_service import NotificationSettingsService


def configured_adapters(session: Session, settings: Settings) -> list[NotificationChannelAdapter]:
    """External channels whose provider settings are filled in. New channels are added here.

    Email (Resend) supports maintenance reminders only; SMS (eSMS) carries every
    message. Zalo and Telegram have no adapter yet; everything always reaches
    the owner through the in-app feed (API-NOTI-003) too.
    """
    adapters: list[NotificationChannelAdapter] = []
    if email_configuration_ready(settings):
        adapters.append(MaintenanceEmailAdapter(session, settings))
    if settings.esms_api_key and settings.esms_secret_key and settings.esms_brandname:
        adapters.append(
            EsmsSmsAdapter(
                session,
                EsmsConfig(
                    api_key=settings.esms_api_key,
                    secret_key=settings.esms_secret_key,
                    brandname=settings.esms_brandname,
                    sms_type=settings.esms_sms_type,
                    unicode=settings.esms_unicode,
                    sandbox=settings.esms_sandbox,
                    timeout_seconds=settings.esms_timeout_seconds,
                ),
            )
        )
    return adapters


def build_notification_service(session: Session) -> NotificationService:
    return NotificationService(configured_adapters(session, get_settings()))


def get_notification_service(
    session: Annotated[Session, Depends(get_session)],
) -> NotificationService:
    return build_notification_service(session)


def get_notification_settings_service(
    session: Annotated[Session, Depends(get_session)],
    notifier: Annotated[NotificationService, Depends(get_notification_service)],
) -> NotificationSettingsService:
    return NotificationSettingsService(
        session,
        available_channels=notifier.available_channels(),
        default_lead_days=get_settings().reminder_default_lead_days,
        email_mode=get_settings().email_mode,
    )


def get_notification_feed_service(session: Annotated[Session, Depends(get_session)]) -> NotificationFeedService:
    return NotificationFeedService(session)
