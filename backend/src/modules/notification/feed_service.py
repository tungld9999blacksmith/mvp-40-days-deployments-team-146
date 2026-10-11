"""In-app notification feed (API-NOTI-003), derived from existing data.

The MVP has no in-app notification table, so the feed is read from the
records each feature already keeps:

* maintenance reminders (``reminder``, FEAT-NOTI-001),
* reviewed quotes (``quote``; unread = ``result_seen_at IS NULL``, us-049 BR-1109),
* booking status changes made by the workshop or the system (``booking_status_event``),
* 24h appointment reminders the job has processed (``booking_reminder``, us-033; us-069 BR-1707),
* satisfaction surveys waiting for an answer (``follow_up`` in ``sent``),
* two-tier price lines (``booking_line``): one entry per line and version while it
  waits for the owner, plus reference prices the workshop confirmed at check-in and
  decisions the workshop recorded by phone (unread until the car is completed, while
  the owner can still dispute them).

Only reviewed quotes, pending surveys and appointment reminders still waiting for the
owner can be "unread"; there is no read state to store.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from sqlmodel import Session, select

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.booking import Booking, BookingStatus, PricingFlow
from src.common.core.maintenance.booking_line import BookingLine, LineStatus
from src.common.core.maintenance.booking_status_event import BookingActorType, BookingStatusEvent
from src.common.core.maintenance.quote import Quote, QuoteStatus
from src.common.core.maintenance.reminder import Reminder
from src.common.core.notification import BookingReminder
from src.common.core.notification.event_delivery import BookingReminderStatus
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop.workshop import Workshop
from src.modules.booking_line.domain import DECIDABLE_STATUSES, DECIDED_VIA_PHONE
from src.modules.oem_integration.service import as_utc, utc_now

from . import schemas

FEED_WINDOW_DAYS = 90
FEED_LIMIT = 50
_BOOKING_UPDATES = (BookingStatus.CONFIRMED, BookingStatus.CANCELLED, BookingStatus.COMPLETED)
# The in-app feed is the default channel: a reminder the job processed reached the owner here
# even when no external channel succeeded (``failed``). ``skipped`` ones were never due.
_PROCESSED_BOOKING_REMINDERS = (BookingReminderStatus.SENT, BookingReminderStatus.FAILED)


class NotificationFeedService:
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._db = session
        self._clock = clock

    def list_for_user(self, user: VehicleUser) -> schemas.NotificationFeedOut:
        since = self._clock() - timedelta(days=FEED_WINDOW_DAYS)
        vehicle_ids = list(self._db.exec(select(UserVehicle.id).where(UserVehicle.user_id == user.user_id)).all())
        items = [
            *self._reminders(vehicle_ids, since),
            *self._quote_results(vehicle_ids, since),
            *self._booking_updates(user, since),
            *self._booking_reminders(user, since),
            *self._follow_ups(user, since),
            *self._booking_lines(user, since),
        ]
        items.sort(key=lambda item: item.occurred_at, reverse=True)
        items = items[:FEED_LIMIT]
        return schemas.NotificationFeedOut(items=items, unread_count=sum(item.unread for item in items))

    # ------------------------------------------------------------------ sources
    def _reminders(self, vehicle_ids: list[UUID], since: datetime) -> list[schemas.NotificationOut]:
        if not vehicle_ids:
            return []
        rows = self._db.exec(
            select(Reminder).where(Reminder.user_vehicle_id.in_(vehicle_ids), Reminder.scheduled_at >= since)
        ).all()
        return [
            schemas.NotificationOut(
                id=f"reminder:{r.id}",
                kind="MAINTENANCE_REMINDER",
                occurred_at=r.scheduled_at,
                unread=False,
                reminder=schemas.ReminderRefOut(
                    user_vehicle_id=r.user_vehicle_id,
                    level=r.reminder_level.value.upper(),
                    odo_milestone_km=r.target_odo_milestone,
                    resolved=r.is_resolved,
                    resolution_reason=r.resolution_reason,
                ),
            )
            for r in rows
        ]

    def _quote_results(self, vehicle_ids: list[UUID], since: datetime) -> list[schemas.NotificationOut]:
        if not vehicle_ids:
            return []
        rows = self._db.exec(
            select(Quote).where(
                Quote.user_vehicle_id.in_(vehicle_ids),
                Quote.status.in_([QuoteStatus.APPROVED, QuoteStatus.REJECTED]),
                Quote.reviewed_at >= since,
            )
        ).all()
        names = self._workshop_names({q.workshop_id for q in rows})
        return [
            schemas.NotificationOut(
                id=f"quote:{q.id}",
                kind="QUOTE_RESULT",
                occurred_at=q.reviewed_at,
                unread=q.result_seen_at is None,
                quote=schemas.QuoteRefOut(
                    quote_id=q.id,
                    status=q.status.value.upper(),
                    approved_total=q.approved_total,
                    workshop_name=names.get(q.workshop_id),
                ),
            )
            for q in rows
        ]

    def _booking_updates(self, user: VehicleUser, since: datetime) -> list[schemas.NotificationOut]:
        rows = self._db.exec(
            select(BookingStatusEvent, Booking)
            .join(Booking, Booking.id == BookingStatusEvent.booking_id)
            .where(
                Booking.user_id == user.user_id,
                BookingStatusEvent.actor_type != BookingActorType.VEHICLE_OWNER,
                BookingStatusEvent.to_status.in_(_BOOKING_UPDATES),
                BookingStatusEvent.created_at >= since,
            )
        ).all()
        names = self._workshop_names({booking.workshop_id for _, booking in rows})
        return [
            schemas.NotificationOut(
                id=f"booking:{event.id}",
                kind="BOOKING_UPDATE",
                occurred_at=event.created_at,
                unread=False,
                booking=schemas.BookingRefOut(
                    booking_id=booking.id,
                    booking_code=booking.booking_code,
                    status=event.to_status.value.upper(),
                    reason_code=event.reason_code,
                    booking_date=booking.booking_date,
                    time_slot=booking.time_slot,
                    workshop_name=names.get(booking.workshop_id),
                ),
            )
            for event, booking in rows
        ]

    def _booking_reminders(self, user: VehicleUser, since: datetime) -> list[schemas.NotificationOut]:
        rows = self._db.exec(
            select(BookingReminder, Booking)
            .join(Booking, Booking.id == BookingReminder.booking_id)
            .where(
                Booking.user_id == user.user_id,
                BookingReminder.status.in_(_PROCESSED_BOOKING_REMINDERS),
                BookingReminder.scheduled_at >= since,
            )
        ).all()
        now = self._clock()
        names = self._workshop_names({booking.workshop_id for _, booking in rows})
        return [
            schemas.NotificationOut(
                id=f"booking-reminder:{reminder.id}",
                kind="BOOKING_REMINDER",
                occurred_at=reminder.sent_at or reminder.scheduled_at,
                # Still something to do: confirmed, attendance not confirmed, appointment ahead.
                unread=(
                    booking.status == BookingStatus.CONFIRMED
                    and booking.attendance_confirmed_at is None
                    and as_utc(reminder.appointment_at) > now
                ),
                booking_reminder=schemas.BookingReminderRefOut(
                    booking_id=booking.id,
                    booking_code=booking.booking_code,
                    booking_date=booking.booking_date,
                    time_slot=booking.time_slot,
                    workshop_name=names.get(booking.workshop_id),
                ),
            )
            for reminder, booking in rows
        ]

    def _follow_ups(self, user: VehicleUser, since: datetime) -> list[schemas.NotificationOut]:
        rows = self._db.exec(
            select(FollowUp, Booking)
            .join(Booking, Booking.id == FollowUp.booking_id)
            .where(
                Booking.user_id == user.user_id,
                FollowUp.status == FollowUpStatus.SENT,
                FollowUp.sent_at >= since,
            )
        ).all()
        names = self._workshop_names({booking.workshop_id for _, booking in rows})
        return [
            schemas.NotificationOut(
                id=f"follow-up:{follow_up.id}",
                kind="FOLLOW_UP",
                occurred_at=follow_up.sent_at,
                unread=True,  # waiting for the owner's answer
                follow_up=schemas.FollowUpRefOut(
                    follow_up_id=follow_up.id,
                    booking_id=booking.id,
                    workshop_name=names.get(booking.workshop_id),
                ),
            )
            for follow_up, booking in rows
        ]

    def _booking_lines(self, user: VehicleUser, since: datetime) -> list[schemas.NotificationOut]:
        rows = self._db.exec(
            select(BookingLine, Booking)
            .join(Booking, Booking.id == BookingLine.booking_id)
            .where(
                Booking.user_id == user.user_id,
                Booking.pricing_flow == PricingFlow.TWO_TIER,
                BookingLine.updated_at >= since,
                (BookingLine.line_status == LineStatus.PROPOSED)
                | ((BookingLine.line_status == LineStatus.CONFIRMED) & BookingLine.confirmed_at.is_not(None))
                | (BookingLine.decided_via == DECIDED_VIA_PHONE),
            )
        ).all()
        names = self._workshop_names({booking.workshop_id for _, booking in rows})
        return [
            schemas.NotificationOut(
                # One entry per (line, version): an edited line shows up again, never twice.
                id=f"booking-line:{line.id}:{line.version}",
                kind="BOOKING_LINE",
                occurred_at=(
                    line.confirmed_at
                    if line.line_status == LineStatus.CONFIRMED
                    else line.decided_at or line.updated_at
                ),
                unread=line.line_status == LineStatus.PROPOSED
                or (line.decided_via == DECIDED_VIA_PHONE and booking.status in DECIDABLE_STATUSES),
                booking_line=schemas.BookingLineRefOut(
                    booking_id=booking.id,
                    booking_code=booking.booking_code,
                    line_id=line.id,
                    kind=str(line.kind),
                    status=str(line.line_status),
                    item_name=line.item_name,
                    price=line.price,
                    is_safety_critical=line.is_safety_critical,
                    workshop_name=names.get(booking.workshop_id),
                    decided_via=line.decided_via,
                    phone_confirmed_by=line.phone_confirmed_by,
                ),
            )
            for line, booking in rows
        ]

    def _workshop_names(self, workshop_ids: set[UUID]) -> dict[UUID, str]:
        if not workshop_ids:
            return {}
        return {w.id: w.name for w in self._db.exec(select(Workshop).where(Workshop.id.in_(workshop_ids))).all()}
