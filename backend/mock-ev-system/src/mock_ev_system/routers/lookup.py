"""API endpoints: Lookup — Vehicle Models & Service Centers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..service import LookupService

router = APIRouter(tags=["Lookup"])


@router.get("/models", summary="Danh sách mẫu xe (master data)")
def list_models(session: Session = Depends(get_session)):
    svc = LookupService(session)
    return [
        {
            "model_id": m.model_id,
            "model_name": m.model_name,
            "trim": m.trim,
            "battery_capacity_kwh": m.battery_capacity_kwh,
            "motor_power_kw": m.motor_power_kw,
            "production_year": m.production_year,
        }
        for m in svc.list_models()
    ]


@router.get("/models/{model_id}", summary="Chi tiết mẫu xe")
def get_model(model_id: str, session: Session = Depends(get_session)):
    svc = LookupService(session)
    m = svc.get_model(model_id)
    if not m:
        raise HTTPException(404, f"Model {model_id} not found")
    return {
        "model_id": m.model_id,
        "model_name": m.model_name,
        "trim": m.trim,
        "battery_capacity_kwh": m.battery_capacity_kwh,
        "motor_power_kw": m.motor_power_kw,
        "production_year": m.production_year,
    }


@router.get("/service-centers", summary="Danh sách đại lý / xưởng dịch vụ")
def list_service_centers(session: Session = Depends(get_session)):
    svc = LookupService(session)
    return [
        {
            "center_id": c.center_id,
            "name": c.name,
            "region": c.region,
            "type": c.type.value,
        }
        for c in svc.list_service_centers()
    ]


@router.get("/service-centers/{center_id}", summary="Chi tiết xưởng dịch vụ")
def get_service_center(
    center_id: str,
    session: Session = Depends(get_session),
):
    svc = LookupService(session)
    c = svc.get_service_center(center_id)
    if not c:
        raise HTTPException(404, f"Service center {center_id} not found")
    return {
        "center_id": c.center_id,
        "name": c.name,
        "region": c.region,
        "type": c.type.value,
    }
