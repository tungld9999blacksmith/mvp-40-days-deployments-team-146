"""In-app notification feed (API-NOTI-003), derived from existing data.

The MVP has no in-app notification table, so the feed is read from the
records each feature already keeps:

* maintenance reminders (``reminder``, FEAT-NOTI-001),
* booking status changes made by the workshop or the system (``booking_status_event``),
* satisfaction surveys waiting for an answer (``follow_up`` in ``sent``).

Only pending surveys can be "unread"; there is no read state to store.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from sqlmodel import Session, select

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_status_event import BookingActorType, BookingStatusEvent
from src.common.core.maintenance.reminder import Reminder
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop.workshop import Workshop
from src.modules.oem_integration.service import utc_now

from . import schemas

FEED_WINDOW_DAYS = 90
FEED_LIMIT = 50
_BOOKING_UPDATES = (BookingStatus.CONFIRMED, BookingStatus.CANCELLED, BookingStatus.COMPLETED)


class NotificationFeedService:
    def __init__(self, session: Session, *, clock: Callable[[], datetime] = utc_now) -> None:
        self._db = session
        self._clock = clock

    def list_for_user(self, user: VehicleUser) -> schemas.NotificationFeedOut:
        since = self._clock() - timedelta(days=FEED_WINDOW_DAYS)
        vehicle_ids = list(self._db.exec(select(UserVehicle.id).where(UserVehicle.user_id == user.user_id)).all())
        items = [
            *self._reminders(vehicle_ids, since),
            *self._booking_updates(user, since),
            *self._follow_ups(user, since),
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
                ),
            )
            for r in rows
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

    def _workshop_names(self, workshop_ids: set[UUID]) -> dict[UUID, str]:
        if not workshop_ids:
            return {}
        return {w.id: w.name for w in self._db.exec(select(Workshop).where(Workshop.id.in_(workshop_ids))).all()}
