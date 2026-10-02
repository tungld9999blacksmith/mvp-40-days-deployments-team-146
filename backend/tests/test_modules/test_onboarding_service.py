"""Service-level tests for the onboarding module.

Exercise OnboardingService directly against an in-memory SQLite session and a
stub manufacturer gateway, covering sign-in, profile, and the full vehicle
verification matrix (success / failure / retry-limit / timeout / idempotency /
already-linked).
"""

from __future__ import annotations

import pytest
from ev_contracts import OwnershipVerifyFailureReason

from src.common.core.identity.vehicle_user import UserStatus
from src.modules.vehicle_owner_onboarding import errors, schemas
from src.modules.vehicle_owner_onboarding.service import OnboardingService
from tests._onboarding import (
    GOOGLE_EMAIL,
    MODEL_ID,
    NATIONAL_ID,
    PLATE,
    VIN,
    StubOemGateway,
    failure_response,
    make_session,
)


def _service(gateway: StubOemGateway, *, max_failed: int = 5) -> OnboardingService:
    session = next(make_session())
    return OnboardingService(
        session,
        gateway,
        retention_days=15,
        max_failed_attempts=max_failed,
        policy_version="2026-09",
    )


def _claims(uid: str = "uid-1", email: str = GOOGLE_EMAIL) -> dict:
    return {
        "uid": uid,
        "email": email,
        "email_verified": True,
        "name": "Dung Pham",
        "firebase": {"sign_in_provider": "google.com"},
    }


def _profile_req(
    phone: str = "0901000004", national_id: str = NATIONAL_ID, consent: bool = True
) -> schemas.ProfileUpdateRequest:
    return schemas.ProfileUpdateRequest(
        fullName="Pham Minh Dung",
        phoneNumber=phone,
        nationalId=national_id,
        location={"addressLine": "So 1 Dai Co Viet, HN", "province": "Ha Noi", "source": "MANUAL"},
        personalDataConsent={"granted": consent, "policyVersion": "2026-09"},
    )


def _verify_req() -> schemas.VehicleVerificationRequest:
    return schemas.VehicleVerificationRequest(
        vin=VIN,
        licensePlate=PLATE,
        modelId=MODEL_ID,
        manufactureYear=2024,
        oemDataSharingConsent={"granted": True, "policyVersion": "2026-09"},
    )


async def _onboard_until_profile(svc: OnboardingService, uid: str = "uid-1"):
    await svc.sign_in(_claims(uid=uid))
    user = svc.find_user_by_firebase_uid(uid)
    svc.update_profile(user, _profile_req())
    return user


# ---------------------------------------------------------------------------
# Sign-in
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sign_in_creates_new_user():
    svc = _service(StubOemGateway())
    data, is_new = await svc.sign_in(_claims())
    assert is_new is True
    assert data.onboarding.status == "ONBOARDING_IN_PROGRESS"
    assert data.onboarding.next_step == "PROFILE"
    assert data.user.roles == ["VEHICLE_USER"]
    assert data.onboarding.expires_at is not None


@pytest.mark.asyncio
async def test_sign_in_existing_user_is_not_new():
    svc = _service(StubOemGateway())
    await svc.sign_in(_claims())
    data, is_new = await svc.sign_in(_claims())
    assert is_new is False


@pytest.mark.asyncio
async def test_sign_in_rejects_non_google_provider():
    svc = _service(StubOemGateway())
    claims = _claims()
    claims["firebase"]["sign_in_provider"] = "password"
    with pytest.raises(errors.OnboardingError) as exc:
        await svc.sign_in(claims)
    assert exc.value.code == "UNSUPPORTED_SIGN_IN_PROVIDER"


@pytest.mark.asyncio
async def test_sign_in_requires_verified_email():
    svc = _service(StubOemGateway())
    claims = _claims()
    claims["email_verified"] = False
    with pytest.raises(errors.OnboardingError) as exc:
        await svc.sign_in(claims)
    assert exc.value.code == "EMAIL_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_sign_in_email_linked_to_another_uid():
    svc = _service(StubOemGateway())
    await svc.sign_in(_claims(uid="uid-1", email=GOOGLE_EMAIL))
    with pytest.raises(errors.EmailAlreadyLinkedError):
        await svc.sign_in(_claims(uid="uid-2", email=GOOGLE_EMAIL))


