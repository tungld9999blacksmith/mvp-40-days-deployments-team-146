"""ServiceProgressService — detailed stages while the car is at the workshop (us-057).

Shared by the Workshop Board (API-PG-01/02 + HOOK-PG-01 inside API-WB-04) and the
owner ticket (API-PG-03). Callers resolve the booking and its ownership first.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

from src.common.core.maintenance.booking import Booking, BookingStatus
from src.common.core.maintenance.booking_status_event import BookingActorType
from src.common.core.maintenance.service_progress import ServiceProgress, ServiceStage
from src.common.core.workshop import Workshop
from src.modules.notification.channels import NotificationMessage
from src.modules.notification.owner_notifier import OwnerNotifier

from . import errors, schemas
from .domain import (
    FROZEN_STATUSES,
    NEXT_STAGES,
    NOTIFY_STAGES,
    STAGE_LABEL_VI,
    derived_stage,
    note_valid,
    owner_next_stages,
)

logger = logging.getLogger(__name__)

# HOOK-PG-01 — Board action → automatic stage.
HOOK_STAGES: dict[str, ServiceStage] = {
    "CHECK_IN": ServiceStage.CHECKED_IN,
    "START": ServiceStage.INSPECTING,
}


class ServiceProgressService:
    def __init__(
        self,
        session: Session,
        *,
        enabled: bool = True,
        notifier: OwnerNotifier | None = None,
        app_base_url: str = "",
    ) -> None:
        self._db = session
        self._enabled = enabled
        self._notifier = notifier
        self._app_base_url = app_base_url.rstrip("/")

    def ensure_enabled(self) -> None:
        if not self._enabled:
            raise errors.FeatureDisabledError()

    # ── read ────────────────────────────────────────────────────────────
    def entries(self, booking_id) -> list[ServiceProgress]:
        return list(
            self._db.exec(
                select(ServiceProgress)
                .where(ServiceProgress.booking_id == booking_id)
                .order_by(ServiceProgress.created_at, ServiceProgress.id)
            ).all()
        )

    def current_stage(self, booking: Booking, entries: list[ServiceProgress]) -> ServiceStage | None:
        return entries[-1].stage if entries else derived_stage(booking.status)

    def timeline(self, booking: Booking, *, for_workshop: bool) -> schemas.ProgressOut:
        """API-PG-01 (``for_workshop``, with ``nextStages``) and API-PG-03."""
        self.ensure_enabled()
        rows = self.entries(booking.id)
        current = self.current_stage(booking, rows)
        return schemas.ProgressOut(
            booking_id=booking.id,
            booking_status=booking.status.value.upper(),
            current_stage=current.value.upper() if current else None,
            is_frozen=booking.status in FROZEN_STATUSES,
            next_stages=(
                [s.value.upper() for s in owner_next_stages(booking.status, current)]
                if for_workshop
                else None
            ),
            entries=[
                schemas.ProgressEntryOut(
                    stage=r.stage.value.upper(),
                    note=r.note,
                    actor_type=r.actor_type.value.upper(),
                    created_at=r.created_at,
                )
                for r in rows
            ],
        )

    # ── API-PG-02 ───────────────────────────────────────────────────────
    async def append(
        self,
        booking: Booking,
        owner_id,
        *,
        stage: ServiceStage,
        note: str | None,
        expected_current: ServiceStage | None,
    ) -> schemas.ProgressOut:
        self.ensure_enabled()
        locked = self._db.exec(
            select(Booking).where(Booking.id == booking.id).with_for_update()
        ).one()
        if locked.status != BookingStatus.IN_PROGRESS:
            raise errors.BookingNotInProgressError(locked.status.value)
        current = self.current_stage(locked, self.entries(locked.id))
        if current != expected_current:
            raise errors.ProgressChangedError(current.value if current else None)
        allowed = owner_next_stages(locked.status, current)
        if stage not in allowed:
            raise errors.InvalidStageTransitionError([s.value for s in allowed])
        note = (note or "").strip() or None
        if not note_valid(stage, note):
            raise errors.NoteRequiredError()

        self._db.add(
            ServiceProgress(
                booking_id=locked.id,
                stage=stage,
                note=note,
                actor_type=BookingActorType.WORKSHOP_OWNER,
                actor_workshop_owner_id=owner_id,
                source="BOARD",
                created_at=datetime.now(UTC),
            )
        )
        self._db.commit()
        logger.info(
            "progress.appended",
            extra={"booking_id": str(locked.id), "stage": stage.value, "actor_type": "workshop_owner"},
        )
        if stage in NOTIFY_STAGES:
            await self._notify(locked, stage, note)
        return self.timeline(locked, for_workshop=True)

    # ── HOOK-PG-01 (inside the Board transaction; no commit) ────────────
    def on_booking_transition(self, booking: Booking, action: str) -> ServiceStage | None:
        stage = HOOK_STAGES.get(action)
        if not self._enabled or stage is None:
            return None
        existing = self.entries(booking.id)
        last = existing[-1].stage if existing else None
        # START may run without a CHECKED_IN row (checked in before the feature was on).
        if stage not in NEXT_STAGES[last] and not (action == "START" and last is None):
            return None  # already recorded — a repeated, idempotent Board action
        self._db.add(
            ServiceProgress(
                booking_id=booking.id,
                stage=stage,
                actor_type=BookingActorType.SYSTEM,
                source=action,
                created_at=datetime.now(UTC),
            )
        )
        return stage

    async def _notify(self, booking: Booking, stage: ServiceStage, note: str | None) -> None:
        if self._notifier is None:
            return
        workshop = self._db.get(Workshop, booking.workshop_id)
        body = f"[EV Care] Cập nhật xe tại {workshop.name if workshop else 'xưởng'}: {STAGE_LABEL_VI[stage]}."
        if note:
            body += "\n" + note[:200]
        link = f"{self._app_base_url}/bookings/{booking.id}" if self._app_base_url else None
        try:
            await self._notifier.notify(
                booking.user_id, NotificationMessage(subject="Cập nhật tiến độ", body=body, link=link)
            )
        except Exception:  # noqa: BLE001 — best effort after commit (EF-1303)
            logger.exception("progress notification failed for booking %s", booking.id)
