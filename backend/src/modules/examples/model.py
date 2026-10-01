"""
Vehicle module — schemas (request/response) and ports (repository interface).

Schemas:
    - Pydantic models for API input validation and response serialization.
    - These are the ONLY objects that cross the HTTP boundary.

Ports:
    - Abstract base classes that define contracts for persistence.
    - The service depends on these abstractions, NOT on concrete implementations.
    - Concrete adapters live in `infrastructure/` and are wired via `dependency.py`.

NOTE:
    In the full project, you might split this into `schemas.py` and `ports.py`
    as described in guide/api.md.  Here they are combined because we are
    keeping the existing file set unchanged.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from src.modules.examples.domain import FuelType, VehicleStatus


# ===========================================================================
# REQUEST SCHEMAS — input validation
# ===========================================================================
class CreateVehicleRequest(BaseModel):
    """Schema for creating a new vehicle."""

    license_plate: str = Field(..., min_length=1, max_length=20, examples=["59A-12345"])
    brand: str = Field(..., min_length=1, max_length=100, examples=["Toyota"])
    model: str = Field(..., min_length=1, max_length=100, examples=["Camry"])
    year: int = Field(..., ge=1886, le=2030, examples=[2024])
    fuel_type: FuelType = Field(default=FuelType.GASOLINE)
    vin: Optional[str] = Field(default=None, max_length=17, examples=["1HGBH41JXMN109186"])

    @field_validator("license_plate")
    @classmethod
    def normalize_plate(cls, v: str) -> str:
        """Uppercase and strip whitespace from the plate."""
        return v.upper().strip()

    model_config = {
        "json_schema_extra": {
            "example": {
                "license_plate": "59A-12345",
                "brand": "Toyota",
                "model": "Camry",
                "year": 2024,
                "fuel_type": "gasoline",
                "vin": "1HGBH41JXMN109186",
            }
        }
    }


class UpdateVehicleRequest(BaseModel):
    """Schema for partially updating a vehicle."""

    license_plate: Optional[str] = Field(default=None, min_length=1, max_length=20)
    brand: Optional[str] = Field(default=None, min_length=1, max_length=100)
    model: Optional[str] = Field(default=None, min_length=1, max_length=100)
    year: Optional[int] = Field(default=None, ge=1886, le=2030)
    fuel_type: Optional[FuelType] = None
    vin: Optional[str] = Field(default=None, max_length=17)

    model_config = {
        "json_schema_extra": {
            "example": {
                "license_plate": "59A-67890",
                "year": 2025,
                "fuel_type": "hybrid",
            }
        }
    }


# ===========================================================================
# RESPONSE SCHEMAS — output serialization
# ===========================================================================
class VehicleResponse(BaseModel):
    """Schema returned when reading a single vehicle."""

    id: str
    owner_id: str
    license_plate: str
    brand: str
    model: str
    year: int
    fuel_type: FuelType
    status: VehicleStatus
    vin: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class VehicleListResponse(BaseModel):
    """Paginated list response."""

    items: List[VehicleResponse]
    total: int
    page: int
    page_size: int


class MessageResponse(BaseModel):
    """Generic message response for mutation operations."""

    success: bool = True
    message: str = ""
    vehicle_id: Optional[str] = None


# ===========================================================================
# PORT — repository interface (abstract)
# ===========================================================================
class VehicleRepositoryPort(ABC):
    """
    Abstract contract for vehicle persistence.

    The service layer depends on this interface.  Concrete implementations
    (e.g., PostgreSQL adapter) live in `infrastructure/` and are injected
    at runtime via `dependency.py`.
    """

    @abstractmethod
    async def get_by_id(self, vehicle_id: str) -> Optional[dict]:
        """Return a vehicle dict or None."""
        ...

    @abstractmethod
    async def get_by_plate(self, plate: str) -> Optional[dict]:
        """Return a vehicle dict matching the license plate, or None."""
        ...

    @abstractmethod
    async def list_by_owner(
        self, owner_id: str, *, page: int = 1, page_size: int = 20
    ) -> tuple[list[dict], int]:
        """Return (items, total_count) for a given owner."""
        ...

    @abstractmethod
    async def create(self, vehicle_data: dict) -> dict:
        """Persist a new vehicle and return the stored dict."""
        ...

    @abstractmethod
    async def update(self, vehicle_id: str, updates: dict) -> Optional[dict]:
        """Apply partial updates; return updated dict or None."""
        ...

    @abstractmethod
    async def delete(self, vehicle_id: str) -> bool:
        """Delete a vehicle; return True if it existed."""
        ...
