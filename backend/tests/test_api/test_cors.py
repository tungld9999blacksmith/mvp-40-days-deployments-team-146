"""CORS origins come from CORS_ORIGINS plus FRONTEND_URL."""

import pytest


@pytest.mark.parametrize(
    ("cors_origins", "frontend_url", "expected"),
    [
        ("", "", []),
        ("http://localhost:5173", "", ["http://localhost:5173"]),
        ("", "https://ev-care.vercel.app/", ["https://ev-care.vercel.app"]),
        (
            "http://localhost:3000, http://localhost:5173",
            "http://localhost:5173",
            ["http://localhost:3000", "http://localhost:5173"],
        ),
        ("*", "https://ev-care.vercel.app", ["*", "https://ev-care.vercel.app"]),
    ],
)
def test_cors_allow_origins_merges_both_variables(cors_origins, frontend_url, expected):
    from src.main import cors_allow_origins

    assert cors_allow_origins(cors_origins, frontend_url) == expected


@pytest.mark.asyncio
async def test_preflight_echoes_an_allowed_origin(client):
    from src.main import allowed_origins

    if not allowed_origins or "*" in allowed_origins:
        pytest.skip("No explicit CORS origin configured in this environment")
    origin = allowed_origins[0]

    response = await client.options(
        "/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )

    assert response.headers.get("access-control-allow-origin") == origin
