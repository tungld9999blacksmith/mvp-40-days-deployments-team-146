"""Follow-up background jobs (us-041 JOB-FU-001, JOB-FU-002).

* ``FollowUpSendJob`` — open due follow-ups (``pending → sent``, even when the
  delivery fails — BR-904) and send them; retry transient delivery failures
  while the follow-up is still open (BR-ENT-508).
* ``close_expired`` — ``sent`` for more than the response window ⇒
  ``closed / NO_RESPONSE`` (BR-909, BR-ENT-502).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlmodel import Session, select

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.identity.vehicle_user import UserStatus, VehicleUser
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.notification import DeliveryStatus, FollowUpDelivery
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus
from src.modules.notification.channels import (
    RETRYABLE_ERRORS,
    NotificationMessage,
    NotificationService,
)
from src.modules.notification.preferences import channel_rows, effective_channels
from src.modules.oem_integration.service import as_utc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FollowUpJobConfig:
    response_window_hours: int = 72
    max_attempts: int = 3
    retry_backoff_minutes: int = 5  # next try after attempts × backoff
    batch_size: int = 200
    frontend_url: str = ""


@dataclass
class SendReport:
    opened: int = 0
    not_eligible: int = 0
    sent: int = 0
    failed: int = 0
    retried: int = 0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class FollowUpSendJob:
    def __init__(
        self,
        session: Session,
        notifications: NotificationService,
        config: FollowUpJobConfig = FollowUpJobConfig(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._notifications = notifications
        self._config = config
        self._clock = clock

    async def run(self) -> SendReport:
        report = SendReport()
        now = self._clock()
        due = self._db.exec(
            select(FollowUp)
            .where(FollowUp.status == FollowUpStatus.PENDING, FollowUp.scheduled_at <= now)
            .order_by(FollowUp.scheduled_at)
            .limit(self._config.batch_size)
            .with_for_update(skip_locked=True)
        ).all()
        for follow_up in due:
            booking = self._db.get(Booking, follow_up.booking_id)
            if not self._eligible(booking):
                follow_up.status = FollowUpStatus.CLOSED
                follow_up.closed_reason = "NOT_ELIGIBLE"
                follow_up.closed_at = now
                self._db.add(follow_up)
                self._db.commit()
                report.not_eligible += 1
                continue
            # BR-904 — the answer window opens now, whatever the delivery result.
            follow_up.status = FollowUpStatus.SENT
            follow_up.sent_at = now
            self._db.add(follow_up)
            channels = effective_channels(channel_rows(self._db, booking.user_id))
            for channel in sorted(channels & self._notifications.available_channels(), key=lambda c: c.value):
                exists = self._db.exec(
                    select(FollowUpDelivery.id).where(
                        FollowUpDelivery.follow_up_id == follow_up.id,
                        FollowUpDelivery.channel == channel,
                    )
                ).first()
                if exists is None:
                    self._db.add(FollowUpDelivery(follow_up_id=follow_up.id, channel=channel))
            self._db.flush()
            report.opened += 1
            for delivery in self._deliveries(follow_up, (DeliveryStatus.PENDING,)):
                ok = await self._attempt(delivery, booking.user_id, follow_up)
                report.sent += ok
                report.failed += not ok
            self._db.commit()
        await self._retry(report)
        logger.info("follow_up.send_job", extra=report.__dict__)
        return report

    def _eligible(self, booking: Booking | None) -> bool:
        """BR-903 — still completed, vehicle still linked, account still active."""
        if booking is None or booking.status != BookingStatus.COMPLETED:
            return False
        vehicle = self._db.get(UserVehicle, booking.user_vehicle_id)
        user = self._db.get(VehicleUser, booking.user_id)
        return (
            vehicle is not None
            and vehicle.link_status == VehicleLinkStatus.ACTIVE
            and user is not None
            and user.status == UserStatus.ACTIVE
        )

    def _deliveries(self, follow_up: FollowUp, statuses) -> list[FollowUpDelivery]:
        return list(
            self._db.exec(
                select(FollowUpDelivery).where(
                    FollowUpDelivery.follow_up_id == follow_up.id,
                    FollowUpDelivery.status.in_(statuses),
                )
            ).all()
        )

    def _message(self, follow_up: FollowUp) -> NotificationMessage:
        base = self._config.frontend_url.rstrip("/")
        link = f"{base}/follow-ups/{follow_up.id}" if base else None
        body = follow_up.message + (f"\nChia sẻ với chúng mình: {link}" if link else "")
        return NotificationMessage(subject="Hỏi thăm sau bảo dưỡng", body=body, link=link)

    async def _attempt(self, delivery: FollowUpDelivery, user_id: int, follow_up: FollowUp) -> bool:
        now = self._clock()
        result = await self._notifications.deliver(delivery.channel, user_id, self._message(follow_up))
        delivery.attempts += 1
        delivery.last_attempt_at = now
        delivery.status = result.status
        delivery.error_code = result.error_code
        if result.status == DeliveryStatus.SENT:
            delivery.sent_at = now
        self._db.add(delivery)
        self._db.flush()
        return result.status == DeliveryStatus.SENT

    async def _retry(self, report: SendReport) -> None:
        """BR-ENT-508 — transient failures, attempts left, follow-up still ``sent``."""
        rows = self._db.exec(
            select(FollowUpDelivery, FollowUp, Booking)
            .join(FollowUp, FollowUp.id == FollowUpDelivery.follow_up_id)
            .join(Booking, Booking.id == FollowUp.booking_id)
            .where(
                FollowUpDelivery.status == DeliveryStatus.FAILED,
                FollowUpDelivery.attempts < self._config.max_attempts,
                FollowUpDelivery.error_code.in_(RETRYABLE_ERRORS),
                FollowUp.status == FollowUpStatus.SENT,
            )
            .limit(self._config.batch_size)
        ).all()
        now = self._clock()
        for delivery, follow_up, booking in rows:
            backoff = timedelta(minutes=self._config.retry_backoff_minutes * delivery.attempts)
            if delivery.last_attempt_at is not None and now < as_utc(delivery.last_attempt_at) + backoff:
                continue
            await self._attempt(delivery, booking.user_id, follow_up)
            report.retried += 1
            self._db.commit()


def close_expired(
    session: Session,
    *,
    response_window_hours: int = 72,
    now: datetime | None = None,
) -> int:
    """JOB-FU-002 — BR-ENT-502; returns the number of follow-ups closed."""
    now = now or _utc_now()
    result = session.execute(
        update(FollowUp)
        .where(
            FollowUp.status == FollowUpStatus.SENT,
            FollowUp.sent_at < now - timedelta(hours=response_window_hours),
        )
        .values(status=FollowUpStatus.CLOSED, closed_reason="NO_RESPONSE", closed_at=now)
        .execution_options(synchronize_session=False)
    )
    session.commit()
    closed = result.rowcount or 0
    logger.info("follow_up.close_expired", extra={"closed": closed})
    return closed
