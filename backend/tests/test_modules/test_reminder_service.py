"""Tests for the maintenance reminder job logic (FEAT-NOTI-001 JOB-NOTI-001)."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time

import pytest
from sqlmodel import select

from src.common.core.identity import DiscordLinkStatus, UserDiscordLink
from src.common.core.identity.vehicle_user import UserStatus
from src.common.core.maintenance import Booking, BookingStatus, Reminder
from src.common.core.maintenance.reminder import ReminderChannel, ReminderLevel
from src.common.core.notification import (
    DeliveryStatus,
    ReminderDelivery,
    UserNotificationChannel,
    UserNotificationSetting,
)
from src.common.core.workshop.workshop import Workshop, WorkshopStatus
from src.modules.notification.adapters import LoggingDiscordAdapter
from src.modules.notification.channels import (
    DeliveryResult,
    NotificationChannelAdapter,
    NotificationMessage,
    NotificationService,
)
from src.modules.notification.reminder_service import (
    MaintenanceReminderService,
    list_eligible_vehicle_ids,
)
from src.modules.user_vehicle.service import UserVehicleService
from tests._user_vehicle import (
    RecordingScheduler,
    add_discord_link,
    add_odometer,
    add_owner,
    add_rules,
    add_vehicle,
    make_session,
    mark_synced,
)

# The first milestone (12,000 km / 12 months) is due on 2026-10-15.
TWO_DAYS_BEFORE = datetime(2026, 10, 13, 1, 0, tzinfo=UTC)  # 08:00 in Vietnam
FIVE_DAYS_BEFORE = datetime(2026, 10, 10, 1, 0, tzinfo=UTC)
THREE_DAYS_LATE = datetime(2026, 10, 18, 1, 0, tzinfo=UTC)


class ScriptedAdapter(NotificationChannelAdapter):
    """Adapter double: returns scripted results and records every call."""

    def __init__(self, channel: ReminderChannel, *results: DeliveryResult) -> None:
        self.channel = channel  # instance attribute shadows the ClassVar
        self._results = list(results)
        self.calls: list[tuple[int, NotificationMessage]] = []

    async def send(self, user_id: int, message: NotificationMessage) -> DeliveryResult:
        self.calls.append((user_id, message))
        return self._results.pop(0) if self._results else DeliveryResult.sent()


@pytest.fixture
def session():
    yield from make_session()


@pytest.fixture
def owner(session):
    return add_owner(session)


@pytest.fixture
def vehicle(session, owner):
    """VF6 bought 2025-10-15, rules seeded, synced, 5,000 km (far from the km threshold)."""
    vehicle = add_vehicle(session, owner)
    add_rules(session)
    add_odometer(session, vehicle, 5_000, TWO_DAYS_BEFORE)
    mark_synced(session, vehicle, TWO_DAYS_BEFORE)
    return vehicle


def _service(session, adapters, now, **kwargs) -> MaintenanceReminderService:
    vehicles = UserVehicleService(session, RecordingScheduler(), clock=lambda: now)
    return MaintenanceReminderService(
        session,
        NotificationService(adapters),
        lambda vehicle, at: vehicles.calculate(vehicle, now=at),
        clock=lambda: now,
        **kwargs,
    )


def _discord(*results: DeliveryResult) -> ScriptedAdapter:
    return ScriptedAdapter(ReminderChannel.DISCORD, *results)


def _deliveries(session) -> list[ReminderDelivery]:
    return list(session.exec(select(ReminderDelivery)).all())


# ── Timing (BR-501, AC-501, AC-502) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_reminds_two_days_before_by_default_ac501(session, vehicle):
    discord = _discord()

    outcome = await _service(session, [discord], TWO_DAYS_BEFORE).remind(vehicle.id)

    assert outcome.created_level is ReminderLevel.EARLY and outcome.deliveries_sent == 1
    (reminder,) = session.exec(select(Reminder)).all()
    assert reminder.target_odo_milestone == 12_000 and not reminder.is_resolved
    (delivery,) = _deliveries(session)
    assert delivery.channel is ReminderChannel.DISCORD
    assert delivery.status is DeliveryStatus.SENT and delivery.attempts == 1
    (_, message) = discord.calls[0]
    assert "12,000 km / 12 months" in message.body and "30A12345" not in message.body


@pytest.mark.asyncio
async def test_no_reminder_before_the_lead_window(session, vehicle):
    discord = _discord()

    outcome = await _service(session, [discord], FIVE_DAYS_BEFORE).remind(vehicle.id)

    assert outcome.created_level is None and discord.calls == []
    assert session.exec(select(Reminder)).all() == []


@pytest.mark.asyncio
async def test_owner_lead_days_apply_ac502(session, vehicle, owner):
    session.add(UserNotificationSetting(user_id=owner.user_id, reminder_lead_days=5))
    session.commit()

    outcome = await _service(session, [_discord()], FIVE_DAYS_BEFORE).remind(vehicle.id)

    assert outcome.created_level is ReminderLevel.EARLY


@pytest.mark.asyncio
async def test_default_lead_days_come_from_config(session, vehicle):
    outcome = await _service(
        session, [_discord()], FIVE_DAYS_BEFORE, default_lead_days=7
    ).remind(vehicle.id)

    assert outcome.created_level is ReminderLevel.EARLY


@pytest.mark.asyncio
async def test_km_threshold_reminds_before_the_date_af502(session, vehicle):
    add_odometer(session, vehicle, 11_700, FIVE_DAYS_BEFORE)

    outcome = await _service(session, [_discord()], FIVE_DAYS_BEFORE).remind(vehicle.id)

    assert outcome.created_level is ReminderLevel.EARLY


@pytest.mark.asyncio
async def test_overdue_sends_expired_once_ac504(session, vehicle):
    discord = _discord()
    service = _service(session, [discord], THREE_DAYS_LATE)

    first = await service.remind(vehicle.id)
    second = await service.remind(vehicle.id)

    assert first.created_level is ReminderLevel.EXPIRED and first.deliveries_sent == 1
    assert second.created_level is None and second.deliveries_sent == 0
    assert len(discord.calls) == 1
    assert "overdue" in discord.calls[0][1].body


# ── Idempotency (BR-502, AC-503) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_same_level_is_never_sent_twice_ac503(session, vehicle):
    discord = _discord()
    service = _service(session, [discord], TWO_DAYS_BEFORE)

    await service.remind(vehicle.id)
    again = await service.remind(vehicle.id)

    assert again.created_level is None and again.deliveries_sent == 0
    assert len(discord.calls) == 1
    assert len(session.exec(select(Reminder)).all()) == 1


@pytest.mark.asyncio
async def test_early_then_expired_are_two_reminders(session, vehicle):
    discord = _discord()
    await _service(session, [discord], TWO_DAYS_BEFORE).remind(vehicle.id)

    await _service(session, [discord], THREE_DAYS_LATE).remind(vehicle.id)

    levels = {r.reminder_level for r in session.exec(select(Reminder)).all()}
    assert levels == {ReminderLevel.EARLY, ReminderLevel.EXPIRED}
    assert len(discord.calls) == 2


# ── Skips ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_disabled_reminders_are_skipped_ac506(session, vehicle, owner):
    session.add(UserNotificationSetting(user_id=owner.user_id, reminders_enabled=False))
    session.commit()

    outcome = await _service(session, [_discord()], TWO_DAYS_BEFORE).remind(vehicle.id)

    assert (outcome.status, outcome.reason) == ("skipped", "REMINDERS_DISABLED")
    assert session.exec(select(Reminder)).all() == []


@pytest.mark.asyncio
async def test_open_booking_stops_and_closes_reminders_ac505(session, vehicle, owner):
    discord = _discord()
    await _service(session, [discord], TWO_DAYS_BEFORE).remind(vehicle.id)
    workshop = Workshop(
        external_center_id="SC-01",
        name="Workshop",
        region="north",
        type="dealer",
        address="Ha Noi",
        total_technicians=4,
        status=WorkshopStatus.INACTIVE,
    )
    session.add(workshop)
    session.commit()
    session.add(
        Booking(
            booking_code="BK-1",
            user_id=owner.user_id,
            user_vehicle_id=vehicle.id,
            workshop_id=workshop.id,
            booking_date=date(2026, 10, 14),
            time_slot=time(9, 0),
            status=BookingStatus.CONFIRMED,
        )
    )
    session.commit()

    outcome = await _service(session, [discord], THREE_DAYS_LATE.replace(day=13)).remind(
        vehicle.id
    )

    assert (outcome.status, outcome.reason) == ("skipped", "HAS_BOOKING")
    assert all(r.is_resolved for r in session.exec(select(Reminder)).all())
    assert len(discord.calls) == 1  # nothing new was sent


@pytest.mark.asyncio
async def test_unknown_status_is_skipped_ef504(session, owner):
    vehicle = add_vehicle(session, owner)  # never synced

    outcome = await _service(session, [_discord()], TWO_DAYS_BEFORE).remind(vehicle.id)

    assert (outcome.status, outcome.reason) == ("skipped", "STATUS_UNKNOWN")


@pytest.mark.asyncio
async def test_inactive_owner_is_skipped_br510(session, vehicle, owner):
    owner.status = UserStatus.SUSPENDED
    session.add(owner)
    session.commit()

    outcome = await _service(session, [_discord()], TWO_DAYS_BEFORE).remind(vehicle.id)

    assert (outcome.status, outcome.reason) == ("skipped", "USER_NOT_ACTIVE")
    assert list_eligible_vehicle_ids(session) == []


@pytest.mark.asyncio
async def test_obsolete_milestone_reminders_are_closed(session, vehicle):
    discord = _discord()
    await _service(session, [discord], TWO_DAYS_BEFORE).remind(vehicle.id)
    # The owner serviced the vehicle: the next milestone is now 24,000 km.
    from src.common.core.vehicle import ServiceRecordSource, VehicleServiceRecord

    session.add(
        VehicleServiceRecord(
            user_vehicle_id=vehicle.id,
            source=ServiceRecordSource.OEM,
            external_order_id="SH-1",
            service_date=date(2026, 10, 14),
            odo_km=12_100,
        )
    )
    session.commit()

    await _service(session, [discord], TWO_DAYS_BEFORE).remind(vehicle.id)

    (old,) = session.exec(select(Reminder)).all()
    assert old.target_odo_milestone == 12_000 and old.is_resolved


# ── Channels (BR-505..BR-507, AF-503) ───────────────────────────────────────


@pytest.mark.asyncio
async def test_no_recipient_is_recorded_and_not_retried_ac507(session, vehicle):
    discord = _discord(DeliveryResult.no_recipient())
    service = _service(session, [discord], TWO_DAYS_BEFORE)

    await service.remind(vehicle.id)
    await service.remind(vehicle.id)

    (delivery,) = _deliveries(session)
    assert delivery.status is DeliveryStatus.NO_RECIPIENT and delivery.attempts == 1
    assert len(discord.calls) == 1


@pytest.mark.asyncio
async def test_logging_discord_adapter_needs_an_active_link(session, vehicle, owner):
    service = _service(session, [LoggingDiscordAdapter(session)], TWO_DAYS_BEFORE)

    await service.remind(vehicle.id)
    assert _deliveries(session)[0].status is DeliveryStatus.NO_RECIPIENT


@pytest.mark.asyncio
async def test_logging_discord_adapter_sends_to_active_link(session, vehicle, owner):
    add_discord_link(session, owner)
    service = _service(
        session, [LoggingDiscordAdapter(session, clock=lambda: TWO_DAYS_BEFORE)], TWO_DAYS_BEFORE
    )

    outcome = await service.remind(vehicle.id)

    assert outcome.deliveries_sent == 1
    assert session.get(UserDiscordLink, owner.user_id).last_delivered_at is not None


@pytest.mark.asyncio
async def test_every_enabled_channel_gets_a_delivery_af503(session, vehicle, owner):
    session.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.DISCORD))
    session.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.TELEGRAM))
    session.commit()
    discord = _discord()
    telegram = ScriptedAdapter(ReminderChannel.TELEGRAM)

    outcome = await _service(session, [discord, telegram], TWO_DAYS_BEFORE).remind(vehicle.id)

    assert outcome.deliveries_sent == 2
    assert {d.channel for d in _deliveries(session)} == {
        ReminderChannel.DISCORD,
        ReminderChannel.TELEGRAM,
    }


@pytest.mark.asyncio
async def test_disabled_channel_is_not_used(session, vehicle, owner):
    session.add(
        UserNotificationChannel(
            user_id=owner.user_id, channel=ReminderChannel.DISCORD, is_enabled=False
        )
    )
    session.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.TELEGRAM))
    session.commit()
    discord = _discord()
    telegram = ScriptedAdapter(ReminderChannel.TELEGRAM)

    await _service(session, [discord, telegram], TWO_DAYS_BEFORE).remind(vehicle.id)

    assert discord.calls == [] and len(telegram.calls) == 1


@pytest.mark.asyncio
async def test_one_failing_channel_does_not_block_the_other(session, vehicle, owner):
    session.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.DISCORD))
    session.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.TELEGRAM))
    session.commit()
    discord = _discord(DeliveryResult.failed("TIMEOUT"))
    telegram = ScriptedAdapter(ReminderChannel.TELEGRAM)

    outcome = await _service(session, [discord, telegram], TWO_DAYS_BEFORE).remind(vehicle.id)

    statuses = {d.channel: d.status for d in _deliveries(session)}
    assert outcome.deliveries_sent == 1
    assert statuses == {
        ReminderChannel.DISCORD: DeliveryStatus.FAILED,
        ReminderChannel.TELEGRAM: DeliveryStatus.SENT,
    }


# ── Retry (BR-508, AC-508) ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transient_failures_are_retried_up_to_the_limit_ac508(session, vehicle, caplog):
    timeout = DeliveryResult.failed("TIMEOUT")
    discord = _discord(timeout, timeout, timeout, timeout)
    service = _service(session, [discord], TWO_DAYS_BEFORE, max_attempts=3)

    with caplog.at_level(logging.ERROR):
        for _ in range(5):
            await service.remind(vehicle.id)

    (delivery,) = _deliveries(session)
    assert delivery.status is DeliveryStatus.FAILED and delivery.attempts == 3
    assert len(discord.calls) == 3
    assert "failed for good" in caplog.text


@pytest.mark.asyncio
async def test_retry_can_succeed(session, vehicle):
    discord = _discord(DeliveryResult.failed("RATE_LIMITED"), DeliveryResult.sent())
    service = _service(session, [discord], TWO_DAYS_BEFORE)

    await service.remind(vehicle.id)
    second = await service.remind(vehicle.id)

    (delivery,) = _deliveries(session)
    assert second.deliveries_sent == 1
    assert delivery.status is DeliveryStatus.SENT and delivery.attempts == 2
    assert delivery.sent_at is not None


@pytest.mark.asyncio
async def test_forbidden_is_final_and_revokes_the_discord_link(session, vehicle, owner):
    add_discord_link(session, owner)
    discord = _discord(DeliveryResult.failed("DELIVERY_FORBIDDEN"))
    service = _service(session, [discord], TWO_DAYS_BEFORE)

    await service.remind(vehicle.id)
    await service.remind(vehicle.id)

    (delivery,) = _deliveries(session)
    assert delivery.status is DeliveryStatus.FAILED and delivery.attempts == 1
    assert len(discord.calls) == 1
    link = session.get(UserDiscordLink, owner.user_id)
    assert link.status is DiscordLinkStatus.REVOKED
    assert link.revoked_reason == "delivery_forbidden"


@pytest.mark.asyncio
async def test_unregistered_channel_fails_without_retry(session, vehicle, owner):
    session.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.SMS))
    session.commit()

    await _service(session, [], TWO_DAYS_BEFORE).remind(vehicle.id)
    await _service(session, [], TWO_DAYS_BEFORE).remind(vehicle.id)

    (delivery,) = _deliveries(session)
    assert delivery.status is DeliveryStatus.FAILED
    assert delivery.error_code == "CHANNEL_NOT_AVAILABLE" and delivery.attempts == 1
