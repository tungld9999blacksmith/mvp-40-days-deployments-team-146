"""Shared demo account ("Dùng thử ngay"): seed, reset, sign-in, logout and limits.

SQLite with foreign keys ON so ``ON DELETE CASCADE`` behaves as on PostgreSQL; the
manufacturer, Firebase and the OEM sync are stubs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from ev_contracts import (
    OwnershipVerifyFailureReason,
    OwnershipVerifyRequest,
    OwnershipVerifyResponse,
    VehicleSpec,
)
from fakeredis import FakeAsyncRedis
from sqlalchemy import MetaData, event
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine, select

from src.common.core.conversation import ChatMessage, Conversation
from src.common.core.conversation.memory import MemoryCleanup
from src.common.core.identity.vehicle_user import OnboardingStatus, VehicleUser
from src.common.core.maintenance.booking import Booking
from src.common.core.maintenance.booking_request import BookingRequest
from src.common.core.maintenance.reminder import ReminderChannel
from src.infrastructure.redis import RedisToolkit
from src.modules.auth.domain import AuthEvent
from src.modules.auth.service import AuthService
from src.modules.conversation import errors as chat_errors
from src.modules.conversation.service import ChatService
from src.modules.demo_account.domain import DemoAccountState
from src.modules.demo_account.errors import DemoAccountUnavailableError
from src.modules.demo_account.identity import DEMO_UID, is_demo_claims
from src.modules.demo_account.ports import DemoIdentityProvider, DemoOwnerAdmin
from src.modules.demo_account.service import VEHICLES, DemoAccountService, demo_resets_at
from src.modules.notification.recipients import email_address, has_recipient, phone_number
from src.modules.vehicle_owner_onboarding import errors as onboarding_errors
from src.modules.vehicle_owner_onboarding.domain import (
    UserConsent,
    UserVehicle,
    VehicleVerificationAttempt,
)
from src.modules.vehicle_owner_onboarding.ports import OemTimeoutError, OemVehicleGateway
from src.modules.vehicle_owner_onboarding.service import OnboardingService
from tests._maintenance import TABLES as MAINTENANCE_TABLES
from tests._maintenance import add_booking, add_workshop
from tests._user_vehicle import _make_sqlite_compatible, add_owner, add_vehicle

NOW = datetime(2026, 10, 11, 3, 0, tzinfo=UTC)
EMAIL = "demo@evcare.invalid"
MODELS = {"MDL-09": ("VF3", "Eco"), "MDL-05": ("VF8", "Eco"), "MDL-08": ("VF Wild", "Plus")}


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    metadata = MetaData()
    for table in [
        *MAINTENANCE_TABLES,
        UserConsent.__table__,
        VehicleVerificationAttempt.__table__,
        DemoAccountState.__table__,
        AuthEvent.__table__,
    ]:
        _make_sqlite_compatible(table.to_metadata(metadata))
    metadata.create_all(engine)
    with Session(engine) as s:
        yield s


class StubGateway(OemVehicleGateway):
    def __init__(self, *, reject_vin: str | None = None, timeout: bool = False) -> None:
        self.reject_vin = reject_vin
        self.timeout = timeout
        self.requests: list[OwnershipVerifyRequest] = []

    async def list_models(self) -> list[dict]:
        return []

    async def verify_ownership(self, request: OwnershipVerifyRequest) -> OwnershipVerifyResponse:
        self.requests.append(request)
        if self.timeout:
            raise OemTimeoutError("stub")
        if request.vin == self.reject_vin:
            return OwnershipVerifyResponse(verified=False, failure_reason=OwnershipVerifyFailureReason.VIN_NOT_FOUND)
        index = [v.vin for v in VEHICLES].index(request.vin) + 1
        name, trim = MODELS[request.model_id]
        return OwnershipVerifyResponse(
            verified=True,
            vehicle=VehicleSpec(
                external_vehicle_id=f"VEH-DEMO-{index}",
                external_owner_id="OWN-DEMO",
                external_model_id=request.model_id,
                model_name=name,
                trim=trim,
                color="Xám",
                manufacture_date=date(2025, 6, 1),
                production_year=2025,
                battery_capacity_kwh=50.0,
                motor_power_kw=100.0,
            ),
            warranties=[],
        )


class StubIdentity(DemoIdentityProvider):
    def __init__(self) -> None:
        self.users: list[tuple[str, str]] = []

    def ensure_user(self, uid: str, *, email: str, display_name: str) -> None:
        self.users.append((uid, email))

    def mint_token(self, uid: str) -> str:
        return f"token-for-{uid}"


class StubOwnerAdmin(DemoOwnerAdmin):
    def __init__(self) -> None:
        self.resets = 0

    async def reset_demo_owner(self) -> None:
        self.resets += 1


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _service(session, *, gateway=None, clock=None, synced=None, owner_admin=None) -> DemoAccountService:
    async def syncer(_session, vehicle_id):
        if synced is not None:
            synced.append(vehicle_id)

    return DemoAccountService(
        session,
        email=EMAIL,
        reset_interval_hours=48,
        gateway=gateway or StubGateway(),
        identity=StubIdentity(),
        owner_admin=owner_admin,
        syncer=syncer,
        clock=clock or Clock(NOW),
    )


def _demo_vehicles(session) -> list[UserVehicle]:
    user = session.exec(select(VehicleUser).where(VehicleUser.firebase_uid == DEMO_UID)).one()
    return list(session.exec(select(UserVehicle).where(UserVehicle.user_id == user.user_id)).all())


# --------------------------------------------------------------------- seed
@pytest.mark.asyncio
async def test_first_session_seeds_one_onboarded_account_with_vf3_vf8_and_vf_wild(session):
    synced: list = []
    service = _service(session, synced=synced)

    token = await service.open_session()
    await service.open_session()  # second visitor: same account, nothing duplicated

    assert token == f"token-for-{DEMO_UID}"
    users = session.exec(select(VehicleUser).where(VehicleUser.firebase_uid == DEMO_UID)).all()
    assert len(users) == 1
    user = users[0]
    assert user.is_demo and user.email == EMAIL and user.email_verified
    assert user.onboarding_status == OnboardingStatus.ACTIVE and user.external_owner_id == "OWN-DEMO"
    vehicles = _demo_vehicles(session)
    assert sorted(v.external_model_id for v in vehicles) == ["MDL-05", "MDL-08", "MDL-09"]
    assert {v.model_name for v in vehicles} == {"VF3", "VF8", "VF Wild"}
    assert len(synced) == 3  # synced once, on the seed only
    assert session.get(DemoAccountState, 1) is not None


@pytest.mark.asyncio
async def test_ownership_check_uses_the_demo_email_and_national_id(session):
    gateway = StubGateway()
    await _service(session, gateway=gateway).ensure_ready()

    assert {r.email for r in gateway.requests} == {EMAIL}
    assert {r.vin for r in gateway.requests} == {v.vin for v in VEHICLES}


@pytest.mark.parametrize("gateway", [StubGateway(reject_vin=VEHICLES[2].vin), StubGateway(timeout=True)])
@pytest.mark.asyncio
async def test_manufacturer_failure_writes_nothing(session, gateway):
    with pytest.raises(DemoAccountUnavailableError):
        await _service(session, gateway=gateway).ensure_ready()

    assert session.exec(select(VehicleUser)).first() is None


# -------------------------------------------------------------------- reset
async def _seed_activity(session) -> tuple[VehicleUser, VehicleUser, Booking]:
    """Bookings and a chat on the demo account, plus a real owner's booking at the same workshop."""
    demo = session.exec(select(VehicleUser).where(VehicleUser.firebase_uid == DEMO_UID)).one()
    vehicle = _demo_vehicles(session)[0]
    workshop = add_workshop(session)
    booking = add_booking(session, demo, vehicle, workshop, d=date(2026, 10, 20), code="EVC-DEMO")
    session.add(
        BookingRequest(
            request_id="req-demo", user_id=demo.user_id, fingerprint="f", token_hash="h", booking_id=booking.id
        )
    )
    conversation = Conversation(user_id=demo.user_id, user_vehicle_id=vehicle.id)
    session.add(conversation)
    session.commit()
    session.add(ChatMessage(conversation_id=conversation.id, role="user", content="Xin chào", seq=1))

    other = add_owner(session, uid="real-owner", email="real@example.com")
    other_vehicle = add_vehicle(session, other, vin="LVVDB11B1PE000099", external_vehicle_id="VEH-099")
    other_booking = add_booking(session, other, other_vehicle, workshop, d=date(2026, 10, 21), code="EVC-REAL")
    session.commit()
    return demo, other, other_booking


