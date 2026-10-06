"""Notification module - HTTP endpoints (API-NOTI-001..003).

Spec: ``docs/specs/sprint-2/api/us-021-sprint-2-spec.api.md``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.core.identity.vehicle_user import VehicleUser
from src.modules.user_vehicle.dependency import require_active_vehicle_owner

from . import schemas
from .dependency import get_notification_feed_service, get_notification_settings_service
from .feed_service import NotificationFeedService
from .settings_service import NotificationSettingsService

router = APIRouter(prefix="/notification-settings", tags=["notification-settings"])


@router.get(
    "",
    response_model=schemas.NotificationSettingsEnvelope,
    summary="Reminder switch, lead days and channels of the signed-in owner",
)
def get_notification_settings(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[NotificationSettingsService, Depends(get_notification_settings_service)],
) -> schemas.NotificationSettingsEnvelope:
    return schemas.NotificationSettingsEnvelope(data=service.get(user))


@router.put(
    "",
    response_model=schemas.NotificationSettingsEnvelope,
    summary="Save reminder switch, lead days and channels",
)
def update_notification_settings(
    payload: schemas.NotificationSettingsUpdateIn,
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[NotificationSettingsService, Depends(get_notification_settings_service)],
) -> schemas.NotificationSettingsEnvelope:
    return schemas.NotificationSettingsEnvelope(data=service.update(user, payload))


feed_router = APIRouter(prefix="/notifications", tags=["notifications"])


@feed_router.get(
    "",
    response_model=schemas.NotificationFeedEnvelope,
    summary="In-app feed: reminders, booking updates and surveys (last 90 days)",
)
def list_notifications(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[NotificationFeedService, Depends(get_notification_feed_service)],
) -> schemas.NotificationFeedEnvelope:
    return schemas.NotificationFeedEnvelope(data=service.list_for_user(user))
