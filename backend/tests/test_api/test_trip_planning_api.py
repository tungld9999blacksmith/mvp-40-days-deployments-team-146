from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlmodel import select

from src.common.core.vehicle import VehicleTripPlan
from src.main import app
from src.modules.trip_planning.service import TripPlanningService
from src.modules.user_vehicle.route import get_trip_service
from src.modules.user_vehicle.service import UserVehicleService
from tests._user_vehicle import NOW, RecordingScheduler, add_owner, add_vehicle
from tests.test_api import test_user_vehicle_api as vehicle_api

AUTH = {"Authorization": "Bearer x"}


@pytest_asyncio.fixture
async def api():
    async for api in vehicle_api.api.__wrapped__():
        vehicles = UserVehicleService(api.session, RecordingScheduler(), clock=lambda: NOW)
        app.dependency_overrides[get_trip_service] = lambda: TripPlanningService(
            api.session, vehicles, clock=lambda: NOW
        )
        yield api


def body():
    return {"departureDate": (NOW.date() + timedelta(days=3)).isoformat(), "distanceKm": 1200, "reminderEnabled": True}


@pytest.mark.asyncio
async def test_trip_create_reload_delete_and_idempotent_put(api):
    owner = add_owner(api.session)
    vehicle = add_vehicle(api.session, owner)
    url = f"/api/v1/user-vehicles/{vehicle.id}/trip-plan"
    assert (await api.client.get(url, headers=AUTH)).json() == {"data": None}
    first = await api.client.put(url, headers=AUTH, json=body())
    assert first.status_code == 200
    data = first.json()["data"]
    assert data["distanceKm"] == 1200 and data["advice"]["status"] == "UNKNOWN"
    assert (await api.client.put(url, headers=AUTH, json=body())).json()["data"]["id"] == data["id"]
    assert (await api.client.get(url, headers=AUTH)).json()["data"]["id"] == data["id"]
    assert (await api.client.delete(url, headers=AUTH)).json() == {"data": None}
    assert not api.session.exec(select(VehicleTripPlan)).all()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get", "put", "delete"])
async def test_trip_other_owner_is_indistinguishable_from_missing(api, method):
    owner = add_owner(api.session)
    vehicle = add_vehicle(api.session, owner)
    add_owner(api.session, uid="uid-2", email="other@example.com")
    api.sign_in_as("uid-2")
    kwargs = {"headers": AUTH} | ({"json": body()} if method == "put" else {})
    existing = await getattr(api.client, method)(f"/api/v1/user-vehicles/{vehicle.id}/trip-plan", **kwargs)
    missing = await getattr(api.client, method)(f"/api/v1/user-vehicles/{uuid4()}/trip-plan", **kwargs)
    assert existing.status_code == missing.status_code == 404
    assert existing.json()["error"]["code"] == missing.json()["error"]["code"]


@pytest.mark.asyncio
async def test_trip_invalid_distance_does_not_replace_existing_plan(api):
    owner = add_owner(api.session)
    vehicle = add_vehicle(api.session, owner)
    url = f"/api/v1/user-vehicles/{vehicle.id}/trip-plan"
    await api.client.put(url, headers=AUTH, json=body())
    rejected = await api.client.put(url, headers=AUTH, json=body() | {"distanceKm": 0})
    assert rejected.status_code == 400
    assert (await api.client.get(url, headers=AUTH)).json()["data"]["distanceKm"] == 1200
