"""Demo account — the manufacturer side of EV Care's shared "Dùng thử ngay" account.

One owner (``OWN-DEMO``) with three vehicles, created on every startup and after
``/admin/reset`` whatever the startup data (dump or built-in seed):

- ``VEH-DEMO-1`` VF3 Eco (MDL-09): young, low ODO, far from its first service;
- ``VEH-DEMO-2`` VF8 Eco (MDL-05): serviced at 15.000 km, now past 30.000 km (overdue);
- ``VEH-DEMO-3`` VF Wild Plus (MDL-08): 300 km before its first service (10.000 km / 6 months
  for this model in EV Care's maintenance rules), so due soon.

Dates are relative to today so the urgency of each vehicle holds; EV Care resets the
account (``POST /admin/demo-owner/reset``) every 48 h, which also refreshes the dates.

``MOCK_DEMO_OWNER_EMAIL`` must match EV Care's ``DEMO_ACCOUNT_EMAIL``; set it to an
empty string to turn the demo owner off.
"""

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from .dev_accounts import _add_months
from .models import (
    DataSource,
    MaintenanceSchedule,
    Owner,
    ServiceCenter,
    ServiceHistory,
    Vehicle,
    VehicleModel,
    VehicleUsage,
    Warranty,
    WarrantyClaim,
    WarrantyPolicy,
    WarrantyStatus,
)

logger = logging.getLogger("uvicorn.error")

EMAIL_ENV = "MOCK_DEMO_OWNER_EMAIL"
DEFAULT_EMAIL = "demo@evcare.invalid"
OWNER_ID = "OWN-DEMO"
NATIONAL_ID = "079299990001"


@dataclass(frozen=True)
class DemoVehicle:
    vehicle_id: str
    vin: str
    license_plate: str
    model_id: str
    color: str
    age_days: int
    current_km: int
    battery_soh: float
    # (milestone km, km at service, days after manufacture) of past periodic services.
    services: tuple[tuple[int, int, int], ...] = ()


VEHICLES: tuple[DemoVehicle, ...] = (
    DemoVehicle("VEH-DEMO-1", "DEMOVF3EC00000001", "30K-999.01", "MDL-09", "Vàng", 150, 4_200, 99.5),
    DemoVehicle(
        "VEH-DEMO-2",
        "DEMOVF8EC00000002",
        "30K-999.02",
        "MDL-05",
        "Xám",
        900,
        31_200,
        96.0,
        services=((15_000, 15_100, 380),),
    ),
    DemoVehicle("VEH-DEMO-3", "DEMOVFWLD00000003", "30K-999.03", "MDL-08", "Xanh dương", 120, 9_700, 99.5),
)


def demo_owner_email() -> str:
    return os.getenv(EMAIL_ENV, DEFAULT_EMAIL).strip().lower()


def ensure_demo_owner(session: Session, *, reset: bool = False, today: date | None = None) -> bool:
    """Create the demo owner and vehicles when missing (``reset`` recreates them). True when written."""
    email = demo_owner_email()
    if not email:
        return False
    today = today or date.today()
    if reset:
        _delete_demo_owner(session)
    elif session.get(Owner, OWNER_ID) is not None:
        return False

    models = {m.model_id for m in session.exec(select(VehicleModel)).all()}
    centers = sorted(session.exec(select(ServiceCenter)).all(), key=lambda c: c.center_id)
    missing = sorted({v.model_id for v in VEHICLES} - models)
    if missing or not centers:
        logger.warning("Demo owner skipped: missing models %s or no service center", missing)
        return False
    clash = session.exec(
        select(Owner.owner_id).where((Owner.email == email) | (Owner.national_id == NATIONAL_ID))
    ).first()
    if clash is not None:
        logger.warning("Demo owner skipped: email %s or national id already belongs to %s", email, clash)
        return False

    session.add(
        Owner(
            owner_id=OWNER_ID,
            full_name="Khách Dùng Thử",
            phone="0900000999",
            email=email,
            national_id=NATIONAL_ID,
        )
    )
    policies = session.exec(select(WarrantyPolicy)).all()
    schedules = {(s.model_id, s.milestone_km): s for s in session.exec(select(MaintenanceSchedule)).all()}
    for spec in VEHICLES:
        mfg = today - timedelta(days=spec.age_days)
        session.add(
            Vehicle(
                vehicle_id=spec.vehicle_id,
                vin=spec.vin,
                model_id=spec.model_id,
                current_owner_id=OWNER_ID,
                color=spec.color,
                manufacture_date=mfg,
                license_plate=spec.license_plate,
            )
        )
        session.add(
            VehicleUsage(
                vehicle_id=spec.vehicle_id,
                current_km=spec.current_km,
                battery_soh=spec.battery_soh,
                data_source=DataSource.telematics,
                last_updated_at=datetime.combine(today, datetime.min.time()).replace(hour=8),
            )
        )
        for policy in (p for p in policies if p.model_id == spec.model_id):
            end = _add_months(mfg, policy.duration_months)
            session.add(
                Warranty(
                    warranty_id=f"WRT-{spec.vehicle_id}-{policy.policy_id}",
                    vehicle_id=spec.vehicle_id,
                    policy_id=policy.policy_id,
                    start_date=mfg,
                    end_date=end,
                    km_limit=policy.km_limit,
                    status=WarrantyStatus.active if end > today else WarrantyStatus.expired,
                )
            )
        for milestone_km, km, days in spec.services:
            schedule = schedules.get((spec.model_id, milestone_km))
            session.add(
                ServiceHistory(
                    order_id=f"SH-{spec.vehicle_id}-{milestone_km}",
                    vehicle_id=spec.vehicle_id,
                    service_center_id=centers[0].center_id,
                    service_date=mfg + timedelta(days=days),
                    km_at_service=km,
                    items_done=schedule.description if schedule else f"Bảo dưỡng định kỳ {milestone_km:,} km",
                    is_periodic=True,
                    total_cost=900_000,
                )
            )
    session.commit()
    logger.info("Demo owner %s (%s) ready with %d vehicles", OWNER_ID, email, len(VEHICLES))
    return True


def _delete_demo_owner(session: Session) -> None:
    """Remove the demo owner and every row hanging off its vehicles (service visits added later too)."""
    ids = [v.vehicle_id for v in session.exec(select(Vehicle).where(Vehicle.current_owner_id == OWNER_ID)).all()]
    for model in (WarrantyClaim, Warranty, ServiceHistory, VehicleUsage):
        for row in session.exec(select(model).where(model.vehicle_id.in_(ids))).all():
            session.delete(row)
    session.flush()
    for row in session.exec(select(Vehicle).where(Vehicle.vehicle_id.in_(ids))).all():
        session.delete(row)
    session.flush()
    owner = session.get(Owner, OWNER_ID)
    if owner is not None:
        session.delete(owner)
    session.flush()
