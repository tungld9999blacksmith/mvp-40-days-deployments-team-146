"""Quick booking — application service (us-061, API-QB-01..04, TOOL-QB-01).

Builds booking proposals from the existing services and turns a confirmed
proposal into a booking through ``BookingService`` — the only path from chat to
a booking (BR-1509, BR-1514):

- milestone: ``UserVehicleService.get_maintenance_status`` (BR-1502),
- workshops: ``WorkshopLocationFinder.rank(ranking=DISTANCE)`` (BR-1506),
- slots: ``BookingService.check_availability`` (us-029 BR-005),
- cost: ``CostEstimationService.estimate`` (us-045),
- booking: ``BookingService.check_availability`` + ``create_hold`` (vehicle lock,
  slot lock, BR-013, AUTO confirmation).

No LLM is called here.
"""

from __future__ import annotations

import logging
import time as _time
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from typing import NoReturn, Protocol
from uuid import UUID

from redis.exceptions import RedisError
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from src.common.core.conversation import ChatMessage, ChatMessageRepository, Conversation, MessageRole
from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.booking import Booking
from src.common.core.maintenance.booking_proposal import (
    BookingProposal,
    BookingProposalStatus,
    LocationBasis,
    ProposalSource,
    SupersededReason,
)
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop import Workshop, WorkshopStatus
from src.common.data_access import eq, gt
from src.infrastructure.messaging import AppendResult, MessageDto
from src.infrastructure.redis.errors import LockAcquireError
from src.infrastructure.redis.toolkit import RedisToolkit
from src.modules.booking import errors as booking_errors
from src.modules.booking.domain import (
    OCCUPYING_STATUSES,
    AnchorSource,
    LocationAnchor,
    appointment_at,
    fold_text,
    now_vn,
)
from src.modules.booking.location import RankedWorkshop, RankingMode, WorkshopLocationFinder
from src.modules.booking.schemas import AlternativeOut, BookingOut
from src.modules.booking.service import BookingService
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.oem_integration.service import as_utc
from src.modules.user_vehicle import errors as vehicle_errors
from src.modules.user_vehicle.schemas import MaintenanceStatusOut
from src.modules.user_vehicle.service import UserVehicleService
from src.modules.vehicle_owner_onboarding.domain import UserLocation

from . import errors, schemas
from .cards import CODE_VISIBLE_STATUSES, enrich_cards
from .domain import (
    CARD_NEED_LOCATION,
    CARD_PROPOSAL,
    CARD_VERSION,
    QUICK_BOOKING_LABEL,
    QuickBookingConfig,
    SlotWindow,
    format_km,
    format_slot,
    mask_plate,
    reason_text,
    slot_windows,
)

logger = logging.getLogger(__name__)

_OCCUPYING = list(OCCUPYING_STATUSES)


class ChatGate(Protocol):
    """What the quick-booking endpoints need from the chat service (same limits as a chat turn)."""

    async def check_rate_limit(self, user_id: int) -> None: ...

    def run_lock(self, conversation_id: UUID) -> AbstractAsyncContextManager[None]: ...


class MessageSink(Protocol):
    async def append(self, conversation_id: UUID, role: MessageRole, content: str = "", **kwargs) -> AppendResult: ...


def _hhmm(t: time) -> str:
    return t.strftime("%H:%M")


def _parse_slot(option: dict) -> tuple[date, time]:
    return date.fromisoformat(option["date"]), time.fromisoformat(option["timeSlot"])


