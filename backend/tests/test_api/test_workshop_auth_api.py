"""API-level tests for workshop-owner auth (FEAT-AUTH-004).

API-201 sign-in audit, API-301 logout and API-302 session check over HTTP,
with Firebase, DB session, OEM gateway and revoker replaced by test doubles.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from firebase_admin import auth as firebase_auth
from httpx import ASGITransport, AsyncClient
from sqlmodel import Session, select

from src.common.core.identity.workshop_owner import WorkshopOwner
from src.infrastructure.supabase.db import get_session
from src.main import app
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.workshop_owner_auth.dependency import (
    get_workshop_session_revoker,
    verify_firebase_token_check_revoked,
)
from src.modules.workshop_owner_auth.domain import AuthEventType, WorkshopAuthEvent
from src.modules.workshop_owner_onboarding.dependency import (
    get_retry_scheduler,
    get_service_center_gateway,
)
from tests._workshop_onboarding import (
    RecordingScheduler,
    StubServiceCenterGateway,
    claims,
    make_engine,
)
from tests.test_modules.test_workshop_auth_service import StubRevoker

BASE = "/api/v1/workshop-owner/oauth"
HEADERS = {"User-Agent": "Mozilla/5.0 Portal", "X-Request-ID": "req-api"}


@pytest_asyncio.fixture
async def ctx():
    session = Session(make_engine())
    revoker = StubRevoker()
    holder = {"claims": claims()}

    def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_service_center_gateway] = StubServiceCenterGateway
    app.dependency_overrides[get_retry_scheduler] = RecordingScheduler
    app.dependency_overrides[get_workshop_session_revoker] = lambda: revoker
    app.dependency_overrides[verify_firebase_token] = lambda: holder["claims"]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session, revoker

    app.dependency_overrides.clear()
    session.close()


def _events(session) -> list[WorkshopAuthEvent]:
    return list(session.exec(select(WorkshopAuthEvent).order_by(WorkshopAuthEvent.created_at)).all())


@pytest.mark.asyncio
async def test_sign_in_is_logged_with_headers(ctx):
    client, session, _ = ctx
    resp = await client.post(f"{BASE}/sign-in", headers=HEADERS)
    assert resp.status_code == 201

    [event] = _events(session)
    assert event.event_type == AuthEventType.LOGIN
    assert event.user_agent == "Mozilla/5.0 Portal"
    assert event.trace_id == "req-api"
    assert event.ip_address  # ASGI test client address


@pytest.mark.asyncio
async def test_logout_is_204_and_logged(ctx):
    client, session, revoker = ctx
    await client.post(f"{BASE}/sign-in", headers=HEADERS)

    resp = await client.post(f"{BASE}/logout", headers=HEADERS)
    assert resp.status_code == 204
    assert resp.content == b""
    assert [e.event_type for e in _events(session)] == [AuthEventType.LOGIN, AuthEventType.LOGOUT]
    assert session.exec(select(WorkshopOwner)).one().last_logout_at is not None
    assert revoker.calls[0]["uid"] == "ws-uid-1"


@pytest.mark.asyncio
async def test_logout_is_503_when_revoke_cannot_be_enqueued(ctx):
    client, session, revoker = ctx
    await client.post(f"{BASE}/sign-in", headers=HEADERS)
    revoker.fail = True

    resp = await client.post(f"{BASE}/logout", headers=HEADERS)
    assert resp.status_code == 503
    err = resp.json()["error"]
    assert err["code"] == "AUTH_PROVIDER_UNAVAILABLE"
    assert err["traceId"] == "req-api"
    assert [e.event_type for e in _events(session)] == [AuthEventType.LOGIN]


@pytest.mark.asyncio
async def test_session_check_returns_state(ctx):
    client, _, _ = ctx
    app.dependency_overrides[verify_firebase_token_check_revoked] = lambda: claims()
    await client.post(f"{BASE}/sign-in", headers=HEADERS)

    resp = await client.get(f"{BASE}/session")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["accountStatus"] == "ACTIVE"
    assert data["onboarding"]["nextStep"] == "PROFILE"
    assert data["lastLoginAt"] is not None


@pytest.mark.asyncio
async def test_session_check_not_registered_is_404(ctx):
    client, _, _ = ctx
    app.dependency_overrides[verify_firebase_token_check_revoked] = lambda: claims()
    resp = await client.get(f"{BASE}/session")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "WORKSHOP_OWNER_NOT_REGISTERED"


@pytest.mark.asyncio
async def test_session_check_without_token_is_401(ctx):
    client, _, _ = ctx
    resp = await client.get(f"{BASE}/session")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exc,status,code",
    [
        (firebase_auth.RevokedIdTokenError("revoked"), 401, "TOKEN_REVOKED"),
        (firebase_auth.ExpiredIdTokenError("expired", cause=None), 401, "INVALID_TOKEN"),
        (firebase_auth.InvalidIdTokenError("bad"), 401, "INVALID_TOKEN"),
        (RuntimeError("firebase down"), 503, "AUTH_PROVIDER_UNAVAILABLE"),
    ],
)
async def test_session_check_maps_firebase_errors(ctx, monkeypatch, exc, status, code):
    client, _, _ = ctx
    seen = {}

    def fake_verify(token, check_revoked=False, clock_skew_seconds=0):
        seen["check_revoked"] = check_revoked
        raise exc

    monkeypatch.setattr(firebase_auth, "verify_id_token", fake_verify)
    resp = await client.get(f"{BASE}/session", headers={"Authorization": "Bearer t"})
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code
    assert seen["check_revoked"] is True
