"""Service-level tests for workshop-owner onboarding (FEAT-AUTH-003).

Run ``WorkshopOnboardingService`` against in-memory SQLite with a stub OEM
gateway and a recording retry scheduler.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ev_contracts import ManagerVerifyFailureReason
from sqlmodel import select

from src.common.core.identity.vehicle_user import UserStatus
from src.common.core.identity.workshop_owner import WorkshopOwner, WorkshopOwnerOnboardingStatus
from src.common.core.workshop.workshop import Workshop, WorkshopOperatingHour, WorkshopStatus
from src.modules.workshop_owner_onboarding import errors, schemas
from src.modules.workshop_owner_onboarding.domain import (
    WorkshopOwnerConsent,
    WorkshopRegistration,
    WorkshopVerificationAttempt,
    mask_national_id,
    normalize_hotline,
)
from tests._workshop_onboarding import (
    MANAGER_EMAIL,
    MANAGER_NATIONAL_ID,
    RecordingScheduler,
    StubServiceCenterGateway,
    claims,
    failure_response,
    make_service,
    make_session,
    profile_body,
    verification_body,
)


@pytest.fixture
def session():
    yield from make_session()


def _profile(**kwargs) -> schemas.WorkshopProfileUpdateRequest:
    return schemas.WorkshopProfileUpdateRequest.model_validate(profile_body(**kwargs))


def _verification(**overrides) -> schemas.WorkshopVerificationRequest:
    return schemas.WorkshopVerificationRequest.model_validate(verification_body(**overrides))


def _signed_in_with_profile(service) -> WorkshopOwner:
    service.sign_in(claims())
    owner = service.find_owner_by_firebase_uid("ws-uid-1")
    service.update_profile(owner, _profile())
    return owner


async def _submit(service, owner, key: str = "key-1", **overrides):
    return await service.submit_verification(
        owner, _verification(**overrides), idempotency_key=key, trace_id="req-1"
    )


# ======================================================================
# API-201 — sign-in
# ======================================================================
def test_sign_in_creates_owner_in_onboarding(session):
    service = make_service(session)
    data, is_new = service.sign_in(claims())

    assert is_new is True
    assert data.owner.email == MANAGER_EMAIL
    assert data.owner.roles == ["WORKSHOP_OWNER"]
    assert data.onboarding.status == "ONBOARDING_IN_PROGRESS"
    assert data.onboarding.next_step == "PROFILE"
    assert data.onboarding.expires_at is not None
    assert data.workshop is None


def test_sign_in_again_returns_existing_owner(session):
    service = make_service(session)
    first, _ = service.sign_in(claims())
    second, is_new = service.sign_in(claims(name="Ha T."))

    assert is_new is False
    assert second.owner.owner_id == first.owner.owner_id
    assert second.owner.display_name == "Ha T."
    assert len(session.exec(select(WorkshopOwner)).all()) == 1


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"email_verified": False}, "EMAIL_NOT_VERIFIED"),
        ({"firebase": {"sign_in_provider": "password"}}, "UNSUPPORTED_SIGN_IN_PROVIDER"),
    ],
)
def test_sign_in_rejects_invalid_identity(session, overrides, code):
    with pytest.raises(errors.WorkshopOnboardingError) as exc:
        make_service(session).sign_in(claims(**overrides))
    assert exc.value.code == code


def test_sign_in_rejects_email_linked_to_another_uid(session):
    service = make_service(session)
    service.sign_in(claims(uid="uid-a"))
    with pytest.raises(errors.WorkshopOnboardingError) as exc:
        service.sign_in(claims(uid="uid-b"))
    assert exc.value.code == "EMAIL_ALREADY_LINKED"


def test_sign_in_rejects_locked_account(session):
    service = make_service(session)
    service.sign_in(claims())
    owner = service.find_owner_by_firebase_uid("ws-uid-1")
    owner.status = UserStatus.SUSPENDED
    session.add(owner)
    session.commit()

    with pytest.raises(errors.AccountLockedError) as exc:
        service.sign_in(claims())
    assert exc.value.code == "ACCOUNT_SUSPENDED"


def test_sign_in_purges_expired_onboarding_and_starts_over(session):
    service = make_service(session)
    service.sign_in(claims())
    owner = service.find_owner_by_firebase_uid("ws-uid-1")
    old_id = owner.id
    owner.created_at = datetime.now(UTC) - timedelta(days=16)
    session.add(owner)
    session.commit()

    data, is_new = service.sign_in(claims())
    assert is_new is True
    assert data.owner.owner_id != old_id


# ======================================================================
# API-203 — profile
# ======================================================================
def test_update_profile_normalizes_and_masks(session):
    service = make_service(session)
    service.sign_in(claims())
    owner = service.find_owner_by_firebase_uid("ws-uid-1")

    data = service.update_profile(owner, _profile())

    assert data.profile.phone_number == "+84912000101"
    assert data.profile.national_id_masked == "001******101"
    assert data.onboarding.next_step == "WORKSHOP"
    assert data.onboarding.status == "ONBOARDING_IN_PROGRESS"
    assert owner.national_id == MANAGER_NATIONAL_ID
    assert len(session.exec(select(WorkshopOwnerConsent)).all()) == 1


def test_update_profile_twice_records_consent_once(session):
    service = make_service(session)
    owner = _signed_in_with_profile(service)
    service.update_profile(owner, _profile())
    assert len(session.exec(select(WorkshopOwnerConsent)).all()) == 1


@pytest.mark.parametrize(
    "kwargs,code,field",
    [
        ({"national_id": "12345678901A"}, "INVALID_FIELD_FORMAT", "nationalId"),
        ({"phone": "0212345678"}, "INVALID_FIELD_FORMAT", "phoneNumber"),
        ({"granted": False}, "CONSENT_REQUIRED", None),
    ],
)
def test_update_profile_validation(session, kwargs, code, field):
    service = make_service(session)
    service.sign_in(claims())
    owner = service.find_owner_by_firebase_uid("ws-uid-1")
    with pytest.raises(errors.WorkshopOnboardingError) as exc:
        service.update_profile(owner, _profile(**kwargs))
    assert exc.value.code == code
    assert exc.value.field == field


def test_update_profile_rejects_unknown_policy_version(session):
    service = make_service(session)
    service.sign_in(claims())
    owner = service.find_owner_by_firebase_uid("ws-uid-1")
    body = profile_body()
    body["personalDataConsent"]["policyVersion"] = "OLD"
    with pytest.raises(errors.ConsentRequiredError):
        service.update_profile(owner, schemas.WorkshopProfileUpdateRequest.model_validate(body))


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"national_id": MANAGER_NATIONAL_ID, "phone": "0987654321"}, "NATIONAL_ID_ALREADY_IN_USE"),
        ({"national_id": "079190000202", "phone": "0912000101"}, "PHONE_ALREADY_IN_USE"),
    ],
)
def test_update_profile_rejects_identity_used_by_another_owner(session, kwargs, code):
    service = make_service(session)
    _signed_in_with_profile(service)
    service.sign_in(claims(uid="uid-2", email="other@example.com"))
    other = service.find_owner_by_firebase_uid("uid-2")

    with pytest.raises(errors.WorkshopOnboardingError) as exc:
        service.update_profile(other, _profile(**kwargs))
    assert exc.value.code == code


# ======================================================================
# API-204 — verification
# ======================================================================
@pytest.mark.asyncio
async def test_submit_requires_completed_profile(session):
    service = make_service(session)
    service.sign_in(claims())
    owner = service.find_owner_by_firebase_uid("ws-uid-1")
    with pytest.raises(errors.OnboardingStateError) as exc:
        await _submit(service, owner)
    assert exc.value.code == "PROFILE_INCOMPLETE"


@pytest.mark.asyncio
async def test_submit_verified_creates_workshop_and_activates_owner(session):
    gateway = StubServiceCenterGateway()
    service = make_service(session, gateway)
    owner = _signed_in_with_profile(service)

    data, status = await _submit(service, owner)

    assert status == 200
    assert data.verification.status == "VERIFIED"
    assert data.onboarding.status == "ACTIVE"
    assert data.onboarding.next_step == "DASHBOARD"
    assert data.onboarding.expires_at is None
    # The OEM got Gmail + CCCD and decided the workshop (no center chosen by user).
    assert gateway.calls[0].manager_email == MANAGER_EMAIL
    assert gateway.calls[0].manager_national_id == MANAGER_NATIONAL_ID

    ws = data.workshop
    assert ws is not None
    assert (ws.center_id, ws.name, ws.region, ws.type) == ("SC-01", "VinFast Thăng Long", "Hà Nội", "DEALER")
    assert ws.status == "ACTIVE"
    assert ws.hotline == "02437654321"
    assert ws.total_technicians == 12 and ws.emergency_slots_reserved == 2
    assert [h.day_of_week for h in ws.operating_hours] == [1, 2, 3, 4, 5, 6, 7]
    assert ws.operating_hours[6].is_closed is True
    assert ws.operating_hours[0].open_time == "08:00"

    workshop = session.exec(select(Workshop)).one()
    assert workshop.owner_id == owner.id
    assert len(session.exec(select(WorkshopOperatingHour)).all()) == 7
    registration = session.exec(select(WorkshopRegistration)).one()
    assert registration.workshop_id == workshop.id
    assert registration.external_center_id == "SC-01"


@pytest.mark.asyncio
async def test_submit_rejected_by_oem_then_fixed_and_resubmitted(session):
    gateway = StubServiceCenterGateway(
        result=failure_response(ManagerVerifyFailureReason.NATIONAL_ID_MISMATCH)
    )
    service = make_service(session, gateway)
    owner = _signed_in_with_profile(service)

    data, status = await _submit(service, owner, key="k1")
    assert status == 200
    assert data.verification.status == "FAILED"
    assert data.verification.failure_reason == "NATIONAL_ID_MISMATCH"
    assert data.verification.failed_attempts_last24h == 1
    assert data.onboarding.status == "VERIFICATION_FAILED"
    assert data.onboarding.next_step == "WORKSHOP"
    assert session.exec(select(Workshop)).first() is None

    # Profile is editable again after a failure (fix the CCCD), then resubmit.
    service.update_profile(owner, _profile())
    gateway.result = StubServiceCenterGateway().result
    data, status = await _submit(service, owner, key="k2", totalTechnicians=10)
    assert status == 200
    assert data.verification.status == "VERIFIED"
    # Still a single draft row, now verified.
    assert len(session.exec(select(WorkshopRegistration)).all()) == 1
    assert len(session.exec(select(WorkshopVerificationAttempt)).all()) == 2


@pytest.mark.asyncio
async def test_submit_already_claimed_workshop_is_rejected(session):
    service = make_service(session)
    other = WorkshopOwner(firebase_uid="uid-x", email="x@example.com", status=UserStatus.ACTIVE)
    session.add(other)
    session.commit()
    session.add(
        Workshop(
            external_center_id="SC-01", name="VinFast Thăng Long", region="Hà Nội",
            type="dealer", address="Somewhere 123", total_technicians=5,
            owner_id=other.id, hotline="0243000000", onboarded_at=datetime.now(UTC),
        )
    )
    session.commit()
    owner = _signed_in_with_profile(service)

    with pytest.raises(errors.WorkshopAlreadyClaimedError) as exc:
        await _submit(service, owner)

    attempt = session.get(WorkshopVerificationAttempt, exc.value.attempt_id)
    assert attempt.failure_reason == "already_claimed"
    session.refresh(owner)
    assert owner.onboarding_status == WorkshopOwnerOnboardingStatus.VERIFICATION_FAILED
    assert session.exec(select(Workshop)).one().owner_id == other.id


@pytest.mark.asyncio
async def test_submit_claims_existing_ownerless_workshop(session):
    session.add(
        Workshop(
            external_center_id="SC-01", name="Old name", region="Hà Nội", type="dealer",
            address="Old address", total_technicians=3, status=WorkshopStatus.INACTIVE,
        )
    )
    session.commit()
    service = make_service(session)
    owner = _signed_in_with_profile(service)

    data, status = await _submit(service, owner)

    assert status == 200
    workshop = session.exec(select(Workshop)).one()  # no duplicate row (AF-204)
    assert workshop.owner_id == owner.id
    assert workshop.status == WorkshopStatus.ACTIVE
    assert workshop.name == "VinFast Thăng Long"  # re-synced from the OEM
    assert workshop.total_technicians == 12


@pytest.mark.asyncio
async def test_submit_timeout_is_pending_and_background_retry_completes(session):
    gateway = StubServiceCenterGateway(timeouts=1)
    scheduler = RecordingScheduler()
    service = make_service(session, gateway, scheduler)
    owner = _signed_in_with_profile(service)

    data, status = await _submit(service, owner)
    assert status == 202
    assert data.verification.status == "PENDING"
    assert data.onboarding.next_step == "VERIFYING"
    attempt_id, delay = scheduler.scheduled[0]
    assert delay == 60

    # While pending, the owner cannot edit or resubmit.
    with pytest.raises(errors.OnboardingStateError) as exc:
        service.update_profile(owner, _profile())
    assert exc.value.code == "VERIFICATION_IN_PROGRESS"

    await service.retry_verification(attempt_id)
    session.refresh(owner)
    assert owner.onboarding_status == WorkshopOwnerOnboardingStatus.ACTIVE
    assert session.get(WorkshopVerificationAttempt, attempt_id).retry_count == 1


@pytest.mark.asyncio
async def test_timeout_retries_five_times_over_30_minutes_then_fails(session):
    gateway = StubServiceCenterGateway(timeouts=100)
    scheduler = RecordingScheduler()
    service = make_service(session, gateway, scheduler)
    owner = _signed_in_with_profile(service)

    _, status = await _submit(service, owner)
    assert status == 202
    attempt_id = scheduler.scheduled[0][0]
    for _ in range(5):
        await service.retry_verification(attempt_id)

    assert [d for _, d in scheduler.scheduled] == [60, 120, 300, 600, 720]
    assert sum(d for _, d in scheduler.scheduled) == 30 * 60
    attempt = session.get(WorkshopVerificationAttempt, attempt_id)
    assert attempt.failure_reason == "oem_unavailable"
    session.refresh(owner)
    assert owner.onboarding_status == WorkshopOwnerOnboardingStatus.VERIFICATION_FAILED
    # OEM outages do not count toward the 5-failures limit.
    assert service.get_onboarding(owner).latest_attempt.failed_attempts_last24h == 0
    # A resolved attempt is not retried again.
    await service.retry_verification(attempt_id)
    assert len(gateway.calls) == 6


@pytest.mark.asyncio
async def test_scheduler_failure_does_not_fail_the_request(session):
    service = make_service(
        session, StubServiceCenterGateway(timeouts=1), RecordingScheduler(fail=True)
    )
    owner = _signed_in_with_profile(service)
    _, status = await _submit(service, owner)
    assert status == 202
    # The reconciler finds it once next_retry_at is overdue.
    attempt = session.exec(select(WorkshopVerificationAttempt)).one()
    attempt.next_retry_at = datetime.now(UTC) - timedelta(minutes=10)
    session.add(attempt)
    session.commit()
    assert service.stale_pending_attempt_ids() == [attempt.id]


@pytest.mark.asyncio
async def test_idempotent_replay_and_key_reuse(session):
    gateway = StubServiceCenterGateway(
        result=failure_response(ManagerVerifyFailureReason.MANAGER_NOT_FOUND)
    )
    service = make_service(session, gateway)
    owner = _signed_in_with_profile(service)

    first, _ = await _submit(service, owner, key="same")
    replay, status = await _submit(service, owner, key="same")
    assert status == 200
    assert replay.verification.attempt_id == first.verification.attempt_id
    assert len(gateway.calls) == 1

    with pytest.raises(errors.IdempotencyKeyReuseError):
        await _submit(service, owner, key="same", totalTechnicians=3)


@pytest.mark.asyncio
async def test_failed_attempt_limit(session):
    gateway = StubServiceCenterGateway(
        result=failure_response(ManagerVerifyFailureReason.MANAGER_NOT_FOUND)
    )
    service = make_service(session, gateway, max_failed_attempts=2)
    owner = _signed_in_with_profile(service)
    await _submit(service, owner, key="a")
    await _submit(service, owner, key="b")

    with pytest.raises(errors.VerificationAttemptsExceededError) as exc:
        await _submit(service, owner, key="c")
    assert 0 < exc.value.retry_after_seconds <= 24 * 3600
    assert len(gateway.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"emergencySlotsReserved": 13}, "emergencySlotsReserved"),
        ({"hotline": "123456789"}, "hotline"),
        ({"latitude": 21.0, "longitude": None}, "latitude"),
        ({"operatingHours": verification_body()["operatingHours"][:6]}, "operatingHours"),
        (
            {
                "operatingHours": [
                    {"dayOfWeek": d, "isClosed": True, "openTime": None, "closeTime": None}
                    for d in range(1, 8)
                ]
            },
            "operatingHours",
        ),
        (
            {
                "operatingHours": [
                    {"dayOfWeek": 1, "isClosed": False, "openTime": "17:00", "closeTime": "08:00"},
                    *verification_body()["operatingHours"][1:],
                ]
            },
            "operatingHours[0].closeTime",
        ),
    ],
)
async def test_submit_validation(session, overrides, field):
    service = make_service(session)
    owner = _signed_in_with_profile(service)
    with pytest.raises(errors.InvalidFieldError) as exc:
        await _submit(service, owner, **overrides)
    assert exc.value.field == field


@pytest.mark.asyncio
async def test_submit_after_active_is_rejected(session):
    service = make_service(session)
    owner = _signed_in_with_profile(service)
    await _submit(service, owner, key="a")
    with pytest.raises(errors.OnboardingStateError) as exc:
        await _submit(service, owner, key="b")
    assert exc.value.code == "ONBOARDING_ALREADY_COMPLETED"


@pytest.mark.asyncio
async def test_get_onboarding_and_sign_in_after_active(session):
    service = make_service(session)
    owner = _signed_in_with_profile(service)
    await _submit(service, owner)

    state = service.get_onboarding(owner)
    assert state.workshop is not None and state.workshop.center_id == "SC-01"
    assert state.registration is None  # the verified row is history, not a draft
    assert state.latest_attempt.status == "VERIFIED"
    assert state.consents["oemDataSharing"].granted is True

    data, is_new = service.sign_in(claims())
    assert is_new is False
    assert data.onboarding.next_step == "DASHBOARD"
    assert data.workshop.center_id == "SC-01"


def test_purge_expired_onboarding_keeps_active_owners(session):
    service = make_service(session)
    service.sign_in(claims(uid="old", email="old@example.com"))
    service.sign_in(claims(uid="new", email="new@example.com"))
    old = service.find_owner_by_firebase_uid("old")
    old.created_at = datetime.now(UTC) - timedelta(days=20)
    session.add(old)
    session.commit()

    assert service.purge_expired_onboarding() == 1
    assert service.find_owner_by_firebase_uid("old") is None
    assert service.find_owner_by_firebase_uid("new") is not None


# ======================================================================
# Domain helpers
# ======================================================================
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("024 3765 4321", "02437654321"),
        ("0912.000.101", "+84912000101"),
        ("1900 1234", "19001234"),
    ],
)
def test_normalize_hotline(raw, expected):
    assert normalize_hotline(raw) == expected


def test_mask_national_id():
    assert mask_national_id("001190000101") == "001******101"
    assert mask_national_id(None) is None