@pytest.mark.asyncio
async def test_sign_in_blocks_suspended_account():
    svc = _service(StubOemGateway())
    await svc.sign_in(_claims())
    user = svc.find_user_by_firebase_uid("uid-1")
    user.status = UserStatus.SUSPENDED
    svc._db.add(user)
    svc._db.commit()
    with pytest.raises(errors.AccountLockedError) as exc:
        await svc.sign_in(_claims())
    assert exc.value.code == "ACCOUNT_SUSPENDED"


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_profile_normalizes_phone_and_completes_step():
    svc = _service(StubOemGateway())
    await svc.sign_in(_claims())
    user = svc.find_user_by_firebase_uid("uid-1")
    data = svc.update_profile(user, _profile_req(phone="0901000004"))
    assert data.profile.phone_number == "+84901000004"
    assert data.onboarding.profile_completed is True
    assert data.onboarding.next_step == "VEHICLE"
    assert data.profile.national_id_masked == "079*******04"


@pytest.mark.asyncio
async def test_update_profile_rejects_invalid_phone():
    svc = _service(StubOemGateway())
    await svc.sign_in(_claims())
    user = svc.find_user_by_firebase_uid("uid-1")
    # 8+ chars (passes schema length) but not a valid VN mobile number.
    with pytest.raises(errors.InvalidProfileError):
        svc.update_profile(user, _profile_req(phone="12345678"))


@pytest.mark.asyncio
async def test_update_profile_requires_consent():
    svc = _service(StubOemGateway())
    await svc.sign_in(_claims())
    user = svc.find_user_by_firebase_uid("uid-1")
    with pytest.raises(errors.ConsentRequiredError):
        svc.update_profile(user, _profile_req(consent=False))


@pytest.mark.asyncio
async def test_update_profile_rejects_duplicate_phone():
    svc = _service(StubOemGateway())
    await svc.sign_in(_claims(uid="uid-1", email="a@example.com"))
    await svc.sign_in(_claims(uid="uid-2", email="b@example.com"))
    user1 = svc.find_user_by_firebase_uid("uid-1")
    user2 = svc.find_user_by_firebase_uid("uid-2")
    svc.update_profile(user1, _profile_req(phone="0901000004", national_id="079200001004"))
    with pytest.raises(errors.PhoneAlreadyInUseError):
        svc.update_profile(user2, _profile_req(phone="0901000004", national_id="079200009999"))


# ---------------------------------------------------------------------------
# Vehicle verification
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verification_success_activates_account():
    gw = StubOemGateway()
    svc = _service(gw)
    user = await _onboard_until_profile(svc)
    data, code = await svc.submit_verification(user, _verify_req(), idempotency_key="k1")
    assert code == 200
    assert data.onboarding.status == "ACTIVE"
    assert data.onboarding.next_step == "HOME"
    assert data.vehicle.verification_status == "VERIFIED"
    assert data.vehicle.spec.model_name == "VF6"
    assert len(data.warranties) == 1
    assert user.external_owner_id == "OWN-004"


@pytest.mark.asyncio
async def test_verification_failure_sets_failed_state():
    gw = StubOemGateway(verify_result=failure_response(OwnershipVerifyFailureReason.PLATE_MISMATCH))
    svc = _service(gw)
    user = await _onboard_until_profile(svc)
    data, code = await svc.submit_verification(user, _verify_req(), idempotency_key="k1")
    assert code == 200
    assert data.onboarding.status == "VERIFICATION_FAILED"
    assert data.verification.failure_reason == "PLATE_MISMATCH"
    assert data.onboarding.next_step == "VEHICLE"


@pytest.mark.asyncio
async def test_verification_idempotent_replay_does_not_call_oem_twice():
    gw = StubOemGateway()
    svc = _service(gw)
    user = await _onboard_until_profile(svc)
    req = _verify_req()
    await svc.submit_verification(user, req, idempotency_key="k1")
    data, code = await svc.submit_verification(user, req, idempotency_key="k1")
    assert code == 200
    assert gw.verify_calls == 1
    assert data.vehicle.verification_status == "VERIFIED"


