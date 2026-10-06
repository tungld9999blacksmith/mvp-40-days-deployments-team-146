"""User-vehicle module — HTTP endpoints (API-VEH-001..003, API-VEH-005).

Read-only for vehicle owners: odometer and service history come from the
manufacturer sync, never from the owner (FEAT-VEH-001 BR-003).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.vehicle import UserVehicle

from . import schemas
from .dependency import (
    get_owned_active_vehicle,
    get_user_vehicle_service,
    require_active_vehicle_owner,
)
from .service import UserVehicleService

router = APIRouter(prefix="/user-vehicles", tags=["user-vehicles"])


@router.get(
    "",
    response_model=schemas.VehicleListEnvelope,
    summary="List the verified, active vehicles of the signed-in owner",
)
def list_user_vehicles(
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[UserVehicleService, Depends(get_user_vehicle_service)],
) -> schemas.VehicleListEnvelope:
    return schemas.VehicleListEnvelope(data=service.list_vehicles(user))


@router.get(
    "/{userVehicleId}",
    response_model=schemas.VehicleProfileEnvelope,
    summary="Vehicle profile: identity, specs, warranties, odometer, last service",
)
def get_user_vehicle_profile(
    vehicle: Annotated[UserVehicle, Depends(get_owned_active_vehicle)],
    service: Annotated[UserVehicleService, Depends(get_user_vehicle_service)],
) -> schemas.VehicleProfileEnvelope:
    return schemas.VehicleProfileEnvelope(data=service.get_profile(vehicle))


@router.get(
    "/{userVehicleId}/maintenance-status",
    response_model=schemas.MaintenanceStatusEnvelope,
    summary="Maintenance due status and next milestone of the vehicle",
)
def get_maintenance_status(
    vehicle: Annotated[UserVehicle, Depends(get_owned_active_vehicle)],
    service: Annotated[UserVehicleService, Depends(get_user_vehicle_service)],
) -> schemas.MaintenanceStatusEnvelope:
    return schemas.MaintenanceStatusEnvelope(data=service.get_maintenance_status(vehicle))


@router.get(
    "/{userVehicleId}/service-records",
    response_model=schemas.ServiceRecordListEnvelope,
    summary="Service history of the vehicle: manufacturer records and EV Care visits",
)
def list_service_records(
    vehicle: Annotated[UserVehicle, Depends(get_owned_active_vehicle)],
    service: Annotated[UserVehicleService, Depends(get_user_vehicle_service)],
) -> schemas.ServiceRecordListEnvelope:
    return schemas.ServiceRecordListEnvelope(data=service.list_service_records(vehicle))
