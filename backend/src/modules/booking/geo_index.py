"""Redis GEO cache of workshop coordinates — narrows "workshops near X" before ranking.

The nearby searches (API-BK-01, quick booking, the agent's ``find_workshops``) used to
load every active workshop and rank them in Python. With a GEO index, Redis returns the
``candidates`` nearest workshop ids (GEOSEARCH, nearest first) and only those rows, plus
the ones the finder must still see (no coordinates — EDGE-412 — and the preferred
workshop), are loaded. ``WorkshopLocationFinder.rank`` then runs unchanged on that
smaller list, so results are identical to the full scan as long as
``candidates >= limit``.

Freshness: the index stores a fingerprint of the workshop table (row counts + latest
``updated_at``). Every search compares it with a cheap aggregate query and rebuilds the
index when it differs, so onboarding / edits / deactivation show up without explicit
invalidation. A TTL is the safety net. Any Redis failure falls back to the full scan.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID, uuid4

from redis.exceptions import RedisError
from sqlalchemy import case, func, or_
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from src.common.core.workshop import Workshop, WorkshopStatus
from src.infrastructure.redis.geo import GeoIndex, GeoPoint, GeoUnit
from src.infrastructure.redis.toolkit import RedisToolkit
from src.infrastructure.supabase.db import run_then_release

logger = logging.getLogger(__name__)

INDEX_NAME = "workshops:active"
# Covers all of Vietnam (≈1,650 km north–south): GEOSEARCH + COUNT then acts as k-nearest.
SEARCH_RADIUS_KM = 3000


def table_fingerprint(session: Session) -> str:
    """Changes when a workshop is added, removed, (de)activated, gains/loses coordinates or is edited.

    ``updated_at`` alone could miss an edit stamped with the same (or an older, transaction-start)
    timestamp, so the indexed-row count is part of the key too; the TTL covers what remains.
    """
    indexed = case(
        (
            (Workshop.status == WorkshopStatus.ACTIVE)
            & Workshop.latitude.is_not(None)
            & Workshop.longitude.is_not(None),
            1,
        ),
        else_=0,
    )
    total, active, latest = session.exec(
        select(func.count(Workshop.id), func.coalesce(func.sum(indexed), 0), func.max(Workshop.updated_at))
    ).one()
    return f"{total}:{active}:{latest.isoformat() if latest else '-'}"


def active_points(session: Session) -> list[tuple[UUID, float, float]]:
    rows = session.exec(
        select(Workshop.id, Workshop.latitude, Workshop.longitude).where(
            Workshop.status == WorkshopStatus.ACTIVE,
            Workshop.latitude.is_not(None),
            Workshop.longitude.is_not(None),
        )
    ).all()
    return [(wid, float(lat), float(lng)) for wid, lat, lng in rows]


def active_workshops(
    session: Session, candidate_ids: Sequence[UUID] | None, preferred_id: UUID | None = None
) -> list[Workshop]:
    """Active workshops to rank: all of them, or the GEO candidates + those without coordinates + preferred."""
    stmt = select(Workshop).where(Workshop.status == WorkshopStatus.ACTIVE)
    if candidate_ids is not None:
        keep = [Workshop.id.in_(list(candidate_ids)), Workshop.latitude.is_(None), Workshop.longitude.is_(None)]
        if preferred_id is not None:
            keep.append(Workshop.id == preferred_id)
        stmt = stmt.where(or_(*keep))
    return list(session.exec(stmt).all())


class WorkshopGeoIndex:
    def __init__(self, toolkit: RedisToolkit, *, ttl_seconds: int = 600, candidates: int = 20) -> None:
        self._redis = toolkit.redis
        self._index: GeoIndex[str] = toolkit.geo(INDEX_NAME, member_type=str)
        self._meta_key = f"{self._index.key}:fingerprint"
        self._ttl = ttl_seconds
        self._candidates = candidates

    async def nearest_ids(self, session: Session, lat: float, lng: float, *, limit: int) -> list[UUID] | None:
        """Ids of the nearest active workshops with coordinates, nearest first.

        ``None`` means "cache unavailable — scan the table instead".
        """
        try:
            fingerprint = await run_in_threadpool(run_then_release, session, table_fingerprint, session)
            if await self._fingerprint() != fingerprint:
                points = await run_in_threadpool(run_then_release, session, active_points, session)
                await self._rebuild(points, fingerprint)
            hits = await self._index.search(
                GeoPoint(latitude=lat, longitude=lng),
                radius=SEARCH_RADIUS_KM,
                unit=GeoUnit.KM,
                limit=max(limit, self._candidates),
                with_distance=False,
                with_point=False,
            )
            return [UUID(hit.member) for hit in hits]
        except (RedisError, OSError, ValueError):
            logger.warning("workshop geo index unavailable, falling back to a table scan", exc_info=True)
            return None

    async def invalidate(self) -> None:
        try:
            await self._redis.delete(self._index.key, self._meta_key)
        except (RedisError, OSError):
            logger.warning("could not invalidate the workshop geo index", exc_info=True)

    async def _fingerprint(self) -> str | None:
        raw = await self._redis.get(self._meta_key)
        return raw.decode() if isinstance(raw, bytes) else raw

    async def _rebuild(self, points: list[tuple[UUID, float, float]], fingerprint: str) -> None:
        """Build into a temp key, then swap it in atomically (RENAME) so readers never see a half index."""
        if points:
            tmp = GeoIndex(self._redis, f"{self._index.key}:tmp:{uuid4().hex}", str)
            await tmp.add_many((str(wid), GeoPoint(latitude=lat, longitude=lng)) for wid, lat, lng in points)
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.rename(tmp.key, self._index.key)
                pipe.expire(self._index.key, self._ttl)
                pipe.set(self._meta_key, fingerprint, ex=self._ttl)
                await pipe.execute()
        else:
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.delete(self._index.key)
                pipe.set(self._meta_key, fingerprint, ex=self._ttl)
                await pipe.execute()
