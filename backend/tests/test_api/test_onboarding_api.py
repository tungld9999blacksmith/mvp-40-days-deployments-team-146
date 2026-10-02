"""API-level tests for the onboarding endpoints (API-001..API-005).

Drive the real FastAPI app over HTTP with the Firebase token, DB session and
manufacturer gateway replaced by test doubles.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from ev_contracts import OwnershipVerifyFailureReason
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from src.common.core.vehicle import OemSyncTrigger
from src.infrastructure.supabase.db import get_session
from src.main import app
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.oem_integration.dependency import get_sync_scheduler
from src.modules.vehicle_owner_onboarding.dependency import get_oem_gateway
from tests._onboarding import (
    _ONBOARDING_TABLES,
    MODEL_ID,
    NATIONAL_ID,
    PLATE,
    VIN,
    StubOemGateway,
    failure_response,
)
from tests._user_vehicle import RecordingScheduler

GOOGLE_EMAIL = "dung.pham@example.com"


class _Api:
    def __init__(self, client, session, gateway, claims_holder, scheduler):
        self.client = client
        self.session = session
        self.gateway = gateway
        self._claims = claims_holder
        self.scheduler = scheduler

    def set_claims(self, uid: str = "uid-1", email: str = GOOGLE_EMAIL, **extra):
        self._claims["claims"] = {
            "uid": uid,
            "email": email,
            "email_verified": True,
            "name": "Dung Pham",
            "firebase": {"sign_in_provider": "google.com"},
            **extra,
        }


@pytest_asyncio.fixture
async def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=_ONBOARDING_TABLES)
    session = Session(engine)
    gateway = StubOemGateway()
    scheduler = RecordingScheduler()
    claims_holder: dict = {"claims": {}}

    def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_oem_gateway] = lambda: gateway
    app.dependency_overrides[get_sync_scheduler] = lambda: scheduler
    app.dependency_overrides[verify_firebase_token] = lambda: claims_holder["claims"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield _Api(client, session, gateway, claims_holder, scheduler)

    app.dependency_overrides.clear()
    session.close()


def _profile_body():
    return {
        "fullName": "Pham Minh Dung",
        "phoneNumber": "0901000004",
        "nationalId": NATIONAL_ID,
        "location": {
            "addressLine": "So 1 Dai Co Viet, Hai Ba Trung, Ha Noi",
            "province": "Ha Noi",
            "source": "MANUAL",
        },
        "personalDataConsent": {"granted": True, "policyVersion": "2026-09"},
    }


def _verify_body():
    return {
        "vin": VIN,
        "licensePlate": PLATE,
        "modelId": MODEL_ID,
        "manufactureYear": 2024,
        "oemDataSharingConsent": {"granted": True, "policyVersion": "2026-09"},
    }


@pytest.mark.asyncio
async def test_full_onboarding_flow(api: _Api):
    api.set_claims()

    # API-001 sign-in creates the account.
    r = await api.client.post("/api/v1/oauth/sign-in", headers={"Authorization": "Bearer x"})
    assert r.status_code == 201
    body = r.json()["data"]
    assert body["isNewUser"] is True
    assert body["onboarding"]["nextStep"] == "PROFILE"

    # API-003 profile.
    r = await api.client.put("/api/v1/onboarding/profile", json=_profile_body())
    assert r.status_code == 200
    assert r.json()["data"]["onboarding"]["nextStep"] == "VEHICLE"
    assert r.json()["data"]["profile"]["phoneNumber"] == "+84901000004"

    # API-004 vehicle models.
    r = await api.client.get("/api/v1/onboarding/vehicle-models")
    assert r.status_code == 200
    assert len(r.json()["data"]["items"]) >= 1

    # API-005 verification -> ACTIVE.
    r = await api.client.post(
        "/api/v1/onboarding/vehicle-verification",
        json=_verify_body(),
        headers={"Idempotency-Key": "k1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["onboarding"]["status"] == "ACTIVE"
    assert data["vehicle"]["verificationStatus"] == "VERIFIED"
    assert data["vehicle"]["spec"]["modelName"] == "VF6"
    # FEAT-VEH-001 BR-011: odometer + service history are pulled right away.
    assert [(t, d) for _, t, d in api.scheduler.calls] == [(OemSyncTrigger.INITIAL, 0)]

    # API-002 read back.
    r = await api.client.get("/api/v1/onboarding")
    assert r.status_code == 200
    assert r.json()["data"]["onboarding"]["nextStep"] == "HOME"


@pytest.mark.asyncio
async def test_sign_in_existing_user_returns_200(api: _Api):
    api.set_claims()
    await api.client.post("/api/v1/oauth/sign-in", headers={"Authorization": "Bearer x"})
    r = await api.client.post("/api/v1/oauth/sign-in", headers={"Authorization": "Bearer x"})
    assert r.status_code == 200
    assert r.json()["data"]["isNewUser"] is False


@pytest.mark.asyncio
async def test_get_onboarding_before_sign_in_is_404(api: _Api):
    api.set_claims(uid="never-signed-in")
    r = await api.client.get("/api/v1/onboarding")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "USER_NOT_REGISTERED"


@pytest.mark.asyncio
async def test_verification_failure_returns_200_with_reason(api: _Api):
    api.set_claims()
    api.gateway.verify_result = failure_response(OwnershipVerifyFailureReason.PLATE_MISMATCH)
    await api.client.post("/api/v1/oauth/sign-in", headers={"Authorization": "Bearer x"})
    await api.client.put("/api/v1/onboarding/profile", json=_profile_body())
    r = await api.client.post(
        "/api/v1/onboarding/vehicle-verification",
        json=_verify_body(),
        headers={"Idempotency-Key": "k1"},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["verification"]["status"] == "FAILED"
    assert data["verification"]["failureReason"] == "PLATE_MISMATCH"
    assert data["onboarding"]["status"] == "VERIFICATION_FAILED"
    assert api.scheduler.calls == []


@pytest.mark.asyncio
async def test_verification_missing_idempotency_key_is_400(api: _Api):
    api.set_claims()
    await api.client.post("/api/v1/oauth/sign-in", headers={"Authorization": "Bearer x"})
    await api.client.put("/api/v1/onboarding/profile", json=_profile_body())
    r = await api.client.post("/api/v1/onboarding/vehicle-verification", json=_verify_body())
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_verification_timeout_returns_202(api: _Api):
    api.set_claims()
    api.gateway.raise_timeout = True
    await api.client.post("/api/v1/oauth/sign-in", headers={"Authorization": "Bearer x"})
    await api.client.put("/api/v1/onboarding/profile", json=_profile_body())
    r = await api.client.post(
        "/api/v1/onboarding/vehicle-verification",
        json=_verify_body(),
        headers={"Idempotency-Key": "k1"},
    )
    assert r.status_code == 202
    assert r.json()["data"]["onboarding"]["status"] == "PENDING_VEHICLE_VERIFICATION"


@pytest.mark.asyncio
async def test_profile_without_consent_is_400_consent_required(api: _Api):
    api.set_claims()
    await api.client.post("/api/v1/oauth/sign-in", headers={"Authorization": "Bearer x"})
    body = _profile_body()
    body["personalDataConsent"]["granted"] = False
    r = await api.client.put("/api/v1/onboarding/profile", json=body)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "CONSENT_REQUIRED"
