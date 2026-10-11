"""Location search over HTTP (API-LOC-001..003) with the fake provider, fakeredis and SQLite."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from httpx import ASGITransport, AsyncClient

from src.common.core.identity.vehicle_user import OnboardingStatus, UserStatus
from src.common.core.identity.workshop_owner import WorkshopOwnerOnboardingStatus
from src.config import get_settings
from src.infrastructure.location import FakePlacesProvider
from src.infrastructure.redis import RedisToolkit
from src.infrastructure.redis.dependency import get_redis_toolkit
from src.infrastructure.supabase.db import get_session
from src.main import app
from src.modules.location.dependency import get_place_search_provider
from src.modules.location.ports import ProviderUnavailableError
from src.modules.oauth.dependency import verify_firebase_token
from tests._maintenance import add_workshop_owner, make_session
from tests._user_vehicle import add_owner


class _DownProvider(FakePlacesProvider):
    async def suggest(self, query, *, near, limit):
        raise ProviderUnavailableError("down")

    async def get_place(self, place_id):
        raise ProviderUnavailableError("down", misconfigured=True)


@pytest_asyncio.fixture
async def ctx():
    gen = make_session()
    session = next(gen)
    redis = FakeAsyncRedis()
    toolkit = RedisToolkit(redis, key_prefix="test", default_cache_ttl=60)
    state = {"uid": "uid-1", "provider": FakePlacesProvider()}

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_redis_toolkit] = lambda: toolkit
    app.dependency_overrides[verify_firebase_token] = lambda: {"uid": state["uid"]}
    app.dependency_overrides[get_place_search_provider] = lambda: state["provider"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session, state
    app.dependency_overrides.clear()
    await redis.flushall()
    await redis.aclose()
    gen.close()


@pytest.mark.asyncio
async def test_suggest_returns_envelope_sorted_by_distance(ctx):
    client, session, _ = ctx
    add_owner(session)

    resp = await client.get("/api/v1/locations/suggest", params={"q": "  cau   giay ", "lat": 21.03, "lng": 105.79})

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["query"] == "cau giay"
    titles = [i["title"] for i in data["items"]]
    # "VinFast Thăng Long" matches through its address (Phường Cầu Giấy).
    assert set(titles) == {"Cầu Giấy", "Công viên Cầu Giấy", "VinFast Thăng Long"}
    first = data["items"][0]
    assert set(first) == {"placeId", "title", "address", "placeType", "position", "distanceMeters", "highlights"}
    assert first["position"].keys() == {"lat", "lng"}
    distances = [i["distanceMeters"] for i in data["items"]]
    assert distances == sorted(distances)
    assert "X-RateLimit-Limit" not in resp.headers  # no rate-limit headers leak from the custom guard


@pytest.mark.asyncio
async def test_suggest_without_results_is_an_empty_list(ctx):
    client, session, _ = ctx
    add_owner(session)
    resp = await client.get("/api/v1/locations/suggest", params={"q": "khong co dau"})
    assert resp.status_code == 200
    assert resp.json()["data"]["items"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"q": " a "}, "q"),
        ({"q": "x" * 201}, "q"),
        ({"q": "cau giay", "lat": 21.0}, "lng"),
        ({"q": "cau giay", "limit": 11}, "limit"),
        ({"q": "cau giay", "lat": 91, "lng": 105}, "lat"),
    ],
)
async def test_suggest_invalid_request_is_enveloped_422(ctx, params, field):
    client, session, _ = ctx
    add_owner(session)
    resp = await client.get("/api/v1/locations/suggest", params=params)
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "INVALID_REQUEST"
    assert error["details"]["field"] == field


@pytest.mark.asyncio
async def test_onboarding_vehicle_owner_and_workshop_owner_may_search(ctx):
    client, session, state = ctx
    add_owner(session, uid="uid-onb", onboarding_status=OnboardingStatus.ONBOARDING_IN_PROGRESS)
    owner = add_workshop_owner(session, uid="ws-1")
    owner.onboarding_status = WorkshopOwnerOnboardingStatus.ONBOARDING_IN_PROGRESS
    session.add(owner)
    session.commit()

    for uid in ("uid-onb", "ws-1"):
        state["uid"] = uid
        resp = await client.get("/api/v1/locations/suggest", params={"q": "vinfast"})
        assert resp.status_code == 200, uid


@pytest.mark.asyncio
async def test_unregistered_or_locked_caller_is_forbidden(ctx):
    client, session, state = ctx
    state["uid"] = "stranger"
    resp = await client.get("/api/v1/locations/suggest", params={"q": "vinfast"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"

    add_owner(session, uid="locked", status=UserStatus.SUSPENDED)
    state["uid"] = "locked"
    resp = await client.get("/api/v1/locations/suggest", params={"q": "vinfast"})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "ACCOUNT_LOCKED"


@pytest.mark.asyncio
async def test_suggest_rate_limit_returns_429_with_retry_after(ctx, monkeypatch):
    client, session, _ = ctx
    add_owner(session)
    monkeypatch.setattr(get_settings(), "location_suggest_rate_per_minute", 3)  # burst = 1

    first = await client.get("/api/v1/locations/suggest", params={"q": "vinfast"})
    second = await client.get("/api/v1/locations/suggest", params={"q": "vinfast"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert int(second.headers["Retry-After"]) >= 1
    assert second.json()["error"]["details"]["retryAfterSeconds"] == int(second.headers["Retry-After"])


@pytest.mark.asyncio
async def test_rate_limiter_down_fails_open(ctx, monkeypatch):
    client, session, _ = ctx
    add_owner(session)
    from redis.exceptions import ConnectionError as RedisConnectionError

    async def boom(*args, **kwargs):
        raise RedisConnectionError("down")

    monkeypatch.setattr("src.infrastructure.redis.ratelimit.token_bucket.TokenBucketLimiter.try_acquire", boom)
    resp = await client.get("/api/v1/locations/suggest", params={"q": "vinfast"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_provider_down_is_503(ctx):
    client, session, state = ctx
    add_owner(session)
    state["provider"] = _DownProvider()

    resp = await client.get("/api/v1/locations/suggest", params={"q": "vinfast"})
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "LOCATION_PROVIDER_UNAVAILABLE"
    resp = await client.get("/api/v1/locations/places/fake-q7")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_place_detail_maps_onto_location_in(ctx):
    client, session, _ = ctx
    add_owner(session)

    resp = await client.get("/api/v1/locations/places/fake-vf-thang-long")

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["placeId"] == "fake-vf-thang-long"
    assert data["province"] == "Hà Nội" and data["countryCode"] == "VN"
    assert data["addressLine"].startswith("Số 1 Phạm Văn Bạch")
    assert data["position"] == {"lat": 21.0303, "lng": 105.7915}
    assert data["provider"] == "fake"


@pytest.mark.asyncio
async def test_unknown_place_is_404(ctx):
    client, session, _ = ctx
    add_owner(session)
    resp = await client.get("/api/v1/locations/places/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "LOCATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_reverse_keeps_the_requested_position(ctx):
    client, session, _ = ctx
    add_owner(session)
    resp = await client.get("/api/v1/locations/reverse", params={"lat": 10.7726, "lng": 106.6981})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["title"] == "Chợ Bến Thành"
    assert data["province"] == "TP. Hồ Chí Minh"
    assert data["position"] == {"lat": 10.7726, "lng": 106.6981}


@pytest.mark.asyncio
async def test_reverse_outside_vietnam_is_422_and_far_from_anything_is_404(ctx):
    client, session, _ = ctx
    add_owner(session)
    resp = await client.get("/api/v1/locations/reverse", params={"lat": 13.75, "lng": 100.5})  # Bangkok
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "LOCATION_OUT_OF_COVERAGE"

    resp = await client.get("/api/v1/locations/reverse", params={"lat": 12.0, "lng": 108.0})  # nothing in the fake
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "LOCATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_reverse_requires_both_coordinates(ctx):
    client, session, _ = ctx
    add_owner(session)
    resp = await client.get("/api/v1/locations/reverse", params={"lat": 21.0})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "INVALID_REQUEST"
