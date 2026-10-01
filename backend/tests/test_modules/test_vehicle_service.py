"""
Service-level tests for the `examples` (vehicle) module.

These exercise VehicleService directly against InMemoryVehicleRepository
instead of going through HTTP: the FastAPI DI wiring (`dependency.py`)
builds a brand-new InMemoryVehicleRepository per request, so persistence
across two HTTP calls cannot be observed at the API layer. Testing the
service/repository pair directly is what actually verifies the CRUD
lifecycle and the domain rules (ownership, uniqueness).
"""

import pytest

from src.modules.examples.error import (
    VehicleNotFoundError,
    VehicleOwnershipDeniedError,
    VehiclePlateAlreadyExistsError,
)
from src.modules.examples.model import CreateVehicleRequest, UpdateVehicleRequest
from src.modules.examples.service import VehicleService
from src.modules.examples.utility import InMemoryVehicleRepository


@pytest.fixture
def service() -> VehicleService:
    return VehicleService(repo=InMemoryVehicleRepository())


@pytest.mark.asyncio
async def test_create_and_get_vehicle(service: VehicleService):
    created = await service.create_vehicle(
        owner_id="user-1",
        req=CreateVehicleRequest(license_plate="59a-12345", brand="Toyota", model="Camry", year=2024),
    )
    assert created.license_plate == "59A-12345"

    fetched = await service.get_vehicle(vehicle_id=created.id, requester_id="user-1")
    assert fetched.id == created.id


@pytest.mark.asyncio
async def test_get_vehicle_not_found(service: VehicleService):
    with pytest.raises(VehicleNotFoundError):
        await service.get_vehicle(vehicle_id="missing-id", requester_id="user-1")


@pytest.mark.asyncio
async def test_get_vehicle_denies_non_owner(service: VehicleService):
    created = await service.create_vehicle(
        owner_id="user-1",
        req=CreateVehicleRequest(license_plate="59A-12345", brand="Toyota", model="Camry", year=2024),
    )
    with pytest.raises(VehicleOwnershipDeniedError):
        await service.get_vehicle(vehicle_id=created.id, requester_id="user-2")


@pytest.mark.asyncio
async def test_create_vehicle_rejects_duplicate_plate(service: VehicleService):
    req = CreateVehicleRequest(license_plate="59A-12345", brand="Toyota", model="Camry", year=2024)
    await service.create_vehicle(owner_id="user-1", req=req)

    with pytest.raises(VehiclePlateAlreadyExistsError):
        await service.create_vehicle(owner_id="user-2", req=req)


@pytest.mark.asyncio
async def test_update_vehicle_by_owner(service: VehicleService):
    created = await service.create_vehicle(
        owner_id="user-1",
        req=CreateVehicleRequest(license_plate="59A-12345", brand="Toyota", model="Camry", year=2024),
    )

    updated = await service.update_vehicle(
        vehicle_id=created.id,
        requester_id="user-1",
        req=UpdateVehicleRequest(model="Corolla"),
    )
    assert updated.model == "Corolla"


@pytest.mark.asyncio
async def test_delete_vehicle_by_owner(service: VehicleService):
    created = await service.create_vehicle(
        owner_id="user-1",
        req=CreateVehicleRequest(license_plate="59A-12345", brand="Toyota", model="Camry", year=2024),
    )

    result = await service.delete_vehicle(vehicle_id=created.id, requester_id="user-1")
    assert result.success is True

    with pytest.raises(VehicleNotFoundError):
        await service.get_vehicle(vehicle_id=created.id, requester_id="user-1")


@pytest.mark.asyncio
async def test_list_vehicles_paginated(service: VehicleService):
    for i in range(3):
        await service.create_vehicle(
            owner_id="user-1",
            req=CreateVehicleRequest(license_plate=f"59A-{i:05d}", brand="Toyota", model="Camry", year=2024),
        )

    page = await service.list_vehicles(owner_id="user-1", page=1, page_size=2)
    assert page.total == 3
    assert len(page.items) == 2
