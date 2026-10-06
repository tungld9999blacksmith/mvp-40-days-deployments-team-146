"""Conversation transports must derive caller scope from authenticated accounts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from firebase_admin import auth
from starlette.websockets import WebSocketDisconnect

from src.common.core.identity.vehicle_user import UserStatus
from src.modules.conversation import dependency, errors, route, ws
from src.modules.workshop_board.dependency import get_owner_workshop
from tests._maintenance import add_booking, add_workshop
from tests._maintenance import make_session as make_booking_session
from tests._user_vehicle import add_owner, make_session


@pytest.fixture
def websocket_app(monkeypatch):
    session = make_session()
    db = next(session)
    owner = add_owner(db)
    service = Mock()
    service.list_messages.return_value = ([], None, False)
    monkeypatch.setattr(dependency, "engine", db.get_bind())
    monkeypatch.setattr(ws, "get_chat_service", lambda: service)
    monkeypatch.setattr(ws, "get_message_service", Mock())
    redis = SimpleNamespace(incr=AsyncMock(return_value=1), expire=AsyncMock(), decr=AsyncMock())
    monkeypatch.setattr(ws, "get_redis_toolkit", lambda: SimpleNamespace(redis=redis, keys=Mock()))
    monkeypatch.setattr(auth, "verify_id_token", Mock(return_value={"uid": owner.firebase_uid}))
    app = FastAPI()
    app.include_router(ws.ws_router)
    yield app, service, owner, db
    session.close()


@pytest.mark.parametrize("frame", [{"type": "auth", "userId": 1}, {"type": "auth", "token": ""}])
def test_websocket_rejects_identity_without_token(websocket_app, frame):
    app, service, _, _ = websocket_app
    with TestClient(app).websocket_connect(f"/conversations/{uuid4()}/stream") as socket:
        socket.send_json(frame)
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
    assert exc.value.code == 4401
    service.get_owned_conversation.assert_not_called()


def test_websocket_uses_verified_owner_instead_of_forged_id(websocket_app):
    app, service, owner, _ = websocket_app
    service.get_owned_conversation.side_effect = errors.ConversationNotFound()
    conversation_id = uuid4()
    with TestClient(app).websocket_connect(f"/conversations/{conversation_id}/stream") as socket:
        socket.send_json({"type": "auth", "token": "valid-token", "userId": 9999})
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
    assert exc.value.code == 4404
    service.get_owned_conversation.assert_called_once_with(owner.user_id, conversation_id)
    auth.verify_id_token.assert_called_once_with("valid-token", check_revoked=True, clock_skew_seconds=10)


@pytest.mark.parametrize("invalid_token", [True, False])
def test_websocket_rejects_invalid_token_and_suspended_owner(websocket_app, invalid_token):
    app, service, owner, db = websocket_app
    if invalid_token:
        auth.verify_id_token.side_effect = auth.InvalidIdTokenError("bad token")
    else:
        owner.status = UserStatus.SUSPENDED
        db.add(owner)
        db.commit()
    with TestClient(app).websocket_connect(f"/conversations/{uuid4()}/stream") as socket:
        socket.send_json({"type": "auth", "token": "token"})
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
    assert exc.value.code == 4401
    service.get_owned_conversation.assert_not_called()


def test_excerpt_requires_auth_even_with_forged_workshop_header():
    app = FastAPI()
    app.include_router(route.workshop_router)
    app.dependency_overrides[dependency.get_chat_service] = lambda: Mock()
    response = TestClient(app).get(
        f"/workshop/bookings/{uuid4()}/conversation-excerpt",
        headers={"X-Workshop-Id": str(uuid4())},
    )
    assert response.status_code in (401, 403)


def test_excerpt_rejects_other_workshop_even_with_matching_header(monkeypatch):
    from datetime import date, time

    from tests._user_vehicle import add_vehicle

    sessions = make_booking_session()
    db = next(sessions)
    try:
        owner = add_owner(db)
        workshop = add_workshop(db)
        booking = add_booking(db, owner, add_vehicle(db, owner), workshop, d=date(2030, 1, 1), t=time(9))
        app = FastAPI()
        app.include_router(route.workshop_router)
        app.dependency_overrides[dependency.get_chat_service] = lambda: Mock()
        app.dependency_overrides[get_owner_workshop] = lambda: SimpleNamespace(workshop=SimpleNamespace(id=uuid4()))
        monkeypatch.setattr(route, "engine", db.get_bind())
        client = TestClient(app, raise_server_exceptions=False)
        # Install the normal domain handler without depending on production services.
        from fastapi.responses import JSONResponse

        @app.exception_handler(errors.ConversationError)
        def handle_error(request, exc):
            return JSONResponse({"code": exc.code}, status_code=errors.status_for(exc.code))

        response = client.get(
            f"/workshop/bookings/{booking.id}/conversation-excerpt",
            headers={"X-Workshop-Id": str(workshop.id)},
        )
        assert response.status_code == 404
    finally:
        sessions.close()


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (auth.RevokedIdTokenError("revoked"), errors.Unauthorized),
        (auth.InvalidIdTokenError("bad"), errors.Unauthorized),
        (ValueError("malformed"), errors.Unauthorized),
        (auth.UserNotFoundError("deleted account"), errors.Unauthorized),
        (RuntimeError("firebase unreachable"), errors.AuthProviderUnavailable),
    ],
)
def test_token_verification_separates_bad_tokens_from_provider_outages(monkeypatch, failure, expected):
    monkeypatch.setattr(auth, "verify_id_token", Mock(side_effect=failure))
    with pytest.raises(expected):
        dependency.user_id_from_token("token", Mock())
    assert errors.ERROR_STATUS[errors.AuthProviderUnavailable.code] == 503


def test_websocket_provider_outage_closes_with_retryable_code(websocket_app, monkeypatch):
    app, service, _, _ = websocket_app
    monkeypatch.setattr(auth, "verify_id_token", Mock(side_effect=RuntimeError("firebase unreachable")))
    with TestClient(app).websocket_connect(f"/conversations/{uuid4()}/stream") as socket:
        socket.send_json({"type": "auth", "token": "valid-token"})
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
    assert exc.value.code == 1013
    service.get_owned_conversation.assert_not_called()


def test_websocket_rejects_non_json_auth_frame(websocket_app):
    app, service, _, _ = websocket_app
    with TestClient(app).websocket_connect(f"/conversations/{uuid4()}/stream") as socket:
        socket.send_text("not-json")
        with pytest.raises(WebSocketDisconnect) as exc:
            socket.receive_json()
    assert exc.value.code == 4401
    service.get_owned_conversation.assert_not_called()


@pytest.mark.asyncio
async def test_send_message_returns_204_when_the_turn_yields_no_frame():
    """Client gone before the first frame: no 500 from StopAsyncIteration."""
    from httpx import ASGITransport, AsyncClient

    from src.main import app
    from src.modules.conversation.dependency import get_chat_service, get_current_user_id

    class SilentTurn:
        async def stream_turn(self, *args, **kwargs):
            return
            yield

    app.dependency_overrides[get_chat_service] = SilentTurn
    app.dependency_overrides[get_current_user_id] = lambda: 1
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/conversations/{uuid4()}/messages",
                json={"clientMessageId": str(uuid4()), "content": "hi"},
            )
    finally:
        app.dependency_overrides.pop(get_chat_service, None)
        app.dependency_overrides.pop(get_current_user_id, None)
    assert response.status_code == 204
    assert response.content == b""
