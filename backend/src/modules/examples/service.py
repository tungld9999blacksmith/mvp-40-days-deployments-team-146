"""
Vehicle module — service layer (use-case orchestration).

Responsibilities:
    - Orchestrate a single use case by combining domain logic + ports.
    - Enforce authorization (owner-based access control).
    - Convert between domain entities and request/response schemas.

Rules:
    - NEVER create database sessions, Redis clients, or SDK instances here.
      They are injected via the repository port.
    - Raise domain/application exceptions — do NOT return HTTP responses.
    - Keep methods focused: one public method ≈ one use case.
"""

from __future__ import annotations

import logging

from src.modules.examples.domain import FuelType, VehicleEntity, VehicleStatus
from src.modules.examples.error import (
    VehicleNotFoundError,
    VehicleOwnershipDeniedError,
    VehiclePlateAlreadyExistsError,
)
from src.modules.examples.model import (
    CreateVehicleRequest,
    MessageResponse,
    UpdateVehicleRequest,
    VehicleListResponse,
    VehicleRepositoryPort,
    VehicleResponse,
)

logger = logging.getLogger(__name__)


class VehicleService:
    """
    Application service for vehicle-related use cases.

    The repository port is injected through the constructor so the service
    stays decoupled from any specific database or ORM.
    """

    def __init__(self, repo: VehicleRepositoryPort) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Use case: Create a new vehicle
    # ------------------------------------------------------------------
    async def create_vehicle(
        self,
        owner_id: str,
        req: CreateVehicleRequest,
    ) -> VehicleResponse:
        """
        Register a new vehicle for *owner_id*.

        Steps:
            1. Check that the license plate is not already taken.
            2. Create a domain entity (enforces business rules).
            3. Persist through the repository port.
            4. Return the response schema.
        """
        # 1. Uniqueness check
        existing = await self._repo.get_by_plate(req.license_plate)
        if existing is not None:
            raise VehiclePlateAlreadyExistsError(req.license_plate)

        # 2. Build domain entity — validates invariants at construction
        entity = VehicleEntity(
            owner_id=owner_id,
            license_plate=req.license_plate,
            brand=req.brand,
            model=req.model,
            year=req.year,
            fuel_type=req.fuel_type,
            vin=req.vin,
        )

        # 3. Persist
        stored = await self._repo.create(
            {
                "id": entity.id,
                "owner_id": entity.owner_id,
                "license_plate": entity.license_plate,
                "brand": entity.brand,
                "model": entity.model,
                "year": entity.year,
                "fuel_type": entity.fuel_type.value,
                "status": entity.status.value,
                "vin": entity.vin,
                "created_at": entity.created_at,
                "updated_at": entity.updated_at,
            }
        )

        logger.info("Vehicle '%s' created for owner '%s'.", entity.id, owner_id)

        # 4. Map to response
        return self._to_response(stored)

    # ------------------------------------------------------------------
    # Use case: Get a vehicle by ID (with ownership check)
    # ------------------------------------------------------------------
    async def get_vehicle(
        self,
        vehicle_id: str,
        requester_id: str,
    ) -> VehicleResponse:
        """
        Retrieve a vehicle and verify that *requester_id* is the owner.
        """
        record = await self._repo.get_by_id(vehicle_id)
        if record is None:
            raise VehicleNotFoundError(vehicle_id)

        # Authorization — customers can only see their own vehicles
        if record["owner_id"] != requester_id:
            raise VehicleOwnershipDeniedError(requester_id, vehicle_id)

        return self._to_response(record)

    # ------------------------------------------------------------------
    # Use case: List vehicles for an owner
    # ------------------------------------------------------------------
    async def list_vehicles(
        self,
        owner_id: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> VehicleListResponse:
        """Return a paginated list of vehicles owned by *owner_id*."""
        items, total = await self._repo.list_by_owner(owner_id, page=page, page_size=page_size)
        return VehicleListResponse(
            items=[self._to_response(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    # ------------------------------------------------------------------
    # Use case: Update vehicle info
    # ------------------------------------------------------------------
    async def update_vehicle(
        self,
        vehicle_id: str,
        requester_id: str,
        req: UpdateVehicleRequest,
    ) -> VehicleResponse:
        """
        Partially update a vehicle.

        Only the owner may update. If license plate is being changed,
        check for duplicates first.
        """
        record = await self._repo.get_by_id(vehicle_id)
        if record is None:
            raise VehicleNotFoundError(vehicle_id)
        if record["owner_id"] != requester_id:
            raise VehicleOwnershipDeniedError(requester_id, vehicle_id)

        # Build update dict — only include fields that were explicitly set
        updates = req.model_dump(exclude_unset=True)

        # If changing plate, ensure it's unique
        if "license_plate" in updates:
            updates["license_plate"] = updates["license_plate"].upper().strip()
            existing = await self._repo.get_by_plate(updates["license_plate"])
            if existing and existing["id"] != vehicle_id:
                raise VehiclePlateAlreadyExistsError(updates["license_plate"])

        updated = await self._repo.update(vehicle_id, updates)
        if updated is None:
            raise VehicleNotFoundError(vehicle_id)

        logger.info("Vehicle '%s' updated by owner '%s'.", vehicle_id, requester_id)
        return self._to_response(updated)

    # ------------------------------------------------------------------
    # Use case: Delete a vehicle
    # ------------------------------------------------------------------
    async def delete_vehicle(
        self,
        vehicle_id: str,
        requester_id: str,
    ) -> MessageResponse:
        """Soft-delete or hard-delete a vehicle. Owner-only."""
        record = await self._repo.get_by_id(vehicle_id)
        if record is None:
            raise VehicleNotFoundError(vehicle_id)
        if record["owner_id"] != requester_id:
            raise VehicleOwnershipDeniedError(requester_id, vehicle_id)

        await self._repo.delete(vehicle_id)
        logger.info("Vehicle '%s' deleted by owner '%s'.", vehicle_id, requester_id)

        return MessageResponse(
            success=True,
            message="Vehicle deleted successfully.",
            vehicle_id=vehicle_id,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _to_response(record: dict) -> VehicleResponse:
        """Map a raw persistence record to a VehicleResponse schema."""
        return VehicleResponse(
            id=record["id"],
            owner_id=record["owner_id"],
            license_plate=record["license_plate"],
            brand=record["brand"],
            model=record["model"],
            year=record["year"],
            fuel_type=FuelType(record["fuel_type"]),
            status=VehicleStatus(record["status"]),
            vin=record.get("vin"),
            created_at=record["created_at"],
            updated_at=record["updated_at"],
        )
