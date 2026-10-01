"""Regression tests for the mock-ev-system workshop-manager verification endpoint."""

import pytest
from fastapi.testclient import TestClient
from mock_ev_system.main import app


@pytest.fixture(scope="module")
def mock_client():
    with TestClient(app) as client:
        yield client


# Manager record for SC-01 (VinFast Thăng Long).
_BASE = {
    "manager_email": "ha.tran.sc01@example.com",
    "manager_national_id": "001190000101",
}


def test_verify_manager_success_returns_the_center(mock_client):
    resp = mock_client.post("/service-centers/verify-manager", json=_BASE)
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["failure_reason"] is None
    assert body["service_center"] == {
        "center_id": "SC-01",
        "name": "VinFast Thăng Long",
        "region": "Hà Nội",
        "type": "dealer",
    }


def test_verify_manager_normalizes_email_and_national_id(mock_client):
    payload = {
        "manager_email": "  HA.Tran.SC01@Example.com ",
        "manager_national_id": "001 190 000 101",
    }
    resp = mock_client.post("/service-centers/verify-manager", json=payload)
    assert resp.json()["verified"] is True


@pytest.mark.parametrize(
    "override,expected",
    [
        ({"manager_email": "nobody@example.com"}, "MANAGER_NOT_FOUND"),
        ({"manager_national_id": "000000000000"}, "NATIONAL_ID_MISMATCH"),
    ],
)
def test_verify_manager_failures(mock_client, override, expected):
    resp = mock_client.post("/service-centers/verify-manager", json={**_BASE, **override})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is False
    assert body["failure_reason"] == expected
    assert body["service_center"] is None


def test_service_center_listing_does_not_leak_manager_identity(mock_client):
    resp = mock_client.get("/service-centers")
    assert resp.status_code == 200
    for center in resp.json():
        assert "manager_email" not in center
        assert "manager_national_id" not in center
