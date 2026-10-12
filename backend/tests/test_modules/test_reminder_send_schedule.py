"""Durable owner schedules, quiet hours, retry and current eligibility."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlmodel import Session, select

from src.common.core.maintenance import Reminder
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import DeliveryStatus, ReminderDelivery
from src.common.core.notification.email import EmailOutbox
from src.modules.notification.channels import DeliveryResult, NotificationMessage
from src.modules.notification.preferences import Preferences
from src.modules.notification.reminder_service import list_due_delivery_ids
from src.modules.notification.schemas import NotificationSettingsUpdateIn
from src.modules.notification.send_schedule import eligible_at, next_allowed_at
from src.modules.notification.settings_service import NotificationSettingsService
from tests.test_modules import test_main_email_reminders as email_tests
from tests.test_modules.test_main_email_reminders import Transport, service


@pytest.fixture
def setup(monkeypatch):
    yield from email_tests.setup.__wrapped__(monkeypatch)


def preferences(preferred=None, quiet=None, zone="Asia/Ho_Chi_Minh"):
    return Preferences(
        True,
        2,
        frozenset(),
        False,
        preferred_send_time=preferred,
        quiet_hours_start=quiet[0] if quiet else None,
        quiet_hours_end=quiet[1] if quiet else None,
        timezone=zone,
    )


@pytest.mark.parametrize(
    "at,preferred,quiet,initial,expected",
    [
        ("2026-10-13T01:00:00+00:00", "19:00", None, True, "2026-10-13T12:00:00+00:00"),
        ("2026-10-13T13:00:00+00:00", "19:00", None, True, "2026-10-14T12:00:00+00:00"),
        ("2026-10-13T12:05:00+00:00", "19:00", ("22:00", "07:00"), False, "2026-10-13T12:05:00+00:00"),
        ("2026-10-13T15:05:00+00:00", "19:00", ("22:00", "07:00"), False, "2026-10-14T12:00:00+00:00"),
        ("2026-10-13T16:00:00+00:00", None, ("22:00", "07:00"), False, "2026-10-14T00:00:00+00:00"),
        ("2026-10-13T01:00:00+00:00", "23:00", ("22:00", "07:00"), True, "2026-10-14T00:00:00+00:00"),
        ("2026-10-13T03:00:00+00:00", None, ("09:00", "17:00"), False, "2026-10-13T10:00:00+00:00"),
        ("2026-10-13T00:00:00+00:00", None, ("22:00", "07:00"), False, "2026-10-13T00:00:00+00:00"),
    ],
)
def test_local_window_boundaries(at, preferred, quiet, initial, expected):
    assert next_allowed_at(
        datetime.fromisoformat(at), preferences(preferred, quiet), initial=initial
    ) == datetime.fromisoformat(expected)


@pytest.mark.parametrize(
    "at,preferred,expected",
    [
        ("2026-03-08T05:00:00+00:00", "02:30", "2026-03-08T07:30:00+00:00"),
        ("2026-11-01T06:00:00+00:00", "01:30", "2026-11-01T06:30:00+00:00"),
    ],
)
def test_dst_missing_and_ambiguous_local_hours(at, preferred, expected):
    assert next_allowed_at(
        datetime.fromisoformat(at), preferences(preferred, zone="America/New_York"), initial=True
    ) == datetime.fromisoformat(expected)


def test_initial_creation_within_selected_minute_does_not_wait_another_day():
    now = datetime(2026, 10, 13, 12, 0, 30, tzinfo=UTC)
    assert next_allowed_at(now, preferences("19:00"), initial=True) == now


def test_midnight_dispatch_tick_preserves_late_slot_without_overriding_quiet_hours():
    due = datetime(2026, 10, 13, 16, 59, tzinfo=UTC)  # 23:59 in VN
    now = due + timedelta(minutes=1)
    assert eligible_at(now, preferences("23:59"), due) == now
    assert eligible_at(now, preferences("23:59", ("00:00", "07:00")), due) > now


@pytest.mark.parametrize(
    "payload",
    [
        {"preferredSendTime": "24:00"},
        {"preferredSendTime": "7:00"},
        {"preferredSendTime": "19:00:00"},
        {"preferredSendTime": 1900},
        {"quietHours": {"start": "22:00", "end": "22:00"}},
        {"quietHours": {"start": "22:00"}},
        {"timezone": "Mars/Zone"},
        {"timezone": None},
    ],
)
def test_invalid_schedule_is_rejected(payload):
    with pytest.raises(ValidationError):
        NotificationSettingsUpdateIn.model_validate(payload)


def save(db, owner, cfg, now, **payload):
    return NotificationSettingsService(
        db, available_channels={ReminderChannel.EMAIL}, default_lead_days=2, clock=lambda: now[0]
    ).update(owner, NotificationSettingsUpdateIn.model_validate(payload))


@pytest.mark.asyncio
async def test_feed_now_email_later_survives_new_session_and_dispatch_is_idempotent(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00", quietHours={"start": "22:00", "end": "07:00"})
    transport = Transport()
    cfg.email_mode = "resend"
    job, _ = service(db, cfg, now, transport)
    outcome = await job.remind(vehicle.id)
    reminder = db.exec(select(Reminder)).one()
    delivery = db.exec(select(ReminderDelivery)).one()
    assert outcome.created_level and reminder.scheduled_at.replace(tzinfo=UTC) == now[0]
    assert not transport.calls and not list_due_delivery_ids(db, now[0])
    assert delivery.next_eligible_send_at.replace(tzinfo=UTC) == now[0] + timedelta(hours=11)
    delivery_id = delivery.id
    now[0] += timedelta(hours=11)
    with Session(db.bind) as restarted:
        dispatch, _ = service(restarted, cfg, now, transport)
        assert list_due_delivery_ids(restarted, now[0]) == [delivery_id]
        dispatch._calculate = Mock(wraps=dispatch._calculate)
        assert await dispatch.dispatch_delivery(delivery_id) == 1
        assert dispatch._calculate.call_count == 1
        assert await dispatch.dispatch_delivery(delivery_id) == 0
        assert not list_due_delivery_ids(restarted, now[0])
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_retry_waits_next_day_and_extends_legacy_23_hour_deadline(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="21:59", quietHours={"start": "22:00", "end": "07:00"})
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("RATE_LIMITED"), DeliveryResult.sent("retry"))
    job, _ = service(db, cfg, now, transport)
    await job.remind(vehicle.id)
    delivery_id = db.exec(select(ReminderDelivery.id)).one()
    now[0] = now[0].replace(hour=14, minute=59)
    assert await job.dispatch_delivery(delivery_id) == 0
    outbox = db.exec(select(EmailOutbox)).one()
    assert outbox.retry_until.replace(tzinfo=UTC) == now[0] + timedelta(hours=72)
    frozen = dict(outbox.payload)
    now[0] += timedelta(minutes=6)
    assert await job.dispatch_delivery(delivery_id) == 0
    assert len(transport.calls) == 1
    now[0] += timedelta(days=1, minutes=-6)
    assert await job.dispatch_delivery(delivery_id) == 1
    assert transport.calls[1][1] == frozen


@pytest.mark.asyncio
async def test_uncertain_email_is_not_retried_next_day_after_provider_key_expiry(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="21:59", quietHours={"start": "22:00", "end": "07:00"})
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"))
    job, _ = service(db, cfg, now, transport)
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    now[0] = now[0].replace(hour=14, minute=59)
    await job.dispatch_delivery(delivery.id)
    outbox = db.exec(select(EmailOutbox)).one()
    assert outbox.delivery_state == "needs_reconciliation"
    assert delivery.next_eligible_send_at is None and outbox.next_attempt_at is None
    now[0] += timedelta(days=1)
    assert await job.dispatch_delivery(delivery.id) == 0
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_rate_limit_cannot_erase_an_earlier_uncertain_attempt(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00")
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"), DeliveryResult.failed("RATE_LIMITED"))
    job, _ = service(db, cfg, now, transport)
    await job.remind(vehicle.id)
    delivery_id = db.exec(select(ReminderDelivery.id)).one()
    now[0] += timedelta(hours=11)
    first = now[0]
    await job.dispatch_delivery(delivery_id)
    now[0] += timedelta(minutes=5)
    await job.dispatch_delivery(delivery_id)
    outbox = db.exec(select(EmailOutbox)).one()
    assert outbox.uncertain_attempt_at.replace(tzinfo=UTC) == first
    save(db, owner, cfg, now, quietHours={"start": "19:06", "end": "07:00"})
    assert outbox.delivery_state == "needs_reconciliation"
    assert db.get(ReminderDelivery, delivery_id).next_eligible_send_at is None
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_changing_time_reschedules_same_delivery_and_disable_cancels(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00")
    job, _ = service(db, cfg, now)
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    saved = save(db, owner, cfg, now, preferredSendTime="20:00")
    assert saved.preferred_send_time == "20:00"
    assert db.get(ReminderDelivery, delivery.id).next_eligible_send_at.replace(tzinfo=UTC) == now[0] + timedelta(
        hours=12
    )
    save(db, owner, cfg, now, remindersEnabled=False)
    assert delivery.error_code == "SCHEDULE_CANCELLED" and delivery.next_eligible_send_at is None
    now[0] += timedelta(hours=12)
    assert await job.dispatch_delivery(delivery.id) == 0


@pytest.mark.asyncio
async def test_adapter_final_gate_blocks_early_direct_send(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00")
    transport = Transport()
    cfg.email_mode = "resend"
    job, adapter = service(db, cfg, now, transport)
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    result = await adapter.send(
        owner.user_id, NotificationMessage("subject", "body", kind="MAINTENANCE_REMINDER", delivery_id=str(delivery.id))
    )
    assert result.deferred and result.error_code == "SEND_TIME_NOT_REACHED"
    assert not transport.calls and delivery.attempts == 0


@pytest.mark.asyncio
async def test_missed_days_do_not_burst_or_send_expired_schedule(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00")
    job, _ = service(db, cfg, now)
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    now[0] += timedelta(days=8)
    assert await job.dispatch_delivery(delivery.id) == 0
    assert delivery.error_code == "DELIVERY_EXPIRED" and delivery.next_eligible_send_at is None


@pytest.mark.asyncio
async def test_booking_confirmation_cancels_pending_delivery_in_same_transaction(setup):
    from src.common.core.maintenance import BookingStatus
    from src.modules.booking.state_machine import Actor, BookingStateMachine
    from tests._maintenance import add_booking, add_workshop

    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00")
    job, _ = service(db, cfg, now)
    await job.remind(vehicle.id)
    delivery_id = db.exec(select(ReminderDelivery.id)).one()
    booking = add_booking(db, owner, vehicle, add_workshop(db), d=now[0].date(), status=BookingStatus.PENDING)
    BookingStateMachine(db).transition(booking, BookingStatus.CONFIRMED, actor=Actor.system(), source="P2_TEST")
    assert db.get(ReminderDelivery, delivery_id).next_eligible_send_at is None
    db.rollback()
    assert db.get(ReminderDelivery, delivery_id).status == DeliveryStatus.PENDING
    BookingStateMachine(db).transition(booking, BookingStatus.CONFIRMED, actor=Actor.system(), source="P2_TEST")
    db.commit()
    assert db.get(ReminderDelivery, delivery_id).error_code == "SCHEDULE_CANCELLED"
    now[0] += timedelta(hours=11)
    assert await job.dispatch_delivery(delivery_id) == 0


@pytest.mark.asyncio
async def test_removing_email_channel_cancels_pending_delivery(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00")
    job, _ = service(db, cfg, now)
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    save(db, owner, cfg, now, channels=[{"channel": "EMAIL", "enabled": False}])
    assert delivery.next_eligible_send_at is None and delivery.error_code == "SCHEDULE_CANCELLED"


@pytest.mark.asyncio
async def test_schedule_changes_do_not_reset_attempts_or_move_expiry_indefinitely(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00")
    job, _ = service(db, cfg, now)
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    expires = delivery.schedule_expires_at
    now[0] += timedelta(days=1)
    save(db, owner, cfg, now, preferredSendTime="20:00", timezone="Asia/Tokyo")
    assert delivery.schedule_expires_at == expires and delivery.attempts == 0


@pytest.mark.asyncio
async def test_dispatch_after_short_downtime_sends_one_current_reminder(setup):
    db, owner, vehicle, cfg, now = setup
    save(db, owner, cfg, now, preferredSendTime="19:00")
    job, _ = service(db, cfg, now)
    await job.remind(vehicle.id)
    delivery_id = db.exec(select(ReminderDelivery.id)).one()
    now[0] += timedelta(hours=12)
    assert await job.dispatch_delivery(delivery_id) == 1
    assert await job.dispatch_delivery(delivery_id) == 0
    assert len(db.exec(select(Reminder)).all()) == 1


@pytest.mark.asyncio
async def test_consent_revocation_cancels_scheduled_predictive_email(setup):
    from tests.test_modules.test_personalized_reminders import configure_usage

    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    save(db, owner, cfg, now, preferredSendTime="19:00")
    job, _ = service(db, cfg, now)
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    assert (db.exec(select(Reminder)).one().details or {}).get("personalization")
    save(db, owner, cfg, now, personalizedRemindersEnabled=False)
    assert delivery.error_code == "PERSONALIZATION_REVOKED" and delivery.next_eligible_send_at is None
    now[0] += timedelta(hours=11)
    assert await job.dispatch_delivery(delivery.id) == 0 and delivery.attempts == 0


@pytest.mark.asyncio
async def test_uncertain_non_email_claim_is_not_sent_again_after_lease_expiry(setup):
    from sqlalchemy import delete

    from src.common.core.notification import UserNotificationChannel
    from src.modules.notification.channels import NotificationService
    from src.modules.notification.reminder_service import MaintenanceReminderService
    from src.modules.user_vehicle.service import UserVehicleService
    from tests._user_vehicle import RecordingScheduler
    from tests.test_modules.test_reminder_service import ScriptedAdapter

    db, owner, vehicle, cfg, now = setup
    db.execute(delete(UserNotificationChannel))
    db.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.SMS))
    db.commit()
    save(db, owner, cfg, now, preferredSendTime="19:00")
    adapter = ScriptedAdapter(ReminderChannel.SMS)
    vehicles = UserVehicleService(db, RecordingScheduler(), clock=lambda: now[0])
    job = MaintenanceReminderService(
        db, NotificationService([adapter]), lambda v, at: vehicles.calculate(v, now=at), clock=lambda: now[0]
    )
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    now[0] += timedelta(hours=11)
    delivery.claim_token, delivery.lease_until = "interrupted-worker", now[0] - timedelta(seconds=1)
    delivery.attempts = 1
    db.add(delivery)
    db.commit()
    assert await job.dispatch_delivery(delivery.id) == 0
    assert delivery.error_code == "DELIVERY_UNCERTAIN" and delivery.next_eligible_send_at is None
    assert not adapter.calls and delivery.attempts == 1