class QuickBookingService:
    def __init__(
        self,
        session: Session,
        *,
        bookings: BookingService,
        vehicles: UserVehicleService,
        estimates: CostEstimationService,
        finder: WorkshopLocationFinder,
        toolkit: RedisToolkit,
        config: QuickBookingConfig,
        chat: ChatGate | None = None,
        messages: MessageSink | None = None,
        lock_ttl_seconds: int = 10,
        clock: Callable[[], datetime] = now_vn,
    ) -> None:
        self._db = session
        self._bookings = bookings
        self._vehicles = vehicles
        self._estimates = estimates
        self._finder = finder
        self._locks = toolkit.locks
        self._config = config
        self._chat = chat
        self._messages = messages
        self._lock_ttl = lock_ttl_seconds
        self._clock = clock

    # ── Guards (API §2) ─────────────────────────────────────────────────
    def _guard(self, user_id: int, conversation_id: UUID) -> tuple[VehicleUser, Conversation, UserVehicle]:
        conversation = self._db.get(Conversation, conversation_id)
        user = self._db.get(VehicleUser, user_id)
        if conversation is None or user is None or conversation.user_id != user_id:
            raise errors.QuickBookingError("Conversation was not found.", code="CONVERSATION_NOT_FOUND")
        try:
            vehicle = self._vehicles.get_owned_active_vehicle(user, conversation.user_vehicle_id)
        except vehicle_errors.UserVehicleError as exc:
            raise errors.QuickBookingError(
                "The vehicle is not verified or no longer linked to this account.", code="VEHICLE_NOT_ACTIVE"
            ) from exc
        return user, conversation, vehicle

    def _owned_proposal(self, user_id: int, conversation: Conversation, proposal_id: UUID) -> BookingProposal:
        proposal = self._db.get(BookingProposal, proposal_id)
        if (
            proposal is None
            or proposal.user_id != user_id
            or proposal.conversation_id != conversation.id
            or proposal.user_vehicle_id != conversation.user_vehicle_id
        ):
            raise errors.ProposalNotFoundError()
        return proposal

    def _require_chat(self) -> tuple[ChatGate, MessageSink]:
        if self._chat is None or self._messages is None:
            raise RuntimeError("QuickBookingService was built without the chat gate / message sink.")
        return self._chat, self._messages

    # ── API-QB-01 ───────────────────────────────────────────────────────
    async def propose_quick(
        self, user_id: int, conversation_id: UUID, request: schemas.QuickBookingRequest
    ) -> schemas.QuickBookingData:
        chat, messages = self._require_chat()
        user, conversation, vehicle = self._guard(user_id, conversation_id)
        await chat.check_rate_limit(user_id)
        async with chat.run_lock(conversation_id):
            user_result = await messages.append(
                conversation_id, MessageRole.USER, QUICK_BOOKING_LABEL, client_message_id=request.clientMessageId
            )
            if not user_result.created:
                reply = self._reply_after(conversation_id, user_result.message)
                if reply is not None:
                    return schemas.QuickBookingData(
                        userMessage=MessageDto.from_message(user_result.message),
                        assistantMessage=self._dto(reply),
                        replayed=True,
                    )

            started = _time.perf_counter()
            content, card, refs, proposal = await self._build_quick(user, conversation, vehicle, request)
            refs = {**refs, "inReplyTo": str(user_result.message.id)}
            assistant = await messages.append(conversation_id, MessageRole.ASSISTANT, content, card=card, refs=refs)
            if proposal is not None:
                self._attach(proposal, assistant.message.id)
            logger.info(
                "quick_booking.proposed",
                extra={
                    "conversation_id": str(conversation_id),
                    "card_type": (card or {}).get("type"),
                    "proposal_id": str(proposal.id) if proposal else None,
                    "duration_ms": round((_time.perf_counter() - started) * 1000, 1),
                },
            )
            return schemas.QuickBookingData(
                userMessage=MessageDto.from_message(user_result.message),
                assistantMessage=self._dto(assistant.message),
            )

    def _reply_after(self, conversation_id: UUID, user_message: ChatMessage) -> ChatMessage | None:
        """The answer saved for this chip message (``refs.inReplyTo``), not just the next assistant message."""
        rows = ChatMessageRepository(self._db).search(
            filters=[
                eq("conversation_id", conversation_id),
                eq("role", MessageRole.ASSISTANT),
                gt("seq", user_message.seq or 0),
            ],
            order_by=("seq",),
            limit=50,
        )
        return next((r for r in rows if (r.refs or {}).get("inReplyTo") == str(user_message.id)), None)

    async def _build_quick(
        self,
        user: VehicleUser,
        conversation: Conversation,
        vehicle: UserVehicle,
        request: schemas.QuickBookingRequest,
    ) -> tuple[str, dict | None, dict, BookingProposal | None]:
        """Return (text, card, refs, proposal) of the assistant answer (FF §9–10)."""
        # EF-1501 — BR-013: one open booking per vehicle.
        open_booking = self._open_booking(vehicle)
        if open_booking is not None:
            workshop = self._db.get(Workshop, open_booking.workshop_id)
            code = f" {open_booking.booking_code}" if open_booking.status.value != "pending" else ""
            text = (
                f"Xe đã có lịch hẹn{code} lúc {format_slot(open_booking.booking_date, open_booking.time_slot)}"
                f" tại {workshop.name if workshop else 'xưởng'}. Bạn xem hoặc đổi lịch ở vé lịch hẹn nhé."
            )
            return text, None, {"bookingId": str(open_booking.id)}, None

        # BR-1502 — the milestone comes from the maintenance-status service only.
        # May seed the demo ODO (a blocking DB write): keep it off the event loop.
        status = await run_in_threadpool(self._vehicles.get_maintenance_status, vehicle)
        if status.due_status == "UNKNOWN" or status.next_milestone is None:
            return _unknown_text(status.unknown_reason), None, {}, None

        # BR-1505 — location anchor.
        anchor, basis, location_label = self._anchor(user, request)
        if anchor is None:
            return _need_location(self._regions(), None)

        now = self._clock()
        milestone = status.next_milestone
        windows = slot_windows(status.due_status, milestone.due_date, now, self._config)
        if windows is None:
            return _too_far_text(status), None, {}, None

        workshops = list(self._db.exec(select(Workshop).where(Workshop.status == WorkshopStatus.ACTIVE)).all())
        ranked, _ = self._finder.rank(
            anchor,
            workshops,
            preferred_workshop_id=user.preferred_workshop_id,
            limit=self._config.max_workshops,
            ranking=RankingMode.DISTANCE,
        )
        if not ranked and basis == LocationBasis.PROVINCE:
            return _need_location(self._regions(), location_label)

        options: list[dict] = []
        window_used: SlotWindow | None = None
        for window in windows:
            options = self._scan(ranked, window, coordinates=anchor.has_coordinates)
            if options:
                window_used = window
                break
        if not options or window_used is None:
            return _no_slot_text(), None, {}, None

        months = milestone.month_milestone
        by_workshop: dict[str, dict | None] = {}
        for option in options:
            if option["workshopId"] not in by_workshop:
                by_workshop[option["workshopId"]] = self._estimate(
                    vehicle, milestone.odo_milestone_km, months, option["workshopId"]
                )
            option["estimate"] = by_workshop[option["workshopId"]]

        reason = reason_text(
            status.due_status,
            milestone.odo_milestone_km,
            milestone.due_date,
            status.remaining_km,
            status.remaining_days if status.remaining_days is not None else 0,
            after_due=window_used.after_due,
        )
        proposal = self._create_proposal(
            user,
            conversation,
            vehicle,
            source=ProposalSource.QUICK_BOOKING,
            odo_milestone=milestone.odo_milestone_km,
            options=options,
            basis=basis,
            reason=SupersededReason.NEW_PROPOSAL,
        )
        card = self._card(
            proposal,
            vehicle,
            milestone=_milestone_out(status),
            reason=reason,
            basis=basis,
            location_label=location_label,
        )
        primary = options[0]
        text = (
            f"{reason} Đề xuất: {primary['workshopName']} lúc "
            f'{format_slot(*_parse_slot(primary))}. Bấm "Xác nhận đặt lịch" trên thẻ để đặt.'
        )
        return text, card, {}, proposal

    def _open_booking(self, vehicle: UserVehicle) -> Booking | None:
        return self._db.exec(
            select(Booking)
            .where(Booking.user_vehicle_id == vehicle.id, Booking.status.in_(_OCCUPYING))
            .order_by(Booking.booking_date, Booking.time_slot)
        ).first()

    def _anchor(
        self, user: VehicleUser, request: schemas.QuickBookingRequest
    ) -> tuple[LocationAnchor | None, LocationBasis, str | None]:
        if request.location is not None:
            anchor = LocationAnchor(
                AnchorSource.SPECIFIED, latitude=request.location.lat, longitude=request.location.lng
            )
            return anchor, LocationBasis.DEVICE, None
        loc = self._db.exec(
            select(UserLocation).where(UserLocation.user_id == user.user_id, UserLocation.is_primary.is_(True))
        ).first()
        if loc is not None and loc.latitude is not None and loc.longitude is not None:
            anchor = LocationAnchor(
                AnchorSource.PROFILE,
                latitude=float(loc.latitude),
                longitude=float(loc.longitude),
                province=loc.province,
            )
            return anchor, LocationBasis.PROFILE, None
        province = (request.province or "").strip() or (loc.province if loc is not None else None)
        if province:
            label = f"Xưởng trong khu vực {province}"
            return LocationAnchor(AnchorSource.SPECIFIED, province=province), LocationBasis.PROVINCE, label
        return None, LocationBasis.NONE, None

    def _regions(self) -> list[str]:
        """Areas with an active workshop; "Hà Nội" and "Ha Noi" count once (matching ignores accents)."""
        rows = self._db.exec(select(Workshop.region).where(Workshop.status == WorkshopStatus.ACTIVE).distinct()).all()
        by_key: dict[str, str] = {}
        for region in sorted(r for r in rows if r):
            by_key.setdefault(fold_text(region), region)
        return sorted(by_key.values())

    def _scan(self, ranked: list[RankedWorkshop], window: SlotWindow, *, coordinates: bool) -> list[dict]:
        """BR-1507 — nearest workshop with a slot first, then the next ones, then more slots there."""
        wanted = 1 + self._config.max_alternatives
        found: list[tuple[RankedWorkshop, date, time]] = []
        for r in ranked:
            slots = self._slots(r.workshop, window, count=1)
            if slots:
                found.append((r, *slots[0]))
            if len(found) >= wanted:
                break
        if found and len(found) < wanted:
            first, d, t = found[0]
            extra = self._slots(first.workshop, window, count=wanted - len(found), after=(d, t))
            found.extend((first, ed, et) for ed, et in extra)
        return [
            _option(i + 1, r.workshop, r.distance_km if coordinates else None, r.is_preferred, d, t)
            for i, (r, d, t) in enumerate(found)
        ]

    def _slots(
        self,
        workshop: Workshop,
        window: SlotWindow,
        *,
        count: int,
        after: tuple[date, time] | None = None,
    ) -> list[tuple[date, time]]:
        days = window.days()
        if not days:
            return []
        out: list[tuple[date, time]] = []
        by_day = self._bookings.open_slots(workshop, days[0], days[-1])  # 3 queries for the whole window
        for d in days:
            for slot in by_day.get(d, []):
                if not slot.available or not window.accepts(d, slot.time_slot):
                    continue
                if after is not None and (d, slot.time_slot) <= after:
                    continue
                out.append((d, slot.time_slot))
                if len(out) >= count:
                    return out
        return out

    def _estimate(
        self, vehicle: UserVehicle, odo_milestone: int, month_milestone: int, workshop_id: str
    ) -> dict | None:
        workshop = self._db.get(Workshop, UUID(workshop_id))
        if workshop is None:
            return None
        data = self._estimates.estimate(vehicle, (odo_milestone, month_milestone), workshop)
        if data.status != "READY" or data.chargeable_total is None:
            return None
        return {
            "chargeableTotal": str(data.chargeable_total),
            "hasReferencePrice": data.has_reference_price,
            "coveredCount": data.covered_count,
        }

    def _month_of(self, vehicle: UserVehicle, odo_milestone: int | None) -> int | None:
        if odo_milestone is None:
            return None
        return self._db.exec(
            select(MaintenanceRule.month_milestone).where(
                MaintenanceRule.model_id == vehicle.external_model_id,
                MaintenanceRule.odo_milestone == odo_milestone,
            )
        ).first()

    # ── Proposals (entity spec §4) ──────────────────────────────────────
    def _create_proposal(
        self,
        user: VehicleUser,
        conversation: Conversation,
        vehicle: UserVehicle,
        *,
        source: ProposalSource,
        odo_milestone: int | None,
        options: list[dict],
        basis: LocationBasis,
        reason: SupersededReason,
    ) -> BookingProposal:
        """BR-ENT-1502: close the owner's waiting proposals, then insert, in one transaction."""
        now_utc = self._clock().astimezone(UTC)
        waiting = self._db.exec(
            select(BookingProposal).where(
                BookingProposal.user_id == user.user_id,
                BookingProposal.status == BookingProposalStatus.PROPOSED,
            )
        ).all()
        for old in waiting:
            if as_utc(old.expires_at) <= now_utc:
                old.status = BookingProposalStatus.EXPIRED
            else:
                old.status = BookingProposalStatus.SUPERSEDED
                old.superseded_reason = reason.value
            old.closed_at = now_utc
            self._db.add(old)
        self._db.flush()

        primary = options[0]
        d, t = _parse_slot(primary)
        proposal = BookingProposal(
            user_id=user.user_id,
            user_vehicle_id=vehicle.id,
            conversation_id=conversation.id,
            source=source.value,
            odo_milestone=odo_milestone,
            workshop_id=UUID(primary["workshopId"]),
            booking_date=d,
            time_slot=t,
            options={"primary": primary, "alternatives": options[1:]},
            location_basis=basis.value,
            expires_at=now_utc + timedelta(minutes=self._config.proposal_ttl_minutes),
        )
        self._db.add(proposal)
        self._db.commit()
        self._db.refresh(proposal)
        return proposal

    def _card(
        self,
        proposal: BookingProposal,
        vehicle: UserVehicle,
        *,
        milestone: dict | None,
        reason: str,
        basis: LocationBasis | str,
        location_label: str | None,
    ) -> dict:
        """API §3.2 snapshot; ``status`` / ``booking`` are added on read (HOOK-QB-01)."""
        return {
            "type": CARD_PROPOSAL,
            "version": CARD_VERSION,
            "proposalId": str(proposal.id),
            "vehicle": {
                "userVehicleId": str(vehicle.id),
                "modelName": vehicle.model_name,
                "trim": vehicle.trim,
                "licensePlateMasked": mask_plate(vehicle.license_plate),
            },
            "milestone": milestone,
            "reason": reason,
            "locationBasis": basis.value if isinstance(basis, LocationBasis) else basis,
            "locationLabel": location_label,
            "primary": proposal.options["primary"],
            "alternatives": proposal.options["alternatives"],
            "expiresAt": as_utc(proposal.expires_at).isoformat(),
        }

    def _snapshot(self, proposal: BookingProposal) -> dict:
        """The card of a proposal's message (for follow-up proposals of the same milestone)."""
        message = self._db.get(ChatMessage, proposal.message_id) if proposal.message_id else None
        return dict(message.card or {}) if message is not None else {}

    def _attach(self, proposal: BookingProposal, message_id: UUID) -> None:
        proposal.message_id = message_id
        self._db.add(proposal)
        self._db.commit()

    def _dto(self, message: ChatMessage) -> MessageDto:
        return enrich_cards(self._db, [MessageDto.from_message(message)], now=self._clock().astimezone(UTC))[0]

    def _is_expired(self, proposal: BookingProposal) -> bool:
        return as_utc(proposal.expires_at) <= self._clock().astimezone(UTC)

    def _close(self, proposal: BookingProposal, status: BookingProposalStatus, reason: str | None = None) -> None:
        proposal.status = status
        proposal.superseded_reason = reason
        proposal.closed_at = self._clock().astimezone(UTC)
        self._db.add(proposal)
        self._db.commit()

    def _require_active(self, proposal: BookingProposal) -> None:
        if proposal.status != BookingProposalStatus.PROPOSED:
            raise errors.ProposalInactiveError(proposal.status.value)
        if self._is_expired(proposal):
            self._close(proposal, BookingProposalStatus.EXPIRED)
            raise errors.ProposalExpiredError()

    @asynccontextmanager
    async def _proposal_lock(self, proposal_id: UUID) -> AsyncIterator[None]:
        """Serialises confirm / revise / cancel of one proposal; the first to get it decides."""
        try:
            async with self._locks.transaction(f"booking-proposal:{proposal_id}", ttl=self._lock_ttl, wait_timeout=2.0):
                yield
        except LockAcquireError as exc:
            raise errors.ProposalInProgressError() from exc
        except RedisError as exc:
            raise errors.QuickBookingError(
                "Booking is temporarily unavailable. Please try again.", code="SERVICE_UNAVAILABLE"
            ) from exc

    def _reload(self, proposal_id: UUID) -> BookingProposal:
        self._db.expire_all()
        proposal = self._db.get(BookingProposal, proposal_id)
        if proposal is None:
            raise errors.ProposalNotFoundError()
        return proposal

    # ── API-QB-02 ───────────────────────────────────────────────────────
    async def confirm(self, user_id: int, conversation_id: UUID, proposal_id: UUID) -> schemas.ConfirmData:
        user, conversation, vehicle = self._guard(user_id, conversation_id)
        self._owned_proposal(user_id, conversation, proposal_id)
        async with self._proposal_lock(proposal_id):
            return await self._confirm_locked(user, conversation, vehicle, proposal_id)

    async def _confirm_locked(
        self, user: VehicleUser, conversation: Conversation, vehicle: UserVehicle, proposal_id: UUID
    ) -> schemas.ConfirmData:
        proposal = self._reload(proposal_id)
        if proposal.status == BookingProposalStatus.CONFIRMED:
            return self._confirmed(proposal, replayed=True)
        # A previous confirm created the booking but stopped before saving the proposal (any booking
        # status: a booking later cancelled must not let the same card book twice).
        linked = self._linked_booking(proposal)
        if linked is not None:
            self._mark_confirmed(proposal, linked.id)
            return self._confirmed(proposal, replayed=True)
        self._require_active(proposal)

        now = self._clock()
        if appointment_at(proposal.booking_date, proposal.time_slot) <= now:
            await self._slot_full(user, conversation, vehicle, proposal, [])
        try:
            # Capacity is re-checked inside the vehicle + slot locks (BR-1510); no full-day scan.
            booking = await self._bookings.create_for_slot(
                user,
                vehicle.id,
                proposal.workshop_id,
                proposal.booking_date,
                proposal.time_slot,
                source="CHAT",
                odo_milestone=proposal.odo_milestone,
                source_message_id=proposal.message_id,
            )
        except booking_errors.SlotFullError as exc:
            await self._slot_full(user, conversation, vehicle, proposal, exc.alternatives)
        except (booking_errors.WorkshopNotFoundError, booking_errors.SlotOutOfHoursError):
            await self._slot_full(user, conversation, vehicle, proposal, [])
        except booking_errors.OpenBookingExistsError as exc:
            open_booking = self._open_booking(vehicle)
            raise errors.QuickBookingError(
                "This vehicle already has an open booking (BR-013).",
                code="OPEN_BOOKING_EXISTS",
                details={"bookingId": str(open_booking.id) if open_booking else None},
            ) from exc

        self._db.expire_all()
        proposal = self._db.get(BookingProposal, proposal_id)
        self._mark_confirmed(proposal, booking.booking_id)

        message = None
        if self._messages is not None:
            result = await self._messages.append(
                conversation.id,
                MessageRole.ASSISTANT,
                self._result_text(booking),
                refs={"bookingId": str(booking.booking_id)},
            )
            message = MessageDto.from_message(result.message)
        logger.info(
            "quick_booking.confirmed",
            extra={
                "proposal_id": str(proposal.id),
                "booking_id": str(booking.booking_id),
                "booking_status": booking.status,
            },
        )
        return schemas.ConfirmData(
            proposalId=proposal.id,
            status="CONFIRMED",
            booking=_booking_out(booking),
            message=message,
        )

    def _result_text(self, booking: BookingOut) -> str:
        """BR-1512 — CONFIRMED shows the code; PENDING waits for the workshop."""
        where = f"{booking.workshop_name or 'xưởng'} lúc {format_slot(booking.booking_date, booking.time_slot)}"
        if booking.status == "CONFIRMED" and booking.booking_code:
            return (
                f"Đã đặt lịch thành công tại {where}. Mã đặt lịch: {booking.booking_code}. "
                "Bạn mở vé lịch hẹn để xem mã QR check-in."
            )
        return (
            f"Đã gửi yêu cầu đặt lịch tại {where}. Xưởng sẽ xác nhận trong tối đa "
            f"{self._config.ws_confirm_deadline_hours} giờ; mã đặt lịch có sau khi xưởng xác nhận."
        )

    def _confirmed(self, proposal: BookingProposal, *, replayed: bool) -> schemas.ConfirmData:
        booking = self._db.get(Booking, proposal.booking_id) if proposal.booking_id else None
        if booking is None:
            raise errors.ProposalInactiveError(proposal.status.value)
        workshop = self._db.get(Workshop, booking.workshop_id)
        return schemas.ConfirmData(
            proposalId=proposal.id,
            status="CONFIRMED",
            booking=schemas.ProposalBookingOut(
                bookingId=booking.id,
                bookingCode=booking.booking_code if booking.status in CODE_VISIBLE_STATUSES else None,
                status=booking.status.value.upper(),
                confirmationMode=workshop.booking_confirmation_mode.value.upper() if workshop else None,
                workshopName=workshop.name if workshop else None,
                bookingDate=booking.booking_date,
                timeSlot=booking.time_slot,
                ownerCancelableUntil=(
                    as_utc(booking.hold_expires_at).isoformat()
                    if booking.status.value == "pending" and booking.hold_expires_at
                    else None
                ),
            ),
            message=self._result_message(proposal, booking.id),
            replayed=replayed,
        )

    def _result_message(self, proposal: BookingProposal, booking_id: UUID) -> MessageDto | None:
        rows = ChatMessageRepository(self._db).search(
            filters=[eq("conversation_id", proposal.conversation_id), eq("role", MessageRole.ASSISTANT)],
            order_by=("-seq",),
            limit=50,
        )
        for row in rows:
            if (row.refs or {}).get("bookingId") == str(booking_id):
                return MessageDto.from_message(row)
        return None

    def _linked_booking(self, proposal: BookingProposal) -> Booking | None:
        """The booking made from this card (``booking.source_message_id`` = the card's message), any status."""
        if proposal.message_id is None:
            return None
        return self._db.exec(
            select(Booking).where(
                Booking.user_vehicle_id == proposal.user_vehicle_id,
                Booking.source_message_id == proposal.message_id,
            )
        ).first()

    def _mark_confirmed(self, proposal: BookingProposal, booking_id: UUID) -> None:
        """The booking exists: the proposal is CONFIRMED even if a chip superseded it meanwhile."""
        proposal.status = BookingProposalStatus.CONFIRMED
        proposal.booking_id = booking_id
        proposal.confirmed_at = self._clock().astimezone(UTC)
        proposal.superseded_reason = None
        proposal.closed_at = None
        self._db.add(proposal)
        self._db.commit()

    async def _slot_full(
        self,
        user: VehicleUser,
        conversation: Conversation,
        vehicle: UserVehicle,
        proposal: BookingProposal,
        extra: list[AlternativeOut],
    ) -> NoReturn:
        """BR-1511 — never books; offers what is still free and asks to confirm again. Always raises."""
        earliest = self._clock() + timedelta(minutes=self._config.min_lead_minutes)
        candidates: list[dict] = []
        seen: set[tuple[str, str, str]] = set()

        def take(option: dict) -> None:
            key = (option["workshopId"], option["date"], option["timeSlot"])
            if key in seen or len(candidates) >= 1 + self._config.max_alternatives:
                return
            seen.add(key)
            candidates.append(option)

        old_by_workshop = {o["workshopId"]: o for o in [proposal.options["primary"], *proposal.options["alternatives"]]}
        for option in proposal.options["alternatives"]:
            d, t = _parse_slot(option)
            if appointment_at(d, t) < earliest:
                continue
            try:
                check = await self._bookings.check_availability(
                    user, UUID(option["workshopId"]), d, t, with_alternatives=False
                )
            except booking_errors.BookingError:
                continue
            if check.requested is not None and check.requested.available:
                take(dict(option))
        for alt in extra:
            if appointment_at(alt.date, alt.time_slot) < earliest:
                continue
            workshop = self._db.get(Workshop, alt.workshop_id)
            if workshop is None:
                continue
            known = old_by_workshop.get(str(alt.workshop_id))
            option = _option(
                0,
                workshop,
                known["distanceKm"] if known else None,
                bool(known and known.get("isPreferred")),
                alt.date,
                alt.time_slot,
            )
            option["estimate"] = known.get("estimate") if known else None
            take(option)

        if not candidates:
            self._close(proposal, BookingProposalStatus.SUPERSEDED, SupersededReason.SLOT_FULL.value)
            message = await self._say(conversation.id, _no_slot_text(), None)
            logger.info("quick_booking.slot_full", extra={"proposal_id": str(proposal.id), "new_proposal_id": None})
            raise errors.ProposalSlotFullError(proposal_id=None, message=_json(message))

        months = self._month_of(vehicle, proposal.odo_milestone)
        for i, option in enumerate(candidates):
            option["optionId"] = f"opt-{i + 1}"
            if option.get("estimate") is None and months is not None and proposal.odo_milestone:
                option["estimate"] = self._estimate(vehicle, proposal.odo_milestone, months, option["workshopId"])

        snapshot = self._snapshot(proposal)
        new = self._create_proposal(
            user,
            conversation,
            vehicle,
            source=ProposalSource(proposal.source),
            odo_milestone=proposal.odo_milestone,
            options=candidates,
            basis=LocationBasis(proposal.location_basis),
            reason=SupersededReason.SLOT_FULL,
        )
        card = self._card(
            new,
            vehicle,
            milestone=snapshot.get("milestone"),
            reason=snapshot.get("reason") or "",
            basis=proposal.location_basis,
            location_label=snapshot.get("locationLabel"),
        )
        old_slot = format_slot(proposal.booking_date, proposal.time_slot)
        primary = candidates[0]
        text = (
            f"Khung giờ {old_slot} vừa hết chỗ. Đề xuất mới: {primary['workshopName']} lúc "
            f'{format_slot(*_parse_slot(primary))}. Bấm "Xác nhận đặt lịch" để đặt lại.'
        )
        message = await self._say(conversation.id, text, card)
        if message is not None:
            self._attach(new, message.id)
        logger.info("quick_booking.slot_full", extra={"proposal_id": str(proposal.id), "new_proposal_id": str(new.id)})
        raise errors.ProposalSlotFullError(proposal_id=str(new.id), message=_json(message))

    async def _say(self, conversation_id: UUID, text: str, card: dict | None) -> ChatMessage | None:
        if self._messages is None:
            return None
        result = await self._messages.append(conversation_id, MessageRole.ASSISTANT, text, card=card)
        return result.message

    # ── API-QB-03 ───────────────────────────────────────────────────────
    async def revise(
        self, user_id: int, conversation_id: UUID, proposal_id: UUID, request: schemas.ReviseRequest
    ) -> schemas.ReviseData:
        chat, _ = self._require_chat()
        user, conversation, vehicle = self._guard(user_id, conversation_id)
        await chat.check_rate_limit(user_id)
        self._owned_proposal(user_id, conversation, proposal_id)
        async with chat.run_lock(conversation_id), self._proposal_lock(proposal_id):
            proposal = self._reload(proposal_id)
            self._require_active(proposal)

            offered = [proposal.options["primary"], *proposal.options["alternatives"]]
            same = [o for o in offered if o["workshopId"] == str(request.workshopId)]
            if not same:
                raise errors.ReviseWorkshopNotOfferedError()
            if appointment_at(request.date, request.timeSlot) < self._clock() + timedelta(
                minutes=self._config.min_lead_minutes
            ):
                raise errors.SlotTooSoonError()
            availability = await self._bookings.check_availability(
                user, request.workshopId, request.date, request.timeSlot, with_alternatives=True
            )
            if availability.requested is None or not availability.requested.available:
                raise errors.QuickBookingError(
                    "The selected time slot is no longer available.",
                    code="SLOT_FULL",
                    details={
                        "alternatives": [a.model_dump(mode="json", by_alias=True) for a in availability.alternatives]
                    },
                )

            chosen = {**same[0], "date": request.date.isoformat(), "timeSlot": _hhmm(request.timeSlot)}
            rest = [
                o
                for o in offered
                if (o["workshopId"], o["date"], o["timeSlot"])
                != (chosen["workshopId"], chosen["date"], chosen["timeSlot"])
            ]
            options = [chosen, *rest[: self._config.max_alternatives]]
            for i, option in enumerate(options):
                options[i] = {**option, "optionId": f"opt-{i + 1}"}

            snapshot = self._snapshot(proposal)
            new = self._create_proposal(
                user,
                conversation,
                vehicle,
                source=ProposalSource(proposal.source),
                odo_milestone=proposal.odo_milestone,
                options=options,
                basis=LocationBasis(proposal.location_basis),
                reason=SupersededReason.REVISED,
            )
            card = self._card(
                new,
                vehicle,
                milestone=snapshot.get("milestone"),
                reason=snapshot.get("reason") or "",
                basis=proposal.location_basis,
                location_label=snapshot.get("locationLabel"),
            )
            text = (
                f"Đã cập nhật đề xuất: {chosen['workshopName']} lúc {format_slot(request.date, request.timeSlot)}. "
                'Bấm "Xác nhận đặt lịch" để đặt.'
            )
            message = await self._say(conversation.id, text, card)
            if message is None:
                raise RuntimeError("revise needs a message sink")
            self._attach(new, message.id)
            logger.info(
                "quick_booking.revised", extra={"proposal_id": str(proposal.id), "new_proposal_id": str(new.id)}
            )
            return schemas.ReviseData(proposalId=new.id, message=self._dto(message))

    # ── API-QB-04 ───────────────────────────────────────────────────────
    async def cancel(self, user_id: int, conversation_id: UUID, proposal_id: UUID) -> schemas.CancelData:
        _, conversation, _ = self._guard(user_id, conversation_id)
        self._owned_proposal(user_id, conversation, proposal_id)
        async with self._proposal_lock(proposal_id):
            proposal = self._reload(proposal_id)
            if proposal.status == BookingProposalStatus.CANCELLED:
                return schemas.CancelData(proposalId=proposal.id, status="CANCELLED")
            if proposal.status == BookingProposalStatus.CONFIRMED:
                raise errors.ProposalAlreadyConfirmedError()
            self._require_active(proposal)  # SUPERSEDED / EXPIRED (expiry wins over cancel)
            self._close(proposal, BookingProposalStatus.CANCELLED)
            logger.info("quick_booking.cancelled", extra={"proposal_id": str(proposal.id)})
            return schemas.CancelData(proposalId=proposal.id, status="CANCELLED")

    # ── TOOL-QB-01 (agent ``propose_booking``) ──────────────────────────
    async def propose_from_agent(
        self,
        user_id: int,
        user_vehicle_id: UUID,
        conversation_id: UUID,
        workshop_id: UUID,
        d: date,
        t: time,
        odo_milestone: int | None,
    ) -> tuple[BookingProposal, dict]:
        """A proposal (never a booking) for a slot the owner picked in free chat (BR-1514).

        The chat turn already holds the conversation run lock; the card is saved
        with the assistant message by ``ChatService``.
        """
        user, conversation, vehicle = self._guard(user_id, conversation_id)
        if vehicle.id != user_vehicle_id:
            raise errors.QuickBookingError("Conversation was not found.", code="CONVERSATION_NOT_FOUND")
        if self._open_booking(vehicle) is not None:  # BR-013: say it now, not at the confirm
            raise booking_errors.OpenBookingExistsError()
        if appointment_at(d, t) < self._clock() + timedelta(minutes=self._config.min_lead_minutes):
            raise errors.SlotTooSoonError()
        availability = await self._bookings.check_availability(user, workshop_id, d, t, with_alternatives=True)
        if availability.requested is None or not availability.requested.available:
            raise booking_errors.SlotFullError(availability.alternatives)

        # May seed the demo ODO (a blocking DB write): keep it off the event loop.
        status = await run_in_threadpool(self._vehicles.get_maintenance_status, vehicle)
        next_milestone = status.next_milestone
        matches = next_milestone is not None and odo_milestone == next_milestone.odo_milestone_km
        workshop = self._db.get(Workshop, workshop_id)
        option = _option(1, workshop, None, workshop.id == user.preferred_workshop_id, d, t)
        if matches:
            option["estimate"] = self._estimate(
                vehicle, next_milestone.odo_milestone_km, next_milestone.month_milestone, option["workshopId"]
            )
            reason = reason_text(
                status.due_status,
                next_milestone.odo_milestone_km,
                next_milestone.due_date,
                status.remaining_km,
                status.remaining_days if status.remaining_days is not None else 0,
            )
        else:
            option["estimate"] = None
            reason = "Đề xuất theo khung giờ bạn đã chọn."
        proposal = self._create_proposal(
            user,
            conversation,
            vehicle,
            source=ProposalSource.CHAT_AGENT,
            odo_milestone=odo_milestone,
            options=[option],
            basis=LocationBasis.NONE,
            reason=SupersededReason.NEW_PROPOSAL,
        )
        card = self._card(
            proposal,
            vehicle,
            milestone=_milestone_out(status) if matches else None,
            reason=reason,
            basis=LocationBasis.NONE,
            location_label=None,
        )
        return proposal, card


