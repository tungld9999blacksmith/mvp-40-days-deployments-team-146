"""Owner guards, immutable detail and raw-body signed webhook on src.main."""

import base64
import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from unittest.mock import Mock
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.agents.tools.dependency import AgentToolServices
from src.agents.tools.reminder_tools import build_reminder_tools
from src.common.core.maintenance.reminder import ReminderChannel
from src.infrastructure.supabase.db import get_session
from src.main import app
from src.modules.notification import dependency, route
from src.modules.notification.context_service import ReminderContextService
from src.modules.notification.settings_service import NotificationSettingsService
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.user_vehicle.service import UserVehicleService
from tests._user_vehicle import add_owner, add_vehicle
from tests.test_modules import test_main_email_reminders as email_tests
from tests.test_modules.test_main_email_reminders import event, service


@pytest.fixture
def setup(monkeypatch):
    yield from email_tests.setup.__wrapped__(monkeypatch)


@pytest_asyncio.fixture
async def api(setup, monkeypatch):
    db, owner, vehicle, cfg, now = setup
    cfg.resend_webhook_secret = "whsec_" + base64.b64encode(b"main-test-signing-key").decode()
    monkeypatch.setattr(route, "get_settings", lambda: cfg)
    monkeypatch.setattr(dependency, "get_settings", lambda: cfg)
    claims = {"uid": owner.firebase_uid}

    def session():
        yield db

    app.dependency_overrides[get_session] = session
    app.dependency_overrides[verify_firebase_token] = lambda: claims
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, claims
    app.dependency_overrides.clear()


def signed(cfg, payload, event_id="evt-test"):
    raw = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    key = base64.b64decode(cfg.resend_webhook_secret.removeprefix("whsec_"))
    signature = base64.b64encode(
        hmac.new(key, f"{event_id}.{timestamp}.".encode() + raw, hashlib.sha256).digest()
    ).decode()
    return raw, {
        "svix-id": event_id,
        "svix-timestamp": timestamp,
        "svix-signature": "v1," + signature,
        "Content-Type": "application/json",
    }


@pytest.mark.asyncio
async def test_settings_verified_opt_in_and_strict_inputs(api, setup):
    client, _ = api
    db, owner, vehicle, cfg, now = setup
    result = await client.get("/api/v1/notification-settings")
    assert result.json()["data"]["emailRecipient"] == owner.email
    assert result.json()["data"]["emailVerified"] is True
    assert result.json()["data"]["emailTransport"] == "mock"
    for bad in [{"remindersEnabled": "false"}, {"reminderLeadDays": True}, {"emailRecipient": "other@example.com"}]:
        assert (await client.put("/api/v1/notification-settings", json=bad)).status_code == 422
    owner.email_verified = False
    db.add(owner)
    db.commit()
    response = await client.put(
        "/api/v1/notification-settings", json={"channels": [{"channel": "EMAIL", "enabled": True}]}
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reminder_detail_outbox_ownership_and_missing(api, setup):
    client, claims = api
    db, owner, vehicle, cfg, now = setup
    reminder, _ = service(db, cfg, now)
    await reminder.remind(vehicle.id)
    response = await client.get("/api/v1/notifications/email-outbox")
    data = response.json()["data"]
    assert data["canRunReminders"] is False and data["mode"] == "mock"
    item = data["items"][0]
    assert "recipient" not in item["payload"] and "sender" not in item["payload"]
    detail = await client.get(f"/api/v1/notifications/reminders/{item['reminderId']}")
    assert detail.status_code == 200 and detail.json()["data"]["snapshotAvailable"] is True
    assert (await client.get(f"/api/v1/notifications/reminders/{uuid4()}")).status_code == 404
    second = add_owner(db, uid="other-uid")
    claims["uid"] = second.firebase_uid
    foreign = await client.get(f"/api/v1/notifications/reminders/{item['reminderId']}")
    # us-069 BR-1708: another owner's reminder looks exactly like a missing one.
    assert foreign.status_code == 404 and foreign.json()["error"]["code"] == "REMINDER_NOT_FOUND"
    assert (await client.get("/api/v1/notifications/email-outbox")).json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_webhook_without_bearer_signature_dedup_and_tamper(api, setup):
    client, _ = api
    db, owner, vehicle, cfg, now = setup
    raw, headers = signed(cfg, event("email.delivered"))
    response = await client.post("/api/v1/notifications/email/webhook", content=raw, headers=headers)
    assert response.status_code == 200 and response.json()["data"]["duplicate"] is False
    assert (await client.post("/api/v1/notifications/email/webhook", content=raw, headers=headers)).json()["data"][
        "duplicate"
    ] is True
    assert (
        await client.post("/api/v1/notifications/email/webhook", content=raw + b" ", headers=headers)
    ).status_code == 401
    assert (await client.post("/api/v1/notifications/email/webhook", json={})).status_code == 401


@pytest.mark.asyncio
async def test_real_mode_never_returns_saved_payload(api, setup):
    client, _ = api
    db, owner, vehicle, cfg, now = setup
    reminder, _ = service(db, cfg, now)
    await reminder.remind(vehicle.id)
    cfg.email_mode = "resend"
    data = (await client.get("/api/v1/notifications/email-outbox")).json()["data"]
    assert data["items"] == [] and data["mode"] == "resend"


def test_agent_uses_same_settings_and_rejects_other_vehicle(setup):
    db, owner, vehicle, cfg, now = setup

    @contextmanager
    def sessions():
        yield db

    def vehicles(session):
        return UserVehicleService(session, Mock(), clock=lambda: now[0])

    def settings(session):
        return NotificationSettingsService(
            session, available_channels={ReminderChannel.EMAIL}, default_lead_days=2, email_mode="mock"
        )

    unused = Mock(side_effect=AssertionError("Not used"))
    services = AgentToolServices(
        sessions,
        vehicles,
        unused,
        unused,
        unused,
        unused,
        notification_settings_service=settings,
        reminder_context_service=lambda s: ReminderContextService(s, vehicles(s)),
    )
    read, change, context = build_reminder_tools(services)
    config = {"configurable": {"user_id": owner.user_id, "user_vehicle_id": str(vehicle.id)}}
    result = change.invoke({"email_enabled": False}, config=config)
    assert result["status"] == "ok"
    assert next(c for c in settings(db).get(owner).channels if c.channel == "EMAIL").enabled is False
    assert read.invoke({}, config=config)["data"]["emailVerified"] is True
    second = add_owner(db, uid="other")
    other = add_vehicle(db, second, vin="LVVDB11B1PE000002", external_vehicle_id="OTHER-VEHICLE")
    forged = {"configurable": {"user_id": owner.user_id, "user_vehicle_id": str(other.id)}}
    assert change.invoke({"email_enabled": True}, config=forged)["status"] == "ERROR"
