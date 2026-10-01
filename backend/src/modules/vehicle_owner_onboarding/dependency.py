"""Onboarding module — dependency injection (composition root).

Wires the DB session + manufacturer gateway into ``OnboardingService`` and
exposes the authenticated-user dependency used by the read/write endpoints.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.common.core.identity.vehicle_user import UserStatus, VehicleUser
from src.config import get_settings
from src.infrastructure.oem.gateway import HttpOemVehicleGateway
from src.infrastructure.supabase.db import get_session
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.oem_integration.dependency import get_sync_scheduler
from src.modules.oem_integration.ports import SyncScheduler

from . import errors
from .service import OnboardingService


def get_oem_gateway() -> HttpOemVehicleGateway:
    settings = get_settings()
    return HttpOemVehicleGateway(
        settings.oem_api_base_url,
        timeout_seconds=settings.oem_api_timeout_seconds,
    )


def get_onboarding_service(
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[HttpOemVehicleGateway, Depends(get_oem_gateway)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
) -> OnboardingService:
    settings = get_settings()
    return OnboardingService(
        session,
        gateway,
        retention_days=settings.onboarding_retention_days,
        max_failed_attempts=settings.vehicle_verify_max_failed_attempts,
        policy_version=settings.consent_policy_version,
        sync_scheduler=scheduler,
    )


def get_current_user(
    claims: Annotated[dict, Depends(verify_firebase_token)],
    service: Annotated[OnboardingService, Depends(get_onboarding_service)],
) -> VehicleUser:
    """Resolve the signed-in account from the Firebase token.

    The user must have completed sign-in (API-001) and not be locked.
    ``user_id`` is never taken from the client — only the token's ``uid``.
    """
    user = service.find_user_by_firebase_uid(claims.get("uid"))
    if user is None:
        raise errors.UserNotRegisteredError()
    if user.status != UserStatus.ACTIVE:
        raise errors.AccountLockedError(suspended=user.status == UserStatus.SUSPENDED)
    return user
