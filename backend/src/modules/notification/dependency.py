"""Notification module - dependency injection (composition root)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.supabase.db import get_session

from .adapters import LoggingDiscordAdapter
from .channels import NotificationService
from .settings_service import NotificationSettingsService


def build_notification_service(session: Session) -> NotificationService:
    """Registers every implemented channel. New channels are added here."""
    return NotificationService([LoggingDiscordAdapter(session)])


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
