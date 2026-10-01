import pytest


@pytest.mark.asyncio
async def test_create_vehicle_returns_201(client):
    response = await client.post(
        "/api/v1/vehicles/",
        json={
            "license_plate": "59a-12345",
            "brand": "Toyota",
            "model": "Camry",
            "year": 2024,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["license_plate"] == "59A-12345"
    assert body["owner_id"] == "user-demo-001"


@pytest.mark.asyncio
async def test_create_vehicle_rejects_invalid_year(client):
    response = await client.post(
        "/api/v1/vehicles/",
        json={
            "license_plate": "59A-12345",
            "brand": "Toyota",
            "model": "Camry",
            "year": 1800,
        },
    )
    assert response.status_code == 422
