"""24h appointment reminders (us-033 HOOK-BR-001 + JOB-BR-001).

* ``BookingReminderScheduler`` — called inside the transaction that confirms,
  cancels or reschedules a booking (BR-ENT-480). It never commits, and a
  failure is swallowed in a SAVEPOINT so it can never break the booking change;
  the job's reconcile phase recreates anything missed (BR-ENT-481).
* ``BookingReminderJob`` — the Celery beat job: reconcile, send due reminders,
  retry transient failures (BR-ENT-482..486).
"""

from __future__ import annotations

import logging
import time as _time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import Session, select

from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_status_event import BookingStatusEvent
from src.common.core.notification import (
    BookingReminder,
    BookingReminderDelivery,
    BookingReminderStatus,
    DeliveryStatus,
)
from src.common.core.workshop import Workshop
from src.modules.notification.channels import (
    RETRYABLE_ERRORS,
    NotificationMessage,
    NotificationService,
)
from src.modules.notification.preferences import channel_rows, effective_channels
from src.modules.oem_integration.service import as_utc

from .domain import TZ_VN, appointment_at

logger = logging.getLogger(__name__)

_WEEKDAYS_VI = ("Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật")


@dataclass(frozen=True)
class ReminderConfig:
    lead_hours: int = 24  # BOOKING_REMINDER_LEAD_HOURS
    min_lead_hours: int = 2  # BOOKING_REMINDER_MIN_LEAD_HOURS
    max_attempts: int = 3  # REMINDER_MAX_ATTEMPTS
    retry_backoff_minutes: int = 5  # next try after attempts × backoff
    batch_size: int = 200
    frontend_url: str = ""


