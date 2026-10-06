"""Booking module — application service (FEAT-BOOK-001, F6).

One service backs both the UI endpoints and the AI-004 booking tools (BR-011).
It owns the capacity formula (BR-005), the atomic hold/confirm (BR-001, BR-007,
BR-014) and the location-based ranking (BR-002..004, delegated to a
``WorkshopLocationFinder`` — Q-401).
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import secrets
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func, update
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from src.common.concurrency import wait_through_cancellation
from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_request import BookingRequest
from src.common.core.maintenance.booking_status_event import BookingActorType, BookingReschedule
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

    async def _write_in_threadpool(self, callback, *args, **kwargs):
        """Keep transaction locks until a blocking write has actually finished.

        Cancelling an await cannot stop a database operation in a worker thread.
        Finish that operation before unwinding its locks/session; a committed
        request can then be recovered through its durable retry receipt.
        """
        write = asyncio.create_task(run_in_threadpool(callback, *args, **kwargs))
        if not await wait_through_cancellation(write):
            return write.result()
        if (exc := write.exception()) is not None:
            rollback = asyncio.create_task(run_in_threadpool(self._session.rollback))
            await wait_through_cancellation(rollback)
            logger.warning("Booking write failed while request was cancelled", exc_info=exc)
        raise asyncio.CancelledError

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
        query = (
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.workshop_id == workshop.id,
                Booking.booking_date == d,
                Booking.time_slot == t,
                Booking.status.in_(_OCCUPYING),
            )
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

    def open_slots(
        self, workshop: Workshop, start: date, end: date, *, exclude_booking_id: UUID | None = None
    ) -> dict[date, list[schemas.SlotOut]]:
        """Slots of every day in ``[start, end]`` with their capacity, in three queries.

        Same rules as ``_slots_for_day`` + ``_capacity`` (BR-005, BR-006), batched for
        scans over many days (us-061 quick booking). Closed days are left out.
        """
        if end < start:
            return {}
        hours = {
            h.day_of_week: h
            for h in self._session.exec(
                select(WorkshopOperatingHour).where(WorkshopOperatingHour.workshop_id == workshop.id)
            ).all()
        }
        occupied_query = (
            select(Booking.booking_date, Booking.time_slot, func.count())
            .where(
                Booking.workshop_id == workshop.id,
                Booking.booking_date >= start,
                Booking.booking_date <= end,
                Booking.status.in_(_OCCUPYING),
            )
            .group_by(Booking.booking_date, Booking.time_slot)
        )
        if exclude_booking_id is not None:
            occupied_query = occupied_query.where(Booking.id != exclude_booking_id)
        occupied = {(d, t): int(n) for d, t, n in self._session.exec(occupied_query).all()}
        blocked = {
            (d, t): int(n or 0)
            for d, t, n in self._session.exec(
                select(
                    WorkshopSlotBlock.block_date,
                    WorkshopSlotBlock.time_slot,
                    func.sum(WorkshopSlotBlock.blocked_count),
                )
                .where(
                    WorkshopSlotBlock.workshop_id == workshop.id,
                    WorkshopSlotBlock.block_date >= start,
                    WorkshopSlotBlock.block_date <= end,
                )
                .group_by(WorkshopSlotBlock.block_date, WorkshopSlotBlock.time_slot)
            ).all()
        }
        out: dict[date, list[schemas.SlotOut]] = {}
        for offset in range((end - start).days + 1):
            d = start + timedelta(days=offset)
            h = hours.get(d.isoweekday())
            if h is None or h.is_closed or h.open_time is None or h.close_time is None:
                continue
            day = []
            for t in slot_starts(d, h.open_time, h.close_time, self._config.slot_minutes):
                remaining, available = available_from(
                    workshop.total_technicians,
                    workshop.emergency_slots_reserved,
                    blocked.get((d, t), 0),
                    occupied.get((d, t), 0),
                )
                day.append(schemas.SlotOut(time_slot=t, available=available, remaining=remaining))
            out[d] = day
        return out

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
        data, has_vehicle = await run_in_threadpool(
            self._find_nearby_sync,
            user,
            anchor_source=anchor_source,
            lat=lat,
            lng=lng,
            query=query,
            province=province,
            user_vehicle_id=user_vehicle_id,
            d=d,
            time_slot=time_slot,
            limit=limit,
        )
        if has_vehicle:
            for workshop in data.workshops:
                if workshop.availability is not None and workshop.availability.available:
                    workshop.availability.confirmation_token = await self._issue_token(
                        user, workshop.workshop_id, d, time_slot
                    )
        return data

    def _find_nearby_sync(
        self,
        user: VehicleUser,
        *,
        anchor_source,
        lat,
        lng,
        query,
        province,
        user_vehicle_id,
        d,
        time_slot,
        limit,
    ) -> tuple[schemas.NearbyData, bool]:
        anchor = self._resolve_anchor(user, anchor_source, lat, lng, query, province)
        vehicle = (
            self.get_owned_active_vehicle(user, user_vehicle_id) if user_vehicle_id else self._default_vehicle(user)
        )

        workshops = self._session.exec(select(Workshop).where(Workshop.status == WorkshopStatus.ACTIVE)).all()
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
            if d and time_slot and self._slot_in_hours(w.id, d, time_slot):
                remaining, available = self._capacity(w, d, time_slot)
                availability = schemas.SlotAvailabilityOut(
                    date=d,
                    time_slot=time_slot,
                    available=available,
                    remaining=remaining,
                    confirmation_token=None,  # issued by find_nearby after the DB work
                )
            out.append(
                schemas.NearbyWorkshopOut(
                    workshop_id=w.id,
                    name=w.name,
                    address=w.address,
                    region=w.region,
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
        ), vehicle is not None

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
            select(UserLocation).where(UserLocation.user_id == user.user_id, UserLocation.is_primary.is_(True))
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
        data, moving = await run_in_threadpool(
            self._availability_sync,
            user,
            workshop_id,
            d,
            time_slot,
            with_alternatives=with_alternatives,
            reschedule_booking_id=reschedule_booking_id,
        )
        if data.requested is not None and data.requested.available:
            data.requested.confirmation_token = await self._issue_token(
                user, workshop_id, d, time_slot, rescheduling=moving
            )
        return data

    def _availability_sync(
        self,
        user: VehicleUser,
        workshop_id: UUID,
        d: date,
        time_slot: time | None,
        *,
        with_alternatives: bool,
        reschedule_booking_id: UUID | None,
    ) -> tuple[schemas.AvailabilityData, Booking | None]:
        workshop = self._get_active_workshop(workshop_id)
        if d < now_vn().date():
            raise errors.SlotOutOfHoursError("The date is in the past.")
        moving = (
            self._reschedulable_booking(user, reschedule_booking_id, workshop_id) if reschedule_booking_id else None
        )
        exclude = moving.id if moving else None

        slots_out = self.open_slots(workshop, d, d, exclude_booking_id=exclude).get(d, [])
        by_time = {slot.time_slot: slot for slot in slots_out}

        requested = None
        alternatives: list[schemas.AlternativeOut] = []
        if time_slot is not None:
            if time_slot not in by_time:
                raise errors.SlotOutOfHoursError()
            if moving and (moving.booking_date, moving.time_slot) == (d, time_slot):
                raise errors.RescheduleSameSlotError()  # EDGE-1202
            slot = by_time[time_slot]
            remaining, available = slot.remaining, slot.available
            requested = schemas.RequestedSlotOut(
                time_slot=time_slot,
                available=available,
                remaining=remaining,
                confirmation_token=None,
            )
            if not available and with_alternatives:
                alternatives = self._alternatives(
                    workshop, d, time_slot, same_workshop_only=moving is not None, exclude=exclude
                )

        return schemas.AvailabilityData(
            workshop_id=workshop_id,
            date=d,
            requested=requested,
            slots=slots_out,
            alternatives=alternatives,
        ), moving

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
        days = self.open_slots(
            workshop, d, d + timedelta(days=self._config.search_horizon_days), exclude_booking_id=exclude
        )

        def alternative(w: Workshop, day: date, slot: schemas.SlotOut) -> schemas.AlternativeOut:
            return schemas.AlternativeOut(
                workshop_id=w.id, name=w.name, date=day, time_slot=slot.time_slot, remaining=slot.remaining
            )

        # 1) Same workshop, same day, other slots (nearest to requested first).
        same_day = [s for s in days.get(d, []) if s.time_slot != t and s.available]
        same_day.sort(key=lambda s: abs(datetime.combine(d, s.time_slot) - datetime.combine(d, t)))
        for s in same_day:
            out.append(alternative(workshop, d, s))
            if len(out) >= 3:
                return out

        # 2) Same workshop, next days, same slot.
        for offset in range(1, self._config.search_horizon_days + 1):
            nd = d + timedelta(days=offset)
            slot = next((s for s in days.get(nd, []) if s.time_slot == t and s.available), None)
            if slot is not None:
                out.append(alternative(workshop, nd, slot))
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
            slot = next((s for s in self.open_slots(w, d, d).get(d, []) if s.time_slot == t and s.available), None)
            if slot is not None:
                out.append(alternative(w, d, slot))
                if len(out) >= 3:
                    return out
        return out

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
        await self._redis.set(self._token_key(token), payload, ex=self._config.token_ttl_seconds)
        return token

    async def _read_token(self, user: VehicleUser, token: str) -> tuple[UUID, date, time]:
        # Consumption happens only after a successful DB commit, under the
        # request/token locks. Validation never destroys another owner's token.
        raw = await self._redis.get(self._token_key(token))
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
        idempotency_key: str | None = None,
    ) -> schemas.BookingOut:
        """``source`` is ``APP`` for the UI and ``CHAT`` for the AI-004 tool (ENT-426)."""
        token_hash = hashlib.sha256(payload.confirmation_token.encode()).hexdigest()
        request_id = hashlib.sha256(json.dumps([user.user_id, idempotency_key or token_hash]).encode()).hexdigest()
        fingerprint = hashlib.sha256(
            json.dumps([payload.model_dump(mode="json"), source], sort_keys=True).encode()
        ).hexdigest()
        receipt = BookingRequest(
            request_id=request_id, user_id=user.user_id, fingerprint=fingerprint, token_hash=token_hash
        )
        try:
            async with self._locks.transaction(
                f"booking:request:{request_id}",
                f"booking:token:{token_hash}",
                ttl=self._config.lock_ttl_seconds,
                wait_timeout=2.0,
            ):
                replay = await run_in_threadpool(self._replay_booking_request, receipt)
                if replay is not None:
                    return replay
                workshop_id, d, t = await self._read_token(user, payload.confirmation_token)
                result = await self.create_for_slot(
                    user,
                    payload.user_vehicle_id,
                    workshop_id,
                    d,
                    t,
                    source=source,
                    odo_milestone=_milestone_from_ref(payload.milestone_ref),
                    receipt=receipt,
                )
                # The DB receipt remains authoritative even when Redis cleanup
                # or the HTTP response fails after commit.
                try:
                    await self._redis.delete(self._token_key(payload.confirmation_token))
                except Exception:  # noqa: BLE001
                    logger.warning("Booking token cleanup failed after commit", exc_info=True)
                return result
        except LockAcquireError as exc:
            raise errors.ServiceUnavailableError() from exc
        except Exception:
            await run_in_threadpool(self._session.rollback)
            raise

    def _replay_booking_request(self, receipt: BookingRequest) -> schemas.BookingOut | None:
        existing = self._session.get(BookingRequest, receipt.request_id)
        if existing is not None:
            if existing.user_id != receipt.user_id or existing.fingerprint != receipt.fingerprint:
                raise errors.IdempotencyConflictError()
            booking = self._session.get(Booking, existing.booking_id)
            workshop = self._session.get(Workshop, booking.workshop_id)
            return self._to_out(booking, workshop)
        used_token = self._session.exec(
            select(BookingRequest.request_id).where(BookingRequest.token_hash == receipt.token_hash)
        ).first()
        if used_token is not None:
            raise errors.IdempotencyConflictError()
        return None

    async def create_for_slot(
        self,
        user: VehicleUser,
        user_vehicle_id: UUID,
        workshop_id: UUID,
        d: date,
        t: time,
        *,
        source: str,
        odo_milestone: int | None = None,
        source_message_id: UUID | None = None,
        receipt: BookingRequest | None = None,
    ) -> schemas.BookingOut:
        """Book a slot the caller already validated (card token, or a chat proposal — us-061 BR-1510).

        Same guards as the app path: owned active vehicle, active workshop, slot in the
        operating hours, then vehicle lock + slot lock + capacity + BR-013. Without the
        full-day scan of ``check_availability``. ``source_message_id`` links a chat
        booking to the message the owner confirmed (AC-F4-06).
        """
        vehicle, workshop = await run_in_threadpool(self._validated_slot, user, user_vehicle_id, workshop_id, d, t)
        return await self._create_for_vehicle(
            user,
            vehicle,
            workshop,
            d,
            t,
            source=source,
            odo_milestone=odo_milestone,
            source_message_id=source_message_id,
            receipt=receipt,
        )

    def _validated_slot(self, user, user_vehicle_id, workshop_id, d, t):
        vehicle = self.get_owned_active_vehicle(user, user_vehicle_id)
        workshop = self._get_active_workshop(workshop_id)
        if not self._slot_in_hours(workshop_id, d, t):
            raise errors.SlotOutOfHoursError()
        return vehicle, workshop

    async def _create_for_vehicle(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        workshop: Workshop,
        d: date,
        t: time,
        *,
        source: str,
        odo_milestone: int | None,
        source_message_id: UUID | None = None,
        receipt: BookingRequest | None = None,
    ) -> schemas.BookingOut:
        """BR-013 + BR-001: vehicle lock, then slot lock (fixed order, no deadlock).

        The open-booking count runs inside the vehicle lock, so two requests for
        different slots of the same vehicle cannot both pass it.
        """
        vehicle_lock = f"booking:vehicle:{vehicle.id}"
        slot_lock = f"booking:{workshop.id}:{d.isoformat()}:{t.isoformat()}"
        try:
            async with self._locks.transaction(vehicle_lock, ttl=self._config.lock_ttl_seconds, wait_timeout=2.0):
                await run_in_threadpool(self._ensure_no_open_booking, vehicle)
                try:
                    async with self._locks.transaction(slot_lock, ttl=self._config.lock_ttl_seconds, wait_timeout=2.0):
                        return await self._write_in_threadpool(
                            self._create_booking_locked,
                            user,
                            vehicle,
                            workshop,
                            d,
                            t,
                            source=source,
                            odo_milestone=odo_milestone,
                            source_message_id=source_message_id,
                            receipt=receipt,
                        )
                except LockAcquireError as exc:
                    raise errors.SlotFullError(await run_in_threadpool(self._alternatives, workshop, d, t)) from exc
        except LockAcquireError as exc:  # another booking for this vehicle is in flight
            raise errors.OpenBookingExistsError() from exc

    def _ensure_no_open_booking(self, vehicle: UserVehicle) -> None:
        """BR-013: one open booking per vehicle."""
        open_exists = self._session.exec(
            select(func.count())
            .select_from(Booking)
            .where(
                Booking.user_vehicle_id == vehicle.id,
                Booking.status.in_(_OCCUPYING),
            )
        ).one()
        if int(open_exists) > 0:
            raise errors.OpenBookingExistsError()

    def _create_booking_locked(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        workshop: Workshop,
        d: date,
        t: time,
        *,
        source: str,
        odo_milestone: int | None,
        source_message_id: UUID | None = None,
        receipt: BookingRequest | None = None,
    ) -> schemas.BookingOut:
        _, available = self._capacity(workshop, d, t)
        if not available:
            raise errors.SlotFullError(self._alternatives(workshop, d, t))

        now = now_vn()
        booking = Booking(
            booking_code=_new_booking_code(),
            user_id=user.user_id,
            user_vehicle_id=vehicle.id,
            workshop_id=workshop.id,
            booking_date=d,
            time_slot=t,
            status=BookingStatus.PENDING,
            hold_expires_at=now + timedelta(minutes=self._config.hold_minutes),
            odo_milestone=odo_milestone,
            source_message_id=source_message_id,
        )
        self._session.add(booking)
        machine = BookingStateMachine(self._session)
        try:
            self._session.flush()
            if receipt is not None:
                receipt.booking_id = booking.id
                self._session.add(receipt)
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
        self._session.commit()
        self._session.refresh(booking)
        return self._to_out(booking, workshop)

    def _to_out(self, booking: Booking, workshop: Workshop) -> schemas.BookingOut:
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

    def _reschedulable_booking(self, user: VehicleUser, booking_id: UUID, workshop_id: UUID) -> Booking:
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

    async def _consume_reschedule_token(self, user: VehicleUser, booking_id: UUID, token: str) -> dict:
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

    async def reschedule(self, user: VehicleUser, booking_id: UUID, token: str, *, source: str = "APP") -> Booking:
        """API-BT-04 — move a confirmed booking atomically; same id and code (BR-1205)."""
        booking = await run_in_threadpool(self._owned_booking, user, booking_id)
        slot = await self._consume_reschedule_token(user, booking_id, token)
        workshop = await run_in_threadpool(self._get_active_workshop, slot["workshop_id"])
        new_d, new_t = slot["date"], slot["time_slot"]
        if not await run_in_threadpool(self._slot_in_hours, workshop.id, new_d, new_t):
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
                        self._locks.transaction(name, ttl=self._config.lock_ttl_seconds, wait_timeout=2.0)
                    )
                return await self._write_in_threadpool(self._reschedule_locked, user, booking, workshop, slot, source)
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
                self._alternatives(workshop, new_d, new_t, same_workshop_only=True, exclude=booking.id)
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
                    self._alternatives(workshop, new_d, new_t, same_workshop_only=True, exclude=booking.id)
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
        pending = self._session.exec(select(Booking).where(Booking.status == BookingStatus.PENDING)).all()
        machine = BookingStateMachine(self._session)
        cancelled = 0
        for booking in pending:
            deadline = booking.created_at + timedelta(hours=self._config.ws_confirm_deadline_hours)
            appointment = datetime.combine(booking.booking_date, booking.time_slot).replace(tzinfo=now.tzinfo)
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
