"""Follow-up & support tickets — application services (us-041).

* ``FollowUpScheduler.on_completed`` — HOOK-FU-001, called inside the Board
  ``COMPLETE`` transaction (us-037 BR-807); never commits.
* ``FollowUpService`` — owner side: read / answer a follow-up (API-FU-01/02) and
  read own tickets (API-FU-03/04).
* ``WorkshopTicketService`` — workshop side: tickets list / detail / START,
  RESOLVE (API-FU-05..07).

The send / auto-close jobs (JOB-FU-001/002) are not part of this module yet.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, update
from sqlmodel import Session, select

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.crm.support_ticket import (
    SupportTicket,
    SupportTicketPriority,
    SupportTicketStatus,
)
from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.maintenance.booking import Booking
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop import Workshop
from src.modules.booking.ticket import mask_plate
from src.modules.notification.channels import NotificationMessage
from src.modules.notification.owner_notifier import OwnerNotifier
from src.modules.oem_integration.service import as_utc

from . import errors, schemas
from .domain import (
    Classification,
    ClassifiedBy,
    FeedbackIntent,
    apply_policy,
    classify_by_rules,
    issue_summary,
    quiet_hours_adjust,
)
from .ports import FeedbackClassifier

logger = logging.getLogger(__name__)

CLASSIFY_TIMEOUT_SECONDS = 5.0
TICKET_ACTIONS: dict[SupportTicketStatus, list[str]] = {
    SupportTicketStatus.OPEN: ["START", "RESOLVE"],
    SupportTicketStatus.IN_PROGRESS: ["RESOLVE"],
    SupportTicketStatus.RESOLVED: [],
}


@dataclass(frozen=True)
class FollowUpConfig:
    delay_hours: int = 12
    response_window_hours: int = 72
    quiet_start_hour: int = 21
    quiet_end_hour: int = 8
    frontend_url: str = ""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _encode_offset(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode()


def _decode_offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(int(base64.urlsafe_b64decode(cursor.encode()).decode()), 0)
    except ValueError as exc:
        raise errors.InvalidRequestError("Invalid cursor.") from exc


def _upper(value) -> str:
    return value.value.upper()


# ── HOOK-FU-001 ─────────────────────────────────────────────────────────────
class FollowUpScheduler:
    def __init__(self, session: Session, config: FollowUpConfig = FollowUpConfig()) -> None:
        self._db = session
        self._config = config

    def on_completed(self, booking: Booking, completed_at: datetime) -> FollowUp:
        """One pending follow-up per booking, +12h outside quiet hours (BR-901, BR-902)."""
        existing = self._db.exec(select(FollowUp).where(FollowUp.booking_id == booking.id)).first()
        if existing is not None:
            return existing  # ON CONFLICT (booking_id) DO NOTHING
        scheduled = quiet_hours_adjust(
            completed_at + timedelta(hours=self._config.delay_hours),
            quiet_start=self._config.quiet_start_hour,
            quiet_end=self._config.quiet_end_hour,
        )
        follow_up = FollowUp(
            booking_id=booking.id,
            message=self._question(booking),
            status=FollowUpStatus.PENDING,
            scheduled_at=scheduled.astimezone(UTC),
        )
        self._db.add(follow_up)
        self._db.flush()
        return follow_up

    def _question(self, booking: Booking) -> str:
        """AI-007 template — model, masked plate, workshop and date; no VIN/phone."""
        vehicle = self._db.get(UserVehicle, booking.user_vehicle_id)
        workshop = self._db.get(Workshop, booking.workshop_id)
        model = vehicle.model_name if vehicle and vehicle.model_name else "của bạn"
        plate = mask_plate(vehicle.license_plate) if vehicle else None
        car = f"Xe {model}" + (f" ({plate})" if plate else "")
        where = workshop.name if workshop else "xưởng"
        return (
            f"{car} đã bảo dưỡng xong tại {where} ngày {booking.booking_date:%d/%m}. "
            "Xe của bạn chạy thế nào?"
        )


# ── owner side ──────────────────────────────────────────────────────────────
class FollowUpService:
    def __init__(
        self,
        session: Session,
        *,
        classifier: FeedbackClassifier | None = None,
        config: FollowUpConfig = FollowUpConfig(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._classifier = classifier
        self._config = config
        self._clock = clock

    def _owned(self, user: VehicleUser, follow_up_id: UUID) -> tuple[FollowUp, Booking]:
        row = self._db.exec(
            select(FollowUp, Booking)
            .join(Booking, Booking.id == FollowUp.booking_id)
            .where(FollowUp.id == follow_up_id, Booking.user_id == user.user_id)
        ).first()
        if row is None:
            raise errors.FollowUpNotFoundError()  # AC-910
        return row

    def _deadline(self, follow_up: FollowUp) -> datetime | None:
        if follow_up.sent_at is None:
            return None
        return as_utc(follow_up.sent_at) + timedelta(hours=self._config.response_window_hours)

    def _ticket(self, follow_up_id: UUID) -> SupportTicket | None:
        return self._db.exec(
            select(SupportTicket).where(SupportTicket.follow_up_id == follow_up_id)
        ).first()

    # API-FU-01
    def get(self, user: VehicleUser, follow_up_id: UUID) -> schemas.FollowUpOut:
        follow_up, booking = self._owned(user, follow_up_id)
        workshop = self._db.get(Workshop, booking.workshop_id)
        deadline = self._deadline(follow_up)
        can_respond = (
            follow_up.status == FollowUpStatus.SENT
            and deadline is not None
            and self._clock() <= deadline
        )
        response = None
        if follow_up.rating is not None and follow_up.responded_at is not None:
            response = schemas.ResponseOut(
                rating=follow_up.rating,
                comment=follow_up.customer_response,
                responded_at=follow_up.responded_at,
            )
        outcome = None
        if follow_up.closed_reason == "PROCESSED":
            ticket = self._ticket(follow_up.id)
            outcome = schemas.OutcomeOut(
                has_issue=follow_up.has_issue,
                safety_advice=bool(ticket and ticket.priority == SupportTicketPriority.HIGH),
                ticket=schemas.TicketRefOut(ticket_id=ticket.id, status=_upper(ticket.status))
                if ticket
                else None,
            )
        return schemas.FollowUpOut(
            follow_up_id=follow_up.id,
            status=_upper(follow_up.status),
            closed_reason=follow_up.closed_reason,
            can_respond=can_respond,
            respond_before=deadline if follow_up.status == FollowUpStatus.SENT else None,
            question=follow_up.message,
            booking=schemas.FollowUpBookingOut(
                booking_id=booking.id,
                booking_code=booking.booking_code,
                booking_date=booking.booking_date,
            ),
            workshop=schemas.WorkshopContactOut(
                name=workshop.name if workshop else "", hotline=workshop.hotline if workshop else None
            ),
            response=response,
            outcome=outcome,
        )

    # API-FU-02
    async def respond(
        self, user: VehicleUser, follow_up_id: UUID, rating: int, comment: str | None
    ) -> schemas.RespondOut:
        follow_up, booking = self._owned(user, follow_up_id)
        workshop = self._db.get(Workshop, booking.workshop_id)
        hotline = workshop.hotline if workshop else None
        self._check_open(follow_up, hotline)
        comment = (comment or "").strip() or None

        result = await self._classify(rating, comment)
        now = self._clock()
        ticket = None
        # sent → responded → closed/PROCESSED in one transaction (BR-907, BR-ENT-501);
        # the conditional UPDATE lets only one of two concurrent answers win.
        claimed = self._db.execute(
            update(FollowUp)
            .where(FollowUp.id == follow_up.id, FollowUp.status == FollowUpStatus.SENT)
            .values(
                status=FollowUpStatus.RESPONDED,
                rating=rating,
                customer_response=comment,
                responded_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if claimed.rowcount != 1:
            self._db.rollback()
            self._db.refresh(follow_up)
            self._check_open(follow_up, hotline)  # raises the precise reason
            raise errors.FollowUpAlreadyRespondedError()
        self._db.refresh(follow_up)
        if result.has_issue:
            ticket = SupportTicket(
                follow_up_id=follow_up.id,
                user_vehicle_id=booking.user_vehicle_id,
                assigned_to=workshop.owner_id if workshop else None,
                issue_summary=issue_summary(result, rating, comment),
                status=SupportTicketStatus.OPEN,
                priority=SupportTicketPriority.HIGH if result.safety else SupportTicketPriority.NORMAL,
            )
            self._db.add(ticket)
        follow_up.status = FollowUpStatus.CLOSED
        follow_up.closed_reason = "PROCESSED"
        follow_up.closed_at = now
        follow_up.has_issue = result.has_issue
        follow_up.feedback_intent = result.intent.value
        follow_up.classification_confidence = result.confidence
        follow_up.classified_by = result.classified_by.value
        self._db.add(follow_up)
        self._db.commit()
        logger.info(
            "follow_up.responded",
            extra={
                "follow_up_id": str(follow_up.id),
                "rating": rating,
                "has_issue": result.has_issue,
                "classified_by": result.classified_by.value,
            },
        )
        where = workshop.name if workshop else "xưởng"
        return schemas.RespondOut(
            follow_up_id=follow_up.id,
            status=_upper(follow_up.status),
            outcome=schemas.OutcomeOut(
                has_issue=result.has_issue,
                safety_advice=result.safety,
                message=(
                    "Cảm ơn bạn đã phản hồi. Chúng mình đã chuyển thông tin tới xưởng "
                    f"{where}. Xưởng sẽ liên hệ lại với bạn."
                    if result.has_issue
                    else "Cảm ơn bạn đã phản hồi!"
                ),
                safety_message=(
                    "Nếu xe có dấu hiệu bất thường khi vận hành, bạn nên dừng xe và liên hệ "
                    f"xưởng ngay: {hotline or where}."
                    if result.safety
                    else None
                ),
                ticket=schemas.TicketRefOut(ticket_id=ticket.id, status=_upper(ticket.status))
                if ticket
                else None,
            ),
        )

    def _check_open(self, follow_up: FollowUp, hotline: str | None) -> None:
        """us-041 §4.2 validation order."""
        if follow_up.status == FollowUpStatus.PENDING:
            raise errors.FollowUpNotOpenError()
        if follow_up.status == FollowUpStatus.RESPONDED or follow_up.closed_reason == "PROCESSED":
            raise errors.FollowUpAlreadyRespondedError()
        if follow_up.status == FollowUpStatus.CLOSED:
            raise errors.FollowUpClosedError(hotline)
        deadline = self._deadline(follow_up)
        if deadline is None or self._clock() > deadline:
            raise errors.FollowUpClosedError(hotline)

    async def _classify(self, rating: int, comment: str | None) -> Classification:
        """BR-906 — rules for a clear 4-5★ without comment; else LLM with rule fallback."""
        if rating >= 4 and not comment:
            return Classification(FeedbackIntent.SATISFIED, False, False, ClassifiedBy.RULES)
        if self._classifier is not None and comment:
            try:
                result = await asyncio.wait_for(
                    self._classifier.classify(rating, comment), timeout=CLASSIFY_TIMEOUT_SECONDS
                )
            except Exception:  # noqa: BLE001 — AI failure never reaches the client (AF-904)
                logger.warning("follow_up.classify_failed", exc_info=True)
                result = None
            if result is not None:
                return apply_policy(result, rating)
        return classify_by_rules(rating, comment, by=ClassifiedBy.LLM_FALLBACK)

    # API-FU-03
    def list_tickets(
        self,
        user: VehicleUser,
        *,
        status: SupportTicketStatus | None,
        limit: int,
        cursor: str | None,
    ) -> schemas.OwnerTicketListData:
        offset = _decode_offset(cursor)
        query = (
            select(SupportTicket, Booking, Workshop)
            .join(FollowUp, FollowUp.id == SupportTicket.follow_up_id)
            .join(Booking, Booking.id == FollowUp.booking_id)
            .join(Workshop, Workshop.id == Booking.workshop_id)
            .where(Booking.user_id == user.user_id)
        )
        if status is not None:
            query = query.where(SupportTicket.status == status)
        rows = self._db.exec(
            query.order_by(SupportTicket.created_at.desc(), SupportTicket.id.desc())
            .offset(offset)
            .limit(limit + 1)
        ).all()
        page = rows[:limit]
        return schemas.OwnerTicketListData(
            items=[
                schemas.OwnerTicketItemOut(
                    ticket_id=t.id,
                    status=_upper(t.status),
                    issue_summary=t.issue_summary,
                    workshop_name=w.name,
                    booking_date=b.booking_date,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                )
                for t, b, w in page
            ],
            next_cursor=_encode_offset(offset + limit) if len(rows) > limit else None,
        )

    # API-FU-04
    def get_ticket(self, user: VehicleUser, ticket_id: UUID) -> schemas.OwnerTicketOut:
        row = self._db.exec(
            select(SupportTicket, FollowUp, Booking)
            .join(FollowUp, FollowUp.id == SupportTicket.follow_up_id)
            .join(Booking, Booking.id == FollowUp.booking_id)
            .where(SupportTicket.id == ticket_id, Booking.user_id == user.user_id)
        ).first()
        if row is None:
            raise errors.SupportTicketNotFoundError()
        ticket, follow_up, booking = row
        workshop = self._db.get(Workshop, booking.workshop_id)
        return schemas.OwnerTicketOut(
            ticket_id=ticket.id,
            status=_upper(ticket.status),
            issue_summary=ticket.issue_summary,
            your_feedback=schemas.FeedbackOut(
                rating=follow_up.rating, comment=follow_up.customer_response
            ),
            booking=schemas.FollowUpBookingOut(
                booking_id=booking.id,
                booking_code=booking.booking_code,
                booking_date=booking.booking_date,
            ),
            workshop=schemas.WorkshopContactOut(
                name=workshop.name if workshop else "", hotline=workshop.hotline if workshop else None
            ),
            started_at=ticket.started_at,
            resolved_at=ticket.resolved_at,
            resolution_note=ticket.resolution_note,
        )


# ── workshop side ───────────────────────────────────────────────────────────
class WorkshopTicketService:
    def __init__(
        self,
        session: Session,
        *,
        notifier: OwnerNotifier | None = None,
        frontend_url: str = "",
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._notifier = notifier
        self._frontend_url = frontend_url.rstrip("/")
        self._clock = clock

    def _scope(self, owner: WorkshopOwner, workshop_id: UUID | None):
        """BR-ENT-506 — assigned to me, or unassigned on a booking of my workshop."""
        mine = SupportTicket.assigned_to == owner.id
        if workshop_id is None:
            return mine
        return or_(mine, and_(SupportTicket.assigned_to.is_(None), Booking.workshop_id == workshop_id))

    def _base(self, owner: WorkshopOwner, workshop_id: UUID | None):
        return (
            select(SupportTicket, FollowUp, Booking, VehicleUser, UserVehicle)
            .join(FollowUp, FollowUp.id == SupportTicket.follow_up_id)
            .join(Booking, Booking.id == FollowUp.booking_id)
            .join(VehicleUser, VehicleUser.user_id == Booking.user_id)
            .join(UserVehicle, UserVehicle.id == SupportTicket.user_vehicle_id)
            .where(self._scope(owner, workshop_id))
        )

    @staticmethod
    def _item(t, f, b, u, v, *, with_phone: bool = False) -> dict:
        return {
            "ticket_id": t.id,
            "status": _upper(t.status),
            "priority": _upper(t.priority),
            "issue_summary": t.issue_summary,
            "rating": f.rating,
            "customer": schemas.CustomerOut(
                full_name=u.full_name, phone=u.phone if with_phone else None
            ),
            "vehicle": schemas.VehicleOut(model_name=v.model_name, license_plate=v.license_plate),
            "booking_code": b.booking_code,
            "created_at": t.created_at,
        }

    # API-FU-05
    def list(
        self,
        owner: WorkshopOwner,
        workshop_id: UUID | None,
        *,
        statuses: list[SupportTicketStatus] | None,
        priority: SupportTicketPriority | None,
        limit: int,
        cursor: str | None,
    ) -> schemas.WorkshopTicketListData:
        offset = _decode_offset(cursor)
        statuses = statuses or [SupportTicketStatus.OPEN, SupportTicketStatus.IN_PROGRESS]
        query = self._base(owner, workshop_id).where(SupportTicket.status.in_(statuses))
        if priority is not None:
            query = query.where(SupportTicket.priority == priority)
        high_first = (SupportTicket.priority == SupportTicketPriority.HIGH).desc()
        rows = self._db.exec(
            query.order_by(high_first, SupportTicket.created_at, SupportTicket.id)
            .offset(offset)
            .limit(limit + 1)
        ).all()
        return schemas.WorkshopTicketListData(
            summary=self._summary(owner, workshop_id),
            items=[schemas.WorkshopTicketItemOut(**self._item(*r)) for r in rows[:limit]],
            next_cursor=_encode_offset(offset + limit) if len(rows) > limit else None,
        )

    def _summary(self, owner: WorkshopOwner, workshop_id: UUID | None) -> dict[str, int]:
        counts = self._db.exec(
            select(SupportTicket.status, SupportTicket.priority, func.count())
            .join(FollowUp, FollowUp.id == SupportTicket.follow_up_id)
            .join(Booking, Booking.id == FollowUp.booking_id)
            .where(self._scope(owner, workshop_id))
            .group_by(SupportTicket.status, SupportTicket.priority)
        ).all()
        summary = {_upper(s): 0 for s in SupportTicketStatus} | {"highOpen": 0}
        for status, priority, count in counts:
            summary[_upper(status)] += int(count)
            if status == SupportTicketStatus.OPEN and priority == SupportTicketPriority.HIGH:
                summary["highOpen"] += int(count)
        return summary

    def _load(self, owner: WorkshopOwner, workshop_id: UUID | None, ticket_id: UUID):
        row = self._db.exec(
            self._base(owner, workshop_id).where(SupportTicket.id == ticket_id)
        ).first()
        if row is None:
            raise errors.SupportTicketNotFoundError()
        return row

    # API-FU-06
    def get(
        self, owner: WorkshopOwner, workshop_id: UUID | None, ticket_id: UUID
    ) -> schemas.WorkshopTicketOut:
        t, f, b, u, v = self._load(owner, workshop_id, ticket_id)
        return schemas.WorkshopTicketOut(
            **self._item(t, f, b, u, v, with_phone=True),
            feedback=schemas.WorkshopFeedbackOut(
                rating=f.rating, comment=f.customer_response, responded_at=f.responded_at
            ),
            classification=schemas.ClassificationOut(
                intent=f.feedback_intent,
                confidence=float(f.classification_confidence)
                if f.classification_confidence is not None
                else None,
                classified_by=f.classified_by,
            ),
            booking=schemas.WorkshopTicketBookingOut(
                booking_id=b.id, booking_date=b.booking_date, time_slot=b.time_slot, actual_cost=b.actual_cost
            ),
            started_at=t.started_at,
            resolved_at=t.resolved_at,
            resolution_note=t.resolution_note,
            allowed_actions=TICKET_ACTIONS[t.status],
        )

    # API-FU-07
    async def transition(
        self,
        owner: WorkshopOwner,
        workshop_id: UUID | None,
        ticket_id: UUID,
        *,
        action: str,
        expected_status: str,
        resolution_note: str | None,
    ) -> schemas.TicketTransitionOut:
        t, _f, b, _u, _v = self._load(owner, workshop_id, ticket_id)
        target = SupportTicketStatus.IN_PROGRESS if action == "START" else SupportTicketStatus.RESOLVED
        if t.status == target and t.assigned_to == owner.id:
            return self._transition_out(t)  # repeated action: idempotent 200
        note = (resolution_note or "").strip()
        if action == "RESOLVE" and not note:
            raise errors.ResolutionNoteRequiredError()
        if _upper(t.status) != expected_status or action not in TICKET_ACTIONS[t.status]:
            raise errors.InvalidStatusTransitionError(t.status.value, TICKET_ACTIONS[t.status])

        now = self._clock()
        t.assigned_to = owner.id  # BR-ENT-506 — whoever acts takes the ticket
        if action == "START":
            t.status = SupportTicketStatus.IN_PROGRESS
            t.started_at = now
        else:
            t.status = SupportTicketStatus.RESOLVED
            t.resolved_at = now
            t.resolution_note = note
        self._db.add(t)
        self._db.commit()
        self._db.refresh(t)
        if action == "RESOLVE":
            await self._notify_resolved(t, b)
        return self._transition_out(t)

    @staticmethod
    def _transition_out(t: SupportTicket) -> schemas.TicketTransitionOut:
        return schemas.TicketTransitionOut(
            ticket_id=t.id,
            status=_upper(t.status),
            started_at=t.started_at,
            resolved_at=t.resolved_at,
            allowed_actions=TICKET_ACTIONS[t.status],
        )

    async def _notify_resolved(self, ticket: SupportTicket, booking: Booking) -> None:
        if self._notifier is None:
            return
        workshop = self._db.get(Workshop, booking.workshop_id)
        link = f"{self._frontend_url}/support-tickets/{ticket.id}" if self._frontend_url else None
        body = f"✅ Xưởng {workshop.name if workshop else ''} đã xử lý phản hồi của bạn."
        try:
            await self._notifier.notify(
                booking.user_id, NotificationMessage(subject="Phiếu hỗ trợ", body=body, link=link)
            )
        except Exception:  # noqa: BLE001 — best effort after commit
            logger.exception("ticket notification failed for %s", ticket.id)
