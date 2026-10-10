"""Two-tier booking pricing — dependency injection."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.storage import get_file_storage_for_bucket
from src.infrastructure.supabase.db import get_session
from src.modules.notification.channels import NotificationService
from src.modules.notification.dependency import get_notification_service
from src.modules.notification.owner_notifier import OwnerNotifier
from src.modules.service_progress.dependency import get_service_progress_service
from src.modules.service_progress.service import ServiceProgressService

from .photos import LinePhotos
from .service import BookingLineService

logger = logging.getLogger(__name__)


def get_line_photos() -> LinePhotos | None:
    """None when the storage is not configured: lines still work, photos are hidden."""
    s = get_settings()
    try:
        storage = get_file_storage_for_bucket(s.booking_line_photo_bucket)
    except Exception:  # noqa: BLE001 — missing Supabase credentials in dev/test
        logger.warning("booking_line.photo_storage_unavailable")
        return None
    return LinePhotos(storage, url_ttl_seconds=s.booking_line_photo_url_ttl_seconds)


def get_booking_line_service(
    session: Annotated[Session, Depends(get_session)],
    notifications: Annotated[NotificationService, Depends(get_notification_service)],
    progress: Annotated[ServiceProgressService, Depends(get_service_progress_service)],
    photos: Annotated[LinePhotos | None, Depends(get_line_photos)],
) -> BookingLineService:
    s = get_settings()
    return BookingLineService(
        session,
        photos=photos,
        notifier=OwnerNotifier(session, notifications),
        progress=progress,
        app_base_url=s.app_base_url or s.frontend_url,
    )
