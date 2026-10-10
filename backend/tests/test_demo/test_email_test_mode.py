"""Real test delivery stays explicitly triggered and bound to a server-configured mailbox."""

import asyncio
import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.demo.dependency import make_services
from src.demo.fixtures import ensure_user
from src.demo.main import create_app
from src.demo.notification_persistence import load_notifications
from src.demo.notifications import DemoEmailConfig, SettingsUpdate
from src.demo.store import DemoError, DemoStore
from src.modules.notification.channels import DeliveryResult


def make_config(**overrides):
    return DemoEmailConfig(
        **{
            "mode": "resend_test",
            "sender": "EV Care <sender@example.com>",
            "api_key": "test-only",
            "test_recipient": "recipient@example.com",
            **overrides,
        }
    )


@pytest.fixture
def rig():
    simulated = [datetime(2026, 10, 7, 9, tzinfo=timezone(timedelta(hours=7)))]
    actual = [datetime(2026, 10, 7, 2, tzinfo=UTC)]
    transport = AsyncMock()
    transport.send.return_value = DeliveryResult.sent("provider-test")
    services = make_services(
        DemoStore(skip_onboarding=True, clock=lambda: simulated[0]),
        email_config=make_config(),
        email_transport=transport,
    )
    services.notifications.delivery_clock = lambda: actual[0]
    user = ensure_user(services.store, {"uid": "owner", "email": "recipient@example.com", "email_verified": True})
    services.notifications.update(
        user["userId"],
        SettingsUpdate(remindersEnabled=True, channels=[{"channel": "EMAIL", "enabled": True}]),
    )
    return services, user, transport, simulated, actual


@pytest.mark.parametrize(
    "recipient", ["", "a@example.com,b@example.com", "Name <a@example.com>", "a\n@example.com", "a@local"]
)
def test_requires_exactly_one_configured_recipient(recipient):
    with pytest.raises(ValueError, match="DEMO_EMAIL_TEST_TO"):
        make_config(test_recipient=recipient)


