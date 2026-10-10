"""Main email integration with actual SQL services and a recording transport.

No Firebase/private keys, Redis, network or real mail. Restart uses new sessions.
"""

from dataclasses import asdict
from datetime import timedelta
from unittest.mock import Mock

import pytest
from sqlmodel import Session, select

from src.common.core.maintenance import BookingStatus, Reminder
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import ReminderDelivery, UserNotificationChannel, UserNotificationSetting
from src.common.core.notification.email import EmailOutbox, EmailSuppression, EmailWebhookEvent
from src.config import Settings
from src.modules.notification.channels import DeliveryResult, NotificationMessage, NotificationService
from src.modules.notification.email_service import MaintenanceEmailAdapter, email_configuration_ready
from src.modules.notification.email_transport import address_hash
from src.modules.notification.reminder_service import MaintenanceReminderService
from src.modules.user_vehicle.service import UserVehicleService
from tests._maintenance import add_booking, add_workshop, make_session
from tests._user_vehicle import add_odometer, add_owner, add_rules, add_vehicle, mark_synced
from tests.test_modules.test_reminder_service import TWO_DAYS_BEFORE


class Transport:
    def __init__(self, *results):
        self.calls, self.results = [], list(results)
        self.on_send = None

    async def send(self, recipient, message):
        self.calls.append((recipient, asdict(message)))
        if self.on_send:
            self.on_send()
        return self.results.pop(0) if self.results else DeliveryResult.sent("provider-1")


@pytest.mark.parametrize("guard", ["firebase_auth_emulator_host", "demo_now", "email_from", "resend_webhook_secret"])
def test_resend_requires_complete_non_demo_configuration(guard):
    cfg = Settings(
        _env_file=None,
        email_mode="resend",
        email_from="EV Care <test@example.com>",
        resend_api_key="fake-key",
        resend_webhook_secret="fake-secret",
    )
    assert email_configuration_ready(cfg)
    setattr(cfg, guard, "demo-value" if guard in {"demo_now", "firebase_auth_emulator_host"} else "")
    assert not email_configuration_ready(cfg)


@pytest.fixture
def setup(monkeypatch):
    gen = make_session()
    db = next(gen)
    cfg = Settings(
        _env_file=None,
        email_mode="mock",
        email_from="EV Care <test@example.com>",
        email_app_url="http://localhost:5173",
        resend_api_key="fake-test-key",
        resend_webhook_secret="fake-test-secret",
    )
    monkeypatch.setattr("src.config.get_settings", lambda: cfg)
    owner = add_owner(db)
    owner.email, owner.email_verified = "owner@example.com", True
    db.add(owner)
    vehicle = add_vehicle(db, owner)
    add_rules(db)
    add_odometer(db, vehicle, 5000, TWO_DAYS_BEFORE)
    mark_synced(db, vehicle, TWO_DAYS_BEFORE)
    db.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.EMAIL))
    db.commit()
    now = [TWO_DAYS_BEFORE]
    yield db, owner, vehicle, cfg, now
    gen.close()


def service(db, cfg, now, transport=None):
    adapter = MaintenanceEmailAdapter(db, cfg, clock=lambda: now[0], transport=transport)
    vehicles = UserVehicleService(db, Mock(), clock=lambda: now[0])
    reminder = MaintenanceReminderService(
        db, NotificationService([adapter]), lambda v, n: vehicles.calculate(v, now=n), clock=lambda: now[0]
    )
    return reminder, adapter


@pytest.mark.asyncio
async def test_main_mock_persists_and_repeat_does_not_send(setup):
    db, owner, vehicle, cfg, now = setup
    reminder, _ = service(db, cfg, now)
    assert (await reminder.remind(vehicle.id)).deliveries_sent == 1
    outbox = db.exec(select(EmailOutbox)).one()
    assert outbox.mode == "mock" and outbox.provider_message_id.startswith("mock-")
    assert "VIN" not in outbox.payload["body"]
    with Session(db.bind) as restarted:
        again, _ = service(restarted, cfg, now)
        assert (await again.remind(vehicle.id)).deliveries_sent == 0
        assert restarted.exec(select(ReminderDelivery)).one().attempts == 1


@pytest.mark.asyncio
async def test_retry_freezes_payload_has_backoff_and_no_transaction_over_http(setup):
    db, owner, vehicle, cfg, now = setup
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"), DeliveryResult.sent("provider-retry"))
    transport.on_send = lambda: _no_transaction(db)
    reminder, _ = service(db, cfg, now, transport)
    await reminder.remind(vehicle.id)
    await reminder.remind(vehicle.id)
    assert len(transport.calls) == 1
    now[0] += timedelta(minutes=5)
    vehicle.model_name = "Changed model"
    db.add(vehicle)
    db.commit()
    await reminder.remind(vehicle.id)
    assert transport.calls[0] == transport.calls[1]
    assert db.exec(select(ReminderDelivery)).one().attempts == 2
    assert db.exec(select(EmailOutbox)).one().provider_message_id == "provider-retry"


