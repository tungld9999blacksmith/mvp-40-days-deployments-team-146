import pytest

from src.main import app
from src.modules.oauth.dependency import verify_firebase_token


@pytest.mark.asyncio
async def test_profile_requires_authorization_header(client):
    response = await client.get("/api/v1/oauth/profile")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_profile_returns_decoded_token_claims(client):
    app.dependency_overrides[verify_firebase_token] = lambda: {
        "uid": "firebase-uid-123",
        "email": "user@example.com",
    }
    try:
        response = await client.get(
            "/api/v1/oauth/profile",
            headers={"Authorization": "Bearer fake-token"},
        )
    finally:
        app.dependency_overrides.pop(verify_firebase_token, None)

    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == "firebase-uid-123"
    assert body["email"] == "user@example.com"