@pytest.mark.asyncio
async def test_reset_waits_for_the_interval(session):
    clock = Clock(NOW)
    admin = StubOwnerAdmin()
    service = _service(session, clock=clock, owner_admin=admin)
    await service.ensure_ready()
    await _seed_activity(session)

    clock.now = NOW + timedelta(hours=47, minutes=59)
    assert await service.reset_if_due() is False

    assert admin.resets == 0
    assert session.exec(select(Booking).where(Booking.booking_code == "EVC-DEMO")).first() is not None


@pytest.mark.asyncio
async def test_reset_after_48_hours_wipes_the_demo_activity_and_nothing_else(session):
    clock = Clock(NOW)
    admin = StubOwnerAdmin()
    synced: list = []
    service = _service(session, clock=clock, owner_admin=admin, synced=synced)
    await service.ensure_ready()
    demo, other, other_booking = await _seed_activity(session)
    old_conversation = session.exec(select(Conversation.id)).one()
    old_vehicle_ids = {v.id for v in _demo_vehicles(session)}

    clock.now = NOW + timedelta(hours=48)
    assert await service.reset_if_due() is True

    assert admin.resets == 1
    assert session.exec(select(Booking).where(Booking.booking_code == "EVC-DEMO")).first() is None
    assert session.exec(select(BookingRequest)).first() is None
    assert session.exec(select(Conversation)).first() is None
    assert session.get(MemoryCleanup, old_conversation) is not None  # checkpoints / vectors queued
    # A fresh account with the three vehicles again.
    assert len(session.exec(select(VehicleUser).where(VehicleUser.firebase_uid == DEMO_UID)).all()) == 1
    vehicles = _demo_vehicles(session)
    assert len(vehicles) == 3 and not ({v.id for v in vehicles} & old_vehicle_ids)
    assert all(session.get(UserVehicle, old_id) is None for old_id in old_vehicle_ids)
    assert len(synced) == 6
    assert demo_resets_at(session, 48) == clock.now + timedelta(hours=48)
    # The real owner keeps everything.
    assert session.get(VehicleUser, other.user_id) is not None
    assert session.get(Booking, other_booking.id) is not None