def test_from_env_allows_emulator_and_simulated_schedule_only_in_test_mode(monkeypatch):
    monkeypatch.setenv("DEMO_EMAIL_MODE", "resend_test")
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    monkeypatch.setenv("DEMO_NOW", "2026-10-07T09:00:00+07:00")
    monkeypatch.setenv("DEMO_EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("RESEND_API_KEY", "test-only")
    monkeypatch.setenv("DEMO_EMAIL_TEST_TO", "recipient@example.com")
    monkeypatch.delenv("RESEND_WEBHOOK_SECRET", raising=False)
    assert DemoEmailConfig.from_env().test_recipient == "recipient@example.com"
    monkeypatch.setenv("DEMO_EMAIL_MODE", "resend")
    with pytest.raises(ValueError, match="real Firebase"):
        DemoEmailConfig.from_env()
    monkeypatch.setenv("DEMO_EMAIL_MODE", "resend_test")
    monkeypatch.delenv("FIREBASE_AUTH_EMULATOR_HOST")
    with pytest.raises(ValueError, match="Emulator"):
        DemoEmailConfig.from_env()


def test_background_scan_never_dispatches_real_test_email(rig):
    services, user, transport, _, _ = rig
    asyncio.run(services.notifications.run())
    asyncio.run(services.notifications.run(user["userId"]))
    assert services.store.reminders
    assert not services.store.email_deliveries
    transport.send.assert_not_awaited()


def test_mock_mode_cannot_use_the_real_test_endpoint(rig):
    services, user, transport, _, _ = rig
    services.notifications.config = DemoEmailConfig()
    with pytest.raises(DemoError, match="chưa được bật"):
        asyncio.run(services.notifications.send_test_email(user["userId"]))
    transport.send.assert_not_awaited()


def test_test_recipient_still_requires_email_claim_and_opt_in(rig):
    services, user, transport, _, _ = rig
    user["emailVerified"] = False
    with pytest.raises(DemoError, match="hợp lệ"):
        asyncio.run(services.notifications.send_test_email(user["userId"]))
    transport.send.assert_not_awaited()


def test_manual_api_requires_opt_in_and_rejects_recipient_override(rig):
    services, user, transport, _, _ = rig
    app = create_app(
        services,
        token_verifier=lambda uid: {
            "uid": uid,
            "email": "recipient@example.com" if uid == "owner" else "other@example.com",
            "email_verified": True,
        },
    )
    with TestClient(app) as client:
        headers = {"Authorization": "Bearer owner"}
        assert client.get("/health").json()["emailMode"] == "resend_test"
        assert client.get("/health").json()["emailManualOnly"] is True
        assert client.post("/api/v1/demo/email-test/send", json={}).status_code == 401
        assert (
            client.post(
                "/api/v1/demo/email-test/send", headers=headers, json={"recipient": "other@example.com"}
            ).status_code
            == 422
        )
        assert (
            client.post("/api/v1/demo/email-test/send", headers={"Authorization": "Bearer other"}, json={}).status_code
            == 403
        )
        assert (
            client.get("/api/v1/notifications/email-outbox", headers={"Authorization": "Bearer other"}).json()["data"][
                "items"
            ]
            == []
        )
        assert client.post("/api/v1/demo/reminders/run", headers=headers).status_code == 200
        transport.send.assert_not_awaited()
        services.notifications.update(user["userId"], SettingsUpdate(channels=[{"channel": "EMAIL", "enabled": False}]))
        assert client.post("/api/v1/demo/email-test/send", headers=headers, json={}).status_code == 422
        transport.send.assert_not_awaited()
        services.notifications.update(user["userId"], SettingsUpdate(channels=[{"channel": "EMAIL", "enabled": True}]))
        assert client.post("/api/v1/demo/email-test/send", headers=headers, json={}).status_code == 200
        response = client.get("/api/v1/notifications/email-outbox", headers=headers).json()["data"]
        assert response["mode"] == "resend_test" and response["canSendTestEmail"]
        assert response["items"][0]["deliveryState"] == "accepted"
        assert client.post("/api/v1/demo/email-test/send", headers=headers, json={}).status_code == 200
    transport.send.assert_awaited_once()
    recipient, message = transport.send.await_args.args
    assert recipient == "recipient@example.com"
    assert message.subject.startswith("[DEMO]")
    assert "dữ liệu demo" in message.body and "dữ liệu demo" in message.html


def test_cooldown_survives_restart_and_simulated_time_cannot_bypass_it(rig, tmp_path):
    services, user, transport, simulated, actual = rig
    services.store.notifications_path = tmp_path / "notifications.json"

    async def click_twice():
        await asyncio.gather(
            services.notifications.send_test_email(user["userId"]),
            services.notifications.send_test_email(user["userId"]),
        )

    asyncio.run(click_twice())
    transport.send.assert_awaited_once()
    resumed = make_services(
        DemoStore(skip_onboarding=True, clock=lambda: simulated[0]),
        email_config=make_config(),
        email_transport=transport,
    )
    resumed.notifications.delivery_clock = lambda: actual[0]
    resumed_user = ensure_user(resumed.store, {"uid": "owner", "email": user["email"], "email_verified": True})
    load_notifications(resumed.store, services.store.notifications_path)
    asyncio.run(resumed.notifications.send_test_email(resumed_user["userId"]))
    simulated[0] += timedelta(days=40)
    # Even a second emulator identity/vehicle using that mailbox cannot resend during cooldown.
    second = ensure_user(resumed.store, {"uid": "second", "email": user["email"], "email_verified": True})
    resumed.notifications.update(
        second["userId"], SettingsUpdate(remindersEnabled=True, channels=[{"channel": "EMAIL", "enabled": True}])
    )
    asyncio.run(resumed.notifications.send_test_email(second["userId"]))
    transport.send.assert_awaited_once()
    second_reminder = next(r for r in resumed.store.reminders.values() if r["uid"] == "second")
    assert second_reminder["emailSkipReason"] == "COOLDOWN"


def test_retry_requires_another_click_and_retains_payload(rig):
    services, user, transport, simulated, actual = rig
    transport.send.side_effect = [DeliveryResult.failed("TIMEOUT"), DeliveryResult.sent("provider-retry")]
    asyncio.run(services.notifications.send_test_email(user["userId"]))
    first = transport.send.await_args.args
    actual[0] += timedelta(minutes=5)
    simulated[0] += timedelta(days=1)
    asyncio.run(services.notifications.run())
    transport.send.assert_awaited_once()
    asyncio.run(services.notifications.send_test_email(user["userId"]))
    assert transport.send.await_count == 2
    assert transport.send.await_args.args == first


def test_wrong_account_and_changed_recipient_cannot_dispatch(rig):
    services, user, transport, _, _ = rig
    user["email"] = "other@example.com"
    with pytest.raises(DemoError, match="trùng"):
        asyncio.run(services.notifications.send_test_email(user["userId"]))
    with pytest.raises(DemoError, match="trùng"):
        services.notifications.update(user["userId"], SettingsUpdate(channels=[{"channel": "EMAIL", "enabled": True}]))
    assert services.notifications.settings(user["userId"])["emailRecipient"] is None
    transport.send.assert_not_awaited()


def test_switching_from_mock_does_not_reuse_or_replay_mock_delivery(rig):
    services, user, transport, _, _ = rig
    services.notifications.config = DemoEmailConfig()
    asyncio.run(services.notifications.run())
    mock_delivery = next(iter(services.store.email_deliveries.values()))
    services.notifications.config = make_config()
    asyncio.run(services.notifications.send_test_email(user["userId"]))
    transport.send.assert_awaited_once()
    assert len(services.store.email_deliveries) == 2
    assert transport.send.await_args.args[1].delivery_id != mock_delivery["id"]
    assert all(email["deliveryState"] != "mock" for email in services.notifications.outbox(user["userId"]))


def test_signed_test_webhook_reconciles_early_arrival_and_blocks_bounced_address(rig):
    services, user, transport, _, actual = rig
    services.notifications.config = make_config(webhook_secret="whsec_dGVzdA==")
    raw = json.dumps(
        {
            "type": "email.bounced",
            "created_at": actual[0].isoformat(),
            "data": {"email_id": "provider-test"},
        }
    ).encode()
    timestamp = str(int(time.time()))
    signature = base64.b64encode(
        hmac.new(b"test", f"event-test.{timestamp}.".encode() + raw, hashlib.sha256).digest()
    ).decode()
    headers = {"svix-id": "event-test", "svix-timestamp": timestamp, "svix-signature": f"v1,{signature}"}
    client = TestClient(create_app(services))
    assert client.post("/api/v1/notifications/email/webhook", content=raw, headers=headers).status_code == 200
    asyncio.run(services.notifications.send_test_email(user["userId"]))
    assert services.notifications.outbox(user["userId"])[0]["deliveryState"] == "bounced"
    with pytest.raises(DemoError, match="chặn"):
        asyncio.run(services.notifications.send_test_email(user["userId"]))
    transport.send.assert_awaited_once()
    assert client.post("/api/v1/notifications/email/webhook", content=raw + b" ", headers=headers).status_code == 401


def test_test_webhook_without_secret_stays_disabled(rig):
    services, _, _, _, _ = rig
    client = TestClient(create_app(services))
    assert client.post("/api/v1/notifications/email/webhook", json={}).status_code == 503


def test_notification_history_defaults_to_separate_file(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_REGISTRATION_FILE", str(tmp_path / "registration.json"))
    monkeypatch.delenv("DEMO_NOTIFICATIONS_FILE", raising=False)

    def capture_path(store, path):
        store.notifications_path = path

    monkeypatch.setattr("src.demo.notification_persistence.load_notifications", capture_path)
    services = make_services(email_config=make_config())
    assert services.store.notifications_path.name == "notifications-resend-test.json"
