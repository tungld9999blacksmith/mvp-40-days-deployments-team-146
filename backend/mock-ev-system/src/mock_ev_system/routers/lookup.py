"""API endpoints: Lookup — Vehicle Models & Service Centers."""

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..db import get_session
from ..models import CenterType, ServiceCenter
from ..service import LookupService

router = APIRouter(tags=["Lookup"])


def _center_out(c: ServiceCenter) -> dict:
    return {
        "center_id": c.center_id,
        "name": c.name,
        "region": c.region,
        "type": c.type.value,
        "address": c.address,
        "latitude": c.latitude,
        "longitude": c.longitude,
    }


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


@router.get("/service-centers", summary="Danh sách đại lý / xưởng dịch vụ (phân trang, lọc)")
def list_service_centers(
    q: str | None = Query(
        None, max_length=200, description="Tìm trong tên / địa chỉ (không phân biệt dấu, hoa thường)"
    ),
    region: str | None = Query(None, max_length=100, description="Tỉnh/thành, ví dụ 'Hà Nội' hoặc 'ha noi'"),
    type: CenterType | None = Query(None, description="dealer | service_only"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_session),
):
    total, centers = LookupService(session).search_service_centers(
        q=q, region=region, center_type=type, page=page, page_size=page_size
    )
    return {
        "items": [_center_out(c) for c in centers],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }


@router.get("/service-centers/{center_id}", summary="Chi tiết xưởng dịch vụ")
def get_service_center(
    center_id: str,
    session: Session = Depends(get_session),
):
    svc = LookupService(session)
    c = svc.get_service_center(center_id)
    if not c:
        raise HTTPException(404, f"Service center {center_id} not found")
    return _center_out(c)
