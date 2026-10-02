"""Shared test helpers for the onboarding module.

Provides an in-memory SQLite session (with all onboarding tables created) and
a configurable stub for the manufacturer gateway, so onboarding tests never
touch a real database or the mock-ev-system HTTP service.
"""

from __future__ import annotations

from collections.abc import Iterator

from ev_contracts import (
    OwnershipVerifyFailureReason,
    OwnershipVerifyRequest,
    OwnershipVerifyResponse,
    VehicleSpec,
    WarrantyContract,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

# Import the models so their tables register on SQLModel.metadata.
from src.common.core.identity import vehicle_user as _vehicle_user  # noqa: F401
from src.modules.vehicle_owner_onboarding import domain as _domain  # noqa: F401
from src.modules.vehicle_owner_onboarding.ports import OemTimeoutError, OemVehicleGateway

_ONBOARDING_TABLES = [
    _vehicle_user.VehicleUser.__table__,
    _domain.UserLocation.__table__,
    _domain.UserVehicle.__table__,
    _domain.VehicleWarranty.__table__,
    _domain.VehicleVerificationAttempt.__table__,
    _domain.UserConsent.__table__,
]


def make_session() -> Iterator[Session]:
    """Yield a fresh in-memory SQLite session with onboarding tables created."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine, tables=_ONBOARDING_TABLES)
    with Session(engine) as session:
        yield session


# Seeded manufacturer record used across tests (mirrors mock owner OWN-004).
GOOGLE_EMAIL = "dung.pham@example.com"
NATIONAL_ID = "079200001004"
VIN = "VF6PLUS2024000001"
PLATE = "29A-444.44"
MODEL_ID = "MDL-03"


def verified_response() -> OwnershipVerifyResponse:
    from datetime import date

    return OwnershipVerifyResponse(
        verified=True,
        vehicle=VehicleSpec(
            external_vehicle_id="VEH-006",
            external_owner_id="OWN-004",
            external_model_id=MODEL_ID,
            model_name="VF6",
            trim="Plus",
            color="Xám",
            manufacture_date=date(2024, 5, 12),
            production_year=2024,
            battery_capacity_kwh=59.6,
            motor_power_kw=150.0,
        ),
        warranties=[
            WarrantyContract(
                external_warranty_id="WAR-0045",
                external_policy_id="WP-009",
                component="battery",
                start_date=date(2024, 5, 12),
                end_date=date(2032, 5, 12),
                km_limit=160000,
                duration_months=96,
                terms_description="Battery warranty 8 years / 160,000 km.",
                status="active",
            ),
        ],
    )


def failure_response(reason: OwnershipVerifyFailureReason) -> OwnershipVerifyResponse:
    return OwnershipVerifyResponse(verified=False, failure_reason=reason)


class StubOemGateway(OemVehicleGateway):
    """Configurable stand-in for the manufacturer gateway."""

    def __init__(
        self,
        *,
        verify_result: OwnershipVerifyResponse | None = None,
        raise_timeout: bool = False,
        models: list[dict] | None = None,
    ) -> None:
        self.verify_result = verify_result or verified_response()
        self.raise_timeout = raise_timeout
        self.models = (
            models
            if models is not None
            else [
                {"model_id": "MDL-03", "model_name": "VF6", "trim": "Plus", "production_year": 2024},
                {"model_id": "MDL-02", "model_name": "VF6", "trim": "Eco", "production_year": 2024},
            ]
        )
        self.verify_calls = 0
        self.last_request: OwnershipVerifyRequest | None = None

    async def list_models(self) -> list[dict]:
        if self.raise_timeout:
            raise OemTimeoutError("stub timeout")
        return self.models

    async def verify_ownership(self, request: OwnershipVerifyRequest) -> OwnershipVerifyResponse:
        self.verify_calls += 1
        self.last_request = request
        if self.raise_timeout:
            raise OemTimeoutError("stub timeout")
        return self.verify_result
