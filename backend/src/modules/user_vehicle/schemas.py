"""User-vehicle module — response schemas (camelCase JSON, ``{"data": ...}`` envelope).

Shapes follow ``docs/specs/sprint-2/api/us-017-sprint-2-spec.api.md`` §C.5, §C.6.
"""

from __future__ import annotations

import datetime as dt
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, protected_namespaces=())


# ── Shared blocks ─────────────────────────────────────────────────────────
class OdometerOut(CamelModel):
    odo_km: int
    recorded_at: datetime
    is_stale: bool
    data_source: str = "OEM"


class MilestoneItemOut(CamelModel):
    item_code: str
    item_name: str
    is_covered_by_warranty: bool


class NextMilestoneOut(CamelModel):
    odo_milestone_km: int
    month_milestone: int
    label: str
    due_date: date
    is_recurring: bool
    items: list[MilestoneItemOut]


class LastServiceOut(CamelModel):
    type: str
    # ``dt.date``: the field name ``date`` would shadow the ``date`` type.
    date: dt.date
    odo_km: int | None = None


class ThresholdsOut(CamelModel):
    due_soon_km: int
    due_soon_days: int


class MaintenanceStatusOut(CamelModel):
    user_vehicle_id: UUID
    due_status: str
    due_reason: str | None = None
    calculation_basis: str | None = None
    unknown_reason: str | None = None
    next_milestone: NextMilestoneOut | None = None
    remaining_km: int | None = None
    remaining_days: int | None = None
    odometer: OdometerOut | None = None
    last_service: LastServiceOut | None = None
    thresholds: ThresholdsOut
    oem_synced_at: datetime | None = None
    calculated_at: datetime


# ── API-VEH-001 ───────────────────────────────────────────────────────────
class VehicleSummaryOut(CamelModel):
    user_vehicle_id: UUID
    model_name: str | None = None
    trim: str | None = None
    license_plate: str
    color: str | None = None


# ── API-VEH-002 ───────────────────────────────────────────────────────────
class WarrantyOut(CamelModel):
    component: str
    start_date: date
    end_date: date
    km_limit: int | None = None
    is_active: bool


class ProfileLastServiceOut(CamelModel):
    service_date: date
    odo_km: int | None = None
    source: str
    center_name: str | None = None


class VehicleProfileOut(CamelModel):
    user_vehicle_id: UUID
    vin_masked: str
    license_plate: str
    model_id: str | None = None
    model_name: str | None = None
    trim: str | None = None
    color: str | None = None
    production_year: int | None = None
    manufacture_date: date | None = None
    battery_capacity_kwh: float | None = None
    motor_power_kw: float | None = None
    warranties: list[WarrantyOut]
    odometer: OdometerOut | None = None
    last_service: ProfileLastServiceOut | None = None
    oem_synced_at: datetime | None = None


# ── Envelopes ─────────────────────────────────────────────────────────────
class VehicleListEnvelope(CamelModel):
    data: list[VehicleSummaryOut]


class VehicleProfileEnvelope(CamelModel):
    data: VehicleProfileOut


class MaintenanceStatusEnvelope(CamelModel):
    data: MaintenanceStatusOut


# ── API-VEH-005 service history ────────────────────────────────────────────
class ServiceRecordWorkshopOut(CamelModel):
    workshop_id: UUID | None = None
    name: str


class ServiceRecordOut(CamelModel):
    record_id: UUID
    source: str  # "OEM" (manufacturer sync) | "EV_CARE" (completed on the Workshop Board)
    service_date: date
    odo_km: int | None = None
    is_periodic: bool
    items_done: str | None = None
    workshop: ServiceRecordWorkshopOut | None = None
    booking_id: UUID | None = None
    booking_code: str | None = None
    actual_cost: Decimal | None = None


class ServiceRecordListOut(CamelModel):
    items: list[ServiceRecordOut]


class ServiceRecordListEnvelope(CamelModel):
    data: ServiceRecordListOut
