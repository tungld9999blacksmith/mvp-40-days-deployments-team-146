"""Workshop Board — application service (us-037 API-WB-01..08).

Every booking query is scoped to the owner's workshop (BR-801). Status changes go
through the shared ``BookingStateMachine`` (BR-802, BR-808); side effects of
``COMPLETE`` (service record + follow-up) happen in the same transaction (BR-807).
Owner notifications are sent after commit, best effort (BR-810).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.quote import Quote
from src.common.core.vehicle import (
    ServiceRecordSource,
    UserVehicle,
    VehicleOdometerReading,
    VehicleServiceRecord,
)
from src.common.core.workshop import (
    BookingConfirmationMode,
    SlotBlockReason,
    Workshop,
    WorkshopOperatingHour,
    WorkshopSlotBlock,
    WorkshopStatus,
)
from src.infrastructure.redis.errors import LockAcquireError
from src.modules.booking.domain import (
    OCCUPYING_STATUSES,
    TZ_VN,
    appointment_at,
    slot_starts,
)
from src.modules.booking.state_machine import Actor, BookingStateMachine, TransitionConflict
from src.modules.follow_up.service import FollowUpScheduler
from src.modules.notification.channels import NotificationMessage
from src.modules.notification.owner_notifier import OwnerNotifier
from src.modules.oem_integration.service import as_utc
from src.modules.service_progress.service import ServiceProgressService

from . import errors, schemas

logger = logging.getLogger(__name__)

S = BookingStatus
_OCCUPYING = [BookingStatus(s) for s in OCCUPYING_STATUSES]

# us-037 §6.2 — action → (from, to).
ACTIONS: dict[str, tuple[BookingStatus, BookingStatus]] = {
    "ACCEPT": (S.PENDING, S.CONFIRMED),
    "REJECT": (S.PENDING, S.CANCELLED),
    "CHECK_IN": (S.CONFIRMED, S.CHECKED_IN),
    "START": (S.CHECKED_IN, S.IN_PROGRESS),
    "COMPLETE": (S.IN_PROGRESS, S.COMPLETED),
    "CANCEL": (S.CONFIRMED, S.CANCELLED),
}
REJECT_REASONS = frozenset({"FULLY_BOOKED", "NOT_SUPPORTED_SERVICE", "WORKSHOP_UNAVAILABLE", "OTHER"})
CANCEL_REASONS = frozenset({"NO_SHOW", "WORKSHOP_UNAVAILABLE", "CUSTOMER_REQUEST", "OTHER"})
REASON_LABEL_VI = {
    "NO_SHOW": "Khách không đến",
    "WORKSHOP_UNAVAILABLE": "Xưởng không thể phục vụ",
    "CUSTOMER_REQUEST": "Theo yêu cầu của khách",
    "OTHER": "Lý do khác",
}
_CODE_RE = re.compile(r"^[A-Z0-9-]{4,20}$")


@dataclass(frozen=True)
class BoardConfig:
    slot_minutes: int = 60
    ws_confirm_deadline_hours: int = 12
    history_days: int = 30
    max_range_days: int = 7
    no_show_grace_minutes: int = 30
    block_max_days_ahead: int = 30
    lock_ttl_seconds: int = 10
    frontend_url: str = ""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _norm_plate(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


class WorkshopBoardService:
    def __init__(
        self,
        session: Session,
        *,
        config: BoardConfig = BoardConfig(),
        locks=None,
        follow_ups: FollowUpScheduler | None = None,
        progress: ServiceProgressService | None = None,
        notifier: OwnerNotifier | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._config = config
        self._locks = locks
        self._follow_ups = follow_ups or FollowUpScheduler(session)
        self._progress = progress
        self._notifier = notifier
        self._clock = clock

    def _today(self) -> date:
        return self._clock().astimezone(TZ_VN).date()

    # ── scope ───────────────────────────────────────────────────────────
    def booking_of(self, workshop: Workshop, booking_id: UUID) -> Booking:
        booking = self._db.get(Booking, booking_id)
        if booking is None or booking.workshop_id != workshop.id:
            raise errors.BookingNotFoundError()  # BR-801: other workshops look missing
        return booking

    @staticmethod
    def require_active(workshop: Workshop) -> None:
        if workshop.status != WorkshopStatus.ACTIVE:
            raise errors.WorkshopInactiveError()  # EDGE-812

    # ── rules shared by list / detail / transitions ─────────────────────
    def confirm_deadline(self, booking: Booking) -> datetime:
        """us-029 BR-015 — min(created_at + deadline, appointment)."""
        created = as_utc(booking.created_at)
        return min(
            created + timedelta(hours=self._config.ws_confirm_deadline_hours),
            appointment_at(booking.booking_date, booking.time_slot).astimezone(UTC),
        )

    def allowed_actions(self, booking: Booking) -> list[str]:
        now = self._clock()
        appt = appointment_at(booking.booking_date, booking.time_slot)
        if booking.status == S.PENDING:
            actions = ["ACCEPT"] if now <= self.confirm_deadline(booking) and now < appt else []
            return [*actions, "REJECT"]
        if booking.status == S.CONFIRMED:
            actions = ["CHECK_IN"] if booking.booking_date == self._today() else []
            return [*actions, "CANCEL"]
        if booking.status == S.CHECKED_IN:
            return ["START"]
        if booking.status == S.IN_PROGRESS:
            return ["COMPLETE"]
        return []

    def _item(self, booking: Booking, user: VehicleUser | None, vehicle: UserVehicle | None) -> dict:
        quote = self._db.exec(select(Quote).where(Quote.booking_id == booking.id)).first()
        return {
            "booking_id": booking.id,
            "booking_code": booking.booking_code,
            "status": booking.status.value.upper(),
            "booking_date": booking.booking_date,
            "time_slot": booking.time_slot,
            # BR-813 — name, phone, plate; never VIN / national id / email.
            "customer": schemas.CustomerOut(
                full_name=user.full_name if user else None, phone=user.phone if user else None
            ),
            "vehicle": schemas.VehicleOut(
                model_name=vehicle.model_name if vehicle else None,
                license_plate=vehicle.license_plate if vehicle else None,
            ),
            "milestone_label": (
                f"Mốc {booking.odo_milestone:,} km".replace(",", ".") if booking.odo_milestone else None
            ),
            "estimated_cost": booking.estimated_cost,
            "quote": schemas.QuoteRefOut(quote_id=quote.id, status=quote.status.value.upper()) if quote else None,
            "attendance_confirmed_at": booking.attendance_confirmed_at,
            "confirm_deadline": self.confirm_deadline(booking) if booking.status == S.PENDING else None,
            "allowed_actions": self.allowed_actions(booking),
        }

    def _people(self, booking: Booking) -> tuple[VehicleUser | None, UserVehicle | None]:
        return self._db.get(VehicleUser, booking.user_id), self._db.get(UserVehicle, booking.user_vehicle_id)

    # ── API-WB-01 ───────────────────────────────────────────────────────
    def list_bookings(
        self,
        workshop: Workshop,
        *,
        from_: date | None,
        to: date | None,
        statuses: list[str] | None,
        q: str | None,
    ) -> schemas.BoardListData:
        today = self._today()
        start = from_ or today
        end = to or start
        if (
            start > end
            or (end - start).days >= self._config.max_range_days
            or start < today - timedelta(days=self._config.history_days)
        ):
            raise errors.InvalidRequestError(
                f"Use a range of at most {self._config.max_range_days} days, "
                f"not older than {self._config.history_days} days."
            )
        if q is not None and not 2 <= len(q.strip()) <= 20:
            raise errors.InvalidRequestError("The search text must be 2-20 characters.")

        rows = self._db.exec(
            select(Booking, VehicleUser, UserVehicle)
            .join(VehicleUser, VehicleUser.user_id == Booking.user_id)
            .join(UserVehicle, UserVehicle.id == Booking.user_vehicle_id)
            .where(
                Booking.workshop_id == workshop.id,
                Booking.booking_date >= start,
                Booking.booking_date <= end,
            )
            .order_by(Booking.booking_date, Booking.time_slot, Booking.created_at)
        ).all()
        summary = {s.value.upper(): 0 for s in BookingStatus}
        for b, _, _ in rows:
            summary[b.status.value.upper()] += 1

        wanted = {s.upper() for s in statuses} if statuses else None
        needle = q.strip().upper() if q else None
        items = []
        for b, u, v in rows:
            if wanted and b.status.value.upper() not in wanted:
                continue
            if (
                needle
                and needle not in b.booking_code.upper()
                and (_norm_plate(needle) not in _norm_plate(v.license_plate or "") or not _norm_plate(needle))
            ):
                continue
            items.append(schemas.BoardItemOut(**self._item(b, u, v)))
        return schemas.BoardListData(
            workshop_id=workshop.id,
            confirmation_mode=workshop.booking_confirmation_mode.value.upper(),
            from_=start,
            to=end,
            summary=summary,
            items=items,
        )

    # ── API-WB-02 ───────────────────────────────────────────────────────
    def detail(self, workshop: Workshop, booking_id: UUID) -> schemas.BoardDetailOut:
        booking = self.booking_of(workshop, booking_id)
        user, vehicle = self._people(booking)
        return schemas.BoardDetailOut(
            **self._item(booking, user, vehicle),
            actual_cost=booking.actual_cost,
            status_history=[
                schemas.StatusEventOut(
                    from_status=e.from_status.value.upper() if e.from_status else None,
                    to_status=e.to_status.value.upper(),
                    actor_type=e.actor_type.value.upper(),
                    source=e.source,
                    reason_code=e.reason_code,
                    note=e.note,
                    at=e.created_at,
                )
                for e in BookingStateMachine(self._db).history(booking.id)
            ],
        )

    # ── API-WB-03 ───────────────────────────────────────────────────────
    def by_code(self, workshop: Workshop, code: str) -> schemas.ByCodeOut:
        normalized = code.strip().upper()
        if not _CODE_RE.match(normalized):
            raise errors.InvalidRequestError("Invalid booking code.")
        booking = self._db.exec(
            select(Booking).where(Booking.booking_code == normalized, Booking.workshop_id == workshop.id)
        ).first()
        if booking is None:
            raise errors.BookingNotFoundError()  # EDGE-803
        user, vehicle = self._people(booking)
        item = self._item(booking, user, vehicle)
        item["customer"] = schemas.CustomerOut(full_name=user.full_name if user else None)
        checked_in_at = None
        if booking.status in (S.CHECKED_IN, S.IN_PROGRESS, S.COMPLETED):
            eligibility = "ALREADY_CHECKED_IN"
            checked_in_at = next(
                (
                    e.created_at
                    for e in BookingStateMachine(self._db).history(booking.id)
                    if e.to_status == S.CHECKED_IN
                ),
                None,
            )
        elif booking.status == S.CONFIRMED:
            eligibility = "ELIGIBLE" if booking.booking_date == self._today() else "NOT_TODAY"
        else:
            eligibility = "NOT_CONFIRMED"
        return schemas.ByCodeOut(**item, check_in_eligibility=eligibility, checked_in_at=checked_in_at)

    # ── API-WB-04 ───────────────────────────────────────────────────────
    async def transition(
        self,
        owner: WorkshopOwner,
        workshop: Workshop,
        booking_id: UUID,
        req: schemas.TransitionRequest,
    ) -> schemas.TransitionOut:
        booking = self.booking_of(workshop, booking_id)
        self.require_active(workshop)
        action = req.action.value
        frm, to = ACTIONS[action]

        if booking.status == to and self._last_actor_is(booking.id, to, owner.id):
            return self._transition_out(booking, None)  # EDGE-805: repeated action
        if req.expected_status.value != frm.value.upper() or booking.status != frm:
            raise errors.InvalidStatusTransitionError(booking.status.value, self.allowed_actions(booking))
        reason, note = self._validate_fields(action, req)
        self._check_time_rules(action, booking, reason)

        machine = BookingStateMachine(self._db)
        actor = Actor.workshop_owner(owner.id)
        values = {"actual_cost": req.actual_cost} if action == "COMPLETE" and req.actual_cost is not None else None
        effects = None
        try:
            machine.transition(
                booking,
                to,
                actor=actor,
                source=req.source.value,
                reason_code=reason,
                note=note,
                values=values,
            )
            if self._progress is not None:
                self._progress.on_booking_transition(booking, action)  # HOOK-PG-01
            if action == "COMPLETE":
                effects = self._on_completed(booking, workshop)
            elif action == "ACCEPT":
                effects = schemas.TransitionEffectsOut(reminder_scheduled=False)
            self._db.commit()
        except TransitionConflict as exc:
            self._db.rollback()
            raise errors.InvalidStatusTransitionError(exc.current.value, self.allowed_actions(booking)) from exc
        except DBAPIError as exc:  # BR-807: COMPLETE is all-or-nothing
            self._db.rollback()
            logger.exception("board transition %s failed for %s", action, booking.id)
            raise errors.ServiceUnavailableError() from exc
        self._db.refresh(booking)
        logger.info(
            "board.transition",
            extra={"booking_id": str(booking.id), "action": action, "workshop_id": str(workshop.id)},
        )
        if action in ("ACCEPT", "REJECT") or (action == "CANCEL" and reason != "NO_SHOW"):
            await self._notify(booking, workshop, action, reason)
        return self._transition_out(booking, effects)

    def _last_actor_is(self, booking_id: UUID, to: BookingStatus, owner_id: UUID) -> bool:
        events = [e for e in BookingStateMachine(self._db).history(booking_id) if e.to_status == to]
        return bool(events) and events[-1].actor_workshop_owner_id == owner_id

    @staticmethod
    def _validate_fields(action: str, req: schemas.TransitionRequest) -> tuple[str | None, str | None]:
        reason = req.reason_code.strip().upper() if req.reason_code else None
        note = (req.note or "").strip() or None
        if req.source.value == "QR_SCAN" and action != "CHECK_IN":
            raise errors.InvalidRequestError("QR_SCAN is only valid for CHECK_IN.")
        if action in ("REJECT", "CANCEL"):
            allowed = REJECT_REASONS if action == "REJECT" else CANCEL_REASONS
            if reason is None:
                raise errors.ReasonRequiredError()
            if reason not in allowed:
                raise errors.InvalidRequestError(
                    f"reasonCode must be one of {sorted(allowed)}.", details={"field": "reasonCode"}
                )
            if reason == "OTHER" and note is None:
                raise errors.ReasonRequiredError("A note is required when the reason is OTHER.")
            return reason, note
        return None, note

    def _check_time_rules(self, action: str, booking: Booking, reason: str | None) -> None:
        now = self._clock()
        appt = appointment_at(booking.booking_date, booking.time_slot)
        if action == "ACCEPT" and (now > self.confirm_deadline(booking) or now >= appt):
            raise errors.ConfirmDeadlinePassedError()  # EF-804
        if action == "CHECK_IN" and booking.booking_date != self._today():
            raise errors.CheckInNotTodayError(booking.booking_date.isoformat())  # EDGE-804
        if action == "CANCEL" and reason == "NO_SHOW":
            allowed_from = appt + timedelta(minutes=self._config.no_show_grace_minutes)
            if now < allowed_from:
                raise errors.NoShowTooEarlyError(allowed_from.astimezone(UTC).isoformat())

    def _on_completed(self, booking: Booking, workshop: Workshop) -> schemas.TransitionEffectsOut:
        """BR-807 — EV Care service record + follow-up, inside the COMPLETE transaction."""
        now = self._clock()
        odo = self._db.exec(
            select(func.max(VehicleOdometerReading.odo_km)).where(
                VehicleOdometerReading.user_vehicle_id == booking.user_vehicle_id
            )
        ).one()
        record = self._db.exec(
            select(VehicleServiceRecord).where(VehicleServiceRecord.booking_id == booking.id)
        ).first()
        if record is None:
            record = VehicleServiceRecord(
                user_vehicle_id=booking.user_vehicle_id,
                source=ServiceRecordSource.EV_CARE,
                booking_id=booking.id,
                service_date=now.astimezone(TZ_VN).date(),
                odo_km=odo,
                external_center_id=workshop.external_center_id,
                workshop_id=workshop.id,
                is_periodic=booking.odo_milestone is not None,
            )
            self._db.add(record)
            self._db.flush()
        follow_up = self._follow_ups.on_completed(booking, now)
        return schemas.TransitionEffectsOut(
            service_record_id=record.id,
            follow_up_id=follow_up.id,
            follow_up_scheduled_at=as_utc(follow_up.scheduled_at),
        )

    def _transition_out(self, booking: Booking, effects: schemas.TransitionEffectsOut | None) -> schemas.TransitionOut:
        return schemas.TransitionOut(
            booking_id=booking.id,
            status=booking.status.value.upper(),
            actual_cost=booking.actual_cost,
            effects=effects,
            allowed_actions=self.allowed_actions(booking),
        )

    async def _notify(self, booking: Booking, workshop: Workshop, action: str, reason: str | None) -> None:
        """BR-810 — after commit, best effort; texts from us-037 §6.4."""
        if self._notifier is None:
            return
        when = f"{booking.time_slot:%H:%M} {booking.booking_date:%d/%m}"
        base = self._config.frontend_url.rstrip("/")
        link = f"{base}/bookings/{booking.id}" if base else None
        if action == "ACCEPT":
            body = f"✅ {workshop.name} đã xác nhận lịch hẹn {when}. Mã: {booking.booking_code}."
        elif action == "REJECT":
            body = f"❌ {workshop.name} chưa nhận được lịch {when}. Mời bạn chọn khung/xưởng khác."
        else:
            body = (
                f"⚠️ {workshop.name} đã huỷ lịch hẹn {when}. Lý do: {REASON_LABEL_VI.get(reason or '', reason or '')}."
            )
        try:
            await self._notifier.notify(booking.user_id, NotificationMessage(subject="Lịch hẹn", body=body, link=link))
        except Exception:  # noqa: BLE001 — never fail after commit
            logger.exception("board notification failed for booking %s", booking.id)

    # ── API-WB-05 ───────────────────────────────────────────────────────
    def capacity(self, workshop: Workshop, *, from_: date | None, days: int) -> schemas.CapacityData:
        today = self._today()
        start = from_ or today
        if start < today:
            raise errors.InvalidRequestError("from must be today or later.")
        base = workshop.total_technicians - workshop.emergency_slots_reserved
        out: list[schemas.CapacityDayOut] = []
        for offset in range(days):
            d = start + timedelta(days=offset)
            hours = self._hours(workshop.id, d)
            if hours is None or hours.is_closed or hours.open_time is None or hours.close_time is None:
                out.append(schemas.CapacityDayOut(date=d, is_closed=True, slots=[]))
                continue
            occupied = self._occupied_by_slot(workshop.id, d)
            blocks = {
                b.time_slot: b
                for b in self._db.exec(
                    select(WorkshopSlotBlock).where(
                        WorkshopSlotBlock.workshop_id == workshop.id, WorkshopSlotBlock.block_date == d
                    )
                ).all()
            }
            slots = []
            for t in slot_starts(d, hours.open_time, hours.close_time, self._config.slot_minutes):
                occ = occupied.get(t, 0)
                block = blocks.get(t)
                blocked = block.blocked_count if block else 0
                slots.append(
                    schemas.CapacitySlotOut(
                        time_slot=t,
                        occupied=occ,
                        blocked=blocked,
                        remaining=max(base - blocked - occ, 0),
                        max_block=max(base - occ, 0),
                        block_reason=block.reason.value.upper() if block else None,
                        block_note=block.note if block else None,
                    )
                )
            out.append(
                schemas.CapacityDayOut(
                    date=d, is_closed=False, open_time=hours.open_time, close_time=hours.close_time, slots=slots
                )
            )
        return schemas.CapacityData(
            total_technicians=workshop.total_technicians,
            emergency_slots_reserved=workshop.emergency_slots_reserved,
            days=out,
        )

    def _hours(self, workshop_id: UUID, d: date) -> WorkshopOperatingHour | None:
        return self._db.exec(
            select(WorkshopOperatingHour).where(
                WorkshopOperatingHour.workshop_id == workshop_id,
                WorkshopOperatingHour.day_of_week == d.isoweekday(),
            )
        ).first()

    def _occupied_by_slot(self, workshop_id: UUID, d: date, t: time | None = None) -> dict[time, int]:
        query = (
            select(Booking.time_slot, func.count())
            .where(
                Booking.workshop_id == workshop_id,
                Booking.booking_date == d,
                Booking.status.in_(_OCCUPYING),
            )
            .group_by(Booking.time_slot)
        )
        if t is not None:
            query = query.where(Booking.time_slot == t)
        return {slot: int(count) for slot, count in self._db.exec(query).all()}

    # ── API-WB-06 ───────────────────────────────────────────────────────
    async def set_slot_block(
        self, owner: WorkshopOwner, workshop: Workshop, req: schemas.SlotBlockRequest
    ) -> schemas.SlotBlockOut:
        self.require_active(workshop)
        today = self._today()
        if not today <= req.date <= today + timedelta(days=self._config.block_max_days_ahead):
            raise errors.BlockDateOutOfRangeError()
        hours = self._hours(workshop.id, req.date)
        if (
            hours is None
            or hours.is_closed
            or hours.open_time is None
            or hours.close_time is None
            or req.time_slot not in slot_starts(req.date, hours.open_time, hours.close_time, self._config.slot_minutes)
        ):
            raise errors.SlotOutOfHoursError()
        note = (req.note or "").strip() or None
        if req.blocked_count > 0 and req.reason is None:
            raise errors.ReasonRequiredError("A reason is required to block slots.")
        if req.reason is not None and req.reason.value == "OTHER" and note is None:
            raise errors.ReasonRequiredError("A note is required when the reason is OTHER.")

        if self._locks is None:
            return self._set_block_locked(owner, workshop, req, note)
        # Same lock as booking creation (us-029 BR-001) so blocks never oversell.
        name = f"booking:{workshop.id}:{req.date.isoformat()}:{req.time_slot.isoformat()}"
        try:
            async with self._locks.transaction(name, ttl=self._config.lock_ttl_seconds, wait_timeout=2.0):
                return self._set_block_locked(owner, workshop, req, note)
        except LockAcquireError as exc:
            raise errors.ServiceUnavailableError() from exc

    def _set_block_locked(
        self, owner: WorkshopOwner, workshop: Workshop, req: schemas.SlotBlockRequest, note: str | None
    ) -> schemas.SlotBlockOut:
        base = workshop.total_technicians - workshop.emergency_slots_reserved
        occupied = self._occupied_by_slot(workshop.id, req.date, req.time_slot).get(req.time_slot, 0)
        max_block = max(base - occupied, 0)
        if req.blocked_count > max_block:
            raise errors.BlockExceedsFreeCapacityError(max_block)
        block = self._db.exec(
            select(WorkshopSlotBlock).where(
                WorkshopSlotBlock.workshop_id == workshop.id,
                WorkshopSlotBlock.block_date == req.date,
                WorkshopSlotBlock.time_slot == req.time_slot,
            )
        ).first()
        if req.blocked_count == 0:
            if block is not None:
                self._db.delete(block)
        else:
            if block is None:
                block = WorkshopSlotBlock(workshop_id=workshop.id, block_date=req.date, time_slot=req.time_slot)
            block.blocked_count = req.blocked_count
            block.reason = SlotBlockReason(req.reason.value.lower())
            block.note = note
            block.created_by = owner.id
            self._db.add(block)
        self._db.commit()
        return schemas.SlotBlockOut(
            date=req.date,
            time_slot=req.time_slot,
            blocked=req.blocked_count,
            occupied=occupied,
            remaining=max(base - req.blocked_count - occupied, 0),
            max_block=max_block,
        )

    # ── API-WB-07 / 08 ──────────────────────────────────────────────────
    def settings(self, workshop: Workshop) -> schemas.BookingSettingsOut:
        pending = self._db.exec(
            select(func.count())
            .select_from(Booking)
            .where(Booking.workshop_id == workshop.id, Booking.status == S.PENDING)
        ).one()
        return schemas.BookingSettingsOut(
            confirmation_mode=workshop.booking_confirmation_mode.value.upper(),
            ws_confirm_deadline_hours=self._config.ws_confirm_deadline_hours,
            pending_count=int(pending),
        )

    def update_settings(self, workshop: Workshop, mode: str) -> schemas.BookingSettingsOut:
        """BR-811 — applies to new bookings only; existing pending ones are untouched."""
        self.require_active(workshop)
        workshop.booking_confirmation_mode = BookingConfirmationMode(mode.lower())
        self._db.add(workshop)
        self._db.commit()
        self._db.refresh(workshop)
        return self.settings(workshop)
