"""Regression tests for the mock-ev-system ownership verification endpoint."""

import pytest
from fastapi.testclient import TestClient
from mock_ev_system.main import app


@pytest.fixture(scope="module")
def mock_client():
    with TestClient(app) as client:
        yield client


# Manufacturer record for VEH-006 (owner OWN-004).
_BASE = {
    "vin": "VF6PLUS2024000001",
    "license_plate": "29A-444.44",
    "model_id": "MDL-03",
    "email": "dung.pham@example.com",
    "national_id": "079200001004",
}


def test_verify_ownership_success(mock_client):
    resp = mock_client.post("/vehicles/verify-ownership", json=_BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["vehicle"]["model_name"] == "VF6"
    assert body["vehicle"]["external_owner_id"] == "OWN-004"
    assert len(body["warranties"]) == 4


@pytest.mark.parametrize(
    "override,expected",
    [
        ({"vin": "NOSUCHVIN00000000"}, "VIN_NOT_FOUND"),
        ({"license_plate": "99Z-99999"}, "PLATE_MISMATCH"),
        ({"model_id": "MDL-02"}, "MODEL_MISMATCH"),
        ({"email": "someone.else@example.com"}, "OWNER_EMAIL_MISMATCH"),
        ({"national_id": "000000000000"}, "NATIONAL_ID_MISMATCH"),
    ],
)
def test_verify_ownership_failures(mock_client, override, expected):
    payload = {**_BASE, **override}
    resp = mock_client.post("/vehicles/verify-ownership", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is False
    assert body["failure_reason"] == expected
