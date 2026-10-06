"""Registration, resume and verification share the same demo account state."""

from datetime import UTC, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.demo.dependency import make_services
from src.demo.main import create_app
from src.demo.store import DemoStore


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DEMO_WORKSHOP_OWNERS", raising=False)
    services = make_services(DemoStore(skip_onboarding=False, clock=lambda: datetime(2026, 10, 4, tzinfo=UTC)))
    with TestClient(
        create_app(
            services, token_verifier=lambda uid: {"uid": uid, "email": f"{uid}@example.com", "email_verified": True}
        )
    ) as c:
        yield c


def auth(uid="driver", key=None):
    return {"Authorization": f"Bearer {uid}", **({"Idempotency-Key": key} if key else {})}


@pytest.mark.parametrize("portal", ["owner", "workshop"])
def test_registration_survives_backend_restart(tmp_path, monkeypatch, portal):
    path = tmp_path / "registration.json"
    monkeypatch.setenv("DEMO_REGISTRATION_FILE", str(path))
    monkeypatch.delenv("DEMO_WORKSHOP_OWNERS", raising=False)
    uid = "driver" if portal == "owner" else "workshop1"
    base = "/api/v1" + ("" if portal == "owner" else "/workshop-owner")

    def boot():
        return TestClient(
            create_app(
                make_services(),
                token_verifier=lambda token: {
                    "uid": token,
                    "email": f"{token}@example.com",
                    "email_verified": True,
                },
            )
        )

    profile = {
        **PROFILE,
        **(
            {
                "location": {
                    "addressLine": "123 Demo",
                    "province": "Ha Noi",
                    "source": "MANUAL",
                }
            }
            if portal == "owner"
            else {}
        ),
    }
    endpoint = "/onboarding/vehicle-verification" if portal == "owner" else "/onboarding/workshop-verification"
    body = (
        VEHICLE
        if portal == "owner"
        else {
            "address": "123 Demo",
            "hotline": "0901234567",
            "totalTechnicians": 2,
            "emergencySlotsReserved": 0,
            "operatingHours": [
                {"dayOfWeek": d, "isClosed": False, "openTime": "08:00", "closeTime": "18:00"} for d in range(1, 8)
            ],
            "oemDataSharingConsent": VEHICLE["oemDataSharingConsent"],
        }
    )
    with boot() as c:
        assert c.post(base + "/oauth/sign-in", headers=auth(uid)).json()["data"]["onboarding"]["nextStep"] == "PROFILE"
        assert c.put(base + "/onboarding/profile", headers=auth(uid), json=profile).status_code == 200
    with boot() as c:
        state = c.post(base + "/oauth/sign-in", headers=auth(uid)).json()["data"]["onboarding"]
        assert state["nextStep"] == ("VEHICLE" if portal == "owner" else "WORKSHOP")
        result = c.post(base + endpoint, headers=auth(uid, "persisted-verify"), json=body).json()
        assert result["data"]["onboarding"]["status"] == "ACTIVE"
    with boot() as c:
        state = c.post(base + "/oauth/sign-in", headers=auth(uid)).json()["data"]["onboarding"]
        assert state["status"] == "ACTIVE"
        assert state["nextStep"] == ("HOME" if portal == "owner" else "DASHBOARD")
        assert c.post(base + endpoint, headers=auth(uid, "persisted-verify"), json=body).json() == result
        assert (
            c.post("/api/v1/oauth/sign-in", headers=auth("new-driver")).json()["data"]["onboarding"]["nextStep"]
            == "PROFILE"
        )
        if portal == "owner":
            assert len(c.get("/api/v1/user-vehicles", headers=auth(uid)).json()["data"]) == 1
        else:
            assert (
                c.get(base + "/onboarding", headers=auth(uid)).json()["data"]["workshop"]["hotline"] == body["hotline"]
            )
            assert c.post(base + "/oauth/sign-in", headers=auth("new-driver")).status_code == 403
    assert "000000001234" not in path.read_text(encoding="utf-8")


PROFILE = {
    "fullName": "Nguyễn Minh Anh",
    "phoneNumber": "0901234567",
    "nationalId": "000000001234",
    "personalDataConsent": {"granted": True, "policyVersion": "2026-09"},
}
VEHICLE = {
    "vin": "VF6ECO20240000001",
    "licensePlate": "51A-11111",
    "modelId": "MDL-02",
    "manufactureYear": 2024,
    "oemDataSharingConsent": {"granted": True, "policyVersion": "2026-09"},
}


