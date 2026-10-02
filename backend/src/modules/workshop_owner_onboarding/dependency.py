"""Workshop-owner onboarding — dependency injection (composition root)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.common.core.identity.vehicle_user import UserStatus
from src.common.core.identity.workshop_owner import WorkshopOwner, WorkshopOwnerOnboardingStatus
from src.config import Settings, get_settings
from src.infrastructure.oem.gateway import HttpOemServiceCenterGateway
from src.infrastructure.supabase.db import get_session
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.workshop_owner_auth.dependency import build_workshop_auth_service

from . import errors
from .ports import OemServiceCenterGateway, SignInAuditor, VerificationRetryScheduler
from .scheduler import CeleryVerificationRetryScheduler
from .service import WorkshopOnboardingService


def get_service_center_gateway() -> OemServiceCenterGateway:
    settings = get_settings()
    return HttpOemServiceCenterGateway(settings.oem_api_base_url, timeout_seconds=settings.oem_api_timeout_seconds)


def get_retry_scheduler() -> VerificationRetryScheduler:
    return CeleryVerificationRetryScheduler()


def get_sign_in_auditor(session: Annotated[Session, Depends(get_session)]) -> SignInAuditor:
    """Sign-in audit is written by the workshop-owner auth module (FEAT-AUTH-004)
    on the same DB session, hence in the same transaction as ``last_login_at``."""
    return build_workshop_auth_service(session)


def build_workshop_onboarding_service(
    session: Session,
    gateway: OemServiceCenterGateway,
    scheduler: VerificationRetryScheduler,
    settings: Settings | None = None,
    auditor: SignInAuditor | None = None,
) -> WorkshopOnboardingService:
    """Shared by the FastAPI dependency and the Celery worker."""
    settings = settings or get_settings()
    return WorkshopOnboardingService(
        session,
        gateway,
        scheduler,
        retention_days=settings.onboarding_retention_days,
        max_failed_attempts=settings.workshop_verify_max_failed_attempts,
        retry_delays_seconds=settings.workshop_verify_retry_delays,
        policy_versions=settings.workshop_consent_policy_version_list,
        auditor=auditor,
    )


def get_workshop_onboarding_service(
    session: Annotated[Session, Depends(get_session)],
    gateway: Annotated[OemServiceCenterGateway, Depends(get_service_center_gateway)],
    scheduler: Annotated[VerificationRetryScheduler, Depends(get_retry_scheduler)],
    auditor: Annotated[SignInAuditor, Depends(get_sign_in_auditor)],
) -> WorkshopOnboardingService:
    return build_workshop_onboarding_service(session, gateway, scheduler, auditor=auditor)


def get_current_workshop_owner(
    claims: Annotated[dict, Depends(verify_firebase_token)],
    service: Annotated[WorkshopOnboardingService, Depends(get_workshop_onboarding_service)],
) -> WorkshopOwner:
    """The signed-in workshop owner (API-202..204). Never trusts a client id."""
    owner = service.find_owner_by_firebase_uid(claims.get("uid"))
    if owner is None:
        raise errors.WorkshopOwnerNotRegisteredError()
    if owner.status != UserStatus.ACTIVE:
        raise errors.AccountLockedError(suspended=owner.status == UserStatus.SUSPENDED)
    return owner


def require_active_workshop_owner(
    owner: Annotated[WorkshopOwner, Depends(get_current_workshop_owner)],
) -> WorkshopOwner:
    """Guard for workshop-management APIs (BR-203)."""
    if owner.onboarding_status != WorkshopOwnerOnboardingStatus.ACTIVE:
        raise errors.WorkshopOnboardingError("Vui lòng hoàn tất onboarding trước.", code="ONBOARDING_REQUIRED")
    return owner