@pytest.mark.asyncio
async def test_forced_reset_ignores_the_interval(session):
    service = _service(session, owner_admin=StubOwnerAdmin())
    await service.ensure_ready()

    assert await service.reset_if_due() is False
    assert await service.reset_if_due(force=True) is True


@pytest.mark.asyncio
async def test_failed_reset_keeps_the_account(session):
    clock = Clock(NOW)
    gateway = StubGateway()
    service = _service(session, clock=clock, gateway=gateway)
    await service.ensure_ready()
    await _seed_activity(session)

    clock.now = NOW + timedelta(hours=49)
    gateway.timeout = True
    with pytest.raises(DemoAccountUnavailableError):
        await service.reset_if_due()

    assert session.exec(select(Booking).where(Booking.booking_code == "EVC-DEMO")).first() is not None


# ------------------------------------------------------------------ sign-in
def _demo_claims(**overrides) -> dict:
    claims = {
        "uid": DEMO_UID,
        "email": EMAIL,
        "email_verified": True,
        "demo": True,
        "firebase": {"sign_in_provider": "custom"},
    }
    claims.update(overrides)
    return claims


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        (_demo_claims(), True),
        (_demo_claims(demo=None), False),
        (_demo_claims(uid="someone-else"), False),
        (_demo_claims(firebase={"sign_in_provider": "google.com"}), False),
        (_demo_claims(demo="true"), False),
    ],
)
def test_only_the_backend_minted_demo_token_counts_as_demo(claims, expected):
    assert is_demo_claims(claims) is expected


