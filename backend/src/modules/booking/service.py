"""Booking module — application service (FEAT-BOOK-001, F6).

One service backs both the UI endpoints and the AI-004 booking tools (BR-011).
It owns the capacity formula (BR-005), the atomic hold/confirm (BR-001, BR-007,
BR-014) and the location-based ranking (BR-002..004, delegated to a
``WorkshopLocationFinder`` — Q-401).
"""

from __future__ import annotations

import contextlib
import json
import logging
import secrets
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, update
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_status_event import BookingActorType, BookingReschedule
from src.common.core.maintenance.quote import Quote, QuoteStatus
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus, VehicleVerificationStatus
from src.common.core.workshop import (
    BookingConfirmationMode,
    Workshop,
    WorkshopOperatingHour,
    WorkshopSlotBlock,
    WorkshopStatus,
)
from src.infrastructure.redis.errors import LockAcquireError
from src.infrastructure.redis.toolkit import RedisToolkit
from src.modules.vehicle_owner_onboarding.domain import UserLocation

from . import errors, schemas
from .domain import (
    OCCUPYING_STATUSES,
    AnchorSource,
    BookingConfig,
    LocationAnchor,
    RankedBy,
    appointment_at,
    available_from,
    now_vn,
    qr_url,
    reschedule_block,
    slot_starts,
)
from .location import WorkshopLocationFinder
from .reminders import BookingReminderScheduler, reminder_config
from .state_machine import Actor, BookingStateMachine, TransitionConflict

logger = logging.getLogger(__name__)

_OCCUPYING = [BookingStatus(s) for s in OCCUPYING_STATUSES]


def _new_booking_code() -> str:
    """Short, unique, customer-facing code (e.g. ``EVC-7F3A9C21``)."""
    return "EVC-" + secrets.token_hex(4).upper()


def _milestone_from_ref(ref: str | None) -> int | None:
    """``milestoneRef`` such as ``"12000"`` or ``"12000km"`` → 12000 (us-053 BR-1202)."""
    digits = "".join(ch for ch in ref or "" if ch.isdigit())
    return int(digits) if digits and int(digits) > 0 else None


