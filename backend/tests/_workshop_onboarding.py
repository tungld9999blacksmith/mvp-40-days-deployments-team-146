"""Shared test helpers for the workshop-owner onboarding module (FEAT-AUTH-003).

In-memory SQLite with the workshop tables, a configurable OEM gateway stub and
a recording retry scheduler — tests never touch Postgres, Celery or the mock
HTTP service.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from ev_contracts import (
    ManagerVerifyFailureReason,
    ManagerVerifyRequest,
    ManagerVerifyResponse,
    ServiceCenterInfo,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from src.common.core.identity import workshop_owner as _workshop_owner
from src.common.core.workshop import workshop as _workshop
from src.modules.workshop_owner_auth import domain as _auth_domain
from src.modules.workshop_owner_onboarding import domain as _domain
from src.modules.workshop_owner_onboarding.ports import (
    OemServiceCenterGateway,
    OemTimeoutError,
    SignInAuditor,
    VerificationRetryScheduler,
)
from src.modules.workshop_owner_onboarding.service import WorkshopOnboardingService

WORKSHOP_TABLES = [
    _workshop_owner.WorkshopOwner.__table__,
    _workshop.Workshop.__table__,
    _workshop.WorkshopOperatingHour.__table__,
    _domain.WorkshopRegistration.__table__,
    _domain.WorkshopVerificationAttempt.__table__,
    _domain.WorkshopOwnerConsent.__table__,
    _auth_domain.WorkshopAuthEvent.__table__,
]

# Manager record of SC-01 in mock-ev-system.
MANAGER_EMAIL = "ha.tran.sc01@example.com"
MANAGER_NATIONAL_ID = "001190000101"
POLICY_VERSION = "WS-2026-09"
RETRY_DELAYS = [60, 120, 300, 600, 720]


def make_engine():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine, tables=WORKSHOP_TABLES)
    return engine


def make_session() -> Iterator[Session]:
    with Session(make_engine()) as session:
        yield session


def center(center_id: str = "SC-01") -> ServiceCenterInfo:
    return ServiceCenterInfo(
        center_id=center_id, name="VinFast Thăng Long", region="Hà Nội", type="dealer"
    )


def verified_response(center_id: str = "SC-01") -> ManagerVerifyResponse:
    return ManagerVerifyResponse(verified=True, service_center=center(center_id))


def failure_response(reason: ManagerVerifyFailureReason) -> ManagerVerifyResponse:
    return ManagerVerifyResponse(verified=False, failure_reason=reason)


class StubServiceCenterGateway(OemServiceCenterGateway):
    """Returns ``result``; raises a timeout while ``timeouts_left > 0``."""

    def __init__(
        self, *, result: ManagerVerifyResponse | None = None, timeouts: int = 0
    ) -> None:
        self.result = result or verified_response()
        self.timeouts_left = timeouts
        self.calls: list[ManagerVerifyRequest] = []

    async def verify_manager(self, request: ManagerVerifyRequest) -> ManagerVerifyResponse:
        self.calls.append(request)
        if self.timeouts_left > 0:
            self.timeouts_left -= 1
            raise OemTimeoutError("stub timeout")
        return self.result


class RecordingScheduler(VerificationRetryScheduler):
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.scheduled: list[tuple[UUID, int]] = []

    def schedule(self, attempt_id: UUID, *, delay_seconds: int) -> None:
        if self.fail:
            raise RuntimeError("broker down")
        self.scheduled.append((attempt_id, delay_seconds))


def make_service(
    session: Session,
    gateway: StubServiceCenterGateway | None = None,
    scheduler: RecordingScheduler | None = None,
    *,
    max_failed_attempts: int = 5,
    auditor: SignInAuditor | None = None,
) -> WorkshopOnboardingService:
    return WorkshopOnboardingService(
        session,
        gateway or StubServiceCenterGateway(),
        scheduler or RecordingScheduler(),
        retention_days=15,
        max_failed_attempts=max_failed_attempts,
        retry_delays_seconds=RETRY_DELAYS,
        policy_versions=[POLICY_VERSION],
        auditor=auditor,
    )


def claims(uid: str = "ws-uid-1", email: str = MANAGER_EMAIL, **extra) -> dict:
    return {
        "uid": uid,
        "email": email,
        "email_verified": True,
        "name": "Ha Tran",
        "firebase": {"sign_in_provider": "google.com"},
        **extra,
    }


def profile_body(
    *, phone: str = "0912 000 101", national_id: str = MANAGER_NATIONAL_ID, granted: bool = True
) -> dict:
    return {
        "fullName": "Trần Thu Hà",
        "phoneNumber": phone,
        "nationalId": national_id,
        "personalDataConsent": {"granted": granted, "policyVersion": POLICY_VERSION},
    }


def week_hours() -> list[dict]:
    hours = [
        {"dayOfWeek": d, "isClosed": False, "openTime": "08:00", "closeTime": "17:30"}
        for d in range(1, 7)
    ]
    hours.append({"dayOfWeek": 7, "isClosed": True, "openTime": None, "closeTime": None})
    return hours


def verification_body(**overrides) -> dict:
    body = {
        "address": "Số 8 Phạm Hùng, Mễ Trì, Nam Từ Liêm, Hà Nội",
        "latitude": 21.017,
        "longitude": 105.781,
        "hotline": "024 3765 4321",
        "totalTechnicians": 12,
        "emergencySlotsReserved": 2,
        "operatingHours": week_hours(),
        "oemDataSharingConsent": {"granted": True, "policyVersion": POLICY_VERSION},
    }
    body.update(overrides)
    return body
