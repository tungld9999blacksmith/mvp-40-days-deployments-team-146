"""
Vehicle module — route layer (HTTP endpoints).

Responsibilities:
    - Declare HTTP method, path, status code, and response schema.
    - Read request context (path params, query params, body, current user).
    - Delegate ALL business logic to the service layer.
    - NEVER put business rules, DB queries, or authorization logic here.

Authentication:
    In production, `get_current_user_id` would verify a Firebase/JWT token
    and extract the user ID.  Here it returns a hardcoded value for demo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from src.modules.examples.dependency import get_vehicle_service
from src.modules.examples.model import (
    CreateVehicleRequest,
    MessageResponse,
    UpdateVehicleRequest,
    VehicleListResponse,
    VehicleResponse,
)
from src.modules.examples.service import VehicleService

# ---------------------------------------------------------------------------
# Router instance — will be mounted in main.py or a parent router
# ---------------------------------------------------------------------------
vehicle_router = APIRouter(prefix="/vehicles", tags=["vehicles"])


# ---------------------------------------------------------------------------
# Fake auth dependency (replace with real Firebase/JWT auth in production)
# ---------------------------------------------------------------------------
async def get_current_user_id() -> str:
    """
    Stub: in production, this would parse and verify the Authorization
    header (e.g. Firebase ID token) and return the authenticated user's ID.
    """
    return "user-demo-001"


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------
@vehicle_router.post(
    "/",
    response_model=VehicleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new vehicle",
)
async def create_vehicle(
    body: CreateVehicleRequest,
    user_id: str = Depends(get_current_user_id),
    svc: VehicleService = Depends(get_vehicle_service),
) -> VehicleResponse:
    """Create a vehicle and associate it with the authenticated user."""
    return await svc.create_vehicle(owner_id=user_id, req=body)


@vehicle_router.get(
    "/{vehicle_id}",
    response_model=VehicleResponse,
    summary="Get a vehicle by ID",
)
async def get_vehicle(
    vehicle_id: str,
    user_id: str = Depends(get_current_user_id),
    svc: VehicleService = Depends(get_vehicle_service),
) -> VehicleResponse:
    """Retrieve a single vehicle. Only the owner can view."""
    return await svc.get_vehicle(vehicle_id=vehicle_id, requester_id=user_id)


@vehicle_router.get(
    "/",
    response_model=VehicleListResponse,
    summary="List my vehicles",
)
async def list_vehicles(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    user_id: str = Depends(get_current_user_id),
    svc: VehicleService = Depends(get_vehicle_service),
) -> VehicleListResponse:
    """Return a paginated list of vehicles owned by the authenticated user."""
    return await svc.list_vehicles(owner_id=user_id, page=page, page_size=page_size)


@vehicle_router.patch(
    "/{vehicle_id}",
    response_model=VehicleResponse,
    summary="Update a vehicle",
)
async def update_vehicle(
    vehicle_id: str,
    body: UpdateVehicleRequest,
    user_id: str = Depends(get_current_user_id),
    svc: VehicleService = Depends(get_vehicle_service),
) -> VehicleResponse:
    """Partially update a vehicle. Only the owner may update."""
    return await svc.update_vehicle(
        vehicle_id=vehicle_id, requester_id=user_id, req=body
    )


@vehicle_router.delete(
    "/{vehicle_id}",
    response_model=MessageResponse,
    summary="Delete a vehicle",
)
async def delete_vehicle(
    vehicle_id: str,
    user_id: str = Depends(get_current_user_id),
    svc: VehicleService = Depends(get_vehicle_service),
) -> MessageResponse:
    """Delete a vehicle. Only the owner may delete."""
    return await svc.delete_vehicle(vehicle_id=vehicle_id, requester_id=user_id)
