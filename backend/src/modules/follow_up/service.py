"""Post-service follow-up — application services (us-041).

* ``FollowUpScheduler.on_completed`` — HOOK-FU-001, called inside the Board
  ``COMPLETE`` transaction (us-037 BR-807); never commits.
* ``FollowUpService`` — owner side: read / answer a follow-up (API-FU-01/02).
  An answer that reports a problem is recorded on the follow-up only; no
  support ticket is opened.

The send / auto-close jobs (JOB-FU-001/002) live in ``jobs.py``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from src.common.core.crm.follow_up import FollowUp, FollowUpStatus
from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.booking import Booking
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop import Workshop
from src.modules.booking.ticket import mask_plate
from src.modules.oem_integration.service import as_utc

from . import errors, schemas
from .domain import (
    Classification,
    ClassifiedBy,
    FeedbackIntent,
    apply_policy,
    classify_by_rules,
    quiet_hours_adjust,
)
from .ports import FeedbackClassifier

logger = logging.getLogger(__name__)

CLASSIFY_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class FollowUpConfig:
    delay_hours: int = 12
    response_window_hours: int = 72
    quiet_start_hour: int = 21
    quiet_end_hour: int = 8
    frontend_url: str = ""


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
        return f"{car} đã bảo dưỡng xong tại {where} ngày {booking.booking_date:%d/%m}. Xe của bạn chạy thế nào?"


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

    # API-FU-01
    def get(self, user: VehicleUser, follow_up_id: UUID) -> schemas.FollowUpOut:
        follow_up, booking = self._owned(user, follow_up_id)
        workshop = self._db.get(Workshop, booking.workshop_id)
        deadline = self._deadline(follow_up)
        can_respond = follow_up.status == FollowUpStatus.SENT and deadline is not None and self._clock() <= deadline
        response = None
        if follow_up.rating is not None and follow_up.responded_at is not None:
            response = schemas.ResponseOut(
                rating=follow_up.rating,
                comment=follow_up.customer_response,
                responded_at=follow_up.responded_at,
            )
        outcome = None
        if follow_up.closed_reason == "PROCESSED":
            # Safety is not stored; the keyword rules on the saved answer tell it again.
            safety = (
                follow_up.has_issue
                and classify_by_rules(follow_up.rating, follow_up.customer_response, by=ClassifiedBy.RULES).safety
            )
            outcome = schemas.OutcomeOut(has_issue=follow_up.has_issue, safety_advice=safety)
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
                    "Cảm ơn bạn đã phản hồi. Chúng mình đã ghi nhận vấn đề bạn gặp. "
                    f"Nếu cần hỗ trợ, bạn hãy liên hệ xưởng {where}" + (f" qua số {hotline}." if hotline else ".")
                    if result.has_issue
                    else "Cảm ơn bạn đã phản hồi!"
                ),
                safety_message=(
                    "Nếu xe có dấu hiệu bất thường khi vận hành, bạn nên dừng xe và liên hệ "
                    f"xưởng ngay: {hotline or where}."
                    if result.safety
                    else None
                ),
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
