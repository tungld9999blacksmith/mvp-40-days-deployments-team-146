"""BookingStateMachine — the single code path that changes ``booking.status``.

Every change is a conditional ``UPDATE ... WHERE status = :from`` (so two
concurrent writers cannot both win) plus one ``booking_status_event`` row in
the same transaction (us-037 BR-802, BR-808; Entity BR-ENT-490..492). Callers
own the transaction: this class flushes but never commits.

Used by the owner flows (us-029 hold/cancel, us-033 cancel), the Workshop Board
(us-037) and the background jobs (us-029 BR-015).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_status_event import BookingActorType, BookingStatusEvent

from .reminders import BookingReminderScheduler, reminder_config

S = BookingStatus

# us-037 FF BR-802 (+ creation as ``(None, pending)``).
ALLOWED_TRANSITIONS: frozenset[tuple[BookingStatus | None, BookingStatus]] = frozenset(
    {
        (None, S.PENDING),
        (S.PENDING, S.CONFIRMED),
        (S.PENDING, S.CANCELLED),
        (S.CONFIRMED, S.CHECKED_IN),
        (S.CONFIRMED, S.CANCELLED),
        (S.CHECKED_IN, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.COMPLETED),
    }
)


@dataclass(frozen=True)
class Actor:
    type: BookingActorType
    user_id: int | None = None
    workshop_owner_id: UUID | None = None

    @classmethod
    def vehicle_owner(cls, user_id: int) -> Actor:
        return cls(BookingActorType.VEHICLE_OWNER, user_id=user_id)

    @classmethod
    def workshop_owner(cls, owner_id: UUID) -> Actor:
        return cls(BookingActorType.WORKSHOP_OWNER, workshop_owner_id=owner_id)

    @classmethod
    def system(cls) -> Actor:
        return cls(BookingActorType.SYSTEM)


class TransitionConflict(Exception):
    """The booking is no longer in the expected status (another writer won)."""

    def __init__(self, current: BookingStatus) -> None:
        super().__init__(f"booking is {current.value}")
        self.current = current


class IllegalTransition(Exception):
    """``(from, to)`` is not in BR-802 — a programming error, not a user error."""


class BookingStateMachine:
    def __init__(self, session: Session) -> None:
        self._db = session
        self._reminders = BookingReminderScheduler(session, reminder_config())

    def record_created(self, booking: Booking, actor: Actor, source: str) -> BookingStatusEvent:
        """Event for a freshly inserted ``pending`` booking (``from_status = NULL``)."""
        return self._event(booking.id, None, booking.status, actor, source, None, None)

    def transition(
        self,
        booking: Booking,
        to: BookingStatus,
        *,
        actor: Actor,
        source: str,
        reason_code: str | None = None,
        note: str | None = None,
        values: dict | None = None,
    ) -> BookingStatusEvent:
        """Move ``booking`` from its current status to ``to`` atomically.

        ``values`` are extra columns written by the same UPDATE (e.g. ``actual_cost``).
        Raises ``TransitionConflict`` when the row changed underneath us.
        """
        frm = booking.status
        if (frm, to) not in ALLOWED_TRANSITIONS:
            raise IllegalTransition(f"{frm} -> {to}")
        if to == S.CANCELLED and not reason_code:
            raise IllegalTransition("a cancellation needs a reason code (BR-ENT-492)")

        result = self._db.execute(
            update(Booking)
            .where(Booking.id == booking.id, Booking.status == frm)
            .values(status=to, **(values or {}))
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self._db.refresh(booking)
            raise TransitionConflict(booking.status)
        self._db.refresh(booking)

        event = self._event(booking.id, frm, to, actor, source, reason_code, note)
        # us-033 HOOK-BR-001 — same transaction; failures never break the change.
        if to == S.CONFIRMED:
            self._reminders.on_confirmed(booking, confirmed_at=event.created_at)
        elif to == S.CANCELLED:
            self._reminders.on_cancelled(booking.id)
        return event

    def history(self, booking_id: UUID) -> list[BookingStatusEvent]:
        return list(
            self._db.exec(
                select(BookingStatusEvent)
                .where(BookingStatusEvent.booking_id == booking_id)
                .order_by(BookingStatusEvent.created_at, BookingStatusEvent.id)
            ).all()
        )

    def _event(
        self,
        booking_id: UUID,
        frm: BookingStatus | None,
        to: BookingStatus,
        actor: Actor,
        source: str,
        reason_code: str | None,
        note: str | None,
    ) -> BookingStatusEvent:
        event = BookingStatusEvent(
            booking_id=booking_id,
            from_status=frm,
            to_status=to,
            actor_type=actor.type,
            actor_user_id=actor.user_id,
            actor_workshop_owner_id=actor.workshop_owner_id,
            source=source,
            reason_code=reason_code,
            note=note,
            # Wall clock, not now(): events of one transaction must keep their order.
            created_at=datetime.now(UTC),
        )
        self._db.add(event)
        self._db.flush()
        return event
