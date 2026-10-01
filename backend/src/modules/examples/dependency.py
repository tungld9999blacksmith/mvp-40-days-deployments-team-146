"""
Vehicle module — dependency injection (composition root).

This file wires concrete infrastructure adapters into the service layer.
It is the ONLY file that knows which concrete repository is used.

In a real project you would:
    - Import the PostgreSQL adapter from `infrastructure/postgres/`.
    - Import the database session factory from `common/database.py`.
    - Potentially add Redis, Firebase, or LLM dependencies.

For this example, we use an in-memory stub (defined in utility.py)
so the module can run without any database setup.
"""

from __future__ import annotations

from fastapi import Depends

from src.modules.examples.model import VehicleRepositoryPort
from src.modules.examples.service import VehicleService
from src.modules.examples.utility import InMemoryVehicleRepository


def get_vehicle_repository() -> VehicleRepositoryPort:
    """
    Provide the vehicle repository implementation.

    In production, replace this with your PostgreSQL adapter:

        from src.infrastructure.postgres.vehicle_repo import PgVehicleRepository
        from src.common.database import get_session

        async def get_vehicle_repository(
            session: AsyncSession = Depends(get_session),
        ) -> VehicleRepositoryPort:
            return PgVehicleRepository(session)
    """
    return InMemoryVehicleRepository()


def get_vehicle_service(
    repo: VehicleRepositoryPort = Depends(get_vehicle_repository),
) -> VehicleService:
    """
    Provide the VehicleService with its dependency injected.

    FastAPI's `Depends()` automatically calls `get_vehicle_repository()`
    and passes the result to this factory function.
    """
    return VehicleService(repo=repo)