def test_owner_registration_resume_failure_retry_and_replay(client):
    c = client
    signed = c.post("/api/v1/oauth/sign-in", headers=auth()).json()["data"]
    assert signed["isNewUser"] and signed["onboarding"]["nextStep"] == "PROFILE"
    assert c.get("/api/v1/user-vehicles", headers=auth()).json()["data"] == []
    assert c.post("/api/v1/onboarding/vehicle-verification", headers=auth(key="early"), json=VEHICLE).status_code == 409
    profile = {
        **PROFILE,
        "dateOfBirth": None,
        "location": {"addressLine": "123 Đường Demo", "province": "Hà Nội", "source": "MANUAL"},
    }
    assert (
        c.put("/api/v1/onboarding/profile", headers=auth(), json={**profile, "nationalId": "123456789"}).status_code
        == 400
    )
    assert (
        c.put("/api/v1/onboarding/profile", headers=auth(), json=profile).json()["data"]["onboarding"]["nextStep"]
        == "VEHICLE"
    )
    snapshot = c.get("/api/v1/onboarding", headers=auth()).json()["data"]
    assert (
        snapshot["profile"]["fullName"] == PROFILE["fullName"]
        and snapshot["profile"]["nationalIdMasked"] == "********1234"
    )
    assert "nationalId" not in snapshot["profile"]
    assert c.get("/api/v1/onboarding", headers=auth("other")).json()["data"]["onboarding"]["nextStep"] == "PROFILE"
    failed = c.post(
        "/api/v1/onboarding/vehicle-verification", headers=auth(key="bad"), json={**VEHICLE, "vin": "AAAAAAAAAAAAAAAAA"}
    ).json()["data"]
    assert (
        failed["verification"]["failureReason"] == "VIN_NOT_FOUND" and failed["verification"]["remainingAttempts"] == 2
    )
    verified = c.post("/api/v1/onboarding/vehicle-verification", headers=auth(key="verify"), json=VEHICLE)
    assert verified.json()["data"]["onboarding"]["status"] == "ACTIVE"
    assert len(c.get("/api/v1/user-vehicles", headers=auth()).json()["data"]) == 1
    assert (
        c.post("/api/v1/onboarding/vehicle-verification", headers=auth(key="verify"), json=VEHICLE).json()
        == verified.json()
    )
    assert (
        c.post(
            "/api/v1/onboarding/vehicle-verification",
            headers=auth(key="verify"),
            json={**VEHICLE, "licensePlate": "30A-12345"},
        ).status_code
        == 409
    )
    assert c.get("/api/v1/onboarding", headers=auth()).json()["data"]["vehicle"]["vin"] == VEHICLE["vin"]
    assert c.post("/api/v1/oauth/sign-in", headers=auth()).json()["data"]["onboarding"]["status"] == "ACTIVE"


def test_workshop_registration_keeps_role_scope_and_resumes(client):
    c = client
    base = "/api/v1/workshop-owner"
    assert c.post(f"{base}/oauth/sign-in", headers=auth()).status_code == 403
    assert (
        c.post(f"{base}/oauth/sign-in", headers=auth("workshop1")).json()["data"]["onboarding"]["nextStep"] == "PROFILE"
    )
    assert (
        c.put(f"{base}/onboarding/profile", headers=auth("workshop1"), json=PROFILE).json()["data"]["onboarding"][
            "nextStep"
        ]
        == "WORKSHOP"
    )
    hours = [{"dayOfWeek": d, "isClosed": False, "openTime": "08:00", "closeTime": "18:00"} for d in range(1, 8)]
    body = {
        "address": "123 Đường Demo",
        "latitude": None,
        "longitude": None,
        "hotline": "0901234567",
        "totalTechnicians": 2,
        "emergencySlotsReserved": 0,
        "operatingHours": hours,
        "oemDataSharingConsent": VEHICLE["oemDataSharingConsent"],
    }
    assert (
        c.post(
            f"{base}/onboarding/workshop-verification",
            headers=auth("workshop1", "bad"),
            json={**body, "operatingHours": []},
        ).status_code
        == 400
    )
    response = c.post(f"{base}/onboarding/workshop-verification", headers=auth("workshop1", "verify"), json=body)
    assert response.json()["data"]["onboarding"]["status"] == "ACTIVE"
    assert response.json()["data"]["workshop"]["hotline"] == body["hotline"]
    assert (
        c.post(f"{base}/onboarding/workshop-verification", headers=auth("workshop1", "verify"), json=body).json()
        == response.json()
    )
    assert (
        c.get(f"{base}/onboarding", headers=auth("workshop1")).json()["data"]["registration"]["address"]
        == body["address"]
    )
    assert c.get(f"{base}/oauth/session", headers=auth("workshop1")).json()["data"]["onboarding"]["status"] == "ACTIVE"
    assert c.get(f"{base}/onboarding", headers=auth("workshop2")).json()["data"]["onboarding"]["nextStep"] == "PROFILE"
