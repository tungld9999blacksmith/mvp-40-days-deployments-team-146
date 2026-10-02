"""Cost-estimate module — application service (API-EST-01..03, TOOL-301).

``CostEstimationService.estimate`` is the single estimate implementation: the UI
endpoints and the agent tool ``estimate_maintenance_cost`` both call it (BR-1006).
Read-only — an estimate is never stored (BR-1007).
"""

from __future__ import annotations

import logging
import time as _time
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.vehicle import UserVehicle, VehicleLinkStatus, VehicleVerificationStatus
from src.common.core.workshop import Workshop, WorkshopStatus
from src.common.core.workshop.service_price import ServicePrice
from src.modules.booking.domain import AnchorSource, LocationAnchor
from src.modules.booking.location import WorkshopLocationFinder
from src.modules.user_vehicle.domain import today_vn
from src.modules.vehicle_owner_onboarding.domain import (
    UserLocation,
    VehicleWarranty,
    WarrantyComponent,
)

from . import errors, schemas
from .domain import (
    EstimateStatus,
    RuleLine,
    WorkshopSelection,
    compute_estimate,
    warranty_state,
)

logger = logging.getLogger(__name__)

MAX_COMPARE = 3
MIN_COMPARE = 2

# Returns the F3 next milestone (km) of a vehicle, or None when UNKNOWN.
NextMilestoneFn = Callable[[UserVehicle], int | None]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class CostEstimationService:
    def __init__(
        self,
        session: Session,
        finder: WorkshopLocationFinder,
        next_milestone: NextMilestoneFn,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._db = session
        self._finder = finder
        self._next_milestone = next_milestone
        self._clock = clock

    # ── Guard (BR-1008) ─────────────────────────────────────────────────
    def get_owned_active_vehicle(self, user: VehicleUser, user_vehicle_id: UUID) -> UserVehicle:
        vehicle = self._db.get(UserVehicle, user_vehicle_id)
        if (
            vehicle is None
            or vehicle.user_id != user.user_id
            or vehicle.verification_status != VehicleVerificationStatus.VERIFIED
            or vehicle.link_status != VehicleLinkStatus.ACTIVE
        ):
            raise errors.VehicleNotFoundError()
        return vehicle

    # ── API-EST-01 ──────────────────────────────────────────────────────
    def list_milestones(self, vehicle: UserVehicle) -> schemas.MilestonesData:
        rows = self._milestone_rows(vehicle.external_model_id)
        next_km = self._next_milestone(vehicle) if rows else None
        return schemas.MilestonesData(
            model_id=vehicle.external_model_id,
            next_odo_milestone=next_km,
            milestones=[
                schemas.MilestoneOptionOut(
                    odo_milestone=km, month_milestone=months, item_count=count, is_next=km == next_km
                )
                for km, months, count in rows
            ],
        )

    def _milestone_rows(self, model_id: str | None) -> list[tuple[int, int, int]]:
        if not model_id:
            return []
        rows = self._db.exec(
            select(
                MaintenanceRule.odo_milestone,
                MaintenanceRule.month_milestone,
                func.count(),
            )
            .where(MaintenanceRule.model_id == model_id)
            .group_by(MaintenanceRule.odo_milestone, MaintenanceRule.month_milestone)
            .order_by(MaintenanceRule.odo_milestone)
        ).all()
        return [(int(km), int(months), int(count)) for km, months, count in rows]

    # ── API-EST-02 ──────────────────────────────────────────────────────
    def estimate_for_request(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        *,
        odo_milestone: int | None,
        workshop_id: UUID | None,
    ) -> schemas.EstimateData:
        """Resolve the milestone (F3) and the workshop (BR-1003), then estimate."""
        rows = self._milestone_rows(vehicle.external_model_id)
        if not rows:
            return self._no_rule(vehicle)
        milestone, is_next = self._resolve_milestone(vehicle, rows, odo_milestone)
        workshop, selected_by = self._resolve_workshop(user, workshop_id)
        return self.estimate(vehicle, milestone, workshop, selected_by=selected_by, is_next=is_next)

    def _resolve_milestone(
        self, vehicle: UserVehicle, rows: list[tuple[int, int, int]], odo_milestone: int | None
    ) -> tuple[tuple[int, int], bool]:
        valid = [km for km, _, _ in rows]
        months_by_km = {km: months for km, months, _ in rows}
        next_km = self._next_milestone(vehicle)
        if odo_milestone is None:
            # AF-1001: F3 UNKNOWN, or a recurring milestone beyond the table.
            if next_km is None or next_km not in months_by_km:
                raise errors.MilestoneRequiredError(valid)
            odo_milestone = next_km
        if odo_milestone not in months_by_km:
            raise errors.MilestoneNotFoundError(valid)
        return (odo_milestone, months_by_km[odo_milestone]), odo_milestone == next_km

    def _resolve_workshop(self, user: VehicleUser, workshop_id: UUID | None) -> tuple[Workshop, WorkshopSelection]:
        if workshop_id is not None:
            return self._active_workshop(workshop_id), WorkshopSelection.REQUEST
        # BR-1003 #1 — the preferred workshop, when still active.
        if user.preferred_workshop_id is not None:
            preferred = self._db.get(Workshop, user.preferred_workshop_id)
            if preferred is not None and preferred.status == WorkshopStatus.ACTIVE:
                return preferred, WorkshopSelection.PREFERRED
        # BR-1003 #2 — the nearest workshop to the primary location (us-029 BR-002..004).
        loc = self._db.exec(
            select(UserLocation).where(UserLocation.user_id == user.user_id, UserLocation.is_primary.is_(True))
        ).first()
        if loc is not None:
            anchor = LocationAnchor(
                AnchorSource.PROFILE,
                latitude=float(loc.latitude) if loc.latitude is not None else None,
                longitude=float(loc.longitude) if loc.longitude is not None else None,
                province=loc.province,
            )
            active = self._db.exec(select(Workshop).where(Workshop.status == WorkshopStatus.ACTIVE)).all()
            ranked, _ = self._finder.rank(anchor, list(active), preferred_workshop_id=None, limit=1)
            if ranked:
                return ranked[0].workshop, WorkshopSelection.NEAREST
        raise errors.WorkshopRequiredError()

    def _active_workshop(self, workshop_id: UUID) -> Workshop:
        workshop = self._db.get(Workshop, workshop_id)
        if workshop is None or workshop.status != WorkshopStatus.ACTIVE:
            raise errors.WorkshopNotFoundError()
        return workshop

    def estimate(
        self,
        vehicle: UserVehicle,
        milestone: tuple[int, int],
        workshop: Workshop,
        *,
        selected_by: WorkshopSelection = WorkshopSelection.REQUEST,
        is_next: bool = False,
    ) -> schemas.EstimateData:
        """BR-1001 / BR-1004 for one milestone at one workshop (shared with TOOL-301)."""
        started = _time.perf_counter()
        now = self._clock()
        today = today_vn(now)
        odo_milestone, month_milestone = milestone
        model_id = vehicle.external_model_id

        rules = self._db.exec(
            select(MaintenanceRule).where(
                MaintenanceRule.model_id == model_id,
                MaintenanceRule.odo_milestone == odo_milestone,
            )
        ).all()
        if not rules:
            return self._no_rule(vehicle)

        codes = [r.item_code for r in rules]
        prices = self._effective_prices(workshop.id, model_id, codes, today)
        state = warranty_state(self._chassis_end_date(vehicle.id), today)
        totals = compute_estimate(
            [RuleLine(r.id, r.item_code, r.item_name, r.is_covered_by_warranty, r.estimated_cost) for r in rules],
            prices,
            state,
        )
        logger.info(
            "estimate.computed",
            extra={
                "user_vehicle_id": str(vehicle.id),
                "workshop_id": str(workshop.id),
                "odo_milestone": odo_milestone,
                "status": EstimateStatus.READY.value,
                "item_count": len(totals.lines),
                "has_reference_price": totals.has_reference_price,
                "duration_ms": round((_time.perf_counter() - started) * 1000, 1),
            },
        )
        return schemas.EstimateData(
            status=EstimateStatus.READY.value,
            user_vehicle_id=vehicle.id,
            model_id=model_id,
            milestone=schemas.EstimateMilestoneOut(
                odo_milestone=odo_milestone, month_milestone=month_milestone, is_next=is_next
            ),
            workshop=schemas.EstimateWorkshopOut(
                workshop_id=workshop.id, name=workshop.name, selected_by=selected_by.value
            ),
            warranty_status=state.value,
            items=[
                schemas.EstimateItemOut(
                    maintenance_rule_id=line.maintenance_rule_id,
                    item_code=line.item_code,
                    item_name=line.item_name,
                    covered=line.covered,
                    price=line.price,
                    price_source=line.price_source.value if line.price_source else None,
                )
                for line in totals.lines
            ],
            covered_count=totals.covered_count,
            chargeable_total=totals.chargeable_total,
            has_reference_price=totals.has_reference_price,
            computed_at=now,
        )

    def _no_rule(self, vehicle: UserVehicle) -> schemas.EstimateData:
        return schemas.EstimateData(
            status=EstimateStatus.NO_RULE.value,
            user_vehicle_id=vehicle.id,
            model_id=vehicle.external_model_id,
            computed_at=self._clock(),
        )

    def _effective_prices(self, workshop_id: UUID, model_id: str, codes: list[str], today: date) -> dict[str, Decimal]:
        """BR-1004: price valid today; overlapping periods → newest ``valid_from`` + WARN."""
        rows = self._db.exec(
            select(ServicePrice).where(
                ServicePrice.workshop_id == workshop_id,
                ServicePrice.model_id == model_id,
                ServicePrice.item_code.in_(codes),
                (ServicePrice.valid_from.is_(None)) | (ServicePrice.valid_from <= today),
                (ServicePrice.valid_to.is_(None)) | (ServicePrice.valid_to >= today),
            )
        ).all()
        chosen: dict[str, ServicePrice] = {}
        for row in rows:
            current = chosen.get(row.item_code)
            if current is None:
                chosen[row.item_code] = row
                continue
            logger.warning(
                "service_price.overlap",
                extra={"workshop_id": str(workshop_id), "item_code": row.item_code},
            )
            if (row.valid_from or date.min) > (current.valid_from or date.min):
                chosen[row.item_code] = row
        return {code: row.price for code, row in chosen.items()}

    def _chassis_end_date(self, user_vehicle_id: UUID) -> date | None:
        return self._db.exec(
            select(func.max(VehicleWarranty.end_date)).where(
                VehicleWarranty.user_vehicle_id == user_vehicle_id,
                VehicleWarranty.component == WarrantyComponent.CHASSIS,
            )
        ).one()

    # ── API-EST-03 ──────────────────────────────────────────────────────
    def compare(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        *,
        odo_milestone: int | None,
        workshop_ids: list[UUID],
    ) -> schemas.CompareData:
        if len(set(workshop_ids)) != len(workshop_ids) or not (MIN_COMPARE <= len(workshop_ids) <= MAX_COMPARE):
            raise errors.InvalidRequestError(f"Provide {MIN_COMPARE}-{MAX_COMPARE} distinct workshops to compare.")
        rows = self._milestone_rows(vehicle.external_model_id)
        if not rows:
            return schemas.CompareData(estimates=[self._no_rule(vehicle)])
        milestone, is_next = self._resolve_milestone(vehicle, rows, odo_milestone)

        ok: list[schemas.EstimateData] = []
        failed: list[schemas.CompareFailureOut] = []
        for workshop_id in workshop_ids:
            try:
                workshop = self._active_workshop(workshop_id)
            except errors.CostEstimateError as exc:
                failed.append(
                    schemas.CompareFailureOut(workshop_id=workshop_id, error=schemas.CompareErrorOut(code=exc.code))
                )
                continue
            ok.append(self.estimate(vehicle, milestone, workshop, is_next=is_next))
        ok.sort(key=lambda e: e.chargeable_total if e.chargeable_total is not None else Decimal("Infinity"))
        return schemas.CompareData(estimates=[*ok, *failed])
