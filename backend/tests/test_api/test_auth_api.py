"""API-level tests for logout (FEAT-AUTH-002, API-101).

Override the Firebase token dependency and inject an ``AuthService`` bound to an
in-memory session + stub revoker, so no Celery/Redis/Firebase is required.
"""

import pytest
from sqlmodel import select

from src.main import app
from src.modules.auth.dependency import get_auth_service
from src.modules.auth.domain import AuthEvent, AuthEventType
from src.modules.auth.errors import AuthProviderUnavailableError
from src.modules.auth.service import AuthService
from src.modules.oauth.dependency import verify_firebase_token
from tests._auth import StubRevoker, make_session, make_user


@pytest.mark.asyncio
async def test_logout_requires_authorization_header(client):
    response = await client.post("/api/v1/oauth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_returns_204_and_audits(client):
    session = next(make_session())
    user = make_user(session, uid="uid-1")
    revoker = StubRevoker()
    service = AuthService(session, revoker)

    app.dependency_overrides[verify_firebase_token] = lambda: {
        "uid": "uid-1",
        "firebase": {"sign_in_provider": "google.com"},
    }
    app.dependency_overrides[get_auth_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/oauth/logout",
            headers={"Authorization": "Bearer fake", "X-Request-ID": "req-9"},
        )
    finally:
        app.dependency_overrides.pop(verify_firebase_token, None)
        app.dependency_overrides.pop(get_auth_service, None)

    assert response.status_code == 204
    assert response.content == b""

    session.refresh(user)
    assert user.last_logout_at is not None
    event = session.exec(select(AuthEvent)).one()
    assert event.event_type == AuthEventType.LOGOUT
    assert revoker.calls[0]["uid"] == "uid-1"


@pytest.mark.asyncio
async def test_logout_provider_unavailable_returns_503_envelope(client):
    class _FailingService(AuthService):
        def logout(self, *a, **k):  # noqa: D401,ANN002,ANN003
            raise AuthProviderUnavailableError()

    session = next(make_session())
    service = _FailingService(session, StubRevoker())

    app.dependency_overrides[verify_firebase_token] = lambda: {"uid": "uid-1"}
    app.dependency_overrides[get_auth_service] = lambda: service
    try:
        response = await client.post(
            "/api/v1/oauth/logout",
            headers={"Authorization": "Bearer fake", "X-Request-ID": "req-x"},
        )
    finally:
        app.dependency_overrides.pop(verify_firebase_token, None)
        app.dependency_overrides.pop(get_auth_service, None)

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "AUTH_PROVIDER_UNAVAILABLE"
    assert body["error"]["traceId"] == "req-x"