# ── helpers ──────────────────────────────────────────────────────────────
def _option(
    index: int,
    workshop: Workshop,
    distance_km: float | None,
    is_preferred: bool,
    d: date,
    t: time,
) -> dict:
    return {
        "optionId": f"opt-{index}",
        "workshopId": str(workshop.id),
        "workshopName": workshop.name,
        "address": workshop.address,
        "region": workshop.region,
        "distanceKm": round(distance_km, 2) if distance_km is not None else None,
        "isPreferred": is_preferred,
        "date": d.isoformat(),
        "timeSlot": _hhmm(t),
        "estimate": None,
    }


def _milestone_out(status: MaintenanceStatusOut) -> dict | None:
    m = status.next_milestone
    if m is None:
        return None
    return {
        "odoMilestoneKm": m.odo_milestone_km,
        "monthMilestone": m.month_milestone,
        "label": m.label,
        "dueDate": m.due_date.isoformat(),
        "dueStatus": status.due_status,
        "dueReason": status.due_reason,
        "remainingKm": status.remaining_km,
        "remainingDays": status.remaining_days,
        "items": [
            {"itemCode": i.item_code, "itemName": i.item_name, "isCoveredByWarranty": i.is_covered_by_warranty}
            for i in m.items
        ],
    }


def _booking_out(booking: BookingOut) -> schemas.ProposalBookingOut:
    return schemas.ProposalBookingOut(
        bookingId=booking.booking_id,
        bookingCode=booking.booking_code,
        status=booking.status,
        confirmationMode=booking.confirmation_mode,
        workshopName=booking.workshop_name,
        bookingDate=booking.booking_date,
        timeSlot=booking.time_slot,
        ownerCancelableUntil=booking.owner_cancelable_until.isoformat() if booking.owner_cancelable_until else None,
    )