def _onboarding(session) -> OnboardingService:
    return OnboardingService(session, StubGateway(), retention_days=15, max_failed_attempts=5, policy_version="2026-09")


@pytest.mark.asyncio
async def test_demo_token_signs_in_to_the_seeded_account(session):
    await _service(session).ensure_ready()

    data, is_new = await _onboarding(session).sign_in(_demo_claims())

    assert is_new is False
    assert data.user.is_demo is True
    assert data.user.demo_resets_at == NOW + timedelta(hours=48)
    assert data.onboarding.next_step == "HOME"


@pytest.mark.parametrize(
    ("claims", "code"),
    [
        (_demo_claims(demo=None), "UNSUPPORTED_SIGN_IN_PROVIDER"),
        (_demo_claims(uid="custom-attacker"), "UNSUPPORTED_SIGN_IN_PROVIDER"),
        (_demo_claims(), "DEMO_ACCOUNT_UNAVAILABLE"),  # not seeded yet
    ],
)
@pytest.mark.asyncio
async def test_other_custom_tokens_and_an_unseeded_demo_are_rejected(session, claims, code):
    with pytest.raises(onboarding_errors.OnboardingError) as exc:
        await _onboarding(session).sign_in(claims)

    assert exc.value.code == code
    assert session.exec(select(VehicleUser)).first() is None


@pytest.mark.asyncio
async def test_demo_profile_and_vehicles_are_read_only(session):
    user = await _service(session).ensure_ready()
    service = _onboarding(session)

    with pytest.raises(onboarding_errors.OnboardingError) as profile:
        service.update_profile(user, None)
    with pytest.raises(onboarding_errors.OnboardingError) as vehicle:
        await service.submit_verification(user, None, idempotency_key="k")

    assert profile.value.code == vehicle.value.code == "DEMO_READ_ONLY"
    assert onboarding_errors.status_for("DEMO_READ_ONLY") == 403


# ----------------------------------------------------- logout, notifications
class RecordingRevoker:
    def __init__(self) -> None:
        self.uids: list[str] = []

    def enqueue_revoke(self, *, uid: str, user_id: int, trace_id: str | None = None) -> None:
        self.uids.append(uid)


@pytest.mark.asyncio
async def test_demo_logout_never_revokes_the_shared_session(session):
    await _service(session).ensure_ready()
    add_owner(session, uid="google-owner", email="g@example.com")
    revoker = RecordingRevoker()
    auth = AuthService(session, revoker)

    auth.logout(_demo_claims())
    auth.logout({"uid": "google-owner", "firebase": {"sign_in_provider": "google.com"}})

    assert revoker.uids == ["google-owner"]
    assert session.exec(select(VehicleUser).where(VehicleUser.firebase_uid == DEMO_UID)).one().last_logout_at


def test_demo_account_has_no_email_or_sms_recipient():
    demo = VehicleUser(firebase_uid=DEMO_UID, email=EMAIL, email_verified=True, phone="+84900000999", is_demo=True)

    assert email_address(demo) is None and phone_number(demo) is None
    assert not has_recipient(demo, ReminderChannel.EMAIL) and not has_recipient(demo, ReminderChannel.SMS)


