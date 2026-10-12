"""Two-tier booking pricing — application service (docs/designs/bao-gia-hai-tang.md).

* Tier 1 — ``snapshot_package`` runs inside ``BookingService._create_booking_locked``
  (same transaction, no commit) and copies the milestone estimate into PACKAGE lines.
* Check-in — the workshop confirms each reference price (``confirm_package``); a
  higher price becomes a PROPOSED line the owner decides on.
* Tier 2 — the workshop proposes / edits / withdraws EXTRA lines; only the owner
  approves or declines (``decide``), with ``version`` so they decide on what they saw.
* By phone — when the owner answers on the phone, the workshop records it
  (``record_phone_decision``, ``decided_via=PHONE`` + who answered) and the owner is
  told at once; until COMPLETE the owner can ``dispute`` it, which sends the line
  back to PROPOSED (not charged, blocks COMPLETE) for them to decide on the app.

Every write locks the booking row first, like COMPLETE does (re-review OV1).
The vehicle owner is told after commit, best effort; the decision card on the
ticket is the source of truth when a notification does not arrive.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.maintenance.booking import Booking, BookingStatus, PricingFlow
from src.common.core.maintenance.booking_line import BookingLine, BookingLinePhoto, LineKind, LineStatus
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop import Workshop
from src.modules.booking.domain import TZ_VN
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.cost_estimate.domain import EstimateStatus
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.notification.channels import NotificationMessage
from src.modules.notification.owner_notifier import OwnerNotifier
from src.modules.service_progress.service import ServiceProgressService

from . import errors, schemas
from .domain import (
    DECIDABLE_STATUSES,
    DECIDED_VIA_APP,
    DECIDED_VIA_PHONE,
    EXTRA_STAGES,
    OWNER_REPLY_SLA,
    PACKAGE_NO_RULE_NOTICE,
    REASON_MAX,
    UNSETTLED,
    billable_total,
    complete_block,
    package_status,
    reason_valid,
    reply_due_at,
    start_block,
    total_if_all_approved,
)
from .photos import LinePhotos
from .settlement import lines_of, lock_booking

logger = logging.getLogger(__name__)

S = BookingStatus


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _vnd(amount: Decimal) -> str:
    return f"{int(amount):,}".replace(",", ".") + " đ"


def price_label(line: BookingLine) -> str:
    if line.kind == LineKind.EXTRA:
        return "Phát sinh"
    if line.is_covered_by_warranty:
        return "Bảo hành"
    if line.price_source != "REFERENCE_PRICE":
        return "Giá xưởng"
    # Once the workshop priced it at check-in, it is no longer a reference price.
    return "Xưởng đã xác nhận" if line.confirmed_at is not None else "Giá tham khảo"


def line_snapshot(line: BookingLine) -> dict:
    """Current state of a line for a ``LINE_CHANGED`` conflict (camelCase, JSON-safe)."""
    return {
        "lineId": str(line.id),
        "status": str(line.line_status),
        "price": float(line.price),
        "unitPrice": float(line.unit_price),
        "version": line.version,
    }


class BookingLineService:
    def __init__(
        self,
        session: Session,
        *,
        photos: LinePhotos | None = None,
        notifier: OwnerNotifier | None = None,
        progress: ServiceProgressService | None = None,
        app_base_url: str = "",
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._photos = photos
        self._notifier = notifier
        self._progress = progress or ServiceProgressService(session)
        self._app_base_url = app_base_url.rstrip("/")
        self._clock = clock

    # ── Tier 1: package lines at booking time (no commit) ───────────────
    def snapshot_package(
        self,
        booking: Booking,
        vehicle: UserVehicle,
        workshop: Workshop,
        *,
        selected_item_codes: set[str] | None = None,
    ) -> list[BookingLine]:
        """Copy the milestone estimate into PACKAGE lines, priced as of the booking date."""
        if booking.odo_milestone is None or not vehicle.external_model_id:
            return []
        rule = self._db.exec(
            select(MaintenanceRule).where(
                MaintenanceRule.model_id == vehicle.external_model_id,
                MaintenanceRule.odo_milestone == booking.odo_milestone,
            )
        ).first()
        if rule is None:
            # D9 — still book; the workshop quotes at the counter, every item is an extra.
            logger.warning(
                "booking_line.no_rule",
                extra={
                    "booking_id": str(booking.id),
                    "model_id": vehicle.external_model_id,
                    "odo_milestone": booking.odo_milestone,
                },
            )
            return []

        on_booking_day = datetime.combine(booking.booking_date, time(12), tzinfo=TZ_VN)
        estimator = CostEstimationService(
            self._db, SimpleTextLocationFinder(), lambda _v: None, clock=lambda: on_booking_day
        )
        estimate = estimator.estimate(vehicle, (booking.odo_milestone, rule.month_milestone), workshop)
        if estimate.status != EstimateStatus.READY.value:
            return []
        if selected_item_codes is not None:
            available_codes = {item.item_code for item in estimate.items}
            if not selected_item_codes or not selected_item_codes.issubset(available_codes):
                from src.modules.booking.errors import MaintenancePackageChangedError

                raise MaintenancePackageChangedError()
            estimate.items = [item for item in estimate.items if item.item_code in selected_item_codes]
        price_rows = estimator.effective_price_rows(
            workshop.id, vehicle.external_model_id, [i.item_code for i in estimate.items], booking.booking_date
        )
        rule_ids = [i.maintenance_rule_id for i in estimate.items]
        safety_rules = set(
            self._db.exec(
                select(MaintenanceRule.id).where(
                    MaintenanceRule.id.in_(rule_ids), MaintenanceRule.is_safety_critical.is_(True)
                )
            ).all()
        )
        lines = []
        for item in estimate.items:
            row = price_rows.get(item.item_code) if item.price_source == "WORKSHOP_PRICE" else None
            line = BookingLine(
                booking_id=booking.id,
                kind=LineKind.PACKAGE,
                line_status=package_status(item.price_source, item.covered),
                item_code=item.item_code,
                item_name=item.item_name,
                maintenance_rule_id=item.maintenance_rule_id,
                service_price_id=row.id if row else None,
                price_source=item.price_source,
                unit_price=item.price,
                is_covered_by_warranty=item.covered,
                is_safety_critical=item.maintenance_rule_id in safety_rules,
                # Wall clock, not now(): lines of one transaction keep their order.
                created_at=datetime.now(UTC),
            )
            self._db.add(line)
            lines.append(line)
        booking.estimated_cost = sum((item.price for item in estimate.items), Decimal(0))
        self._db.add(booking)
        self._db.flush()
        return lines

    # ── reads ───────────────────────────────────────────────────────────
    def owned_booking(self, user: VehicleUser, booking_id: UUID) -> Booking:
        booking = self._db.get(Booking, booking_id)
        if booking is None or booking.user_id != user.user_id:
            raise errors.BookingNotFoundError()  # never reveal another owner's booking
        vehicle = self._db.get(UserVehicle, booking.user_vehicle_id)
        if vehicle is None or vehicle.user_id != user.user_id:
            raise errors.BookingNotFoundError()
        return booking

    def workshop_booking(self, workshop: Workshop, booking_id: UUID) -> Booking:
        booking = self._db.get(Booking, booking_id)
        if booking is None or booking.workshop_id != workshop.id:
            raise errors.BookingNotFoundError()
        return booking

    def view(self, booking: Booking) -> schemas.LinesOut:
        lines = lines_of(self._db, booking.id) if booking.pricing_flow == PricingFlow.TWO_TIER else []
        photos = self._photos_by_line([line.id for line in lines])
        urls = self._photos.urls([p.storage_key for ps in photos.values() for p in ps]) if self._photos else {}
        two_tier = booking.pricing_flow == PricingFlow.TWO_TIER
        has_package = any(line.kind == LineKind.PACKAGE for line in lines)
        open_ = booking.status in DECIDABLE_STATUSES
        now = self._clock()
        return schemas.LinesOut(
            booking_id=booking.id,
            booking_status=booking.status.value.upper(),
            pricing_flow=str(booking.pricing_flow),
            package_notice=PACKAGE_NO_RULE_NOTICE if two_tier and not has_package else None,
            lines=[self._line_out(line, photos.get(line.id, []), urls, open_=open_, now=now) for line in lines],
            current_total=billable_total(lines),
            total_if_all_approved=total_if_all_approved(lines),
            pending_decision_count=sum(1 for line in lines if line.line_status == LineStatus.PROPOSED),
            unconfirmed_count=start_block(lines),
            blocked_actions=self.blocked_actions(booking, lines),
        )

    def blocked_actions(
        self, booking: Booking, lines: list[BookingLine] | None = None
    ) -> list[schemas.BlockedActionOut]:
        """re-review OV9 — why START / COMPLETE are disabled on the board."""
        if booking.pricing_flow != PricingFlow.TWO_TIER:
            return []
        lines = lines if lines is not None else lines_of(self._db, booking.id)
        out = []
        if booking.status == S.CHECKED_IN and (n := start_block(lines)):
            out.append(
                schemas.BlockedActionOut(
                    action="START", reason_code="BOOKING_LINES_UNCONFIRMED", message=f"Còn {n} dòng chưa xác nhận giá"
                )
            )
        if booking.status == S.IN_PROGRESS and (n := complete_block(lines)):
            out.append(
                schemas.BlockedActionOut(
                    action="COMPLETE", reason_code="BOOKING_LINES_UNSETTLED", message=f"Còn {n} hạng mục chờ chốt giá"
                )
            )
        return out

    def _photos_by_line(self, line_ids: list[UUID]) -> dict[UUID, list[BookingLinePhoto]]:
        if not line_ids:
            return {}
        out: dict[UUID, list[BookingLinePhoto]] = {}
        for photo in self._db.exec(
            select(BookingLinePhoto)
            .where(BookingLinePhoto.line_id.in_(line_ids))
            .order_by(BookingLinePhoto.created_at, BookingLinePhoto.id)
        ).all():
            out.setdefault(photo.line_id, []).append(photo)
        return out

    @staticmethod
    def _line_out(
        line: BookingLine, photos: list[BookingLinePhoto], urls: dict[str, str], *, open_: bool, now: datetime
    ) -> schemas.LineOut:
        due = reply_due_at(line)
        return schemas.LineOut(
            line_id=line.id,
            kind=str(line.kind),
            status=str(line.line_status),
            item_code=line.item_code,
            item_name=line.item_name,
            unit_price=line.unit_price,
            confirmed_price=line.confirmed_price,
            price=line.price,
            price_source=line.price_source,
            price_label=price_label(line),
            is_covered_by_warranty=line.is_covered_by_warranty,
            is_safety_critical=line.is_safety_critical,
            reason=line.reason,
            version=line.version,
            confirmed_at=line.confirmed_at,
            decided_at=line.decided_at,
            decided_via=line.decided_via,
            phone_confirmed_by=line.phone_confirmed_by,
            disputed_at=line.disputed_at,
            can_dispute=open_ and line.decided_via == DECIDED_VIA_PHONE,
            reply_due_at=due,
            call_owner=open_ and due is not None and now >= due,
            created_at=line.created_at,
            photos=[schemas.LinePhotoOut(photo_id=p.id, url=urls.get(p.storage_key)) for p in photos],
        )

    # ── shared write guards ─────────────────────────────────────────────
    def _lock_two_tier(self, booking: Booking, allowed: tuple[BookingStatus, ...]) -> Booking:
        if booking.pricing_flow != PricingFlow.TWO_TIER:
            raise errors.NotTwoTierError()
        locked = lock_booking(self._db, booking.id)
        if locked.status not in allowed:
            raise errors.BookingStatusInvalidError(locked.status.value)
        return locked

    def _line(self, booking: Booking, line_id: UUID) -> BookingLine:
        line = self._db.get(BookingLine, line_id)
        if line is None or line.booking_id != booking.id:
            raise errors.LineNotFoundError()
        self._db.refresh(line)
        return line

    @staticmethod
    def _expect(line: BookingLine, status: LineStatus, version: int) -> None:
        if line.line_status != status or line.version != version:
            raise errors.LineChangedError(line_snapshot(line))

    @staticmethod
    def _optional_reason(reason: str | None) -> str | None:
        reason = (reason or "").strip() or None
        if reason is not None and len(reason) > REASON_MAX:
            raise errors.ReasonRequiredError()
        return reason

    def _stage_allows_extra(self, booking: Booking) -> None:
        stage = self._progress.current_stage(booking, self._progress.entries(booking.id))
        if stage not in EXTRA_STAGES:
            raise errors.StageNotAllowedError(stage.value if stage else None)

    # ── check-in: the workshop confirms reference prices ───────────────
    async def confirm_package(
        self,
        owner: WorkshopOwner,
        workshop: Workshop,
        booking_id: UUID,
        line_id: UUID,
        req: schemas.ConfirmPackageRequest,
    ) -> schemas.LinesOut:
        booking = self._lock_two_tier(self.workshop_booking(workshop, booking_id), (S.CHECKED_IN,))
        line = self._line(booking, line_id)
        if line.kind != LineKind.PACKAGE:
            raise errors.LineNotFoundError()
        self._expect(line, LineStatus.PENDING_CONFIRM, req.expected_version)
        self._set_package_price(line, owner, Decimal(req.price), req.reason)
        self._db.commit()
        await self._notify_line(booking, workshop, line)
        return self.view(booking)

    def _set_package_price(self, line: BookingLine, owner: WorkshopOwner, price: Decimal, reason: str | None) -> None:
        """≤ reference → CONFIRMED (reason optional); > reference → PROPOSED (reason required)."""
        now = self._clock()
        if price > line.unit_price:
            if not reason_valid(reason):
                raise errors.ReasonRequiredError("A reason of 10-500 characters is required to raise a price.")
            line.line_status = LineStatus.PROPOSED
            line.reason = (reason or "").strip()
            line.proposed_by = owner.id
            line.asked_at = now
        else:
            line.line_status = LineStatus.CONFIRMED
            line.reason = self._optional_reason(reason)
        line.confirmed_price = price
        line.confirmed_by = owner.id
        line.confirmed_at = now
        line.version += 1
        self._db.add(line)

    # ── tier 2: extras ──────────────────────────────────────────────────
    def sign_photo_upload(self, workshop: Workshop, booking_id: UUID, content_type: str):
        booking = self.workshop_booking(workshop, booking_id)
        if booking.pricing_flow != PricingFlow.TWO_TIER:
            raise errors.NotTwoTierError()
        if booking.status != S.IN_PROGRESS:
            raise errors.BookingStatusInvalidError(booking.status.value)
        if self._photos is None:
            raise errors.ServiceUnavailableError()
        return self._photos.sign_upload(booking.id, content_type)

    async def propose_extra(
        self,
        owner: WorkshopOwner,
        workshop: Workshop,
        booking_id: UUID,
        req: schemas.ProposeExtraRequest,
    ) -> schemas.LinesOut:
        booking = self._lock_two_tier(self.workshop_booking(workshop, booking_id), (S.IN_PROGRESS,))
        self._stage_allows_extra(booking)
        if not reason_valid(req.reason):
            raise errors.ReasonRequiredError()
        name, code, rule_id, safety = self._extra_item(booking, req)
        photos = []
        if req.photo_keys:
            if self._photos is None:
                raise errors.ServiceUnavailableError()
            photos = self._photos.validate(booking.id, req.photo_keys)

        line = BookingLine(
            booking_id=booking.id,
            kind=LineKind.EXTRA,
            line_status=LineStatus.PROPOSED,
            item_code=code,
            item_name=name,
            maintenance_rule_id=rule_id,
            unit_price=Decimal(req.price),
            is_safety_critical=safety,
            reason=req.reason.strip(),
            proposed_by=owner.id,
            asked_at=self._clock(),
            created_at=datetime.now(UTC),
        )
        self._db.add(line)
        self._db.flush()
        for p in photos:
            self._db.add(
                BookingLinePhoto(
                    line_id=line.id, storage_key=p.key, content_type=p.content_type, size_bytes=p.size_bytes
                )
            )
        self._db.commit()
        logger.info(
            "booking_line.extra_proposed",
            extra={"booking_id": str(booking.id), "line_id": str(line.id), "photos": len(photos)},
        )
        await self._notify_line(booking, workshop, line)
        return self.view(booking)

    def _extra_item(
        self, booking: Booking, req: schemas.ProposeExtraRequest
    ) -> tuple[str, str | None, UUID | None, bool]:
        """(name, code, rule id, safety) — a catalog item of the model, or free text."""
        if req.item_code:
            vehicle = self._db.get(UserVehicle, booking.user_vehicle_id)
            rule = self._db.exec(
                select(MaintenanceRule).where(
                    MaintenanceRule.model_id == (vehicle.external_model_id if vehicle else None),
                    MaintenanceRule.item_code == req.item_code,
                )
            ).first()
            if rule is None:
                raise errors.InvalidRequestError("Unknown item for this vehicle model.", details={"field": "itemCode"})
            return rule.item_name, rule.item_code, rule.id, rule.is_safety_critical or req.is_safety_critical
        name = (req.item_name or "").strip()
        if not name:
            raise errors.InvalidRequestError("Enter the item name.", details={"field": "itemName"})
        return name, None, None, req.is_safety_critical

    async def edit_line(
        self,
        owner: WorkshopOwner,
        workshop: Workshop,
        booking_id: UUID,
        line_id: UUID,
        req: schemas.EditLineRequest,
    ) -> schemas.LinesOut:
        """Change a PROPOSED line; the new version is sent to the owner again."""
        booking = self._lock_two_tier(self.workshop_booking(workshop, booking_id), DECIDABLE_STATUSES)
        line = self._line(booking, line_id)
        self._expect(line, LineStatus.PROPOSED, req.expected_version)
        if line.kind == LineKind.PACKAGE:
            self._set_package_price(line, owner, Decimal(req.price), req.reason)
        else:
            if not reason_valid(req.reason):
                raise errors.ReasonRequiredError()
            line.unit_price = Decimal(req.price)
            line.reason = (req.reason or "").strip()
            if req.item_name is not None and line.item_code is None:
                if not req.item_name.strip():
                    raise errors.InvalidRequestError("Enter the item name.", details={"field": "itemName"})
                line.item_name = req.item_name.strip()
            if req.is_safety_critical is not None and line.item_code is None:
                line.is_safety_critical = req.is_safety_critical
            line.proposed_by = owner.id
            line.asked_at = self._clock()
            line.version += 1
            self._db.add(line)
        self._db.commit()
        await self._notify_line(booking, workshop, line)
        return self.view(booking)

    def withdraw(
        self, workshop: Workshop, booking_id: UUID, line_id: UUID, req: schemas.WithdrawRequest
    ) -> schemas.LinesOut:
        booking = self._lock_two_tier(self.workshop_booking(workshop, booking_id), DECIDABLE_STATUSES)
        line = self._line(booking, line_id)
        if line.kind != LineKind.EXTRA:
            raise errors.InvalidRequestError("Only extra items can be withdrawn.")
        self._expect(line, LineStatus.PROPOSED, req.expected_version)
        line.line_status = LineStatus.WITHDRAWN
        line.version += 1
        self._db.add(line)
        self._db.commit()
        return self.view(booking)

    # ── the owner's decision (HITL) ─────────────────────────────────────
    def decide(
        self, user: VehicleUser, booking_id: UUID, line_id: UUID, req: schemas.DecideRequest
    ) -> schemas.LinesOut:
        booking = self._lock_two_tier(self.owned_booking(user, booking_id), DECIDABLE_STATUSES)
        line = self._line(booking, line_id)
        declining = req.decision == schemas.Decision.DECLINE
        if declining and line.is_safety_critical and not req.confirm_safety and line.line_status in UNSETTLED:
            raise errors.SafetyConfirmationRequiredError()
        result = self._db.execute(
            update(BookingLine)
            .where(
                BookingLine.id == line.id,
                BookingLine.booking_id == booking.id,
                BookingLine.line_status == LineStatus.PROPOSED,
                BookingLine.version == req.seen_version,
            )
            .values(
                line_status=LineStatus.DECLINED if declining else LineStatus.APPROVED,
                decided_by=user.user_id,
                decided_at=self._clock(),
                decided_via=DECIDED_VIA_APP,
                version=BookingLine.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self._db.rollback()
            raise errors.LineChangedError(line_snapshot(self._line(booking, line_id)))
        self._db.commit()
        logger.info(
            "booking_line.decided",
            extra={"booking_id": str(booking.id), "line_id": str(line.id), "decision": req.decision.value},
        )
        return self.view(booking)

    # ── decisions by phone (TODOS P2, concern R2-2) ─────────────────────
    async def record_phone_decision(
        self,
        owner: WorkshopOwner,
        workshop: Workshop,
        booking_id: UUID,
        line_id: UUID,
        req: schemas.PhoneDecisionRequest,
    ) -> schemas.LinesOut:
        """The owner answered by phone: same compare-and-set as ``decide``, then tell the owner."""
        booking = self._lock_two_tier(self.workshop_booking(workshop, booking_id), DECIDABLE_STATUSES)
        line = self._line(booking, line_id)
        declining = req.decision == schemas.Decision.DECLINE
        if declining and line.is_safety_critical and not req.confirm_safety and line.line_status in UNSETTLED:
            raise errors.SafetyConfirmationRequiredError()
        result = self._db.execute(
            update(BookingLine)
            .where(
                BookingLine.id == line.id,
                BookingLine.booking_id == booking.id,
                BookingLine.line_status == LineStatus.PROPOSED,
                BookingLine.version == req.seen_version,
            )
            .values(
                line_status=LineStatus.DECLINED if declining else LineStatus.APPROVED,
                decided_by=None,
                decided_at=self._clock(),
                decided_via=DECIDED_VIA_PHONE,
                phone_confirmed_by=req.confirmed_by_name,
                recorded_by=owner.id,
                version=BookingLine.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self._db.rollback()
            raise errors.LineChangedError(line_snapshot(self._line(booking, line_id)))
        self._db.commit()
        line = self._line(booking, line_id)
        logger.info(
            "booking_line.phone_decision_recorded",
            extra={"booking_id": str(booking.id), "line_id": str(line.id), "decision": req.decision.value},
        )
        await self._notify_phone_decision(booking, workshop, line)
        return self.view(booking)

    def dispute(
        self, user: VehicleUser, booking_id: UUID, line_id: UUID, req: schemas.DisputeRequest
    ) -> schemas.LinesOut:
        """ "Tôi không đồng ý": a phone decision goes back to PROPOSED for the owner to decide on the app."""
        booking = self._lock_two_tier(self.owned_booking(user, booking_id), DECIDABLE_STATUSES)
        line = self._line(booking, line_id)
        if line.decided_via != DECIDED_VIA_PHONE:
            raise errors.InvalidRequestError("Only a decision recorded by phone can be disputed.")
        now = self._clock()
        result = self._db.execute(
            update(BookingLine)
            .where(
                BookingLine.id == line.id,
                BookingLine.booking_id == booking.id,
                BookingLine.decided_via == DECIDED_VIA_PHONE,
                BookingLine.version == req.seen_version,
            )
            .values(
                line_status=LineStatus.PROPOSED,
                decided_by=None,
                decided_at=None,
                decided_via=None,
                phone_confirmed_by=None,
                disputed_at=now,
                asked_at=now,
                version=BookingLine.version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self._db.rollback()
            raise errors.LineChangedError(line_snapshot(self._line(booking, line_id)))
        self._db.commit()
        logger.info(
            "booking_line.phone_decision_disputed", extra={"booking_id": str(booking.id), "line_id": str(line.id)}
        )
        return self.view(booking)

    async def _notify_phone_decision(self, booking: Booking, workshop: Workshop, line: BookingLine) -> None:
        if self._notifier is None:
            return
        link = f"{self._app_base_url}/bookings/{booking.id}" if self._app_base_url else None
        answer = "đồng ý làm" if line.line_status == LineStatus.APPROVED else "không làm"
        body = (
            f"Xưởng {workshop.name} ghi nhận qua điện thoại ({line.phone_confirmed_by}) rằng bạn {answer} "
            f'{line.item_name} · {_vnd(line.price)}. Nếu không đúng, bấm "Tôi không đồng ý" trên phiếu '
            "trước khi xe hoàn tất."
        )
        try:
            await self._notifier.notify(
                booking.user_id, NotificationMessage(subject="Xưởng ghi nhận quyết định của bạn", body=body, link=link)
            )
        except Exception:  # noqa: BLE001 — never fail after commit; the ticket still shows the line
            logger.exception("booking_line phone notification failed for line %s v%s", line.id, line.version)

    # ── notifications (re-review OV8; text from design 10A) ─────────────
    async def _notify_line(self, booking: Booking, workshop: Workshop, line: BookingLine) -> None:
        if self._notifier is None:
            return
        link = f"{self._app_base_url}/bookings/{booking.id}" if self._app_base_url else None
        if line.line_status == LineStatus.PROPOSED:
            vehicle = self._db.get(UserVehicle, booking.user_vehicle_id)
            plate = vehicle.license_plate if vehicle and vehicle.license_plate else "của bạn"
            count = sum(1 for x in lines_of(self._db, booking.id) if x.line_status == LineStatus.PROPOSED)
            minutes = int(OWNER_REPLY_SLA.total_seconds() // 60)
            body = (
                f"Xưởng {workshop.name} đề xuất {count} hạng mục thêm cho xe {plate}. "
                f"Chưa có trả lời sau {minutes} phút, xưởng sẽ gọi cho bạn. Chỉ làm khi bạn đồng ý."
            )
            subject = "Cần bạn quyết định"
        elif line.line_status == LineStatus.CONFIRMED:
            body = f"Xưởng {workshop.name} đã xác nhận giá {line.item_name}: {_vnd(line.price)}."
            subject = "Xưởng xác nhận giá"
        else:
            return
        try:
            await self._notifier.notify(booking.user_id, NotificationMessage(subject=subject, body=body, link=link))
        except Exception:  # noqa: BLE001 — never fail after commit; the ticket card still shows the line
            logger.exception("booking_line notification failed for line %s v%s", line.id, line.version)
