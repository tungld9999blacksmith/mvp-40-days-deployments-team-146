"""Cost-estimate module — HTTP endpoints (API-EST-01..03, FEAT-COST-001 / F5).

Read-only: an estimate is computed on demand and never stored (BR-1007).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.vehicle import UserVehicle
from src.modules.user_vehicle.dependency import require_active_vehicle_owner

from . import schemas
from .dependency import get_cost_estimation_service, get_estimable_vehicle
from .service import CostEstimationService

router = APIRouter(prefix="/user-vehicles", tags=["cost-estimate"])


@router.get(
    "/{userVehicleId}/maintenance-milestones",
    response_model=schemas.MilestonesEnvelope,
    summary="Milestones with a maintenance schedule for the vehicle's model (UC-1002)",
)
def list_maintenance_milestones(
    vehicle: Annotated[UserVehicle, Depends(get_estimable_vehicle)],
    service: Annotated[CostEstimationService, Depends(get_cost_estimation_service)],
) -> schemas.MilestonesEnvelope:
    return schemas.MilestonesEnvelope(data=service.list_milestones(vehicle))


@router.get(
    "/{userVehicleId}/cost-estimate",
    response_model=schemas.EstimateEnvelope,
    summary="Estimated cost of one milestone at one workshop (UC-1001, BR-1001)",
)
def get_cost_estimate(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    vehicle: Annotated[UserVehicle, Depends(get_estimable_vehicle)],
    service: Annotated[CostEstimationService, Depends(get_cost_estimation_service)],
    odo_milestone: Annotated[int | None, Query(alias="odoMilestone", gt=0)] = None,
    workshop_id: Annotated[UUID | None, Query(alias="workshopId")] = None,
) -> schemas.EstimateEnvelope:
    data = service.estimate_for_request(user, vehicle, odo_milestone=odo_milestone, workshop_id=workshop_id)
    return schemas.EstimateEnvelope(data=data)


@router.get(
    "/{userVehicleId}/cost-estimate/compare",
    response_model=schemas.CompareEnvelope,
    summary="Compare the same milestone at 2-3 workshops (UC-1003, Q-1003)",
)
def compare_cost_estimates(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    vehicle: Annotated[UserVehicle, Depends(get_estimable_vehicle)],
    service: Annotated[CostEstimationService, Depends(get_cost_estimation_service)],
    workshop_ids: Annotated[list[UUID], Query(alias="workshopIds")],
    odo_milestone: Annotated[int | None, Query(alias="odoMilestone", gt=0)] = None,
) -> schemas.CompareEnvelope:
    data = service.compare(user, vehicle, odo_milestone=odo_milestone, workshop_ids=workshop_ids)
    return schemas.CompareEnvelope(data=data)
