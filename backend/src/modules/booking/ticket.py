"""Booking ticket — the owner's side of an existing booking (us-033, us-053).

API-BR-01 detail (= Booking Ticket), API-BR-02 attendance, API-BR-03 cancel,
API-BT-01 "my bookings", API-BT-02 QR image, API-BT-03 lookup by code.
Rescheduling needs the capacity machinery and lives in ``BookingService``.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, update
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_status_event import (
    BookingActorType,
    BookingReschedule,
    BookingStatusEvent,
)
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop import Workshop
from src.modules.oem_integration.service import as_utc

from . import errors, schemas
from .domain import BookingConfig, appointment_at, qr_url, reschedule_block
from .state_machine import Actor, BookingStateMachine, TransitionConflict

logger = logging.getLogger(__name__)

S = BookingStatus
UPCOMING_STATUSES = (S.PENDING, S.CONFIRMED, S.CHECKED_IN, S.IN_PROGRESS)
PAST_STATUSES = (S.COMPLETED, S.CANCELLED)
HISTORY_LIMIT = 20
_CODE_RE = re.compile(r"^EVC-[0-9A-F]{8}$")


@dataclass(frozen=True)
class TicketConfig:
    booking: BookingConfig = field(default_factory=BookingConfig)
    reschedule_enabled: bool = True
    app_base_url: str = ""
    documents_to_bring: tuple[str, ...] = ()
    past_days: int = 90


def _utc_now() -> datetime:
    return datetime.now(UTC)


def mask_plate(plate: str | None) -> str | None:
    """``30A12345`` → ``30A-***.45`` — never the full plate on the owner ticket."""
    if not plate:
        return None
    compact = re.sub(r"[^A-Za-z0-9]", "", plate).upper()
    if len(compact) < 5:
        return "***"
    return f"{compact[:3]}-***.{compact[-2:]}"


def _encode_cursor(b: Booking) -> str:
    raw = json.dumps([b.booking_date.isoformat(), b.time_slot.isoformat(), str(b.id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[date, time, UUID]:
    try:
        d, t, ident = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return date.fromisoformat(d), time.fromisoformat(t), UUID(ident)
    except (ValueError, TypeError) as exc:
        raise errors.BookingError("Invalid cursor.", code="INVALID_REQUEST") from exc


class BookingTicketService:
    def __init__(
        self,
        session: Session,
        *,
        config: TicketConfig = TicketConfig(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._config = config
        self._clock = clock

    # ── ownership ───────────────────────────────────────────────────────
    def owned_booking(self, user: VehicleUser, booking_id: UUID) -> Booking:
        booking = self._db.get(Booking, booking_id)
        if booking is None or booking.user_id != user.user_id:
            raise errors.BookingNotFoundError()  # BR-713: never reveal another owner's booking
        return booking

    # ── allowed actions (us-033 §3.4 + us-053 §3.2) ─────────────────────
    def _actions(self, booking: Booking, now: datetime) -> tuple[list[str], str | None]:
        appt = appointment_at(booking.booking_date, booking.time_slot)
        actions: list[str] = []
        if booking.status == S.CONFIRMED and now < appt:
            if booking.attendance_confirmed_at is None:
                actions.append("CONFIRM_ATTENDANCE")
            actions.append("CANCEL")
        if booking.status == S.PENDING and booking.hold_expires_at and now <= as_utc(booking.hold_expires_at):
            actions.append("CANCEL_HOLD")

        block = None
        if self._config.reschedule_enabled:
            reason = reschedule_block(booking.status.value, appt, booking.reschedule_count, now, self._config.booking)
            if reason is None:
                actions.append("RESCHEDULE")
            elif booking.status in (S.PENDING, S.CONFIRMED):
                block = reason.value
        elif booking.status == S.CONFIRMED and now < appt:
            actions.append("RESCHEDULE")  # GUIDE mode: FE explains how to reschedule
        return actions, block

    # ── API-BR-01 ───────────────────────────────────────────────────────
    def get_ticket(self, user: VehicleUser, booking_id: UUID, *, src: str | None = None) -> schemas.TicketOut:
        booking = self.owned_booking(user, booking_id)
        logger.info("booking.ticket_viewed", extra={"booking_id": str(booking.id), "src": src})
        return self.ticket(booking)

    def ticket(self, booking: Booking) -> schemas.TicketOut:
        now = self._clock()
        workshop = self._db.get(Workshop, booking.workshop_id)
        vehicle = self._db.get(UserVehicle, booking.user_vehicle_id)
        actions, block = self._actions(booking, now)
        confirmed = booking.status == S.CONFIRMED
        appt = appointment_at(booking.booking_date, booking.time_slot)
        lead = timedelta(minutes=self._config.booking.reschedule_min_lead_minutes)
        return schemas.TicketOut(
            booking_id=booking.id,
            booking_code=booking.booking_code if confirmed else None,
            status=booking.status.value.upper(),
            booking_date=booking.booking_date,
            time_slot=booking.time_slot,
            appointment_at=appt.astimezone(UTC),
            workshop=self._workshop_out(workshop, booking.workshop_id, with_contact=True),
            vehicle=schemas.TicketVehicleOut(
                user_vehicle_id=booking.user_vehicle_id,
                model_name=vehicle.model_name if vehicle else None,
                plate_masked=mask_plate(vehicle.license_plate if vehicle else None),
            ),
            estimated_cost=booking.estimated_cost,
            qr_url=qr_url(booking.id) if confirmed else None,
            qr_payload=self._qr_payload(booking) if confirmed else None,
            attendance_confirmed_at=booking.attendance_confirmed_at,
            allowed_actions=actions,
            reschedule_mode="F6B" if self._config.reschedule_enabled else "GUIDE",
            reschedule_blocked_reason=block,
            odo_milestone=booking.odo_milestone,
            items=self._items(booking, vehicle),
            cost=self._cost(booking),
            documents_to_bring=list(self._config.documents_to_bring),
            reschedule_count=booking.reschedule_count,
            reschedule_deadline=(appt - lead).astimezone(UTC) if confirmed else None,
            history=self._history(booking.id),
        )

    def _qr_payload(self, booking: Booking) -> str:
        return f"{self._config.app_base_url.rstrip('/')}/c/{booking.booking_code}"

    @staticmethod
    def _workshop_out(workshop: Workshop | None, workshop_id: UUID, *, with_contact: bool) -> schemas.TicketWorkshopOut:
        return schemas.TicketWorkshopOut(
            workshop_id=workshop_id,
            name=workshop.name if workshop else "",
            address=workshop.address if workshop and with_contact else None,
            phone=workshop.hotline if workshop and with_contact else None,
        )

    def _items(self, booking: Booking, vehicle: UserVehicle | None) -> list[schemas.TicketItemOut]:
        """BR-1202 — the items of the milestone's maintenance schedule."""
        if booking.odo_milestone is None or vehicle is None or not vehicle.external_model_id:
            return []
        rules = self._db.exec(
            select(MaintenanceRule)
            .where(
                MaintenanceRule.model_id == vehicle.external_model_id,
                MaintenanceRule.odo_milestone == booking.odo_milestone,
            )
            .order_by(MaintenanceRule.item_code)
        ).all()
        return [schemas.TicketItemOut(item_name=r.item_name, covered=r.is_covered_by_warranty) for r in rules]

    @staticmethod
    def _cost(booking: Booking) -> schemas.TicketCostOut:
        if booking.estimated_cost is not None:
            return schemas.TicketCostOut(amount=booking.estimated_cost, label="ESTIMATE")
        return schemas.TicketCostOut(label="NONE")

    def _history(self, booking_id: UUID) -> list[schemas.TicketHistoryOut]:
        """BR-1211 — status events + reschedules, newest first, at most 20."""
        out: list[schemas.TicketHistoryOut] = [
            schemas.TicketHistoryOut(
                type="STATUS",
                at=e.created_at,
                actor_type=e.actor_type.value.upper(),
                source=e.source,
                from_status=e.from_status.value.upper() if e.from_status else None,
                to_status=e.to_status.value.upper(),
                reason_code=e.reason_code,
            )
            for e in BookingStateMachine(self._db).history(booking_id)
        ]
        for r in self._db.exec(select(BookingReschedule).where(BookingReschedule.booking_id == booking_id)).all():
            out.append(
                schemas.TicketHistoryOut(
                    type="RESCHEDULE",
                    at=r.created_at,
                    actor_type=r.actor_type.value.upper(),
                    source=r.source,
                    from_date=r.from_date,
                    from_time_slot=r.from_time_slot,
                    to_date=r.to_date,
                    to_time_slot=r.to_time_slot,
                )
            )
        out.sort(key=lambda h: h.at, reverse=True)
        return out[:HISTORY_LIMIT]

    # ── API-BT-01 ───────────────────────────────────────────────────────
    def list_for_user(
        self, user: VehicleUser, *, scope: str = "UPCOMING", limit: int = 20, cursor: str | None = None
    ) -> schemas.MyBookingsData:
        now = self._clock()
        past = scope == "PAST"
        query = select(Booking).where(Booking.user_id == user.user_id)
        if past:
            since = (now - timedelta(days=self._config.past_days)).date()
            query = query.where(Booking.status.in_(PAST_STATUSES), Booking.booking_date >= since)
            order = (Booking.booking_date.desc(), Booking.time_slot.desc(), Booking.id.desc())
        else:
            query = query.where(Booking.status.in_(UPCOMING_STATUSES))
            order = (Booking.booking_date, Booking.time_slot, Booking.id)
        if cursor:
            d, t, ident = _decode_cursor(cursor)
            if past:
                query = query.where(
                    or_(
                        Booking.booking_date < d,
                        and_(Booking.booking_date == d, Booking.time_slot < t),
                        and_(Booking.booking_date == d, Booking.time_slot == t, Booking.id < ident),
                    )
                )
            else:
                query = query.where(
                    or_(
                        Booking.booking_date > d,
                        and_(Booking.booking_date == d, Booking.time_slot > t),
                        and_(Booking.booking_date == d, Booking.time_slot == t, Booking.id > ident),
                    )
                )
        rows = list(self._db.exec(query.order_by(*order).limit(limit + 1)).all())
        page, more = rows[:limit], len(rows) > limit

        workshops = (
            {
                w.id: w
                for w in self._db.exec(select(Workshop).where(Workshop.id.in_({b.workshop_id for b in page}))).all()
            }
            if page
            else {}
        )
        items = []
        for b in page:
            actions, _ = self._actions(b, now)
            items.append(
                schemas.MyBookingItemOut(
                    booking_id=b.id,
                    booking_code=b.booking_code if b.status == S.CONFIRMED else None,
                    status=b.status.value.upper(),
                    appointment_at=appointment_at(b.booking_date, b.time_slot).astimezone(UTC),
                    booking_date=b.booking_date,
                    time_slot=b.time_slot,
                    workshop=self._workshop_out(workshops.get(b.workshop_id), b.workshop_id, with_contact=False),
                    cost=self._cost(b),
                    allowed_actions=actions,
                )
            )
        return schemas.MyBookingsData(items=items, next_cursor=_encode_cursor(page[-1]) if more else None)

    # ── API-BR-02 ───────────────────────────────────────────────────────
    def confirm_attendance(self, user: VehicleUser, booking_id: UUID) -> schemas.AttendanceData:
        booking = self.owned_booking(user, booking_id)
        if booking.attendance_confirmed_at is None:
            if booking.status != S.CONFIRMED:
                raise errors.BookingNotConfirmedError(booking.status.value)
            if self._clock() >= appointment_at(booking.booking_date, booking.time_slot):
                raise errors.AppointmentStartedError()
            # BR-ENT-488 — written once; a concurrent writer keeps its value.
            self._db.execute(
                update(Booking)
                .where(
                    Booking.id == booking.id,
                    Booking.status == S.CONFIRMED,
                    Booking.attendance_confirmed_at.is_(None),
                )
                .values(attendance_confirmed_at=self._clock())
                .execution_options(synchronize_session=False)
            )
            self._db.commit()
            self._db.refresh(booking)
            if booking.attendance_confirmed_at is None:
                raise errors.BookingNotConfirmedError(booking.status.value)
        return schemas.AttendanceData(
            booking_id=booking.id,
            status=booking.status.value.upper(),
            attendance_confirmed_at=booking.attendance_confirmed_at,
        )

    # ── API-BR-03 ───────────────────────────────────────────────────────
    def cancel_by_owner(
        self, user: VehicleUser, booking_id: UUID, *, source: str, reason: str | None
    ) -> schemas.OwnerCancelData:
        booking = self.owned_booking(user, booking_id)
        if booking.status == S.CANCELLED:
            event = self._owner_cancel_event(booking.id, user.user_id)
            if event is not None:  # EF-705 — already cancelled by this owner: idempotent
                return self._cancel_out(booking, event)
            raise errors.BookingNotConfirmedError(booking.status.value)
        if booking.status != S.CONFIRMED:
            raise errors.BookingNotConfirmedError(booking.status.value)
        if self._clock() >= appointment_at(booking.booking_date, booking.time_slot):
            raise errors.AppointmentStartedError()  # Q-702
        note = (reason or "").strip() or None
        try:
            event = BookingStateMachine(self._db).transition(
                booking,
                S.CANCELLED,
                actor=Actor.vehicle_owner(user.user_id),
                source=source,
                reason_code="OWNER_CANCELLED",
                note=note,
            )
        except TransitionConflict as exc:
            self._db.rollback()
            self._db.refresh(booking)
            again = self._owner_cancel_event(booking.id, user.user_id)
            if booking.status == S.CANCELLED and again is not None:
                return self._cancel_out(booking, again)
            raise errors.BookingNotConfirmedError(exc.current.value) from exc
        self._db.commit()
        logger.info("booking.cancelled", extra={"booking_id": str(booking.id), "src": source})
        return self._cancel_out(booking, event)

    def _owner_cancel_event(self, booking_id: UUID, user_id: int) -> BookingStatusEvent | None:
        return self._db.exec(
            select(BookingStatusEvent).where(
                BookingStatusEvent.booking_id == booking_id,
                BookingStatusEvent.to_status == S.CANCELLED,
                BookingStatusEvent.actor_type == BookingActorType.VEHICLE_OWNER,
                BookingStatusEvent.actor_user_id == user_id,
            )
        ).first()

    @staticmethod
    def _cancel_out(booking: Booking, event: BookingStatusEvent) -> schemas.OwnerCancelData:
        return schemas.OwnerCancelData(
            booking_id=booking.id,
            status=S.CANCELLED.value.upper(),
            cancelled_at=event.created_at,
            cancelled_by="VEHICLE_OWNER",
            source=event.source,
        )

    # ── API-BT-02 ───────────────────────────────────────────────────────
    def qr_png(self, user: VehicleUser, booking_id: UUID) -> bytes:
        booking = self.owned_booking(user, booking_id)
        if booking.status != S.CONFIRMED:
            raise errors.QrNotAvailableError()
        import segno  # local import: only this endpoint needs it

        qr = segno.make(self._qr_payload(booking), error="m")
        buf = io.BytesIO()
        # 512 px target: scale so (modules + 2×border) × scale ≈ 512.
        modules = qr.symbol_size(border=4)[0]
        qr.save(buf, kind="png", scale=max(1, 512 // modules), border=4)
        return buf.getvalue()

    # ── API-BT-03 ───────────────────────────────────────────────────────
    def find_by_code(self, user: VehicleUser, code: str) -> UUID:
        normalized = code.strip().upper()
        if not _CODE_RE.match(normalized):
            raise errors.BookingNotFoundError()
        booking = self._db.exec(
            select(Booking).where(Booking.booking_code == normalized, Booking.user_id == user.user_id)
        ).first()
        if booking is None:
            raise errors.BookingNotFoundError()  # EDGE-1208
        return booking.id