def _json(message: ChatMessage | None) -> dict | None:
    return MessageDto.from_message(message).model_dump(mode="json") if message is not None else None


def _unknown_text(reason: str | None) -> str:
    """EF-1502 — say what is missing; never guess the ODO or the milestone."""
    if reason == "OEM_DATA_NOT_SYNCED":
        return (
            "Mình chưa có đủ dữ liệu xe từ hãng (số ODO, lịch sử bảo dưỡng) để xác định mốc bảo dưỡng. "
            "Hệ thống đang lấy dữ liệu, bạn thử lại sau ít phút nhé."
        )
    if reason == "NO_MAINTENANCE_RULE":
        return (
            "Dòng xe của bạn chưa có lịch bảo dưỡng trong hệ thống. Bạn liên hệ xưởng để được tư vấn mốc bảo dưỡng nhé."
        )
    return "Mình chưa xác định được mốc bảo dưỡng của xe. Bạn thử lại sau nhé."


def _need_location(regions: list[str], missing: str | None) -> tuple[str, dict, dict, None]:
    """AF-1501 — ask for the area instead of guessing."""
    if missing:
        text = f"Chưa có xưởng đang hoạt động ở khu vực bạn chọn ({missing.removeprefix('Xưởng trong khu vực ')})."
        text += " Bạn chọn khu vực khác nhé."
    else:
        text = "Mình chưa biết vị trí của bạn. Bạn muốn bảo dưỡng ở khu vực nào?"
    card = {"type": CARD_NEED_LOCATION, "version": CARD_VERSION, "regions": regions}
    return text, card, {}, None


def _too_far_text(status: MaintenanceStatusOut) -> str:
    """EF-1504 — not due yet and the due date is beyond the look-ahead."""
    m = status.next_milestone
    km = f"{format_km(status.remaining_km)} / " if status.remaining_km is not None else ""
    return (
        f"Xe chưa đến hạn bảo dưỡng: còn {km}{status.remaining_days} ngày tới mốc {format_km(m.odo_milestone_km)} "
        f"(hạn {m.due_date.strftime('%d/%m/%Y')}). Ứng dụng sẽ nhắc bạn khi gần hạn."
    )


def _no_slot_text() -> str:
    """EF-1503."""
    return (
        "Các xưởng gần bạn hiện không còn khung giờ phù hợp trong thời gian tới. "
        "Bạn nhắn ngày mong muốn để mình tìm khung giờ khác nhé."
    )
