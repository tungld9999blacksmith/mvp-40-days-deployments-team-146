"""API-level tests for workshop-owner onboarding (API-201..API-204).

Drive the real FastAPI app over HTTP; the Firebase token, DB session, OEM
gateway and retry scheduler are replaced by test doubles.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from ev_contracts import ManagerVerifyFailureReason
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, SQLModel, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.infrastructure.supabase.db import get_session
from src.main import app
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.workshop_owner_onboarding.dependency import (
    get_retry_scheduler,
    get_service_center_gateway,
)
from tests._workshop_onboarding import (
    RecordingScheduler,
    StubServiceCenterGateway,
    claims,
    failure_response,
    make_engine,
    profile_body,
    verification_body,
)

BASE = "/api/v1/workshop-owner"


class _Api:
    def __init__(self, client, session, gateway, scheduler, holder):
        self.client = client
        self.session = session
        self.gateway = gateway
        self.scheduler = scheduler
        self._holder = holder

    def as_user(self, **kwargs) -> None:
        self._holder["claims"] = claims(**kwargs)

    async def sign_in(self):
        return await self.client.post(f"{BASE}/oauth/sign-in")

    async def profile(self, **kwargs):
        return await self.client.put(f"{BASE}/onboarding/profile", json=profile_body(**kwargs))

    async def verify(self, key: str = "idem-1", **overrides):
        return await self.client.post(
            f"{BASE}/onboarding/workshop-verification",
            json=verification_body(**overrides),
            headers={"Idempotency-Key": key, "X-Request-ID": "req-test"},
        )


@pytest_asyncio.fixture
async def api():
    session = Session(make_engine())
    gateway = StubServiceCenterGateway()
    scheduler = RecordingScheduler()
    holder: dict = {"claims": claims()}

    def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_service_center_gateway] = lambda: gateway
    app.dependency_overrides[get_retry_scheduler] = lambda: scheduler
    app.dependency_overrides[verify_firebase_token] = lambda: holder["claims"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield _Api(client, session, gateway, scheduler, holder)

    app.dependency_overrides.clear()
    session.close()


@pytest.mark.asyncio
async def test_full_happy_path(api):
    resp = await api.sign_in()
    assert resp.status_code == 201
    body = resp.json()["data"]
    assert body["isNewOwner"] is True
    assert body["onboarding"]["nextStep"] == "PROFILE"
    assert body["owner"]["roles"] == ["WORKSHOP_OWNER"]

    resp = await api.profile()
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["onboarding"]["nextStep"] == "WORKSHOP"
    assert data["profile"]["nationalIdMasked"] == "001******101"
    assert "nationalId" not in data["profile"]

    resp = await api.verify()
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["verification"]["status"] == "VERIFIED"
    assert data["onboarding"]["status"] == "ACTIVE"
    assert data["workshop"]["centerId"] == "SC-01"
    assert data["workshop"]["type"] == "DEALER"
    assert data["workshop"]["latitude"] == 21.017
    assert data["workshop"]["operatingHours"][0] == {
        "dayOfWeek": 1, "isClosed": False, "openTime": "08:00", "closeTime": "17:30"
    }

    resp = await api.client.get(f"{BASE}/onboarding")
    assert resp.status_code == 200
    assert resp.json()["data"]["workshop"]["name"] == "VinFast Thăng Long"

    resp = await api.sign_in()
    assert resp.status_code == 200
    assert resp.json()["data"]["onboarding"]["nextStep"] == "DASHBOARD"


@pytest.mark.asyncio
async def test_endpoints_require_sign_in_first(api):
    resp = await api.client.get(f"{BASE}/onboarding")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "WORKSHOP_OWNER_NOT_REGISTERED"


@pytest.mark.asyncio
async def test_workshop_owner_and_vehicle_owner_are_separate_accounts(api):
    """BR-209: the workshop portal sign-in never creates a vehicle_user."""
    SQLModel.metadata.create_all(api.session.get_bind(), tables=[VehicleUser.__table__])
    await api.sign_in()
    assert api.session.exec(select(VehicleUser)).first() is None
    assert api.session.exec(select(WorkshopOwner)).one().email == claims()["email"]


@pytest.mark.asyncio
async def test_verify_before_profile_is_409(api):
    await api.sign_in()
    resp = await api.verify()
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "PROFILE_INCOMPLETE"


@pytest.mark.asyncio
async def test_oem_rejection_is_200_failed(api):
    api.gateway.result = failure_response(ManagerVerifyFailureReason.MANAGER_NOT_FOUND)
    await api.sign_in()
    await api.profile()
    resp = await api.verify()
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["verification"]["status"] == "FAILED"
    assert data["verification"]["failureReason"] == "MANAGER_NOT_FOUND"
    assert data["onboarding"]["status"] == "VERIFICATION_FAILED"
    assert data["workshop"] is None

    state = (await api.client.get(f"{BASE}/onboarding")).json()["data"]
    assert state["registration"]["failureReason"] == "MANAGER_NOT_FOUND"
    assert state["latestAttempt"]["failedAttemptsLast24h"] == 1


@pytest.mark.asyncio
async def test_oem_timeout_is_202_pending(api):
    api.gateway.timeouts_left = 1
    await api.sign_in()
    await api.profile()
    resp = await api.verify()
    assert resp.status_code == 202
    assert resp.json()["data"]["onboarding"]["nextStep"] == "VERIFYING"
    assert api.scheduler.scheduled[0][1] == 60

    resp = await api.verify(key="another")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "VERIFICATION_IN_PROGRESS"


@pytest.mark.asyncio
async def test_already_claimed_is_409_with_attempt_id(api):
    # Another owner onboards SC-01 first.
    api.as_user(uid="first", email="first@example.com")
    await api.sign_in()
    await api.profile(phone="0987000001", national_id="001190000999")
    assert (await api.verify()).status_code == 200

    api.as_user()
    await api.sign_in()
    await api.profile()
    resp = await api.verify()
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "WORKSHOP_ALREADY_CLAIMED"
    assert err["details"]["attemptId"]
    assert err["traceId"] == "req-test"


@pytest.mark.asyncio
async def test_invalid_operating_hours_is_400_with_field(api):
    await api.sign_in()
    await api.profile()
    hours = verification_body()["operatingHours"]
    hours[5] = {"dayOfWeek": 6, "isClosed": False, "openTime": "12:00", "closeTime": "08:00"}
    resp = await api.verify(operatingHours=hours)
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["code"] == "INVALID_FIELD_FORMAT"
    assert err["details"] == {"field": "operatingHours[5].closeTime"}


@pytest.mark.asyncio
async def test_schema_violation_uses_error_envelope(api):
    await api.sign_in()
    resp = await api.client.put(f"{BASE}/onboarding/profile", json={"fullName": "A"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_missing_idempotency_key_is_400(api):
    await api.sign_in()
    await api.profile()
    resp = await api.client.post(
        f"{BASE}/onboarding/workshop-verification", json=verification_body()
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_idempotency_key_reuse_is_422(api):
    api.gateway.result = failure_response(ManagerVerifyFailureReason.NATIONAL_ID_MISMATCH)
    await api.sign_in()
    await api.profile()
    await api.verify(key="k")
    resp = await api.verify(key="k", totalTechnicians=3)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.asyncio
async def test_attempt_limit_is_429_with_retry_after(api):
    api.gateway.result = failure_response(ManagerVerifyFailureReason.NATIONAL_ID_MISMATCH)
    await api.sign_in()
    await api.profile()
    for i in range(5):
        assert (await api.verify(key=f"k{i}")).status_code == 200
    resp = await api.verify(key="k5")
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0
    assert resp.json()["error"]["details"]["retryAfterSeconds"] > 0