def _no_transaction(db):
    assert not db.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("guard", ["opt_out", "unverified", "suppressed", "changed_recipient"])
async def test_retry_rechecks_recipient_and_preferences(setup, guard):
    db, owner, vehicle, cfg, now = setup
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"))
    reminder, _ = service(db, cfg, now, transport)
    await reminder.remind(vehicle.id)
    if guard == "opt_out":
        row = db.exec(select(UserNotificationChannel)).one()
        row.is_enabled = False
        db.add(row)
    elif guard == "unverified":
        owner.email_verified = False
        db.add(owner)
    elif guard == "changed_recipient":
        owner.email = "different@example.com"
        db.add(owner)
    else:
        db.add(EmailSuppression(recipient_hash=address_hash(owner.email), reason="bounced", created_at=now[0]))
    db.commit()
    now[0] += timedelta(minutes=6)
    await reminder.remind(vehicle.id)
    assert len(transport.calls) == 1
    assert db.exec(select(ReminderDelivery)).one().attempts == 1


@pytest.mark.asyncio
async def test_cooldown_between_levels_and_recovery_after_seven_days(setup):
    db, owner, vehicle, cfg, now = setup
    reminder, _ = service(db, cfg, now)
    await reminder.remind(vehicle.id)
    now[0] += timedelta(days=5)
    assert (await reminder.remind(vehicle.id)).deliveries_sent == 0
    assert len(db.exec(select(EmailOutbox)).all()) == 1
    now[0] += timedelta(days=2)
    assert (await reminder.remind(vehicle.id)).deliveries_sent == 1
    assert len(db.exec(select(EmailOutbox)).all()) == 2


@pytest.mark.asyncio
async def test_same_milestone_booking_pauses_cancel_reopens_without_reset(setup):
    db, owner, vehicle, cfg, now = setup
    reminder, _ = service(db, cfg, now)
    # First create in-app reminder with Email disabled.
    channel = db.exec(select(UserNotificationChannel)).one()
    channel.is_enabled = False
    db.add(channel)
    db.commit()
    await reminder.remind(vehicle.id)
    original = db.exec(select(Reminder)).one().id
    ws = add_workshop(db)
    booking = add_booking(db, owner, vehicle, ws, d=now[0].date() + timedelta(days=1))
    booking.odo_milestone = 12000
    db.add(booking)
    db.commit()
    assert (await reminder.remind(vehicle.id)).reason == "HAS_BOOKING"
    booking.status = BookingStatus.CANCELLED
    channel.is_enabled = True
    db.add(booking)
    db.add(channel)
    db.commit()
    assert (await reminder.remind(vehicle.id)).deliveries_sent == 1
    assert db.exec(select(Reminder)).one().id == original


@pytest.mark.asyncio
async def test_other_milestone_booking_does_not_pause(setup):
    db, owner, vehicle, cfg, now = setup
    ws = add_workshop(db)
    booking = add_booking(db, owner, vehicle, ws, d=now[0].date() + timedelta(days=1))
    booking.odo_milestone = 24000
    db.add(booking)
    db.commit()
    reminder, _ = service(db, cfg, now)
    assert (await reminder.remind(vehicle.id)).deliveries_sent == 1


@pytest.mark.asyncio
async def test_ongoing_previous_day_booking_still_pauses(setup):
    db, owner, vehicle, cfg, now = setup
    ws = add_workshop(db)
    booking = add_booking(db, owner, vehicle, ws, d=now[0].date() - timedelta(days=1), status=BookingStatus.IN_PROGRESS)
    booking.odo_milestone = 12000
    db.add(booking)
    db.commit()
    reminder, _ = service(db, cfg, now)
    assert (await reminder.remind(vehicle.id)).reason == "HAS_BOOKING"
    assert not db.exec(select(EmailOutbox)).all()


@pytest.mark.asyncio
async def test_board_complete_resolves_reminder_and_preserves_delivery(setup):
    from src.common.core.identity.workshop_owner import WorkshopOwner
    from src.modules.workshop_board.schemas import TransitionRequest
    from src.modules.workshop_board.service import WorkshopBoardService

    db, owner, vehicle, cfg, now = setup
    reminder, _ = service(db, cfg, now)
    await reminder.remind(vehicle.id)
    original = db.exec(select(EmailOutbox)).one().delivery_id
    ws = add_workshop(db)
    booking = add_booking(db, owner, vehicle, ws, d=now[0].date(), status=BookingStatus.IN_PROGRESS)
    booking.odo_milestone = 12000
    db.add(booking)
    db.commit()
    board = WorkshopBoardService(db, clock=lambda: now[0])
    req = TransitionRequest(action="COMPLETE", expected_status="IN_PROGRESS", actual_cost="350000.00")
    await board.transition(db.get(WorkshopOwner, ws.owner_id), ws, booking.id, req)
    closed = db.exec(select(Reminder)).one()
    assert closed.is_resolved and closed.resolution_reason == "MAINTENANCE_COMPLETED"
    assert db.get(EmailOutbox, original) is not None
    await reminder.remind(vehicle.id)
    assert len(db.exec(select(EmailOutbox)).all()) == 1


