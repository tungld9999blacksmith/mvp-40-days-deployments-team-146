"""
Vehicle module — domain layer.

This file contains:
    - Enums that represent domain concepts (fuel type, vehicle status).
    - Entity classes with embedded business rules.
    - Value objects that carry validated, immutable data.

Rules:
    - NO imports from FastAPI, SQLAlchemy, Redis, or any external SDK.
    - The only allowed third-party import is `pydantic` for data validation.
    - Business invariants are enforced inside entity methods, not in services.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums — domain vocabulary
# ---------------------------------------------------------------------------
class FuelType(str, Enum):
    """Supported fuel types for a vehicle."""

    GASOLINE = "gasoline"
    DIESEL = "diesel"
    ELECTRIC = "electric"
    HYBRID = "hybrid"


class VehicleStatus(str, Enum):
    """Lifecycle status of a vehicle in the system."""

    ACTIVE = "active"
    IN_SERVICE = "in_service"
    DEACTIVATED = "deactivated"


# ---------------------------------------------------------------------------
# Entity — Vehicle
# ---------------------------------------------------------------------------
class VehicleEntity:
    """
    Core domain entity representing a customer's vehicle.

    All business rules live here so they can be unit-tested independently
    of any framework or database.
    """

    def __init__(
        self,
        *,
        id: str | None = None,
        owner_id: str,
        license_plate: str,
        brand: str,
        model: str,
        year: int,
        fuel_type: FuelType = FuelType.GASOLINE,
        status: VehicleStatus = VehicleStatus.ACTIVE,
        vin: Optional[str] = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        self.id = id or str(uuid.uuid4())
        self.owner_id = owner_id
        self.license_plate = license_plate.upper().strip()
        self.brand = brand.strip()
        self.model = model.strip()
        self.year = year
        self.fuel_type = fuel_type
        self.status = status
        self.vin = vin
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()

        # Enforce invariants at construction time
        self._validate()

    # ---- business rules ---------------------------------------------------

    def _validate(self) -> None:
        """Enforce domain invariants."""
        if self.year < 1886 or self.year > datetime.utcnow().year + 1:
            raise ValueError(
                f"Vehicle year must be between 1886 and {datetime.utcnow().year + 1}."
            )
        if not self.license_plate:
            raise ValueError("License plate must not be empty.")

    def deactivate(self) -> None:
        """Mark the vehicle as deactivated (e.g. sold, scrapped)."""
        if self.status == VehicleStatus.DEACTIVATED:
            raise ValueError("Vehicle is already deactivated.")
        self.status = VehicleStatus.DEACTIVATED
        self.updated_at = datetime.utcnow()

    def send_to_service(self) -> None:
        """Mark the vehicle as currently being serviced."""
        if self.status != VehicleStatus.ACTIVE:
            raise ValueError("Only active vehicles can be sent to service.")
        self.status = VehicleStatus.IN_SERVICE
        self.updated_at = datetime.utcnow()

    def mark_service_done(self) -> None:
        """Mark the vehicle as back from service."""
        if self.status != VehicleStatus.IN_SERVICE:
            raise ValueError("Vehicle is not currently in service.")
        self.status = VehicleStatus.ACTIVE
        self.updated_at = datetime.utcnow()

    def belongs_to(self, user_id: str) -> bool:
        """Check if *user_id* is the owner of this vehicle."""
        return self.owner_id == user_id

    def __repr__(self) -> str:
        return (
            f"<Vehicle id={self.id} plate={self.license_plate} "
            f"status={self.status.value}>"
        )
