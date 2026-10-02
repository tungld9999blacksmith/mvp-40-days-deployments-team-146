"""API-level tests for FEAT-VEH-001 (API-VEH-001..004).

Drive the real FastAPI app with the Firebase token, DB session, sync scheduler,
webhook event store and clock replaced by test doubles.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from ev_contracts import sign_webhook
from httpx import ASGITransport, AsyncClient

from src.common.core.identity.vehicle_user import OnboardingStatus, VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.core.vehicle import (
    OemSyncTrigger,
    ServiceRecordSource,
    VehicleLinkStatus,
    VehicleOemSync,
    VehicleServiceRecord,
)
from src.infrastructure.supabase.db import get_session
from src.main import app
from src.modules.oauth.dependency import verify_firebase_token
from src.modules.oem_integration.dependency import get_sync_scheduler, get_webhook_service
from src.modules.oem_integration.service import OemWebhookService
from src.modules.user_vehicle.dependency import get_user_vehicle_service
from src.modules.user_vehicle.service import UserVehicleService
from tests._user_vehicle import (
    NOW,
    MemoryEventStore,
    RecordingScheduler,
    add_odometer,
    add_owner,
    add_rules,
    add_vehicle,
    make_session,
    mark_synced,
)

SECRET = "api-test-secret"
AUTH = {"Authorization": "Bearer x"}


class _Api:
    def __init__(self, client, session, scheduler, claims):
        self.client = client
        self.session = session
        self.scheduler = scheduler
        self._claims = claims

    def sign_in_as(self, uid: str) -> None:
        self._claims["claims"] = {"uid": uid}


@pytest_asyncio.fixture
async def api():
    session = next(make_session())
    scheduler = RecordingScheduler()
    claims: dict = {"claims": {"uid": "uid-1"}}

    def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[verify_firebase_token] = lambda: claims["claims"]
    app.dependency_overrides[get_sync_scheduler] = lambda: scheduler
    app.dependency_overrides[get_user_vehicle_service] = lambda: UserVehicleService(
        session, scheduler, clock=lambda: NOW
    )
    app.dependency_overrides[get_webhook_service] = lambda: OemWebhookService(
        session, scheduler, MemoryEventStore(), secret=SECRET, clock=lambda: NOW
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield _Api(client, session, scheduler, claims)

    app.dependency_overrides.clear()
    session.close()


@pytest.fixture
def ready_vehicle(api: _Api):
    """VF6 bought 2025-10-15, rules seeded, synced, OEM odometer 11,600 km."""
    user = add_owner(api.session)
    vehicle = add_vehicle(api.session, user)
    add_rules(api.session)
    add_odometer(api.session, vehicle, 11_600)
    mark_synced(api.session, vehicle)
    return vehicle


# ── API-VEH-001 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_only_active_verified_vehicles(api: _Api, ready_vehicle):
    add_vehicle(
        api.session,
        api.session.get(VehicleUser, ready_vehicle.user_id),
        vin="LVVDB11B1PE000002",
        external_vehicle_id="VEH-007",
        link_status=VehicleLinkStatus.UNLINKED,
    )

    r = await api.client.get("/api/v1/user-vehicles", headers=AUTH)

    assert r.status_code == 200
    data = r.json()["data"]
    assert [v["userVehicleId"] for v in data] == [str(ready_vehicle.id)]
    assert data[0] == {
        "userVehicleId": str(ready_vehicle.id),
        "modelName": "VF6",
        "trim": "Plus",
        "licensePlate": "30A12345",
        "color": "White",
    }


# ── API-VEH-002 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_profile_masks_vin_and_shows_oem_data(api: _Api, ready_vehicle):
    api.session.add(
        VehicleServiceRecord(
            user_vehicle_id=ready_vehicle.id,
            source=ServiceRecordSource.OEM,
            external_order_id="SH-001",
            service_date=date(2026, 3, 10),
            odo_km=6_100,
        )
    )
    api.session.commit()

    r = await api.client.get(f"/api/v1/user-vehicles/{ready_vehicle.id}", headers=AUTH)

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["vinMasked"] == "LVVDB1******00001"
    assert data["modelId"] == "MDL-03"
    assert data["odometer"]["odoKm"] == 11_600
    assert data["odometer"]["dataSource"] == "OEM"
    assert data["warranties"] == [
        {
            "component": "BATTERY",
            "startDate": "2025-10-15",
            "endDate": "2033-10-15",
            "kmLimit": 200000,
            "isActive": True,
        }
    ]
    assert data["lastService"] == {
        "serviceDate": "2026-03-10",
        "odoKm": 6100,
        "source": "OEM",
        "centerName": None,
    }
    assert data["oemSyncedAt"] is not None


# ── API-VEH-003 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_status_due_soon_ac001(api: _Api, ready_vehicle):
    r = await api.client.get(f"/api/v1/user-vehicles/{ready_vehicle.id}/maintenance-status", headers=AUTH)

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["dueStatus"] == "DUE_SOON"
    assert data["dueReason"] == "KM"
    assert data["calculationBasis"] == "KM_AND_TIME"
    assert data["remainingKm"] == 400
    assert data["remainingDays"] == 17
    assert data["nextMilestone"]["odoMilestoneKm"] == 12_000
    assert data["nextMilestone"]["dueDate"] == "2026-10-15"
    assert data["nextMilestone"]["label"] == "12,000 km / 12 months"
    assert "price" not in json.dumps(data["nextMilestone"]).lower()
    assert data["lastService"] == {"type": "PURCHASE_DATE", "date": "2025-10-15", "odoKm": 0}
    assert data["thresholds"] == {"dueSoonKm": 500, "dueSoonDays": 14}
    assert data["odometer"]["recordedAt"].startswith("2026-09-28T02:00:00")
    assert api.scheduler.calls == []


@pytest.mark.asyncio
async def test_status_new_oem_odometer_applies_ac003(api: _Api, ready_vehicle):
    add_odometer(api.session, ready_vehicle, 12_300, NOW + timedelta(minutes=5))

    data = (await api.client.get(f"/api/v1/user-vehicles/{ready_vehicle.id}/maintenance-status", headers=AUTH)).json()[
        "data"
    ]

    assert data["dueStatus"] == "OVERDUE"
    assert data["remainingKm"] == -300


@pytest.mark.asyncio
async def test_status_odometer_never_goes_down_ac006(api: _Api, ready_vehicle):
    add_odometer(api.session, ready_vehicle, 12_300, NOW + timedelta(minutes=5))
    add_odometer(api.session, ready_vehicle, 12_100, NOW + timedelta(minutes=10))

    data = (await api.client.get(f"/api/v1/user-vehicles/{ready_vehicle.id}/maintenance-status", headers=AUTH)).json()[
        "data"
    ]

    assert data["odometer"]["odoKm"] == 12_300


@pytest.mark.asyncio
async def test_status_time_only_when_oem_has_no_odometer_ac002(api: _Api):
    vehicle = add_vehicle(api.session, add_owner(api.session))
    add_rules(api.session)
    mark_synced(api.session, vehicle)

    data = (await api.client.get(f"/api/v1/user-vehicles/{vehicle.id}/maintenance-status", headers=AUTH)).json()["data"]

    assert data["calculationBasis"] == "TIME_ONLY"
    assert data["remainingKm"] is None
    assert data["odometer"] is None
    assert data["dueStatus"] == "NORMAL"


@pytest.mark.asyncio
async def test_status_unknown_before_first_sync_self_heals_ac011(api: _Api):
    vehicle = add_vehicle(api.session, add_owner(api.session))
    add_rules(api.session)

    data = (await api.client.get(f"/api/v1/user-vehicles/{vehicle.id}/maintenance-status", headers=AUTH)).json()["data"]

    assert data["dueStatus"] == "UNKNOWN"
    assert data["unknownReason"] == "OEM_DATA_NOT_SYNCED"
    assert data["nextMilestone"] is None
    assert api.scheduler.calls == [(vehicle.id, OemSyncTrigger.INITIAL, 0)]


@pytest.mark.asyncio
async def test_status_no_self_heal_when_sync_just_attempted(api: _Api):
    vehicle = add_vehicle(api.session, add_owner(api.session))
    api.session.add(VehicleOemSync(user_vehicle_id=vehicle.id, last_attempt_at=NOW - timedelta(minutes=1)))
    api.session.commit()

    await api.client.get(f"/api/v1/user-vehicles/{vehicle.id}/maintenance-status", headers=AUTH)

    assert api.scheduler.calls == []


@pytest.mark.asyncio
async def test_status_unknown_without_maintenance_rules_ef003(api: _Api):
    vehicle = add_vehicle(api.session, add_owner(api.session))
    mark_synced(api.session, vehicle)
    add_odometer(api.session, vehicle, 5_200)

    data = (await api.client.get(f"/api/v1/user-vehicles/{vehicle.id}/maintenance-status", headers=AUTH)).json()["data"]

    assert data["dueStatus"] == "UNKNOWN"
    assert data["unknownReason"] == "NO_MAINTENANCE_RULE"
    assert data["odometer"]["odoKm"] == 5_200


@pytest.mark.asyncio
async def test_status_next_milestone_after_oem_service_ac007(api: _Api, ready_vehicle):
    api.session.add(
        VehicleServiceRecord(
            user_vehicle_id=ready_vehicle.id,
            source=ServiceRecordSource.OEM,
            external_order_id="SH-001",
            service_date=date(2026, 9, 1),
            odo_km=12_100,
        )
    )
    api.session.commit()

    data = (await api.client.get(f"/api/v1/user-vehicles/{ready_vehicle.id}/maintenance-status", headers=AUTH)).json()[
        "data"
    ]

    assert data["nextMilestone"]["odoMilestoneKm"] == 24_000
    assert data["lastService"]["type"] == "OEM_SERVICE_RECORD"
    assert data["dueStatus"] == "NORMAL"


@pytest.mark.asyncio
async def test_status_ignores_non_periodic_repair_q304(api: _Api, ready_vehicle):
    api.session.add(
        VehicleServiceRecord(
            user_vehicle_id=ready_vehicle.id,
            source=ServiceRecordSource.OEM,
            external_order_id="SH-REPAIR",
            service_date=date(2026, 9, 20),
            odo_km=11_500,
            is_periodic=False,
        )
    )
    api.session.commit()

    data = (await api.client.get(f"/api/v1/user-vehicles/{ready_vehicle.id}/maintenance-status", headers=AUTH)).json()[
        "data"
    ]

    # The repair is not a baseline: still measured from the purchase date.
    assert data["lastService"]["type"] == "PURCHASE_DATE"
    assert data["nextMilestone"]["odoMilestoneKm"] == 12_000
    assert data["dueStatus"] == "DUE_SOON"


# ── Guards (API spec §C.2) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_other_owners_vehicle_is_not_found_ac008(api: _Api, ready_vehicle):
    add_owner(api.session, uid="uid-2", email="owner2@example.com")
    api.sign_in_as("uid-2")

    for path in ("", "/maintenance-status"):
        r = await api.client.get(f"/api/v1/user-vehicles/{ready_vehicle.id}{path}", headers=AUTH)
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "VEHICLE_NOT_FOUND"


@pytest.mark.asyncio
async def test_unknown_vehicle_id_is_not_found(api: _Api, ready_vehicle):
    r = await api.client.get(f"/api/v1/user-vehicles/{uuid4()}", headers=AUTH)

    assert r.status_code == 404


@pytest.mark.asyncio
async def test_unlinked_vehicle_is_not_active_ef004(api: _Api):
    vehicle = add_vehicle(api.session, add_owner(api.session), link_status=VehicleLinkStatus.UNLINKED)

    r = await api.client.get(f"/api/v1/user-vehicles/{vehicle.id}", headers=AUTH)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "VEHICLE_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_onboarding_required(api: _Api):
    add_owner(api.session, onboarding_status=OnboardingStatus.ONBOARDING_IN_PROGRESS)

    r = await api.client.get("/api/v1/user-vehicles", headers=AUTH)

    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ONBOARDING_REQUIRED"


@pytest.mark.asyncio
async def test_workshop_owner_token_is_forbidden(api: _Api):
    api.session.add(WorkshopOwner(firebase_uid="ws-uid", email="ws@example.com"))
    api.session.commit()
    api.sign_in_as("ws-uid")

    r = await api.client.get("/api/v1/user-vehicles", headers=AUTH)

    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_unregistered_user(api: _Api):
    api.sign_in_as("nobody")

    r = await api.client.get("/api/v1/user-vehicles", headers=AUTH)

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "USER_NOT_REGISTERED"


@pytest.mark.asyncio
async def test_invalid_vehicle_id_is_bad_request(api: _Api, ready_vehicle):
    r = await api.client.get("/api/v1/user-vehicles/not-a-uuid", headers=AUTH)

    assert r.status_code == 400
    assert r.json()["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_no_endpoint_to_write_odometer_ac005(api: _Api, ready_vehicle):
    r = await api.client.post(
        f"/api/v1/user-vehicles/{ready_vehicle.id}/odometer-readings",
        json={"odoKm": 13_000},
        headers=AUTH,
    )

    assert r.status_code in (404, 405)


# ── API-VEH-004 ────────────────────────────────────────────────────────────


def _webhook_request(body: dict, *, secret: str = SECRET, event_id: str = "evt_api_1"):
    raw = json.dumps(body).encode()
    ts = int(NOW.timestamp())
    return raw, {
        "Content-Type": "application/json",
        "X-OEM-Event-Id": event_id,
        "X-OEM-Timestamp": str(ts),
        "X-OEM-Signature": sign_webhook(secret, ts, raw),
    }


@pytest.mark.asyncio
async def test_webhook_accepted_and_sync_scheduled_ac010(api: _Api, ready_vehicle):
    raw, headers = _webhook_request(
        {
            "eventType": "vehicle.service_history.updated",
            "vehicleId": "VEH-006",
            "occurredAt": "2026-09-28T02:00:00Z",
        }
    )

    r = await api.client.post("/api/v1/integrations/oem/webhooks", content=raw, headers=headers)

    assert r.status_code == 202
    assert r.json()["data"] == {
        "eventId": "evt_api_1",
        "accepted": True,
        "duplicate": False,
        "ignored": False,
    }
    assert api.scheduler.calls == [(ready_vehicle.id, OemSyncTrigger.WEBHOOK, 10)]


@pytest.mark.asyncio
async def test_webhook_bad_signature_is_401(api: _Api, ready_vehicle):
    raw, headers = _webhook_request(
        {"eventType": "vehicle.usage.updated", "vehicleId": "VEH-006", "occurredAt": "2026-09-28T02:00:00Z"},
        secret="wrong",
    )

    r = await api.client.post("/api/v1/integrations/oem/webhooks", content=raw, headers=headers)

    assert r.status_code == 401
    assert r.json()["error"]["code"] == "WEBHOOK_SIGNATURE_INVALID"
    assert api.scheduler.calls == []


@pytest.mark.asyncio
async def test_webhook_unsupported_event_is_422(api: _Api, ready_vehicle):
    raw, headers = _webhook_request(
        {"eventType": "vehicle.deleted", "vehicleId": "VEH-006", "occurredAt": "2026-09-28T02:00:00Z"}
    )

    r = await api.client.post("/api/v1/integrations/oem/webhooks", content=raw, headers=headers)

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "UNSUPPORTED_EVENT_TYPE"
