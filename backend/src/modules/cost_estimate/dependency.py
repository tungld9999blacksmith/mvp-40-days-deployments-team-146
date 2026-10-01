"""Cost-estimate module — dependency injection (FEAT-COST-001)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path
from sqlmodel import Session

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.vehicle import UserVehicle
from src.infrastructure.supabase.db import get_session
from src.modules.booking.location import WorkshopLocationFinder, get_location_finder
from src.modules.user_vehicle.dependency import (
    get_user_vehicle_service,
    require_active_vehicle_owner,
)
from src.modules.user_vehicle.service import UserVehicleService

from .service import CostEstimationService


def get_cost_estimation_service(
    session: Annotated[Session, Depends(get_session)],
    finder: Annotated[WorkshopLocationFinder, Depends(get_location_finder)],
    vehicles: Annotated[UserVehicleService, Depends(get_user_vehicle_service)],
) -> CostEstimationService:
    def next_milestone(vehicle: UserVehicle) -> int | None:
        milestone = vehicles.calculate(vehicle).next_milestone
        return milestone.odo_milestone_km if milestone else None

    return CostEstimationService(session, finder, next_milestone)


def get_estimable_vehicle(
    user_vehicle_id: Annotated[UUID, Path(alias="userVehicleId")],
    user: Annotated[VehicleUser, Depends(require_active_vehicle_owner)],
    service: Annotated[CostEstimationService, Depends(get_cost_estimation_service)],
) -> UserVehicle:
    """Owned, verified, linked vehicle — anything else is 404 (BR-1008)."""
    return service.get_owned_active_vehicle(user, user_vehicle_id)
