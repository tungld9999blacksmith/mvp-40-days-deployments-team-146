"""API-level tests for FEAT-NOTI-001 (API-NOTI-001..002)."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlmodel import select

from src.common.core.identity.vehicle_user import OnboardingStatus
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import UserNotificationChannel, UserNotificationSetting
from src.infrastructure.supabase.db import get_session
from src.main import app
from src.modules.notification.channels import (
    DeliveryResult,
    NotificationChannelAdapter,
    NotificationMessage,
    NotificationService,
)
from src.modules.notification.dependency import get_notification_service
from src.modules.oauth.dependency import verify_firebase_token
from tests._user_vehicle import add_owner, make_session

URL = "/api/v1/notification-settings"
AUTH = {"Authorization": "Bearer x"}


class _FakeAdapter(NotificationChannelAdapter):
    def __init__(self, channel: ReminderChannel) -> None:
        self.channel = channel

    async def send(self, user_id: int, message: NotificationMessage) -> DeliveryResult:
        return DeliveryResult.sent()


class _Api:
    def __init__(self, client, session, claims, notifier):
        self.client = client
        self.session = session
        self._claims = claims
        self._notifier = notifier

    def sign_in_as(self, uid: str) -> None:
        self._claims["claims"] = {"uid": uid}

    def configure(self, *channels: ReminderChannel) -> None:
        """Pretend the providers of ``channels`` are configured (no adapter by default)."""
        for channel in channels:
            self._notifier.register(_FakeAdapter(channel))


@pytest_asyncio.fixture
async def api():
    session = next(make_session())
    claims: dict = {"claims": {"uid": "uid-1"}}
    # Independent of the SMTP / eSMS settings in the developer's .env.
    notifier = NotificationService()

    def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[verify_firebase_token] = lambda: claims["claims"]
    app.dependency_overrides[get_notification_service] = lambda: notifier

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield _Api(client, session, claims, notifier)

    app.dependency_overrides.clear()
    session.close()


@pytest.fixture
def owner(api: _Api):
    return add_owner(api.session)


def _channel(data: dict, name: str) -> dict:
    return next(c for c in data["channels"] if c["channel"] == name)


# ── API-NOTI-001 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_defaults_when_never_configured_ac509(api: _Api, owner):
    api.configure(ReminderChannel.EMAIL)  # EMAIL_MODE=mock (the default) registers the email adapter
    r = await api.client.get(URL, headers=AUTH)

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["remindersEnabled"] is True
    assert data["reminderLeadDays"] == 2 and data["defaultReminderLeadDays"] == 2
    # Email mock is implemented and opt-in; other channels remain unavailable.
    assert [c["channel"] for c in data["channels"]] == [
        "ZALO",
        "TELEGRAM",
        "SMS",
        "EMAIL",
    ]
    for name in ("ZALO", "TELEGRAM", "SMS"):
        assert _channel(data, name) == {
            "channel": name,
            "enabled": False,
            "available": False,
            "status": "COMING_SOON",
        }
    assert _channel(data, "EMAIL") == {"channel": "EMAIL", "enabled": False, "available": True, "status": "NOT_CONNECTED"}
    assert data["emailTransport"] == "mock"


@pytest.mark.asyncio
async def test_get_does_not_create_rows(api: _Api, owner):
    await api.client.get(URL, headers=AUTH)

    assert api.session.exec(select(UserNotificationSetting)).all() == []
    assert api.session.exec(select(UserNotificationChannel)).all() == []


# ── API-NOTI-002 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_lead_days_and_switch_ac502(api: _Api, owner):
    r = await api.client.put(URL, json={"reminderLeadDays": 5, "remindersEnabled": False}, headers=AUTH)

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["reminderLeadDays"] == 5 and data["remindersEnabled"] is False
    saved = api.session.get(UserNotificationSetting, owner.user_id)
    assert saved.reminder_lead_days == 5 and saved.reminders_enabled is False
    # Nothing was said about channels: still the default (none).
    assert not any(c["enabled"] for c in data["channels"])


@pytest.mark.asyncio
async def test_partial_update_keeps_other_values(api: _Api, owner):
    await api.client.put(URL, json={"reminderLeadDays": 7}, headers=AUTH)

    data = (await api.client.put(URL, json={"remindersEnabled": False}, headers=AUTH)).json()["data"]

    assert data["reminderLeadDays"] == 7 and data["remindersEnabled"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [-1, 31, 100])
async def test_lead_days_out_of_range_is_rejected(api: _Api, owner, days):
    r = await api.client.put(URL, json={"reminderLeadDays": days}, headers=AUTH)

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "INVALID_LEAD_DAYS"
    assert api.session.get(UserNotificationSetting, owner.user_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [0, 30])
async def test_lead_days_bounds_are_accepted(api: _Api, owner, days):
    r = await api.client.put(URL, json={"reminderLeadDays": days}, headers=AUTH)

    assert r.status_code == 200 and r.json()["data"]["reminderLeadDays"] == days


@pytest.mark.asyncio
async def test_unavailable_channel_cannot_be_enabled_ac510(api: _Api, owner):
    r = await api.client.put(URL, json={"channels": [{"channel": "SMS", "enabled": True}]}, headers=AUTH)

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "CHANNEL_NOT_AVAILABLE"
    assert api.session.exec(select(UserNotificationChannel)).all() == []


@pytest.mark.asyncio
async def test_unavailable_channel_can_be_switched_off(api: _Api, owner):
    r = await api.client.put(
        URL,
        json={
            "remindersEnabled": False,
            "channels": [{"channel": "SMS", "enabled": False}],
        },
        headers=AUTH,
    )

    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reminders_on_without_external_channel_is_fine(api: _Api, owner):
    """Reminders always reach the in-app feed, so no external channel is required."""
    r = await api.client.put(
        URL,
        json={"remindersEnabled": True, "channels": [{"channel": "SMS", "enabled": False}]},
        headers=AUTH,
    )

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["remindersEnabled"] is True
    assert not any(c["enabled"] for c in data["channels"])


@pytest.mark.asyncio
async def test_switching_a_channel_again_updates_the_same_row(api: _Api, owner):
    off = {"channels": [{"channel": "SMS", "enabled": False}]}
    await api.client.put(URL, json=off, headers=AUTH)

    r = await api.client.put(URL, json=off, headers=AUTH)

    assert r.status_code == 200 and _channel(r.json()["data"], "SMS")["enabled"] is False
    assert len(api.session.exec(select(UserNotificationChannel)).all()) == 1


@pytest.mark.asyncio
async def test_empty_body_is_rejected(api: _Api, owner):
    r = await api.client.put(URL, json={}, headers=AUTH)

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_settings_are_per_owner(api: _Api, owner):
    add_owner(api.session, uid="uid-2", email="owner2@example.com")
    await api.client.put(URL, json={"reminderLeadDays": 9}, headers=AUTH)
    api.sign_in_as("uid-2")

    data = (await api.client.get(URL, headers=AUTH)).json()["data"]

    assert data["reminderLeadDays"] == 2


# ── Email / SMS once configured (BR-506) ─────────────────────────────────────


@pytest.mark.asyncio
async def test_configured_channels_are_offered_with_connection_status(api: _Api, owner):
    owner.email_verified = True  # Google sign-in; no phone number on the profile
    api.session.add(owner)
    api.session.commit()
    api.configure(ReminderChannel.EMAIL, ReminderChannel.SMS)

    data = (await api.client.get(URL, headers=AUTH)).json()["data"]

    assert _channel(data, "EMAIL") == {"channel": "EMAIL", "enabled": False, "available": True, "status": "CONNECTED"}
    assert _channel(data, "SMS") == {"channel": "SMS", "enabled": False, "available": True, "status": "NOT_CONNECTED"}
    assert _channel(data, "ZALO")["status"] == "COMING_SOON"


@pytest.mark.asyncio
async def test_unverified_email_is_not_connected(api: _Api, owner):
    api.configure(ReminderChannel.EMAIL)

    data = (await api.client.get(URL, headers=AUTH)).json()["data"]

    assert _channel(data, "EMAIL")["status"] == "NOT_CONNECTED"


@pytest.mark.asyncio
async def test_owner_can_enable_email_and_sms(api: _Api, owner):
    owner.phone = "+84901000001"
    owner.email, owner.email_verified = "owner@example.com", True  # email needs a verified address
    api.session.add(owner)
    api.session.commit()
    api.configure(ReminderChannel.EMAIL, ReminderChannel.SMS)

    r = await api.client.put(
        URL,
        json={"channels": [{"channel": "EMAIL", "enabled": True}, {"channel": "SMS", "enabled": True}]},
        headers=AUTH,
    )

    assert r.status_code == 200
    data = r.json()["data"]
    assert _channel(data, "EMAIL")["enabled"] is True
    assert _channel(data, "SMS") == {"channel": "SMS", "enabled": True, "available": True, "status": "CONNECTED"}
    rows = api.session.exec(select(UserNotificationChannel)).all()
    assert {(row.channel, row.is_enabled) for row in rows} == {
        (ReminderChannel.EMAIL, True),
        (ReminderChannel.SMS, True),
    }


# ── Guard ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_without_finished_onboarding_is_forbidden(api: _Api):
    add_owner(
        api.session,
        uid="uid-3",
        email="o3@example.com",
        onboarding_status=OnboardingStatus.PENDING_VEHICLE_VERIFICATION,
    )
    api.sign_in_as("uid-3")

    reads = await api.client.get(URL, headers=AUTH)
    writes = await api.client.put(URL, json={"reminderLeadDays": 3}, headers=AUTH)

    for r in (reads, writes):
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "ONBOARDING_REQUIRED"
