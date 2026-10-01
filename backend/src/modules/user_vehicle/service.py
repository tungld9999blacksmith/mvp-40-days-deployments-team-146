"""User-vehicle module — application service (API-VEH-001..003, TOOL-VEH-001).

Reads only the database: manufacturer data arrives through the sync job
(``modules/oem_integration``), so viewing a vehicle never calls the OEM and
never fails because the OEM is down (FEAT-VEH-001 EF-001).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.vehicle import (
    OemSyncTrigger,
    ServiceRecordSource,
    UserVehicle,
    VehicleLinkStatus,
    VehicleOdometerReading,
    VehicleOemSync,
    VehicleServiceRecord,
    VehicleVerificationStatus,
)
from src.common.core.workshop.workshop import Workshop
from src.modules.oem_integration.ports import SyncScheduler
from src.modules.oem_integration.service import as_utc, utc_now
from src.modules.vehicle_owner_onboarding.domain import VehicleWarranty

from . import errors, schemas
from .domain import (
    DueConfig,
    DueResult,
    LastService,
    LastServiceType,
    Odometer,
    RuleItem,
    UnknownReason,
    calculate_due_status,
    today_vn,
    unknown,
)

logger = logging.getLogger(__name__)

# API-VEH-003: re-enqueue the initial sync when it seems lost.
SELF_HEAL_AFTER = timedelta(minutes=5)


def mask_vin(vin: str) -> str:
    """Keep the first 6 and last 5 characters (``LVVDB1******00001``)."""
    if len(vin) <= 11:
        return vin
    return vin[:6] + "*" * (len(vin) - 11) + vin[-5:]


class UserVehicleService:
    def __init__(
        self,
        session: Session,
        scheduler: SyncScheduler,
        *,
        config: DueConfig = DueConfig(),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db = session
        self._scheduler = scheduler
        self._config = config
        self._clock = clock

    # ------------------------------------------------------------ access
    def list_vehicles(self, user: VehicleUser) -> list[schemas.VehicleSummaryOut]:
        """API-VEH-001 — verified, active vehicles of the account."""
        vehicles = self._db.exec(
            select(UserVehicle)
            .where(
                UserVehicle.user_id == user.user_id,
                UserVehicle.verification_status == VehicleVerificationStatus.VERIFIED,
                UserVehicle.link_status == VehicleLinkStatus.ACTIVE,
            )
            .order_by(UserVehicle.created_at)
        ).all()
        return [
            schemas.VehicleSummaryOut(
                user_vehicle_id=v.id,
                model_name=v.model_name,
                trim=v.trim,
                license_plate=v.license_plate,
                color=v.color,
            )
            for v in vehicles
        ]

    def get_owned_active_vehicle(self, user: VehicleUser, user_vehicle_id: UUID) -> UserVehicle:
        """Guard of API-VEH-002/003 (API spec §C.2)."""
        vehicle = self._db.get(UserVehicle, user_vehicle_id)
        if vehicle is None or vehicle.user_id != user.user_id:
            raise errors.VehicleNotFoundError()
        if (
            vehicle.verification_status != VehicleVerificationStatus.VERIFIED
            or vehicle.link_status != VehicleLinkStatus.ACTIVE
        ):
            raise errors.VehicleNotActiveError()
        return vehicle

    # ----------------------------------------------------------- profile
    def get_profile(self, vehicle: UserVehicle) -> schemas.VehicleProfileOut:
        """API-VEH-002."""
        odometer = self._effective_odometer(vehicle.id)
        today = today_vn(self._clock())
        warranties = self._db.exec(
            select(VehicleWarranty)
            .where(VehicleWarranty.user_vehicle_id == vehicle.id)
            .order_by(VehicleWarranty.component)
        ).all()

        last = self._latest_service_record(vehicle.id)
        last_out = None
        if last is not None:
            center_name = (
                self._db.get(Workshop, last.workshop_id).name if last.workshop_id else None
            )
            last_out = schemas.ProfileLastServiceOut(
                service_date=last.service_date,
                odo_km=last.odo_km,
                source="OEM" if last.source == ServiceRecordSource.OEM else "EV_CARE",
                center_name=center_name,
            )

        sync = self._db.get(VehicleOemSync, vehicle.id)
        return schemas.VehicleProfileOut(
            user_vehicle_id=vehicle.id,
            vin_masked=mask_vin(vehicle.vin),
            license_plate=vehicle.license_plate,
            model_id=vehicle.external_model_id,
            model_name=vehicle.model_name,
            trim=vehicle.trim,
            color=vehicle.color,
            production_year=vehicle.production_year,
            manufacture_date=vehicle.manufacture_date,
            battery_capacity_kwh=_to_float(vehicle.battery_capacity_kwh),
            motor_power_kw=_to_float(vehicle.motor_power_kw),
            warranties=[
                schemas.WarrantyOut(
                    component=w.component.name,
                    start_date=w.start_date,
                    end_date=w.end_date,
                    km_limit=w.km_limit,
                    is_active=w.end_date >= today
                    and (w.km_limit is None or odometer is None or odometer.odo_km <= w.km_limit),
                )
                for w in warranties
            ],
            odometer=_odometer_out(odometer),
            last_service=last_out,
            oem_synced_at=_synced_at(sync),
        )

    # ---------------------------------------------------- due status
    def get_maintenance_status(self, vehicle: UserVehicle) -> schemas.MaintenanceStatusOut:
        """API-VEH-003 / TOOL-VEH-001."""
        now = self._clock()
        sync = self._db.get(VehicleOemSync, vehicle.id)
        result = self.calculate(vehicle, now=now, sync=sync)
        if result.unknown_reason == UnknownReason.OEM_DATA_NOT_SYNCED:
            self._self_heal(vehicle.id, sync, now)
        return _status_out(vehicle.id, result, self._config, sync, now)

    def calculate(
        self,
        vehicle: UserVehicle,
        *,
        now: datetime | None = None,
        sync: VehicleOemSync | None = None,
    ) -> DueResult:
        """RM-401 inputs from the DB -> ``calculate_due_status`` (shared with F7)."""
        now = now or self._clock()
        sync = sync if sync is not None else self._db.get(VehicleOemSync, vehicle.id)
        today = today_vn(now)
        odometer = self._effective_odometer(vehicle.id, today=today)
        last_record = self._latest_service_record(vehicle.id)

        # BR-ENT-436: never compute a status before the first history sync.
        if last_record is None and (sync is None or sync.service_history_synced_at is None):
            return unknown(UnknownReason.OEM_DATA_NOT_SYNCED, odometer)

        rules = [
            RuleItem(
                r.odo_milestone,
                r.month_milestone,
                r.item_code,
                r.item_name,
                r.is_covered_by_warranty,
            )
            for r in self._db.exec(
                select(MaintenanceRule).where(
                    MaintenanceRule.model_id == vehicle.external_model_id
                )
            ).all()
        ]
        last_service = None
        if last_record is not None:
            last_service = LastService(
                LastServiceType.OEM_SERVICE_RECORD
                if last_record.source == ServiceRecordSource.OEM
                else LastServiceType.EV_CARE_SERVICE_RECORD,
                last_record.service_date,
                last_record.odo_km,
            )
        return calculate_due_status(
            rules=rules,
            purchase_date=self._purchase_date(vehicle),
            odometer=odometer,
            last_service=last_service,
            today=today,
            config=self._config,
        )

    # ----------------------------------------------------------- helpers
    def _effective_odometer(self, user_vehicle_id: UUID, *, today=None) -> Odometer | None:
        """BR-ENT-430: the highest value wins; ties -> latest measurement."""
        row = self._db.exec(
            select(VehicleOdometerReading)
            .where(VehicleOdometerReading.user_vehicle_id == user_vehicle_id)
            .order_by(
                VehicleOdometerReading.odo_km.desc(), VehicleOdometerReading.recorded_at.desc()
            )
            .limit(1)
        ).first()
        if row is None:
            return None
        today = today or today_vn(self._clock())
        recorded_at = as_utc(row.recorded_at)
        stale = (today - today_vn(recorded_at)).days > self._config.odo_stale_days
        return Odometer(odo_km=row.odo_km, recorded_at=recorded_at, is_stale=stale)

    def _latest_service_record(self, user_vehicle_id: UUID) -> VehicleServiceRecord | None:
        """BR-ENT-434: latest periodic service wins; same day -> higher km (Q-304)."""
        return self._db.exec(
            select(VehicleServiceRecord)
            .where(
                VehicleServiceRecord.user_vehicle_id == user_vehicle_id,
                VehicleServiceRecord.is_periodic.is_(True),
            )
            .order_by(
                VehicleServiceRecord.service_date.desc(),
                VehicleServiceRecord.odo_km.desc().nulls_last(),
            )
            .limit(1)
        ).first()

    def _purchase_date(self, vehicle: UserVehicle):
        """FF BR-005: earliest warranty start, else manufacture date."""
        first_warranty = self._db.exec(
            select(func.min(VehicleWarranty.start_date)).where(
                VehicleWarranty.user_vehicle_id == vehicle.id
            )
        ).one()
        if first_warranty is not None:
            return first_warranty
        if vehicle.manufacture_date is not None:
            return vehicle.manufacture_date
        # Not expected for a verified vehicle; fall back to the link date.
        return today_vn(as_utc(vehicle.verified_at or vehicle.created_at))

    def _self_heal(self, user_vehicle_id: UUID, sync: VehicleOemSync | None, now: datetime) -> None:
        if sync is not None and sync.last_attempt_at is not None:
            if now - as_utc(sync.last_attempt_at) < SELF_HEAL_AFTER:
                return
        try:
            self._scheduler.schedule(user_vehicle_id, OemSyncTrigger.INITIAL)
        except Exception:  # noqa: BLE001 — a broker outage must not fail a read
            logger.exception("could not enqueue initial OEM sync for %s", user_vehicle_id)


def _synced_at(sync: VehicleOemSync | None) -> datetime | None:
    if sync is None or sync.usage_synced_at is None:
        return None
    return as_utc(sync.usage_synced_at)


def _to_float(value) -> float | None:
    return float(value) if value is not None else None


def _odometer_out(odometer: Odometer | None) -> schemas.OdometerOut | None:
    if odometer is None:
        return None
    return schemas.OdometerOut(
        odo_km=odometer.odo_km, recorded_at=odometer.recorded_at, is_stale=odometer.is_stale
    )


def _status_out(
    user_vehicle_id: UUID,
    result: DueResult,
    config: DueConfig,
    sync: VehicleOemSync | None,
    now: datetime,
) -> schemas.MaintenanceStatusOut:
    milestone = result.next_milestone
    return schemas.MaintenanceStatusOut(
        user_vehicle_id=user_vehicle_id,
        due_status=result.due_status.value,
        due_reason=result.due_reason.value if result.due_reason else None,
        calculation_basis=result.calculation_basis.value if result.calculation_basis else None,
        unknown_reason=result.unknown_reason.value if result.unknown_reason else None,
        next_milestone=(
            schemas.NextMilestoneOut(
                odo_milestone_km=milestone.odo_milestone_km,
                month_milestone=milestone.month_milestone,
                label=milestone.label,
                due_date=milestone.due_date,
                is_recurring=milestone.is_recurring,
                items=[
                    schemas.MilestoneItemOut(
                        item_code=i.item_code,
                        item_name=i.item_name,
                        is_covered_by_warranty=i.is_covered_by_warranty,
                    )
                    for i in milestone.items
                ],
            )
            if milestone
            else None
        ),
        remaining_km=result.remaining_km,
        remaining_days=result.remaining_days,
        odometer=_odometer_out(result.odometer),
        last_service=(
            schemas.LastServiceOut(
                type=result.last_service.type.value,
                date=result.last_service.date,
                odo_km=result.last_service.odo_km,
            )
            if result.last_service
            else None
        ),
        thresholds=schemas.ThresholdsOut(
            due_soon_km=config.due_soon_km, due_soon_days=config.due_soon_days
        ),
        oem_synced_at=_synced_at(sync),
        calculated_at=now,
    )