@pytest.mark.asyncio
async def test_verification_idempotency_key_reuse_with_different_body():
    gw = StubOemGateway(verify_result=failure_response(OwnershipVerifyFailureReason.PLATE_MISMATCH))
    svc = _service(gw)
    user = await _onboard_until_profile(svc)
    await svc.submit_verification(user, _verify_req(), idempotency_key="k1")
    other = schemas.VehicleVerificationRequest(
        vin="VF8PLUS2023000001",
        licensePlate=PLATE,
        modelId=MODEL_ID,
        oemDataSharingConsent={"granted": True, "policyVersion": "2026-09"},
    )
    with pytest.raises(errors.IdempotencyKeyReuseError):
        await svc.submit_verification(user, other, idempotency_key="k1")


@pytest.mark.asyncio
async def test_verification_retry_limit_exceeded():
    gw = StubOemGateway(verify_result=failure_response(OwnershipVerifyFailureReason.VIN_NOT_FOUND))
    svc = _service(gw, max_failed=2)
    user = await _onboard_until_profile(svc)
    await svc.submit_verification(user, _verify_req(), idempotency_key="k1")
    await svc.submit_verification(user, _verify_req(), idempotency_key="k2")
    with pytest.raises(errors.VerificationAttemptsExceededError):
        await svc.submit_verification(user, _verify_req(), idempotency_key="k3")


@pytest.mark.asyncio
async def test_verification_timeout_returns_pending():
    gw = StubOemGateway(raise_timeout=True)
    svc = _service(gw)
    user = await _onboard_until_profile(svc)
    data, code = await svc.submit_verification(user, _verify_req(), idempotency_key="k1")
    assert code == 202
    assert data.onboarding.status == "PENDING_VEHICLE_VERIFICATION"
    assert data.onboarding.next_step == "VERIFYING"


@pytest.mark.asyncio
async def test_oem_timeout_does_not_count_against_retry_limit():
    gw = StubOemGateway(raise_timeout=True)
    svc = _service(gw, max_failed=1)
    user = await _onboard_until_profile(svc)
    await svc.submit_verification(user, _verify_req(), idempotency_key="k1")
    # A pending (timed-out) attempt must not consume the failure budget.
    assert svc._remaining_attempts(user.user_id) == 1


@pytest.mark.asyncio
async def test_verification_vin_already_linked_to_other_account():
    gw = StubOemGateway()
    svc = _service(gw)
    user_a = await _onboard_until_profile(svc, uid="uid-1")
    await svc.submit_verification(user_a, _verify_req(), idempotency_key="k1")

    await svc.sign_in(_claims(uid="uid-2", email="other@example.com"))
    user_b = svc.find_user_by_firebase_uid("uid-2")
    svc.update_profile(user_b, _profile_req(phone="0901000009", national_id="079200009999"))
    with pytest.raises(errors.VehicleAlreadyLinkedError):
        await svc.submit_verification(user_b, _verify_req(), idempotency_key="k2")


@pytest.mark.asyncio
async def test_verification_requires_completed_profile():
    gw = StubOemGateway()
    svc = _service(gw)
    await svc.sign_in(_claims())
    user = svc.find_user_by_firebase_uid("uid-1")
    with pytest.raises(errors.OnboardingStateError) as exc:
        await svc.submit_verification(user, _verify_req(), idempotency_key="k1")
    assert exc.value.code == "PROFILE_INCOMPLETE"


@pytest.mark.asyncio
async def test_get_onboarding_reports_state_and_consents():
    gw = StubOemGateway()
    svc = _service(gw)
    user = await _onboard_until_profile(svc)
    snapshot = svc.get_onboarding(user)
    assert snapshot.onboarding.next_step == "VEHICLE"
    assert snapshot.location is not None
    assert snapshot.consents["personalDataProcessing"].granted is True
    assert snapshot.remaining_attempts == 5


@pytest.mark.asyncio
async def test_list_vehicle_models_maps_and_sorts():
    gw = StubOemGateway()
    svc = _service(gw)
    data = await svc.list_vehicle_models()
    assert [m.trim for m in data.items] == ["Eco", "Plus"]


@pytest.mark.asyncio
async def test_list_vehicle_models_oem_unavailable():
    gw = StubOemGateway(raise_timeout=True)
    svc = _service(gw)
    with pytest.raises(errors.OemUnavailableError):
        await svc.list_vehicle_models()
