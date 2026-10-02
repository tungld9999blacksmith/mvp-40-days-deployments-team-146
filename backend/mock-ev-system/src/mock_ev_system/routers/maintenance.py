"""API endpoints: Maintenance (schedule, items, service history, next-due)."""

from datetime import date
from decimal import Decimal

from ev_contracts import WebhookEventType
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from ..db import get_session
from ..models import ServiceCenter
from ..service import MaintenanceService, VehicleService
from ..webhooks import dispatch

router = APIRouter(tags=["Maintenance"])


@router.get(
    "/vehicles/{vehicle_id}/maintenance-schedule",
    summary="Lịch bảo dưỡng chuẩn theo model xe (tất cả các mốc)",
)
def get_maintenance_schedule(
    vehicle_id: str,
    session: Session = Depends(get_session),
):
    v_svc = VehicleService(session)
    vehicle = v_svc.get_vehicle(vehicle_id)
    if not vehicle:
        raise HTTPException(404, f"Vehicle {vehicle_id} not found")

    m_svc = MaintenanceService(session)
    schedules = m_svc.get_schedule_by_model(vehicle.model_id)

    result = []
    for s in schedules:
        items = m_svc.get_items_for_schedule(s.schedule_id)
        result.append(
            {
                "schedule_id": s.schedule_id,
                "milestone_km": s.milestone_km,
                "milestone_months": s.milestone_months,
                "description": s.description,
                "items": [
                    {
                        "item_id": item.item_id,
                        "item_name": item.item_name,
                        "is_covered_by_warranty": item.is_covered_by_warranty,
                        "reference_price": float(item.reference_price),
                    }
                    for item in items
                ],
            }
        )

    return {"vehicle_id": vehicle_id, "model_id": vehicle.model_id, "schedules": result}


@router.get(
    "/vehicles/{vehicle_id}/service-history",
    summary="Lịch sử bảo dưỡng thực tế tại xưởng",
)
def get_service_history(
    vehicle_id: str,
    session: Session = Depends(get_session),
):
    v_svc = VehicleService(session)
    if not v_svc.get_vehicle(vehicle_id):
        raise HTTPException(404, f"Vehicle {vehicle_id} not found")

    m_svc = MaintenanceService(session)
    history = m_svc.get_service_history(vehicle_id)
    return [
        {
            "order_id": h.order_id,
            "vehicle_id": h.vehicle_id,
            "service_center_id": h.service_center_id,
            "service_date": str(h.service_date),
            "km_at_service": h.km_at_service,
            "items_done": h.items_done,
            "is_periodic": h.is_periodic,
            "total_cost": float(h.total_cost),
        }
        for h in history
    ]


class ServiceRecordCreate(BaseModel):
    service_center_id: str = Field(..., examples=["SC-01"])
    service_date: date
    km_at_service: int = Field(..., ge=0, le=999_999)
    items_done: str = Field(..., min_length=1, max_length=2000)
    is_periodic: bool = True
    total_cost: Decimal = Field(default=Decimal(0), ge=0)


@router.post(
    "/vehicles/{vehicle_id}/service-history",
    status_code=status.HTTP_201_CREATED,
    summary="Record a completed service visit and notify EV Care via webhook",
)
def create_service_record(
    vehicle_id: str,
    body: ServiceRecordCreate,
    session: Session = Depends(get_session),
):
    if not VehicleService(session).get_vehicle(vehicle_id):
        raise HTTPException(404, f"Vehicle {vehicle_id} not found")
    if not session.get(ServiceCenter, body.service_center_id):
        raise HTTPException(404, f"Service center {body.service_center_id} not found")

    record = MaintenanceService(session).add_service_record(
        vehicle_id=vehicle_id,
        service_center_id=body.service_center_id,
        service_date=body.service_date,
        km_at_service=body.km_at_service,
        items_done=body.items_done,
        total_cost=body.total_cost,
        is_periodic=body.is_periodic,
    )
    dispatch(WebhookEventType.VEHICLE_SERVICE_HISTORY_UPDATED, vehicle_id)
    return {
        "order_id": record.order_id,
        "vehicle_id": record.vehicle_id,
        "service_center_id": record.service_center_id,
        "service_date": str(record.service_date),
        "km_at_service": record.km_at_service,
        "items_done": record.items_done,
        "is_periodic": record.is_periodic,
        "total_cost": float(record.total_cost),
    }


@router.get(
    "/vehicles/{vehicle_id}/next-maintenance",
    summary="Mốc bảo dưỡng tiếp theo (computed) — dùng cho flow AI nhắc lịch",
)
def get_next_maintenance(
    vehicle_id: str,
    session: Session = Depends(get_session),
):
    m_svc = MaintenanceService(session)
    result = m_svc.compute_next_maintenance(vehicle_id)
    if result is None:
        raise HTTPException(404, f"Vehicle {vehicle_id} not found or no schedule")
    return result