# --------------------------------------------------------------- chat limits
@pytest.mark.asyncio
async def test_demo_chat_is_limited_per_client_ip(session, monkeypatch):
    user = await _service(session).ensure_ready()
    real = add_owner(session, uid="real-chat", email="chat@example.com")
    settings = SimpleNamespace(
        chat_rate_limit_per_minute=100,
        chat_rate_limit_per_day=1000,
        demo_login_enabled=True,
        demo_chat_rate_limit_per_minute=100,
        demo_chat_rate_limit_per_day=2,
        demo_chat_total_per_day=100,
    )
    chat = ChatService(
        session.get_bind(),
        None,
        RedisToolkit(FakeAsyncRedis(), key_prefix=f"t-{uuid4().hex}"),
        None,
        None,
        None,
        settings,
        None,
    )
    ip = {"value": "1.1.1.1"}
    monkeypatch.setattr("src.modules.conversation.service.current_client_ip", lambda: ip["value"])

    await chat.check_rate_limit(user.user_id)
    await chat.check_rate_limit(user.user_id)
    with pytest.raises(chat_errors.RateLimited):
        await chat.check_rate_limit(user.user_id)
    ip["value"] = "2.2.2.2"  # another visitor still has their quota
    await chat.check_rate_limit(user.user_id)
    for _ in range(3):  # real owners keep their own per-account limits
        await chat.check_rate_limit(real.user_id)


# ------------------------------------------------------------- endpoint, beat
class FakeDemoService:
    async def open_session(self) -> str:
        return "custom-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(("enabled", "status"), [(False, 404), (True, 200)])
async def test_demo_session_endpoint_follows_the_flag(monkeypatch, enabled, status):
    from httpx import ASGITransport, AsyncClient

    from src.main import app
    from src.modules.demo_account import dependency

    monkeypatch.setattr(dependency, "get_settings", lambda: SimpleNamespace(demo_login_enabled=enabled))
    app.dependency_overrides[dependency.get_demo_service] = FakeDemoService
    app.dependency_overrides[dependency.limit_demo_sessions] = lambda: None
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/v1/auth/demo-session")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == status
    if enabled:
        assert resp.json() == {"data": {"customToken": "custom-token"}}
    else:
        assert resp.json()["error"]["code"] == "DEMO_LOGIN_DISABLED"


@pytest.mark.asyncio
async def test_demo_sessions_are_rate_limited_per_ip(monkeypatch):
    from starlette.requests import Request

    from src.modules.demo_account import dependency
    from src.modules.demo_account.errors import DemoRateLimitedError

    monkeypatch.setattr(
        dependency,
        "get_settings",
        lambda: SimpleNamespace(demo_session_rate_limit_per_hour=2, rate_limit_trust_forwarded=False),
    )
    toolkit = RedisToolkit(FakeAsyncRedis(), key_prefix=f"t-{uuid4().hex}")

    def request(ip: str) -> Request:
        return Request({"type": "http", "headers": [], "client": (ip, 1234)})

    await dependency.limit_demo_sessions(request("1.1.1.1"), toolkit)
    await dependency.limit_demo_sessions(request("1.1.1.1"), toolkit)
    with pytest.raises(DemoRateLimitedError) as exc:
        await dependency.limit_demo_sessions(request("1.1.1.1"), toolkit)
    await dependency.limit_demo_sessions(request("2.2.2.2"), toolkit)

    assert exc.value.retry_after_seconds >= 1


@pytest.mark.parametrize(("enabled", "scheduled"), [("false", False), ("true", True)])
def test_reset_job_is_scheduled_only_with_demo_login(monkeypatch, enabled, scheduled):
    import importlib

    import src.celery_tasks as celery_tasks
    from src.config import get_settings

    monkeypatch.setenv("DEMO_LOGIN_ENABLED", enabled)
    get_settings.cache_clear()
    try:
        beat = importlib.reload(celery_tasks).celery.conf.beat_schedule
        assert ("demo-account-reset" in beat) is scheduled
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        importlib.reload(celery_tasks)
