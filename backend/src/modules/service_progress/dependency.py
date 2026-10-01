"""Service progress — dependency injection (us-057)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.supabase.db import get_session
from src.modules.notification.channels import NotificationService
from src.modules.notification.dependency import get_notification_service
from src.modules.notification.owner_notifier import OwnerNotifier

from .service import ServiceProgressService


def get_service_progress_service(
    session: Annotated[Session, Depends(get_session)],
    notifications: Annotated[NotificationService, Depends(get_notification_service)],
) -> ServiceProgressService:
    settings = get_settings()
    return ServiceProgressService(
        session,
        enabled=settings.feature_service_progress_enabled,
        notifier=OwnerNotifier(session, notifications),
        app_base_url=settings.app_base_url or settings.frontend_url,
    )