def reminder_config() -> ReminderConfig:
    from src.config import get_settings

    s = get_settings()
    return ReminderConfig(
        lead_hours=s.booking_reminder_lead_hours,
        min_lead_hours=s.booking_reminder_min_lead_hours,
        max_attempts=s.reminder_max_attempts,
        frontend_url=s.frontend_url,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _appt_utc(booking: Booking) -> datetime:
    return appointment_at(booking.booking_date, booking.time_slot).astimezone(UTC)


class BookingReminderScheduler:
    def __init__(
        self,
        session: Session,
        config: ReminderConfig = ReminderConfig(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._config = config
        self._clock = clock

    def on_confirmed(self, booking: Booking, *, confirmed_at: datetime | None = None) -> None:
        """BR-ENT-480 — schedule (or record as skipped) the reminder of the current slot."""
        self._safely(self._schedule, booking, confirmed_at or self._clock())

    def on_cancelled(self, booking_id: UUID) -> None:
        self._safely(self._skip_scheduled, booking_id, "BOOKING_CANCELLED")

    def on_rescheduled(self, booking: Booking) -> None:
        """BR-1210 — the old reminder is skipped, a new one follows the new time."""
        self._safely(self._skip_scheduled, booking.id, "RESCHEDULED")
        self.on_confirmed(booking)

    def _safely(self, fn, *args) -> None:
        try:
            with self._db.begin_nested():
                fn(*args)
        except Exception:  # noqa: BLE001 — reconcile (BR-ENT-481) repairs a missed hook
            logger.warning("booking_reminder.hook_failed", exc_info=True)

    def _schedule(self, booking: Booking, confirmed_at: datetime) -> BookingReminder:
        appt = _appt_utc(booking)
        existing = self._db.exec(
            select(BookingReminder).where(
                BookingReminder.booking_id == booking.id,
                BookingReminder.appointment_at == appt,
            )
        ).first()
        if existing is not None:
            return existing  # ON CONFLICT DO NOTHING
        scheduled = appt - timedelta(hours=self._config.lead_hours)
        reminder = BookingReminder(booking_id=booking.id, appointment_at=appt, scheduled_at=scheduled)
        if as_utc(confirmed_at) >= scheduled:  # BR-703 — confirmed within 24h
            reminder.status = BookingReminderStatus.SKIPPED
            reminder.skip_reason = "BOOKED_WITHIN_24H"
        self._db.add(reminder)
        self._db.flush()
        return reminder

    def _skip_scheduled(self, booking_id: UUID, reason: str) -> None:
        for reminder in self._db.exec(
            select(BookingReminder).where(
                BookingReminder.booking_id == booking_id,
                BookingReminder.status == BookingReminderStatus.SCHEDULED,
            )
        ).all():
            reminder.status = BookingReminderStatus.SKIPPED
            reminder.skip_reason = reason
            self._db.add(reminder)
        self._db.flush()


@dataclass
class JobReport:
    reconciled: int = 0
    due: int = 0
    sent: int = 0
    failed: int = 0
    retried: int = 0
    skipped_by_reason: Counter | None = None

    def as_dict(self) -> dict:
        return {
            "reconciled": self.reconciled,
            "due": self.due,
            "sent": self.sent,
            "failed": self.failed,
            "retried": self.retried,
            "skipped_by_reason": dict(self.skipped_by_reason or {}),
        }


class BookingReminderJob:
    def __init__(
        self,
        session: Session,
        notifications: NotificationService,
        config: ReminderConfig = ReminderConfig(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._notifications = notifications
        self._config = config
        self._clock = clock
        self._scheduler = BookingReminderScheduler(session, config, clock)

    async def run(self) -> JobReport:
        started = _time.perf_counter()
        report = JobReport(skipped_by_reason=Counter())
        report.reconciled = self._reconcile()
        await self._send_due(report)
        await self._retry(report)
        logger.info(
            "booking_reminder.job",
            extra={**report.as_dict(), "duration_ms": round((_time.perf_counter() - started) * 1000)},
        )
        return report

    # ── Phase A — reconcile (BR-ENT-481) ────────────────────────────────
    def _reconcile(self) -> int:
        now = self._clock()
        horizon = now + timedelta(hours=self._config.lead_hours + 1)
        candidates = self._db.exec(
            select(Booking).where(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.booking_date >= now.astimezone(TZ_VN).date(),
                Booking.booking_date <= horizon.astimezone(TZ_VN).date(),
            )
        ).all()
        created = 0
        for booking in candidates:
            appt = _appt_utc(booking)
            if not (now < appt <= horizon):
                continue
            exists = self._db.exec(
                select(BookingReminder.id).where(
                    BookingReminder.booking_id == booking.id,
                    BookingReminder.appointment_at == appt,
                )
            ).first()
            if exists is not None:
                continue
            confirmed_at = self._db.exec(
                select(BookingStatusEvent.created_at)
                .where(
                    BookingStatusEvent.booking_id == booking.id,
                    BookingStatusEvent.to_status == BookingStatus.CONFIRMED,
                )
                .order_by(BookingStatusEvent.created_at.desc())
            ).first()
            # Unknown confirmation time ⇒ treat as "too close" (spec [Proposal]).
            self._scheduler.on_confirmed(booking, confirmed_at=confirmed_at or now)
            created += 1
        self._db.commit()
        return created

    # ── Phase B — send due reminders (BR-ENT-482/483/486) ───────────────
    async def _send_due(self, report: JobReport) -> None:
        now = self._clock()
        due = self._db.exec(
            select(BookingReminder)
            .where(
                BookingReminder.status == BookingReminderStatus.SCHEDULED,
                BookingReminder.scheduled_at <= now,
            )
            .order_by(BookingReminder.scheduled_at)
            .limit(self._config.batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        report.due = len(due)
        for reminder in due:
            booking = self._db.get(Booking, reminder.booking_id)
            reason = self._skip_reason(reminder, booking, now)
            if reason is not None:
                reminder.status = BookingReminderStatus.SKIPPED
                reminder.skip_reason = reason
                self._db.add(reminder)
                self._db.commit()
                report.skipped_by_reason[reason] += 1
                continue
            channels = effective_channels(channel_rows(self._db, booking.user_id))
            channels &= self._notifications.available_channels()
            for channel in sorted(channels, key=lambda c: c.value):
                exists = self._db.exec(
                    select(BookingReminderDelivery.id).where(
                        BookingReminderDelivery.booking_reminder_id == reminder.id,
                        BookingReminderDelivery.channel == channel,
                    )
                ).first()
                if exists is None:
                    self._db.add(BookingReminderDelivery(booking_reminder_id=reminder.id, channel=channel))
            self._db.flush()
            await self._deliver_pending(reminder, booking)
            self._settle(reminder)
            self._db.commit()
            if reminder.status == BookingReminderStatus.SENT:
                report.sent += 1
            elif reminder.status == BookingReminderStatus.FAILED:
                report.failed += 1

    def _skip_reason(self, reminder: BookingReminder, booking: Booking | None, now: datetime) -> str | None:
        """BR-707 / BR-702 — re-check the booking right before sending."""
        if booking is None or booking.status == BookingStatus.CANCELLED:
            return "BOOKING_CANCELLED"
        if booking.status != BookingStatus.CONFIRMED:
            return "BOOKING_NOT_CONFIRMED"
        if _appt_utc(booking) != as_utc(reminder.appointment_at):
            return "RESCHEDULED"
        if now > as_utc(reminder.appointment_at) - timedelta(hours=self._config.min_lead_hours):
            return "TOO_LATE"
        return None

    async def _deliver_pending(self, reminder: BookingReminder, booking: Booking) -> None:
        message = self._message(booking)
        rows = self._db.exec(
            select(BookingReminderDelivery).where(
                BookingReminderDelivery.booking_reminder_id == reminder.id,
                BookingReminderDelivery.status.in_([DeliveryStatus.PENDING, DeliveryStatus.FAILED]),
            )
        ).all()
        for delivery in rows:
            await self._attempt(delivery, booking.user_id, message)

    async def _attempt(self, delivery, user_id: int, message: NotificationMessage) -> None:
        now = self._clock()
        result = await self._notifications.deliver(delivery.channel, user_id, message)
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.status = result.status
        delivery.error_code = result.error_code
        if result.status == DeliveryStatus.SENT:
            delivery.sent_at = now
        self._db.add(delivery)
        self._db.flush()

    def _settle(self, reminder: BookingReminder) -> None:
        """BR-712 — sent if any channel succeeded, else failed.

        A failed reminder whose deliveries are still retryable is picked up by
        phase C, which flips it to sent on a later success.
        """
        rows = self._db.exec(
            select(BookingReminderDelivery).where(
                BookingReminderDelivery.booking_reminder_id == reminder.id
            )
        ).all()
        sent = [r for r in rows if r.status == DeliveryStatus.SENT]
        if sent:
            reminder.status = BookingReminderStatus.SENT
            reminder.sent_at = min(as_utc(r.sent_at) for r in sent)
        else:
            reminder.status = BookingReminderStatus.FAILED
        self._db.add(reminder)

    def _retryable(self, delivery: BookingReminderDelivery, reminder: BookingReminder) -> bool:
        """BR-ENT-485 — transient error, attempts left, and still ≥ MIN_LEAD before the slot."""
        now = self._clock()
        backoff = timedelta(minutes=self._config.retry_backoff_minutes * delivery.attempts)
        return (
            delivery.status == DeliveryStatus.FAILED
            and delivery.error_code in RETRYABLE_ERRORS
            and delivery.attempts < self._config.max_attempts
            and (delivery.last_attempt_at is None or now >= as_utc(delivery.last_attempt_at) + backoff)
            and now <= as_utc(reminder.appointment_at) - timedelta(hours=self._config.min_lead_hours)
        )

    # ── Phase C — retry (BR-ENT-485) ────────────────────────────────────
    async def _retry(self, report: JobReport) -> None:
        rows = self._db.exec(
            select(BookingReminderDelivery, BookingReminder)
            .join(BookingReminder, BookingReminder.id == BookingReminderDelivery.booking_reminder_id)
            .where(
                BookingReminderDelivery.status == DeliveryStatus.FAILED,
                BookingReminderDelivery.attempts < self._config.max_attempts,
                BookingReminder.status == BookingReminderStatus.FAILED,
            )
            .limit(self._config.batch_size)
        ).all()
        for delivery, reminder in rows:
            if not self._retryable(delivery, reminder):
                continue
            booking = self._db.get(Booking, reminder.booking_id)
            if self._skip_reason(reminder, booking, self._clock()) is not None:
                continue
            await self._attempt(delivery, booking.user_id, self._message(booking))
            report.retried += 1
            self._settle(reminder)
            self._db.commit()
            if reminder.status == BookingReminderStatus.SENT:
                report.sent += 1

    def _message(self, booking: Booking) -> NotificationMessage:
        """AI-006 INT-603 — no VIN / phone / email / national id (BR-706)."""
        workshop = self._db.get(Workshop, booking.workshop_id)
        appt = appointment_at(booking.booking_date, booking.time_slot)
        when = f"{appt:%H:%M} {_WEEKDAYS_VI[appt.weekday()]}, {appt:%d/%m}"
        base = self._config.frontend_url.rstrip("/")
        link = f"{base}/bookings/{booking.id}?src=REMINDER_24H" if base else None
        body = (
            f"📅 Nhắc lịch hẹn: {when} tại {workshop.name if workshop else 'xưởng'}\n"
            f"Mã lịch hẹn: {booking.booking_code}"
        )
        return NotificationMessage(subject="Nhắc lịch hẹn", body=body, link=link)