def event(kind, delivery_id=None, provider="provider-1"):
    return {
        "type": kind,
        "created_at": "2026-10-13T01:00:00Z",
        "data": {
            "email_id": provider,
            "to": ["owner@example.com"],
            "tags": {"delivery_id": str(delivery_id)} if delivery_id else {},
        },
    }


@pytest.mark.asyncio
async def test_early_webhook_dedup_and_out_of_order_cannot_unsuppress(setup):
    db, owner, vehicle, cfg, now = setup
    cfg.email_mode = "resend"
    transport = Transport()
    reminder, adapter = service(db, cfg, now, transport)

    def early():
        outbox = db.exec(select(EmailOutbox)).one()
        adapter.record_webhook("early", event("email.delivered", outbox.delivery_id))

    transport.on_send = early
    await reminder.remind(vehicle.id)
    outbox = db.exec(select(EmailOutbox)).one()
    assert outbox.delivery_state == "delivered"
    assert adapter.record_webhook("bounce", event("email.bounced")) is True
    assert adapter.record_webhook("bounce", event("email.bounced")) is False
    adapter.record_webhook("late-sent", event("email.sent"))
    assert db.get(EmailOutbox, outbox.delivery_id).delivery_state == "bounced"
    assert db.get(EmailSuppression, address_hash(owner.email))
    assert len(db.exec(select(EmailWebhookEvent)).all()) == 3


@pytest.mark.asyncio
async def test_event_without_tag_is_reconciled_after_provider_response(setup):
    db, owner, vehicle, cfg, now = setup
    cfg.email_mode = "resend"
    transport = Transport()
    reminder, adapter = service(db, cfg, now, transport)
    transport.on_send = lambda: adapter.record_webhook("early-no-tag", event("email.delivered"))
    await reminder.remind(vehicle.id)
    assert db.exec(select(EmailOutbox)).one().delivery_state == "delivered"
    assert db.exec(select(EmailWebhookEvent)).one().applied_at is not None


@pytest.mark.asyncio
async def test_unknown_response_stops_after_retry_window(setup):
    db, owner, vehicle, cfg, now = setup
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"))
    reminder, _ = service(db, cfg, now, transport)
    await reminder.remind(vehicle.id)
    now[0] += timedelta(hours=23)
    await reminder.remind(vehicle.id)
    assert len(transport.calls) == 1
    assert db.exec(select(EmailOutbox)).one().delivery_state == "needs_reconciliation"


@pytest.mark.asyncio
async def test_claim_blocks_other_worker_and_recovery_reuses_payload(setup):
    db, owner, vehicle, cfg, now = setup
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"))
    reminder, adapter = service(db, cfg, now, transport)
    await reminder.remind(vehicle.id)
    outbox = db.exec(select(EmailOutbox)).one()
    frozen = dict(outbox.payload)
    outbox.next_attempt_at = None
    outbox.claim_token, outbox.lease_until = "old-worker", now[0] + timedelta(seconds=60)
    db.add(outbox)
    db.commit()
    await reminder.remind(vehicle.id)
    assert len(transport.calls) == 1
    now[0] += timedelta(seconds=61)
    transport.results = [DeliveryResult.sent("recovered")]
    await reminder.remind(vehicle.id)
    assert len(transport.calls) == 2 and transport.calls[1][1] == frozen


@pytest.mark.asyncio
async def test_booking_mail_is_never_sent_by_email_adapter(setup):
    db, owner, vehicle, cfg, now = setup
    transport = Transport()
    _, adapter = service(db, cfg, now, transport)
    result = await NotificationService([adapter]).deliver(
        ReminderChannel.EMAIL, owner.user_id, NotificationMessage("booking", "text")
    )
    assert result.error_code == "EMAIL_MAINTENANCE_ONLY" and not transport.calls


@pytest.mark.asyncio
async def test_retention_removes_payload_but_keeps_cooldown_history(setup):
    db, owner, vehicle, cfg, now = setup
    reminder, adapter = service(db, cfg, now)
    await reminder.remind(vehicle.id)
    now[0] += timedelta(days=31)
    assert adapter.purge_payloads() == 1
    outbox = db.exec(select(EmailOutbox)).one()
    assert outbox.payload is None and outbox.recipient is None
    assert outbox.accepted_at and outbox.recipient_hash and outbox.provider_message_id
