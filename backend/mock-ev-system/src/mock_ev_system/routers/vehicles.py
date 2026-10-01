"""API endpoints: Vehicles & Owners."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..db import get_session
from ..service import OwnerService, VehicleService

router = APIRouter(tags=["Vehicles & Owners"])


# ── Vehicles ─────────────────────────────────────────────────────────


@router.get("/vehicles", summary="Danh sách tất cả xe")
def list_vehicles(session: Session = Depends(get_session)):
    svc = VehicleService(session)
    vehicles = svc.list_vehicles()
    return [
        {
            "vehicle_id": v.vehicle_id,
            "vin": v.vin,
            "model_id": v.model_id,
            "current_owner_id": v.current_owner_id,
            "color": v.color,
            "manufacture_date": str(v.manufacture_date),
            "license_plate": v.license_plate,
        }
        for v in vehicles
    ]


@router.get("/vehicles/{vehicle_id}", summary="Chi tiết xe (kèm thông tin model & chủ xe)")
def get_vehicle(vehicle_id: str, session: Session = Depends(get_session)):
    svc = VehicleService(session)
    v = svc.get_vehicle(vehicle_id)
    if not v:
        raise HTTPException(404, f"Vehicle {vehicle_id} not found")

    result = {
        "vehicle_id": v.vehicle_id,
        "vin": v.vin,
        "color": v.color,
        "manufacture_date": str(v.manufacture_date),
        "license_plate": v.license_plate,
    }

    if v.model:
        result["model"] = {
            "model_id": v.model.model_id,
            "model_name": v.model.model_name,
            "trim": v.model.trim,
            "battery_capacity_kwh": v.model.battery_capacity_kwh,
            "motor_power_kw": v.model.motor_power_kw,
            "production_year": v.model.production_year,
        }

    if v.owner:
        result["owner"] = {
            "owner_id": v.owner.owner_id,
            "full_name": v.owner.full_name,
            "phone": v.owner.phone,
            "email": v.owner.email,
        }

    return result


@router.get(
    "/vehicles/lookup/by-vin",
    summary="Tra cứu xe theo VIN",
)
def lookup_by_vin(
    vin: str = Query(..., description="Vehicle Identification Number"),
    session: Session = Depends(get_session),
):
    svc = VehicleService(session)
    v = svc.get_vehicle_by_vin(vin)
    if not v:
        raise HTTPException(404, f"Vehicle with VIN {vin} not found")
    return {"vehicle_id": v.vehicle_id, "vin": v.vin, "license_plate": v.license_plate}


@router.get(
    "/vehicles/lookup/by-plate",
    summary="Tra cứu xe theo biển số",
)
def lookup_by_plate(
    plate: str = Query(..., description="Biển số xe"),
    session: Session = Depends(get_session),
):
    svc = VehicleService(session)
    v = svc.get_vehicle_by_plate(plate)
    if not v:
        raise HTTPException(404, f"Vehicle with plate {plate} not found")
    return {"vehicle_id": v.vehicle_id, "vin": v.vin, "license_plate": v.license_plate}


# ── Owners ───────────────────────────────────────────────────────────


@router.get("/owners", summary="Danh sách chủ xe")
def list_owners(session: Session = Depends(get_session)):
    svc = OwnerService(session)
    return [
        {
            "owner_id": o.owner_id,
            "full_name": o.full_name,
            "phone": o.phone,
            "email": o.email,
        }
        for o in svc.list_owners()
    ]


@router.get("/owners/{owner_id}", summary="Chi tiết chủ xe (kèm danh sách xe)")
def get_owner(owner_id: str, session: Session = Depends(get_session)):
    svc = OwnerService(session)
    owner = svc.get_owner(owner_id)
    if not owner:
        raise HTTPException(404, f"Owner {owner_id} not found")

    vehicles = svc.get_owner_vehicles(owner_id)
    return {
        "owner_id": owner.owner_id,
        "full_name": owner.full_name,
        "phone": owner.phone,
        "email": owner.email,
        "national_id": owner.national_id,
        "vehicles": [
            {
                "vehicle_id": v.vehicle_id,
                "vin": v.vin,
                "license_plate": v.license_plate,
                "model_id": v.model_id,
            }
            for v in vehicles
        ],
    }
