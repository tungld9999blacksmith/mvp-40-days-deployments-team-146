"""Notification module - dependency injection (composition root)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.supabase.db import get_session

from .channels import NotificationService
from .feed_service import NotificationFeedService
from .settings_service import NotificationSettingsService


def build_notification_service(session: Session) -> NotificationService:
    """Registers every implemented external channel. New channels are added here.

    None is implemented yet: reminders and other events reach the owner through
    the in-app feed (API-NOTI-003) only.
    """
    return NotificationService()


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
    )


def get_notification_feed_service(session: Annotated[Session, Depends(get_session)]) -> NotificationFeedService:
    return NotificationFeedService(session)
