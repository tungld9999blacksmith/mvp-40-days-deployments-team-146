"""User-vehicle module — dependency injection and guards (API spec §C.2)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import OnboardingStatus, UserStatus, VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.vehicle import UserVehicle
from src.config import get_settings
from src.infrastructure.supabase.db import get_session
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.oem_integration.dependency import get_sync_scheduler
from src.modules.oem_integration.ports import SyncScheduler

from . import errors
from .domain import DueConfig
from .service import UserVehicleService


def get_due_config() -> DueConfig:
    settings = get_settings()
    return DueConfig(
        due_soon_km=settings.due_soon_km,
        due_soon_days=settings.due_soon_days,
        recurring_km=settings.maintenance_recurring_km,
        recurring_months=settings.maintenance_recurring_months,
        odo_stale_days=settings.odo_stale_days,
    )


def get_user_vehicle_service(
    session: Annotated[Session, Depends(get_session)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
    config: Annotated[DueConfig, Depends(get_due_config)],
) -> UserVehicleService:
    return UserVehicleService(session, scheduler, config=config)


def require_active_vehicle_owner(
    claims: Annotated[dict, Depends(verify_firebase_token)],
    session: Annotated[Session, Depends(get_session)],
) -> VehicleUser:
    """Vehicle owner with an ACTIVE account that finished onboarding (BR-003 of FEAT-AUTH-001)."""
    uid = claims.get("uid")
    user = session.exec(select(VehicleUser).where(VehicleUser.firebase_uid == uid)).first()
    if user is None:
        is_workshop_owner = session.exec(
            select(WorkshopOwner.id).where(WorkshopOwner.firebase_uid == uid)
        ).first()
        raise errors.ForbiddenError() if is_workshop_owner else errors.UserNotRegisteredError()
    if user.status != UserStatus.ACTIVE:
        raise errors.AccountLockedError(suspended=user.status == UserStatus.SUSPENDED)
    if user.onboarding_status != OnboardingStatus.ACTIVE:
        raise errors.OnboardingRequiredError()
    return user


def get_owned_active_vehicle(
    user_vehicle_id: Annotated[UUID, Path(alias="userVehicleId")],
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[UserVehicleService, Depends(get_user_vehicle_service)],
) -> UserVehicle:
    return service.get_owned_active_vehicle(user, user_vehicle_id)
