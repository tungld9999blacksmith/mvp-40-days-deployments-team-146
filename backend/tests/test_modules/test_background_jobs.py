"""Tests for the sprint 3-4 background jobs (in-memory SQLite, fake external channel).

* us-033 HOOK-BR-001 / JOB-BR-001 — 24h appointment reminders.
* us-041 JOB-FU-001 / JOB-FU-002 — follow-up send and auto-close.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlmodel import select

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.maintenance.booking import BookingStatus
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import (
    BookingReminder,
    BookingReminderDelivery,
    BookingReminderStatus,
    FollowUpDelivery,
    UserNotificationChannel,
)
from src.modules.booking.reminders import BookingReminderJob, BookingReminderScheduler, ReminderConfig
from src.modules.booking.state_machine import Actor, BookingStateMachine
from src.modules.follow_up.jobs import FollowUpSendJob, close_expired
from src.modules.notification.channels import (
    DeliveryResult,
    NotificationChannelAdapter,
    NotificationService,
)
from src.modules.oem_integration.service import as_utc
from tests._maintenance import add_booking, add_workshop, make_session
from tests._user_vehicle import add_owner, add_vehicle

# 2026-10-03 09:00 VN.
NOW = datetime(2026, 10, 3, 2, 0, tzinfo=UTC)


class FakeChannel(NotificationChannelAdapter):
    """Stands in for a future external channel (none is implemented yet)."""

    channel = ReminderChannel.ZALO

    def __init__(self, results: list[DeliveryResult] | None = None) -> None:
        self.results = list(results or [])
        self.sent: list[tuple[int, str]] = []

    async def send(self, user_id, message):
        self.sent.append((user_id, message.body))
        return self.results.pop(0) if self.results else DeliveryResult.sent()


@pytest.fixture
def session():
    yield from make_session()


@pytest.fixture
def world(session):
    user = add_owner(session)
    session.add(UserNotificationChannel(user_id=user.user_id, channel=ReminderChannel.ZALO))
    session.commit()
    vehicle = add_vehicle(session, user)
    workshop = add_workshop(session)
    return session, user, vehicle, workshop


def _job(session, adapter, now=NOW):
    return BookingReminderJob(session, NotificationService([adapter]), ReminderConfig(), clock=lambda: now)


# ── HOOK-BR-001 ─────────────────────────────────────────────────────────────
def test_confirm_schedules_reminder_and_cancel_skips_it(world, monkeypatch):
    from src.modules.booking import state_machine

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    # The status event passes its timestamp to the reminder scheduler. Freeze
    # that clock so this scenario remains a >24h appointment after October 2026.
    monkeypatch.setattr(state_machine, "datetime", FixedDatetime)
    session, user, vehicle, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 5), status=BookingStatus.PENDING)
    machine = BookingStateMachine(session)
    machine.transition(booking, BookingStatus.CONFIRMED, actor=Actor.system(), source="AUTO_CONFIRM")
    session.commit()

    reminder = session.exec(select(BookingReminder)).one()
    assert reminder.status == BookingReminderStatus.SCHEDULED
    # 05/10 09:00 VN = 02:00 UTC; minus 24h.
    assert as_utc(reminder.scheduled_at) == datetime(2026, 10, 4, 2, 0, tzinfo=UTC)

    machine.transition(
        booking,
        BookingStatus.CANCELLED,
        actor=Actor.vehicle_owner(user.user_id),
        source="APP",
        reason_code="OWNER_CANCELLED",
    )
    session.commit()
    session.refresh(reminder)
    assert reminder.status == BookingReminderStatus.SKIPPED
    assert reminder.skip_reason == "BOOKING_CANCELLED"


def test_confirmed_within_24h_is_recorded_as_skipped(world):
    session, user, vehicle, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 3), t=time(15))
    BookingReminderScheduler(session, clock=lambda: NOW).on_confirmed(booking, confirmed_at=NOW)
    reminder = session.exec(select(BookingReminder)).one()
    assert (reminder.status, reminder.skip_reason) == (BookingReminderStatus.SKIPPED, "BOOKED_WITHIN_24H")


# ── JOB-BR-001 ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_job_sends_due_reminder_once(world):
    session, user, vehicle, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 4), t=time(8))
    BookingReminderScheduler(session).on_confirmed(booking, confirmed_at=NOW - timedelta(days=2))
    session.commit()
    adapter = FakeChannel()

    report = await _job(session, adapter).run()
    assert report.sent == 1 and len(adapter.sent) == 1
    assert booking.booking_code in adapter.sent[0][1]
    reminder = session.exec(select(BookingReminder)).one()
    assert reminder.status == BookingReminderStatus.SENT

    again = await _job(session, adapter).run()  # second run: nothing due
    assert again.due == 0 and len(adapter.sent) == 1


@pytest.mark.asyncio
async def test_job_skips_rescheduled_and_reconciles_missing(world):
    session, user, vehicle, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 4), t=time(8))
    # Reconcile: confirmed booking without reminder and no confirmation event ⇒
    # treated as confirmed too close to the slot (BR-ENT-481 proposal): skipped.
    report = await _job(session, FakeChannel()).run()
    assert report.reconciled == 1 and report.sent == 0
    assert session.exec(select(BookingReminder)).one().skip_reason == "BOOKED_WITHIN_24H"

    other = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 4), t=time(9), code="EVC-0002")
    BookingReminderScheduler(session).on_confirmed(other, confirmed_at=NOW - timedelta(days=2))
    other.time_slot = time(10)  # moved elsewhere without the hook
    session.add(other)
    session.commit()
    report = await _job(session, FakeChannel()).run()
    assert report.skipped_by_reason["RESCHEDULED"] == 1


@pytest.mark.asyncio
async def test_job_retries_transient_failure(world):
    session, user, vehicle, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 4), t=time(8))
    BookingReminderScheduler(session).on_confirmed(booking, confirmed_at=NOW - timedelta(days=2))
    session.commit()
    adapter = FakeChannel([DeliveryResult.failed("TIMEOUT")])

    first = await _job(session, adapter).run()
    assert first.failed == 1 and first.retried == 0  # backoff: not in the same run
    second = await _job(session, adapter, now=NOW + timedelta(minutes=15)).run()
    assert second.retried == 1 and second.sent == 1
    delivery = session.exec(select(BookingReminderDelivery)).one()
    assert delivery.attempts == 2


# ── JOB-FU-001 / JOB-FU-002 ─────────────────────────────────────────────────
def _follow_up(session, booking, *, scheduled_at=NOW - timedelta(minutes=1)):
    follow_up = FollowUp(booking_id=booking.id, message="Xe chạy thế nào?", scheduled_at=scheduled_at)
    session.add(follow_up)
    session.commit()
    return follow_up


@pytest.mark.asyncio
async def test_follow_up_job_opens_and_sends(world):
    session, user, vehicle, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 2), status=BookingStatus.COMPLETED)
    follow_up = _follow_up(session, booking)
    adapter = FakeChannel([DeliveryResult.failed("TIMEOUT")])

    report = await FollowUpSendJob(session, NotificationService([adapter]), clock=lambda: NOW).run()
    session.refresh(follow_up)
    # BR-904 — opened even though the first delivery failed.
    assert follow_up.status == FollowUpStatus.SENT and report.opened == 1 and report.failed == 1
    later = NOW + timedelta(minutes=15)
    retry = await FollowUpSendJob(session, NotificationService([adapter]), clock=lambda: later).run()
    assert retry.retried == 1
    assert session.exec(select(FollowUpDelivery)).one().attempts == 2


@pytest.mark.asyncio
async def test_follow_up_opens_without_external_channel(world):
    """The survey is shown in the in-app feed even when no external channel is on."""
    session, user, vehicle, workshop = world
    session.delete(session.exec(select(UserNotificationChannel)).one())
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 2), status=BookingStatus.COMPLETED)
    follow_up = _follow_up(session, booking)

    report = await FollowUpSendJob(session, NotificationService([FakeChannel()]), clock=lambda: NOW).run()
    session.refresh(follow_up)
    assert follow_up.status == FollowUpStatus.SENT and report.opened == 1 and report.sent == 0
    assert session.exec(select(FollowUpDelivery)).all() == []


@pytest.mark.asyncio
async def test_follow_up_not_eligible_when_booking_not_completed(world):
    session, user, vehicle, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 10, 2), status=BookingStatus.CANCELLED)
    follow_up = _follow_up(session, booking)
    report = await FollowUpSendJob(session, NotificationService([FakeChannel()]), clock=lambda: NOW).run()
    session.refresh(follow_up)
    assert report.not_eligible == 1
    assert (follow_up.status, follow_up.closed_reason) == (FollowUpStatus.CLOSED, "NOT_ELIGIBLE")


def test_close_expired_after_72h(world):
    session, user, vehicle, workshop = world
    booking = add_booking(session, user, vehicle, workshop, d=date(2026, 9, 28), status=BookingStatus.COMPLETED)
    follow_up = _follow_up(session, booking)
    follow_up.status, follow_up.sent_at = FollowUpStatus.SENT, NOW - timedelta(hours=73)
    session.add(follow_up)
    session.commit()

    assert close_expired(session, now=NOW) == 1
    session.refresh(follow_up)
    assert (follow_up.status, follow_up.closed_reason) == (FollowUpStatus.CLOSED, "NO_RESPONSE")
