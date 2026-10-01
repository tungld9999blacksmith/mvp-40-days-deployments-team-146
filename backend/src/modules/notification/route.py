"""Notification module - HTTP endpoints (API-NOTI-001..002).

Spec: ``docs/specs/sprint-2/api/us-021-sprint-2-spec.api.md``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.core.identity.vehicle_user import VehicleUser
from src.modules.user_vehicle.dependency import require_active_vehicle_owner

from . import schemas
from .dependency import get_notification_settings_service
from .settings_service import NotificationSettingsService

router = APIRouter(prefix="/notification-settings", tags=["notification-settings"])


@router.get(
    "",
    response_model=schemas.NotificationSettingsEnvelope,
    summary="Reminder switch, lead days and channels of the signed-in owner",
)
async def get_notification_settings(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[NotificationSettingsService, Depends(get_notification_settings_service)],
) -> schemas.NotificationSettingsEnvelope:
    return schemas.NotificationSettingsEnvelope(data=service.get(user))


@router.put(
    "",
    response_model=schemas.NotificationSettingsEnvelope,
    summary="Save reminder switch, lead days and channels",
)
async def update_notification_settings(
    payload: schemas.NotificationSettingsUpdateIn,
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[NotificationSettingsService, Depends(get_notification_settings_service)],
) -> schemas.NotificationSettingsEnvelope:
    return schemas.NotificationSettingsEnvelope(data=service.update(user, payload))