class BookingService:
    def __init__(
        self,
        session: Session,
        toolkit: RedisToolkit,
        finder: WorkshopLocationFinder,
        *,
        config: BookingConfig,
    ) -> None:
        self._session = session
        self._redis = toolkit.redis
        self._locks = toolkit.locks
        self._keys = toolkit.keys
        self._finder = finder
        self._config = config

    # ── Ownership guards ────────────────────────────────────────────────
    def get_owned_active_vehicle(self, user: VehicleUser, user_vehicle_id: UUID) -> UserVehicle:
        vehicle = self._session.get(UserVehicle, user_vehicle_id)
        # Never reveal another owner's vehicle (AC-009).
        if vehicle is None or vehicle.user_id != user.user_id:
            raise errors.VehicleNotFoundError()
        if (
            vehicle.verification_status != VehicleVerificationStatus.VERIFIED
            or vehicle.link_status != VehicleLinkStatus.ACTIVE
        ):
            raise errors.VehicleNotActiveError()
        return vehicle

    def _default_vehicle(self, user: VehicleUser) -> UserVehicle | None:
        return self._session.exec(
            select(UserVehicle).where(
                UserVehicle.user_id == user.user_id,
                UserVehicle.verification_status == VehicleVerificationStatus.VERIFIED,
                UserVehicle.link_status == VehicleLinkStatus.ACTIVE,
            )
        ).first()

    def _get_active_workshop(self, workshop_id: UUID) -> Workshop:
        w = self._session.get(Workshop, workshop_id)
        if w is None or w.status != WorkshopStatus.ACTIVE:
            raise errors.WorkshopNotFoundError()
        return w

    # ── Capacity (BR-005) ───────────────────────────────────────────────
    def _capacity(
        self, workshop: Workshop, d: date, t: time, *, exclude_booking_id: UUID | None = None
    ) -> tuple[int, bool]:
        """BR-005; ``exclude_booking_id`` frees the slot of a booking being moved (BR-1204)."""
        query = select(func.count()).select_from(Booking).where(
            Booking.workshop_id == workshop.id,
            Booking.booking_date == d,
            Booking.time_slot == t,
            Booking.status.in_(_OCCUPYING),
        )
        if exclude_booking_id is not None:
            query = query.where(Booking.id != exclude_booking_id)
        occupied = self._session.exec(query).one()
        blocked = self._session.exec(
            select(func.coalesce(func.sum(WorkshopSlotBlock.blocked_count), 0)).where(
                WorkshopSlotBlock.workshop_id == workshop.id,
                WorkshopSlotBlock.block_date == d,
                WorkshopSlotBlock.time_slot == t,
            )
        ).one()
        return available_from(
            workshop.total_technicians, workshop.emergency_slots_reserved, int(blocked), int(occupied)
        )

    def _operating_hours(self, workshop_id: UUID, d: date) -> WorkshopOperatingHour | None:
        return self._session.exec(
            select(WorkshopOperatingHour).where(
                WorkshopOperatingHour.workshop_id == workshop_id,
                WorkshopOperatingHour.day_of_week == d.isoweekday(),
            )
        ).first()

    def _slots_for_day(self, workshop_id: UUID, d: date) -> list[time]:
        """Every slot start within the operating hours of ``d`` (BR-006)."""
        hours = self._operating_hours(workshop_id, d)
        if hours is None or hours.is_closed or hours.open_time is None or hours.close_time is None:
            return []
        return slot_starts(d, hours.open_time, hours.close_time, self._config.slot_minutes)

    def _slot_in_hours(self, workshop_id: UUID, d: date, t: time) -> bool:
        return t in self._slots_for_day(workshop_id, d)

    # ── API-BK-01 nearby (UC-401, BR-002..004) ──────────────────────────
    async def find_nearby(
        self,
        user: VehicleUser,
        *,
        anchor_source: str | None,
        lat: float | None,
        lng: float | None,
        query: str | None,
        province: str | None,
        user_vehicle_id: UUID | None,
        d: date | None,
        time_slot: time | None,
        limit: int | None,
    ) -> schemas.NearbyData:
        anchor = self._resolve_anchor(user, anchor_source, lat, lng, query, province)
        vehicle = (
            self.get_owned_active_vehicle(user, user_vehicle_id)
            if user_vehicle_id
            else self._default_vehicle(user)
        )

        workshops = self._session.exec(
            select(Workshop).where(Workshop.status == WorkshopStatus.ACTIVE)
        ).all()
        ranked, ranked_by = self._finder.rank(
            anchor,
            list(workshops),
            preferred_workshop_id=user.preferred_workshop_id,
            limit=limit or self._config.nearby_limit,
        )
        if not ranked:
            raise errors.WorkshopNotFoundError()

        out: list[schemas.NearbyWorkshopOut] = []
        for r in ranked:
            w = r.workshop
            hours = self._operating_hours(w.id, d) if d else None
            availability = None
            token = None
            if d and time_slot and self._slot_in_hours(w.id, d, time_slot):
                remaining, available = self._capacity(w, d, time_slot)
                if available and vehicle is not None:
                    token = await self._issue_token(user, w.id, d, time_slot)
                availability = schemas.SlotAvailabilityOut(
                    date=d, time_slot=time_slot, available=available,
                    remaining=remaining, confirmation_token=token,
                )
            out.append(
                schemas.NearbyWorkshopOut(
                    workshop_id=w.id, name=w.name, address=w.address, region=w.region,
                    distance_km=(round(r.distance_km, 2) if r.distance_km is not None else None),
                    is_preferred=r.is_preferred,
                    operating_hours_today=(
                        schemas.OperatingHoursOut(
                            is_closed=hours.is_closed,
                            open_time=hours.open_time,
                            close_time=hours.close_time,
                        )
                        if hours
                        else None
                    ),
                    availability=availability,
                )
            )
        return schemas.NearbyData(
            anchor=schemas.AnchorOut(
                source=anchor.source.value,
                province=anchor.province,
                lat=anchor.latitude,
                lng=anchor.longitude,
                query=anchor.query,
                ranked_by=ranked_by.value,
            ),
            workshops=out,
        )

    def _resolve_anchor(
        self,
        user: VehicleUser,
        anchor_source: str | None,
        lat: float | None,
        lng: float | None,
        query: str | None,
        province: str | None,
    ) -> LocationAnchor:
        # BR-002 #1 — a location specified in the request.
        if lat is not None and lng is not None:
            return LocationAnchor(AnchorSource.SPECIFIED, latitude=lat, longitude=lng)
        if query or province:
            return LocationAnchor(AnchorSource.SPECIFIED, province=province, query=query)

        # BR-002 #2 — the primary profile location.
        loc = self._session.exec(
            select(UserLocation).where(
                UserLocation.user_id == user.user_id, UserLocation.is_primary.is_(True)
            )
        ).first()
        if loc is not None:
            return LocationAnchor(
                AnchorSource.PROFILE,
                latitude=float(loc.latitude) if loc.latitude is not None else None,
                longitude=float(loc.longitude) if loc.longitude is not None else None,
                province=loc.province,
            )

        # BR-002 #3 — the preferred workshop's own location.
        if user.preferred_workshop_id is not None:
            w = self._session.get(Workshop, user.preferred_workshop_id)
            if w is not None:
                return LocationAnchor(
                    AnchorSource.PREFERRED,
                    latitude=float(w.latitude) if w.latitude is not None else None,
                    longitude=float(w.longitude) if w.longitude is not None else None,
                    province=w.region,
                    preferred_workshop_id=str(w.id),
                )
        raise errors.LocationAnchorRequiredError()

    # ── API-BK-02 availability (UC-402, BR-005/006/008) ─────────────────
    async def check_availability(
        self,
        user: VehicleUser,
        workshop_id: UUID,
        d: date,
        time_slot: time | None,
        *,
        with_alternatives: bool,
        reschedule_booking_id: UUID | None = None,
    ) -> schemas.AvailabilityData:
        workshop = self._get_active_workshop(workshop_id)
        if d < now_vn().date():
            raise errors.SlotOutOfHoursError("The date is in the past.")
        moving = (
            self._reschedulable_booking(user, reschedule_booking_id, workshop_id)
            if reschedule_booking_id
            else None
        )
        exclude = moving.id if moving else None

        day_slots = self._slots_for_day(workshop_id, d)
        slots_out: list[schemas.SlotOut] = []
        for t in day_slots:
            remaining, available = self._capacity(workshop, d, t, exclude_booking_id=exclude)
            slots_out.append(schemas.SlotOut(time_slot=t, available=available, remaining=remaining))

        requested = None
        alternatives: list[schemas.AlternativeOut] = []
        if time_slot is not None:
            if time_slot not in day_slots:
                raise errors.SlotOutOfHoursError()
            if moving and (moving.booking_date, moving.time_slot) == (d, time_slot):
                raise errors.RescheduleSameSlotError()  # EDGE-1202
            remaining, available = self._capacity(workshop, d, time_slot, exclude_booking_id=exclude)
            token = None
            if available:
                token = await self._issue_token(user, workshop_id, d, time_slot, rescheduling=moving)
            requested = schemas.RequestedSlotOut(
                time_slot=time_slot, available=available, remaining=remaining,
                confirmation_token=token,
            )
            if not available and with_alternatives:
                alternatives = self._alternatives(
                    workshop, d, time_slot, same_workshop_only=moving is not None, exclude=exclude
                )

        return schemas.AvailabilityData(
            workshop_id=workshop_id, date=d, requested=requested,
            slots=slots_out, alternatives=alternatives,
        )

    def _alternatives(
        self,
        workshop: Workshop,
        d: date,
        t: time,
        *,
        same_workshop_only: bool = False,
        exclude: UUID | None = None,
    ) -> list[schemas.AlternativeOut]:
        """BR-008: same workshop other slots → same workshop next days → same region.

        A reschedule stays in the same workshop (us-053 AF-1203).
        """
        out: list[schemas.AlternativeOut] = []

        # 1) Same workshop, same day, other slots (nearest to requested first).
        same_day = [
            s for s in self._slots_for_day(workshop.id, d) if s != t
            and self._capacity(workshop, d, s, exclude_booking_id=exclude)[1]
        ]
        same_day.sort(key=lambda s: abs(
            datetime.combine(d, s) - datetime.combine(d, t)
        ))
        for s in same_day:
            out.append(self._alt(workshop, d, s))
            if len(out) >= 3:
                return out

        # 2) Same workshop, next days, same slot.
        for offset in range(1, self._config.search_horizon_days + 1):
            nd = d + timedelta(days=offset)
            if (
                t in self._slots_for_day(workshop.id, nd)
                and self._capacity(workshop, nd, t, exclude_booking_id=exclude)[1]
            ):
                out.append(self._alt(workshop, nd, t))
                if len(out) >= 3:
                    return out
        if same_workshop_only:
            return out

        # 3) Other workshops in the same region, same date + slot.
        others = self._session.exec(
            select(Workshop).where(
                Workshop.status == WorkshopStatus.ACTIVE,
                Workshop.region == workshop.region,
                Workshop.id != workshop.id,
            )
        ).all()
        for w in others:
            if t in self._slots_for_day(w.id, d) and self._capacity(w, d, t)[1]:
                out.append(self._alt(w, d, t))
                if len(out) >= 3:
                    return out
        return out

    def _alt(self, w: Workshop, d: date, t: time) -> schemas.AlternativeOut:
        remaining, _ = self._capacity(w, d, t)
        return schemas.AlternativeOut(
            workshop_id=w.id, name=w.name, date=d, time_slot=t, remaining=remaining
        )

    # ── Confirmation token (issued at BK-02, single-use at BK-03) ────────
    def _token_key(self, token: str) -> str:
        return self._keys.build("booking", "cft", token)

    async def _issue_token(
        self,
        user: VehicleUser,
        workshop_id: UUID,
        d: date,
        t: time,
        *,
        rescheduling: Booking | None = None,
    ) -> str:
        """Single-use card token; a reschedule token carries the booking and its old slot."""
        token = secrets.token_urlsafe(24)
        data = {
            "purpose": "RESCHEDULE" if rescheduling else "BOOK",
            "user_id": user.user_id,
            "workshop_id": str(workshop_id),
            "date": d.isoformat(),
            "time_slot": t.isoformat(),
        }
        if rescheduling is not None:
            data |= {
                "booking_id": str(rescheduling.id),
                "old_date": rescheduling.booking_date.isoformat(),
                "old_time_slot": rescheduling.time_slot.isoformat(),
            }
        payload = json.dumps(data)
        await self._redis.set(
            self._token_key(token), payload, ex=self._config.token_ttl_seconds
        )
        return token

    async def _consume_token(self, user: VehicleUser, token: str) -> tuple[UUID, date, time]:
        raw = await self._redis.getdel(self._token_key(token))
        if raw is None:
            raise errors.HoldExpiredError()  # missing or expired
        try:
            data = json.loads(raw)
            if int(data["user_id"]) != user.user_id or data.get("purpose", "BOOK") != "BOOK":
                raise errors.InvalidConfirmationTokenError()
            return (
                UUID(data["workshop_id"]),
                date.fromisoformat(data["date"]),
                time.fromisoformat(data["time_slot"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise errors.InvalidConfirmationTokenError() from exc

    # ── API-BK-03 create: owner Confirm → hold [+auto] (BR-001/007/009/014) ─
    async def create_hold(
        self,
        user: VehicleUser,
        payload: schemas.HoldRequest,
        *,
        source: str = "APP",
    ) -> schemas.BookingOut:
        """``source`` is ``APP`` for the UI and ``CHAT`` for the AI-004 tool (ENT-426)."""
        workshop_id, d, t = await self._consume_token(user, payload.confirmation_token)
        vehicle = self.get_owned_active_vehicle(user, payload.user_vehicle_id)
        workshop = self._get_active_workshop(workshop_id)
        if not self._slot_in_hours(workshop_id, d, t):
            raise errors.SlotOutOfHoursError()

        quote = self._validate_quote(payload.quote_id, vehicle, workshop_id) if payload.quote_id else None

        # BR-013: one open booking per vehicle.
        open_exists = self._session.exec(
            select(func.count()).select_from(Booking).where(
                Booking.user_vehicle_id == vehicle.id,
                Booking.status.in_(_OCCUPYING),
            )
        ).one()
        if int(open_exists) > 0:
            raise errors.OpenBookingExistsError()

        lock_name = f"booking:{workshop_id}:{d.isoformat()}:{t.isoformat()}"
        try:
            async with self._locks.transaction(
                lock_name, ttl=self._config.lock_ttl_seconds, wait_timeout=2.0
            ):
                return self._create_booking_locked(
                    user, vehicle, workshop, d, t, quote,
                    source=source, odo_milestone=_milestone_from_ref(payload.milestone_ref),
                )
        except LockAcquireError as exc:
            raise errors.SlotFullError(self._alternatives(workshop, d, t)) from exc

    def _create_booking_locked(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        workshop: Workshop,
        d: date,
        t: time,
        quote: Quote | None,
        *,
        source: str,
        odo_milestone: int | None,
    ) -> schemas.BookingOut:
        _, available = self._capacity(workshop, d, t)
        if not available:
            raise errors.SlotFullError(self._alternatives(workshop, d, t))

        now = now_vn()
        if odo_milestone is None and quote is not None:
            odo_milestone = quote.odo_milestone
        booking = Booking(
            booking_code=_new_booking_code(),
            user_id=user.user_id,
            user_vehicle_id=vehicle.id,
            workshop_id=workshop.id,
            booking_date=d,
            time_slot=t,
            status=BookingStatus.PENDING,
            hold_expires_at=now + timedelta(minutes=self._config.hold_minutes),
            estimated_cost=quote.approved_total if quote else None,
            odo_milestone=odo_milestone,
        )
        self._session.add(booking)
        machine = BookingStateMachine(self._session)
        try:
            self._session.flush()
            machine.record_created(booking, Actor.vehicle_owner(user.user_id), source)
            if workshop.booking_confirmation_mode == BookingConfirmationMode.AUTO:
                machine.transition(
                    booking,
                    BookingStatus.CONFIRMED,
                    actor=Actor.system(),
                    source="AUTO_CONFIRM",
                    values={"hold_expires_at": None},
                )
        except DBAPIError as exc:  # capacity trigger (Q-ENT-451) as a final guard
            self._session.rollback()
            if "SLOT_FULL" in str(getattr(exc, "orig", exc)):
                raise errors.SlotFullError(self._alternatives(workshop, d, t)) from exc
            raise
        if quote is not None:
            quote.booking_id = booking.id
            self._session.add(quote)
        self._session.commit()
        self._session.refresh(booking)
        return self._to_out(booking, workshop, quote)

    def _validate_quote(self, quote_id: str, vehicle: UserVehicle, workshop_id: UUID) -> Quote:
        try:
            quote = self._session.get(Quote, UUID(quote_id))
        except ValueError as exc:
            raise errors.QuoteExpiredError() from exc
        if (
            quote is None
            or quote.status != QuoteStatus.APPROVED
            or quote.user_vehicle_id != vehicle.id
            or quote.workshop_id != workshop_id
            or quote.expires_at is None
            or quote.expires_at <= now_vn()
        ):
            raise errors.QuoteExpiredError()
        return quote

    def _to_out(self, booking: Booking, workshop: Workshop, quote: Quote | None) -> schemas.BookingOut:
        confirmed = booking.status == BookingStatus.CONFIRMED
        return schemas.BookingOut(
            booking_id=booking.id,
            status=booking.status.value.upper(),
            confirmation_mode=workshop.booking_confirmation_mode.value.upper(),
            workshop_id=workshop.id,
            workshop_name=workshop.name,
            booking_date=booking.booking_date,
            time_slot=booking.time_slot,
            hold_expires_at=booking.hold_expires_at,
            owner_cancelable_until=booking.hold_expires_at,
            booking_code=booking.booking_code if confirmed else None,
            qr_url=qr_url(booking.id) if confirmed else None,
            estimated_cost=booking.estimated_cost,
            quote_id=str(quote.id) if quote else None,
        )

    # ── API-BK-04 cancel hold (BR-010) ──────────────────────────────────
    def cancel_hold(self, user: VehicleUser, booking_id: UUID) -> schemas.CancelData:
        booking = self._session.get(Booking, booking_id)
        if booking is None or booking.user_id != user.user_id:
            raise errors.BookingNotFoundError()
        if booking.status != BookingStatus.PENDING:
            raise errors.HoldWindowClosedError()
        if booking.hold_expires_at is None or booking.hold_expires_at <= now_vn():
            raise errors.HoldWindowClosedError()
        try:
            # Also releases any attached quote (BR-ENT-404 reverse).
            BookingStateMachine(self._session).transition(
                booking,
                BookingStatus.CANCELLED,
                actor=Actor.vehicle_owner(user.user_id),
                source="APP",
                reason_code="OWNER_CANCELLED_HOLD",
            )
        except TransitionConflict as exc:
            self._session.rollback()
            raise errors.HoldWindowClosedError() from exc
        self._session.commit()
        return schemas.CancelData(booking_id=booking.id, status=BookingStatus.CANCELLED.value.upper())

    # ── us-053 reschedule (API-BK-02 extension + API-BT-04) ─────────────
    def _owned_booking(self, user: VehicleUser, booking_id: UUID) -> Booking:
        booking = self._session.get(Booking, booking_id)
        if booking is None or booking.user_id != user.user_id:
            raise errors.BookingNotFoundError()  # never reveal another owner's booking
        return booking

    def _reschedulable_booking(
        self, user: VehicleUser, booking_id: UUID, workshop_id: UUID
    ) -> Booking:
        booking = self._owned_booking(user, booking_id)
        block = reschedule_block(
            booking.status.value,
            appointment_at(booking.booking_date, booking.time_slot),
            booking.reschedule_count,
            now_vn(),
            self._config,
        )
        if block is not None:
            raise errors.RescheduleNotAllowedError(block.value)
        if booking.workshop_id != workshop_id:
            raise errors.RescheduleWorkshopMismatchError()  # Q-1201
        return booking

    async def _consume_reschedule_token(
        self, user: VehicleUser, booking_id: UUID, token: str
    ) -> dict:
        raw = await self._redis.getdel(self._token_key(token))
        if raw is None:
            raise errors.ConfirmationTokenExpiredError()
        try:
            data = json.loads(raw)
            valid = (
                data.get("purpose") == "RESCHEDULE"
                and int(data["user_id"]) == user.user_id
                and data.get("booking_id") == str(booking_id)
            )
            if not valid:
                raise errors.InvalidConfirmationTokenError()
            return {
                "workshop_id": UUID(data["workshop_id"]),
                "date": date.fromisoformat(data["date"]),
                "time_slot": time.fromisoformat(data["time_slot"]),
                "old_date": date.fromisoformat(data["old_date"]),
                "old_time_slot": time.fromisoformat(data["old_time_slot"]),
            }
        except (KeyError, ValueError, TypeError) as exc:
            raise errors.InvalidConfirmationTokenError() from exc

    async def reschedule(
        self, user: VehicleUser, booking_id: UUID, token: str, *, source: str = "APP"
    ) -> Booking:
        """API-BT-04 — move a confirmed booking atomically; same id and code (BR-1205)."""
        booking = self._owned_booking(user, booking_id)
        slot = await self._consume_reschedule_token(user, booking_id, token)
        workshop = self._get_active_workshop(slot["workshop_id"])
        new_d, new_t = slot["date"], slot["time_slot"]
        if not self._slot_in_hours(workshop.id, new_d, new_t):
            raise errors.SlotOutOfHoursError()

        # Lock both slots in a stable order so two crossing moves cannot deadlock.
        names = sorted(
            f"booking:{workshop.id}:{d.isoformat()}:{t.isoformat()}"
            for d, t in {(slot["old_date"], slot["old_time_slot"]), (new_d, new_t)}
        )
        try:
            async with contextlib.AsyncExitStack() as stack:
                for name in names:
                    await stack.enter_async_context(
                        self._locks.transaction(
                            name, ttl=self._config.lock_ttl_seconds, wait_timeout=2.0
                        )
                    )
                return self._reschedule_locked(user, booking, workshop, slot, source)
        except LockAcquireError as exc:
            raise errors.ServiceUnavailableError() from exc

    def _reschedule_locked(
        self, user: VehicleUser, booking: Booking, workshop: Workshop, slot: dict, source: str
    ) -> Booking:
        self._session.refresh(booking)
        if booking.status != BookingStatus.CONFIRMED:
            raise errors.BookingNotConfirmedError(booking.status.value)
        block = reschedule_block(
            booking.status.value,
            appointment_at(booking.booking_date, booking.time_slot),
            booking.reschedule_count,
            now_vn(),
            self._config,
        )
        if block is not None:
            raise (
                errors.RescheduleLimitReachedError()
                if block.value == "MAX_RESCHEDULES_REACHED"
                else errors.RescheduleTooLateError()
            )
        old_d, old_t = slot["old_date"], slot["old_time_slot"]
        if (booking.booking_date, booking.time_slot) != (old_d, old_t):
            raise errors.BookingChangedError()  # EDGE-1205
        new_d, new_t = slot["date"], slot["time_slot"]
        if not self._capacity(workshop, new_d, new_t, exclude_booking_id=booking.id)[1]:
            raise errors.SlotFullError(
                self._alternatives(
                    workshop, new_d, new_t, same_workshop_only=True, exclude=booking.id
                )
            )
        try:
            result = self._session.execute(
                update(Booking)
                .where(
                    Booking.id == booking.id,
                    Booking.status == BookingStatus.CONFIRMED,
                    Booking.booking_date == old_d,
                    Booking.time_slot == old_t,
                )
                .values(
                    booking_date=new_d,
                    time_slot=new_t,
                    reschedule_count=Booking.reschedule_count + 1,
                    attendance_confirmed_at=None,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                self._session.rollback()
                raise errors.BookingChangedError()
            self._session.refresh(booking)
            BookingReminderScheduler(self._session, reminder_config()).on_rescheduled(booking)
            self._session.add(
                BookingReschedule(
                    booking_id=booking.id,
                    from_date=old_d,
                    from_time_slot=old_t,
                    to_date=new_d,
                    to_time_slot=new_t,
                    actor_type=BookingActorType.VEHICLE_OWNER,
                    actor_user_id=user.user_id,
                    source=source,
                    created_at=datetime.now(UTC),
                )
            )
            self._session.commit()
        except DBAPIError as exc:  # capacity trigger (Q-ENT-451)
            self._session.rollback()
            if "SLOT_FULL" in str(getattr(exc, "orig", exc)):
                raise errors.SlotFullError(
                    self._alternatives(
                        workshop, new_d, new_t, same_workshop_only=True, exclude=booking.id
                    )
                ) from exc
            raise
        self._session.refresh(booking)
        logger.info(
            "booking.rescheduled",
            extra={"booking_id": str(booking.id), "source": source},
        )
        return booking

    # ── BR-015 background job: auto-cancel unconfirmed manual holds ──────
    def cancel_unconfirmed(self, *, now: datetime | None = None) -> int:
        """Cancel ``pending`` bookings past the workshop-confirm deadline (BR-015).

        Deadline = min(created_at + BOOKING_WS_CONFIRM_DEADLINE_HOURS, appointment time).
        Returns the number of bookings cancelled.
        """
        now = now or now_vn()
        pending = self._session.exec(
            select(Booking).where(Booking.status == BookingStatus.PENDING)
        ).all()
        machine = BookingStateMachine(self._session)
        cancelled = 0
        for booking in pending:
            deadline = booking.created_at + timedelta(hours=self._config.ws_confirm_deadline_hours)
            appointment = datetime.combine(booking.booking_date, booking.time_slot).replace(
                tzinfo=now.tzinfo
            )
            if now >= min(deadline, appointment):
                try:
                    machine.transition(
                        booking,
                        BookingStatus.CANCELLED,
                        actor=Actor.system(),
                        source="JOB_WS_DEADLINE",
                        reason_code="WS_CONFIRM_TIMEOUT",
                    )
                except TransitionConflict:
                    continue  # the workshop accepted it meanwhile
                cancelled += 1
        if cancelled:
            self._session.commit()
        return cancelled
