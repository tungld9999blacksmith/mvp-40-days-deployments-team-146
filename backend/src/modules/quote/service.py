"""Quote module — quotes approved by the workshop owner (us-049, HITL).

* Vehicle owner: draft from (vehicle, workshop, milestone) — the lines are a
  snapshot of ``CostEstimationService.estimate`` (BR-1101, BR-1102); read, submit,
  delete a draft (API-QT-01..05).
* Workshop owner: list / read / approve (line prices, validity) / reject
  (API-QT-11..14), scoped to their workshop and never showing drafts (BR-1110).
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.maintenance.quote import Quote, QuoteStatus
from src.common.core.maintenance.quote_item import QuoteItem
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop import Workshop, WorkshopStatus
from src.modules.cost_estimate.errors import CostEstimateError
from src.modules.cost_estimate.schemas import EstimateData
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.oem_integration.service import as_utc

from . import errors, schemas

logger = logging.getLogger(__name__)

ESTIMATE_LABEL = "Chi phí ước tính"
APPROVED_LABEL = "Báo giá đã duyệt"
EXPIRED_LABEL = "Đã hết hiệu lực"
WAITING_LONG_HOURS = 24  # Q-1105
REJECT_NOTE_MIN, REJECT_NOTE_MAX = 10, 500


@dataclass(frozen=True)
class QuoteConfig:
    default_validity_days: int = 7
    max_validity_days: int = 30
    draft_refresh_hours: int = 24


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


class QuoteService:
    def __init__(
        self,
        session: Session,
        estimator: CostEstimationService,
        *,
        config: QuoteConfig = QuoteConfig(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._estimator = estimator
        self._config = config
        self._clock = clock

    # ── derived state (§4 table) ────────────────────────────────────────
    def _items(self, quote_id: UUID) -> list[QuoteItem]:
        return list(
            self._db.exec(select(QuoteItem).where(QuoteItem.quote_id == quote_id).order_by(QuoteItem.item_code)).all()
        )

    def display_status(self, quote: Quote, items: list[QuoteItem] | None = None) -> tuple[str, str]:
        """Return (displayStatus, priceLabel)."""
        if quote.status == QuoteStatus.APPROVED:
            if quote.expires_at is not None and self._clock() >= as_utc(quote.expires_at):
                return "EXPIRED", EXPIRED_LABEL
            items = items if items is not None else self._items(quote.id)
            modified = any(i.approved_price is not None and i.approved_price != i.estimated_price for i in items)
            return ("MODIFIED" if modified else "APPROVED"), APPROVED_LABEL
        return quote.status.value.upper(), ESTIMATE_LABEL

    def _can_attach(self, quote: Quote, display: str) -> bool:
        if display not in ("APPROVED", "MODIFIED"):
            return False
        if quote.booking_id is None:
            return True
        booking = self._db.get(Booking, quote.booking_id)
        return booking is not None and booking.status == BookingStatus.CANCELLED

    def _detail(self, quote: Quote) -> dict:
        items = self._items(quote.id)
        display, label = self.display_status(quote, items)
        workshop = self._db.get(Workshop, quote.workshop_id)
        return {
            "quote_id": quote.id,
            "status": quote.status.value.upper(),
            "display_status": display,
            "price_label": label,
            "can_attach_to_booking": self._can_attach(quote, display),
            "user_vehicle_id": quote.user_vehicle_id,
            "workshop": schemas.QuoteWorkshopOut(workshop_id=quote.workshop_id, name=workshop.name if workshop else ""),
            "odo_milestone": quote.odo_milestone,
            "items": [
                schemas.QuoteItemOut(
                    quote_item_id=i.id,
                    item_code=i.item_code,
                    item_name=i.item_name,
                    covered=i.is_covered_by_warranty,
                    price_source=i.price_source,
                    estimated_price=i.estimated_price,
                    approved_price=i.approved_price,
                    reviewer_note=i.reviewer_note,
                )
                for i in items
            ],
            "estimated_total": quote.estimated_total,
            "approved_total": quote.approved_total,
            "created_at": quote.created_at,
            "submitted_at": quote.submitted_at,
            "reviewed_at": quote.reviewed_at,
            "expires_at": quote.expires_at,
            "reviewer_note": quote.reviewer_note,
            "booking_id": quote.booking_id,
        }

    # ── owner: guards ───────────────────────────────────────────────────
    def _owned_vehicle(self, user: VehicleUser, user_vehicle_id: UUID) -> UserVehicle:
        try:
            return self._estimator.get_owned_active_vehicle(user, user_vehicle_id)
        except CostEstimateError as exc:
            raise errors.QuoteError(exc.message, code=exc.code) from exc

    def _owned_quote(self, user: VehicleUser, quote_id: UUID) -> Quote:
        row = self._db.exec(
            select(Quote)
            .join(UserVehicle, UserVehicle.id == Quote.user_vehicle_id)
            .where(Quote.id == quote_id, UserVehicle.user_id == user.user_id)
        ).first()
        if row is None:
            raise errors.QuoteNotFoundError()
        return row

    def _active_workshop(self, workshop_id: UUID) -> Workshop:
        workshop = self._db.get(Workshop, workshop_id)
        if workshop is None or workshop.status != WorkshopStatus.ACTIVE:
            raise errors.WorkshopInactiveError()
        return workshop

    def _snapshot(self, vehicle: UserVehicle, workshop: Workshop, odo_milestone: int) -> EstimateData:
        """us-045 estimate of one milestone — the single source of quote numbers."""
        month = self._db.exec(
            select(MaintenanceRule.month_milestone).where(
                MaintenanceRule.model_id == vehicle.external_model_id,
                MaintenanceRule.odo_milestone == odo_milestone,
            )
        ).first()
        if month is None:
            has_rules = self._db.exec(
                select(MaintenanceRule.odo_milestone).where(MaintenanceRule.model_id == vehicle.external_model_id)
            ).all()
            if not has_rules:
                raise errors.NoMaintenanceRuleError()
            raise errors.QuoteError(
                "The maintenance milestone is not in the schedule of this vehicle.",
                code="MILESTONE_NOT_FOUND",
                details={"validMilestones": sorted(set(has_rules))},
            )
        estimate = self._estimator.estimate(vehicle, (odo_milestone, month), workshop)
        if estimate.status != "READY":
            raise errors.NoMaintenanceRuleError()
        return estimate

    @staticmethod
    def _lines(quote_id: UUID, estimate: EstimateData) -> list[QuoteItem]:
        return [
            QuoteItem(
                quote_id=quote_id,
                maintenance_rule_id=item.maintenance_rule_id,
                item_code=item.item_code,
                item_name=item.item_name,
                is_covered_by_warranty=item.covered,
                price_source=item.price_source,
                estimated_price=item.price,
            )
            for item in estimate.items
        ]

    # ── API-QT-01 ───────────────────────────────────────────────────────
    def create(
        self,
        user: VehicleUser,
        payload: schemas.CreateQuoteRequest,
        *,
        source_message_id: UUID | None = None,
    ) -> schemas.QuoteOut:
        vehicle = self._owned_vehicle(user, payload.user_vehicle_id)
        workshop = self._active_workshop(payload.workshop_id)
        estimate = self._snapshot(vehicle, workshop, payload.odo_milestone)
        quote = Quote(
            user_vehicle_id=vehicle.id,
            workshop_id=workshop.id,
            odo_milestone=payload.odo_milestone,
            status=QuoteStatus.DRAFT,
            estimated_total=estimate.chargeable_total,
            source_message_id=source_message_id,
            created_at=self._clock(),
        )
        self._db.add(quote)
        self._db.flush()
        self._db.add_all(self._lines(quote.id, estimate))
        self._db.commit()
        self._db.refresh(quote)
        logger.info("quote.created", extra={"quote_id": str(quote.id), "workshop_id": str(workshop.id)})
        return schemas.QuoteOut(**self._detail(quote))

    # ── API-QT-02 ───────────────────────────────────────────────────────
    def list_for_owner(
        self,
        user: VehicleUser,
        *,
        user_vehicle_id: UUID | None,
        statuses: list[QuoteStatus] | None,
        unseen_result: bool,
        limit: int,
        cursor: str | None,
    ) -> schemas.QuoteListData:
        offset = _decode_offset(cursor)
        query = (
            select(Quote)
            .join(UserVehicle, UserVehicle.id == Quote.user_vehicle_id)
            .where(UserVehicle.user_id == user.user_id)
        )
        if user_vehicle_id is not None:
            query = query.where(Quote.user_vehicle_id == user_vehicle_id)
        if statuses:
            query = query.where(Quote.status.in_(statuses))
        if unseen_result:
            query = query.where(
                Quote.status.in_([QuoteStatus.APPROVED, QuoteStatus.REJECTED]),
                Quote.result_seen_at.is_(None),
            )
        rows = list(
            self._db.exec(
                query.order_by(Quote.created_at.desc(), Quote.id.desc()).offset(offset).limit(limit + 1)
            ).all()
        )
        items = []
        for q in rows[:limit]:
            d = self._detail(q)
            items.append(
                schemas.QuoteSummaryOut(
                    **{k: v for k, v in d.items() if k in schemas.QuoteSummaryOut.model_fields},
                    result_seen=q.result_seen_at is not None,
                )
            )
        return schemas.QuoteListData(
            items=items, next_cursor=_encode_offset(offset + limit) if len(rows) > limit else None
        )

    # ── API-QT-03 ───────────────────────────────────────────────────────
    def get_for_owner(self, user: VehicleUser, quote_id: UUID) -> schemas.QuoteOut:
        quote = self._owned_quote(user, quote_id)
        if quote.status in (QuoteStatus.APPROVED, QuoteStatus.REJECTED) and quote.result_seen_at is None:
            quote.result_seen_at = self._clock()  # BR-1109 badge (idempotent)
            self._db.add(quote)
            self._db.commit()
            self._db.refresh(quote)
        return schemas.QuoteOut(**self._detail(quote))

    # ── API-QT-04 ───────────────────────────────────────────────────────
    def submit(self, user: VehicleUser, quote_id: UUID) -> schemas.QuoteOut:
        quote = self._owned_quote(user, quote_id)
        if quote.status != QuoteStatus.DRAFT:
            raise errors.QuoteNotDraftError(quote.status.value)
        workshop = self._active_workshop(quote.workshop_id)
        now = self._clock()
        if now - as_utc(quote.created_at) > timedelta(hours=self._config.draft_refresh_hours):
            self._refresh_snapshot(quote, workshop)  # Q-1104; raises when numbers changed

        pending = self._pending_twin(quote)
        if pending is not None:
            raise errors.QuoteAlreadyPendingError(str(pending))
        try:
            result = self._db.execute(
                update(Quote)
                .where(Quote.id == quote.id, Quote.status == QuoteStatus.DRAFT)
                .values(status=QuoteStatus.PENDING_APPROVAL, submitted_at=now)
                .execution_options(synchronize_session=False)
            )
            self._db.commit()
        except IntegrityError as exc:  # uq_quote_pending_per_milestone (concurrent submit)
            self._db.rollback()
            twin = self._pending_twin(quote)
            raise errors.QuoteAlreadyPendingError(str(twin) if twin else None) from exc
        self._db.refresh(quote)
        if result.rowcount != 1:
            raise errors.QuoteNotDraftError(quote.status.value)
        logger.info("quote.submitted", extra={"quote_id": str(quote.id)})
        return schemas.QuoteOut(**self._detail(quote))

    def _pending_twin(self, quote: Quote) -> UUID | None:
        return self._db.exec(
            select(Quote.id).where(
                Quote.user_vehicle_id == quote.user_vehicle_id,
                Quote.workshop_id == quote.workshop_id,
                Quote.odo_milestone == quote.odo_milestone,
                Quote.status == QuoteStatus.PENDING_APPROVAL,
                Quote.id != quote.id,
            )
        ).first()

    def _refresh_snapshot(self, quote: Quote, workshop: Workshop) -> None:
        vehicle = self._db.get(UserVehicle, quote.user_vehicle_id)
        estimate = self._snapshot(vehicle, workshop, quote.odo_milestone)
        old = {(i.item_code, i.estimated_price, i.is_covered_by_warranty) for i in self._items(quote.id)}
        new = {(i.item_code, i.price, i.covered) for i in estimate.items}
        if old == new and quote.estimated_total == estimate.chargeable_total:
            return
        for item in self._items(quote.id):
            self._db.delete(item)
        self._db.flush()
        self._db.add_all(self._lines(quote.id, estimate))
        quote.estimated_total = estimate.chargeable_total
        quote.created_at = self._clock()  # the snapshot is fresh again
        self._db.add(quote)
        self._db.commit()
        raise errors.QuoteDraftRefreshedError()

    # ── API-QT-05 ───────────────────────────────────────────────────────
    def delete_draft(self, user: VehicleUser, quote_id: UUID) -> None:
        quote = self._owned_quote(user, quote_id)
        if quote.status != QuoteStatus.DRAFT:
            raise errors.QuoteNotDraftError(quote.status.value)
        for item in self._items(quote.id):
            self._db.delete(item)
        self._db.delete(quote)
        self._db.commit()

    # ── workshop owner ──────────────────────────────────────────────────
    def _workshop_quote(self, workshop_id: UUID, quote_id: UUID) -> Quote:
        quote = self._db.get(Quote, quote_id)
        if quote is None or quote.workshop_id != workshop_id or quote.status == QuoteStatus.DRAFT:
            raise errors.QuoteNotFoundError()  # BR-1110
        return quote

    def _customer(self, quote: Quote) -> tuple[schemas.CustomerOut, UserVehicle | None]:
        vehicle = self._db.get(UserVehicle, quote.user_vehicle_id)
        user = self._db.get(VehicleUser, vehicle.user_id) if vehicle else None
        return (
            schemas.CustomerOut(full_name=user.full_name if user else None, phone=user.phone if user else None),
            vehicle,
        )

    # API-QT-11
    def list_for_workshop(
        self,
        workshop_id: UUID,
        *,
        statuses: list[QuoteStatus] | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        cursor: str | None,
    ) -> schemas.WorkshopQuoteListData:
        offset = _decode_offset(cursor)
        statuses = [s for s in (statuses or [QuoteStatus.PENDING_APPROVAL]) if s != QuoteStatus.DRAFT]
        query = select(Quote).where(Quote.workshop_id == workshop_id, Quote.status.in_(statuses))
        if date_from is not None:
            query = query.where(Quote.submitted_at >= datetime.combine(date_from, time.min, tzinfo=UTC))
        if date_to is not None:
            query = query.where(
                Quote.submitted_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=UTC)
            )
        rows = list(self._db.exec(query.order_by(Quote.submitted_at, Quote.id).offset(offset).limit(limit + 1)).all())
        now = self._clock()
        items = []
        for q in rows[:limit]:
            customer, vehicle = self._customer(q)
            waiting = (
                round((now - as_utc(q.submitted_at)).total_seconds() / 3600, 1)
                if q.submitted_at and q.status == QuoteStatus.PENDING_APPROVAL
                else None
            )
            display, _ = self.display_status(q)
            items.append(
                schemas.WorkshopQuoteItemOut(
                    quote_id=q.id,
                    status=q.status.value.upper(),
                    display_status=display,
                    customer=customer,
                    model_name=vehicle.model_name if vehicle else None,
                    plate_number=vehicle.license_plate if vehicle else None,
                    odo_milestone=q.odo_milestone,
                    estimated_total=q.estimated_total,
                    approved_total=q.approved_total,
                    submitted_at=q.submitted_at,
                    waiting_hours=waiting,
                    is_waiting_long=waiting is not None and waiting >= WAITING_LONG_HOURS,
                    has_conversation=q.source_message_id is not None,
                )
            )
        return schemas.WorkshopQuoteListData(
            items=items, next_cursor=_encode_offset(offset + limit) if len(rows) > limit else None
        )

    # API-QT-12
    def get_for_workshop(self, workshop_id: UUID, quote_id: UUID) -> schemas.WorkshopQuoteOut:
        return self._workshop_out(self._workshop_quote(workshop_id, quote_id))

    def _workshop_out(self, quote: Quote) -> schemas.WorkshopQuoteOut:
        customer, vehicle = self._customer(quote)
        return schemas.WorkshopQuoteOut(
            **self._detail(quote),
            customer=customer,
            model_name=vehicle.model_name if vehicle else None,
            plate_number=vehicle.license_plate if vehicle else None,
            conversation_excerpt_url=(
                f"/api/v1/workshop/quotes/{quote.id}/conversation-excerpt" if quote.source_message_id else None
            ),
        )

    def _lock_pending(self, workshop_id: UUID, quote_id: UUID) -> Quote:
        self._workshop_quote(workshop_id, quote_id)
        quote = self._db.exec(select(Quote).where(Quote.id == quote_id).with_for_update()).one()
        if quote.status != QuoteStatus.PENDING_APPROVAL:
            raise errors.QuoteAlreadyReviewedError(quote.status.value)  # EF-1102
        return quote

    # API-QT-13
    def approve(
        self, owner: WorkshopOwner, workshop_id: UUID, quote_id: UUID, payload: schemas.ApproveQuoteRequest
    ) -> schemas.WorkshopQuoteOut:
        validity = payload.validity_days or self._config.default_validity_days
        if validity > self._config.max_validity_days:
            raise errors.InvalidRequestError(f"validityDays must be between 1 and {self._config.max_validity_days}.")
        quote = self._lock_pending(workshop_id, quote_id)
        items = {i.id: i for i in self._items(quote.id)}
        edits: dict[UUID, schemas.ApproveItemIn] = {}
        for edit in payload.items:
            if edit.quote_item_id not in items or edit.quote_item_id in edits:
                raise errors.InvalidRequestError("Unknown or duplicated quoteItemId.")
            if items[edit.quote_item_id].is_covered_by_warranty and edit.approved_price != 0:
                raise errors.CoveredItemLockedError(str(edit.quote_item_id))
            edits[edit.quote_item_id] = edit

        total = Decimal(0)
        for item_id, item in items.items():
            edit = edits.get(item_id)
            item.approved_price = edit.approved_price if edit else item.estimated_price
            if edit is not None and edit.note:
                item.reviewer_note = edit.note.strip()
            total += item.approved_price
            self._db.add(item)
        now = self._clock()
        reviewer_id = owner.id
        with self._db.no_autoflush:  # the CHECKs hold only once every field is set
            quote.status = QuoteStatus.APPROVED
            quote.approved_total = total  # BR-ENT-414
            quote.reviewed_by = reviewer_id
            quote.reviewed_at = now
            quote.expires_at = now + timedelta(days=validity)
            quote.reviewer_note = (payload.reviewer_note or "").strip() or None
        self._db.add(quote)
        self._db.commit()
        self._db.refresh(quote)
        logger.info("quote.approved", extra={"quote_id": str(quote.id), "actor": str(owner.id)})
        return self._workshop_out(quote)

    # API-QT-14
    def reject(
        self, owner: WorkshopOwner, workshop_id: UUID, quote_id: UUID, reviewer_note: str | None
    ) -> schemas.WorkshopQuoteOut:
        note = (reviewer_note or "").strip()
        if not REJECT_NOTE_MIN <= len(note) <= REJECT_NOTE_MAX:
            raise errors.ReviewerNoteRequiredError()  # BR-1107
        quote = self._lock_pending(workshop_id, quote_id)
        reviewer_id = owner.id
        with self._db.no_autoflush:
            quote.status = QuoteStatus.REJECTED
            quote.reviewed_by = reviewer_id
            quote.reviewed_at = self._clock()
            quote.reviewer_note = note
        self._db.add(quote)
        self._db.commit()
        self._db.refresh(quote)
        logger.info("quote.rejected", extra={"quote_id": str(quote.id), "actor": str(owner.id)})
        return self._workshop_out(quote)
