"""Redis GEO cache of workshop coordinates used by the nearby searches (API-BK-01, quick booking).

In-memory SQLite + fakeredis (GEOSEARCH BYRADIUS is supported by fakeredis).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fakeredis import FakeAsyncRedis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.common.core.workshop import WorkshopStatus
from src.infrastructure.redis import RedisToolkit
from src.modules.booking.domain import BookingConfig
from src.modules.booking.geo_index import WorkshopGeoIndex
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.booking.service import BookingService
from tests._maintenance import add_workshop, make_session
from tests._user_vehicle import add_owner

# Hoan Kiem, Hanoi — the search anchor.
LAT, LNG = 21.0285, 105.8542


@pytest.fixture
def session():
    yield from make_session()


@pytest_asyncio.fixture
async def toolkit():
    redis = FakeAsyncRedis()
    tk = RedisToolkit(redis, key_prefix="test", default_cache_ttl=60)
    yield tk
    await tk.pubsub.stop()
    await tk.cache.write_back_buffer.stop(final_flush=False)
    await redis.flushall()
    await redis.aclose()


def _workshop(session, name: str, km_north: float | None, **kwargs):
    """A workshop ``km_north`` km north of the anchor (≈ 0.009° latitude per km); None = no coordinates."""
    w = add_workshop(session, name=name, **kwargs)
    if km_north is not None:
        w.latitude = Decimal(str(round(LAT + km_north * 0.008993, 6)))
        w.longitude = Decimal(str(LNG))
        session.add(w)
        session.commit()
        session.refresh(w)
    return w


def _touch(session, workshop):
    """Bump updated_at past SQLite's one-second resolution, like a later edit would."""
    workshop.updated_at = datetime.now(UTC) + timedelta(seconds=5)
    session.add(workshop)
    session.commit()


async def _nearby(session, toolkit, user, *, limit: int, candidates: int = 20):
    service = BookingService(
        session, toolkit, SimpleTextLocationFinder(), config=BookingConfig(geo_candidates=candidates)
    )
    data = await service.find_nearby(
        user,
        anchor_source=None,
        lat=LAT,
        lng=LNG,
        query=None,
        province=None,
        user_vehicle_id=None,
        d=None,
        time_slot=None,
        limit=limit,
    )
    return [w.name for w in data.workshops]


@pytest.mark.asyncio
async def test_nearest_ids_are_sorted_and_limited(session, toolkit):
    far = _workshop(session, "Far", 30)
    near = _workshop(session, "Near", 1)
    mid = _workshop(session, "Mid", 5)
    _workshop(session, "No coords", None)
    _workshop(session, "Inactive", 0.5, status=WorkshopStatus.INACTIVE)

    index = WorkshopGeoIndex(toolkit, candidates=2)
    assert await index.nearest_ids(session, LAT, LNG, limit=2) == [near.id, mid.id]
    assert await index.nearest_ids(session, LAT, LNG, limit=5) == [near.id, mid.id, far.id]


@pytest.mark.asyncio
async def test_index_is_rebuilt_when_workshops_change(session, toolkit):
    near = _workshop(session, "Near", 2)
    index = WorkshopGeoIndex(toolkit, candidates=5)
    assert await index.nearest_ids(session, LAT, LNG, limit=5) == [near.id]

    nearer = _workshop(session, "Nearer", 1)  # onboarded later
    assert await index.nearest_ids(session, LAT, LNG, limit=5) == [nearer.id, near.id]

    nearer.status = WorkshopStatus.INACTIVE  # deactivated
    nearer.owner_id = None
    _touch(session, nearer)
    assert await index.nearest_ids(session, LAT, LNG, limit=5) == [near.id]

    near.latitude = Decimal(str(LAT + 50 * 0.008993))  # moved 50 km away
    _touch(session, near)
    far_again = _workshop(session, "Close", 10)
    assert await index.nearest_ids(session, LAT, LNG, limit=5) == [far_again.id, near.id]


@pytest.mark.asyncio
async def test_redis_failure_falls_back_to_table_scan(session, toolkit):
    _workshop(session, "Near", 1)
    toolkit.redis.get = AsyncMock(side_effect=RedisConnectionError("down"))
    index = WorkshopGeoIndex(toolkit)
    assert await index.nearest_ids(session, LAT, LNG, limit=5) is None

    user = add_owner(session)
    service = BookingService(session, toolkit, SimpleTextLocationFinder(), config=BookingConfig())
    service.geo_index = index
    data = await service.find_nearby(
        user,
        anchor_source=None,
        lat=LAT,
        lng=LNG,
        query=None,
        province=None,
        user_vehicle_id=None,
        d=None,
        time_slot=None,
        limit=5,
    )
    assert [w.name for w in data.workshops] == ["Near"]


@pytest.mark.asyncio
async def test_find_nearby_with_geo_matches_full_ranking(session, toolkit):
    """Narrowing by GEO keeps the preferred workshop (even far away) and the ones without coordinates."""
    user = add_owner(session)
    for i, km in enumerate([3, 1, 8, 2, 15, 40]):
        _workshop(session, f"W{i} {km}km", km)
    preferred = _workshop(session, "Preferred far", 200)
    _workshop(session, "No coords", None)
    user.preferred_workshop_id = preferred.id
    session.add(user)
    session.commit()

    # candidates=2 → Redis returns only the 3 nearest (max(limit, candidates)); the rest must still be right.
    names = await _nearby(session, toolkit, user, limit=3, candidates=2)
    assert names == ["Preferred far", "W1 1km", "W3 2km"]

    names = await _nearby(session, toolkit, user, limit=10, candidates=2)
    assert names == [
        "Preferred far",
        "W1 1km",
        "W3 2km",
        "W0 3km",
        "W2 8km",
        "W4 15km",
        "W5 40km",
        "No coords",
    ]
    assert await toolkit.redis.exists(WorkshopGeoIndex(toolkit)._index.key)
