"""
Typed geospatial index (Redis GEO: members on a 2-D longitude/latitude plane, stored as a geohash-scored sorted set).

    stations = toolkit.geo("charging-stations", member_type=int)
    await stations.add(17, GeoPoint(longitude=105.8342, latitude=21.0278))
    near = await stations.nearby(GeoPoint(longitude=105.85, latitude=21.03), radius=5, unit=GeoUnit.KM, limit=10)
    for hit in near:
        print(hit.member, hit.distance, hit.point)
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis

from .serializers import Serializer, serializer_for

T = TypeVar("T")

# Redis GEO accepts latitudes within ±85.05112878 (Web Mercator limit)
MAX_LATITUDE = 85.05112878


class GeoUnit(StrEnum):
    M = "m"
    KM = "km"
    MI = "mi"
    FT = "ft"


class GeoPoint(BaseModel):
    model_config = ConfigDict(frozen=True)

    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-MAX_LATITUDE, le=MAX_LATITUDE)


@dataclass(frozen=True)
class GeoResult(Generic[T]):
    member: T
    distance: float | None = None
    """Distance from the search center, in the search unit."""
    point: GeoPoint | None = None


class GeoIndex(Generic[T]):
    def __init__(
        self,
        redis: Redis,
        key: str,
        member_type: Any = str,
        *,
        serializer: Serializer[T] | None = None,
    ) -> None:
        self._redis = redis
        self.key = key
        self.serializer: Serializer[T] = serializer or serializer_for(member_type)

    def _enc(self, member: T) -> bytes:
        return self.serializer.dumps(member)

    def _dec(self, raw: bytes) -> T:
        return self.serializer.loads(raw)

    # ------------------------------------------------------------------ write
    async def add(self, member: T, point: GeoPoint, *, nx: bool = False, xx: bool = False) -> bool:
        """Add or move *member*. nx: only add new members; xx: only move existing ones. Returns True if changed."""
        changed = await self._redis.geoadd(
            self.key, [point.longitude, point.latitude, self._enc(member)], nx=nx, xx=xx, ch=True
        )
        return bool(changed)

    async def add_many(self, points: Mapping[T, GeoPoint] | Iterable[tuple[T, GeoPoint]]) -> int:
        items = points.items() if isinstance(points, Mapping) else points
        values: list[Any] = []
        for member, point in items:
            values += [point.longitude, point.latitude, self._enc(member)]
        if not values:
            return 0
        return int(await self._redis.geoadd(self.key, values))

    async def remove(self, *members: T) -> int:
        if not members:
            return 0
        return int(await self._redis.zrem(self.key, *(self._enc(m) for m in members)))

    async def clear(self) -> None:
        await self._redis.delete(self.key)

    # ------------------------------------------------------------------- read
    async def position(self, member: T) -> GeoPoint | None:
        return (await self.positions([member]))[0]

    async def positions(self, members: Iterable[T]) -> list[GeoPoint | None]:
        encoded = [self._enc(m) for m in members]
        if not encoded:
            return []
        rows = await self._redis.geopos(self.key, *encoded)
        return [None if row is None else GeoPoint(longitude=row[0], latitude=row[1]) for row in rows]

    async def distance(self, a: T, b: T, unit: GeoUnit = GeoUnit.KM) -> float | None:
        value = await self._redis.geodist(self.key, self._enc(a), self._enc(b), unit=unit.value)
        return None if value is None else float(value)

    async def geohash(self, member: T) -> str | None:
        (value,) = await self._redis.geohash(self.key, self._enc(member))
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    async def contains(self, member: T) -> bool:
        return await self._redis.zscore(self.key, self._enc(member)) is not None

    async def size(self) -> int:
        return int(await self._redis.zcard(self.key))

    # ----------------------------------------------------------------- search
    async def search(
        self,
        center: GeoPoint | T,
        *,
        radius: float | None = None,
        width: float | None = None,
        height: float | None = None,
        unit: GeoUnit = GeoUnit.KM,
        limit: int | None = None,
        sort: Literal["ASC", "DESC"] | None = "ASC",
        with_distance: bool = True,
        with_point: bool = True,
        any_match: bool = False,
    ) -> list[GeoResult[T]]:
        """
        GEOSEARCH around *center* (a GeoPoint, or an existing member) within a circle
        (*radius*) or a box (*width* x *height*). `sort="ASC"` = nearest first.
        `any_match=True` returns as soon as *limit* matches are found (faster, not the nearest).
        """
        if (radius is None) == (width is None or height is None):
            raise ValueError("Pass either radius, or both width and height")
        location: dict[str, Any]
        if isinstance(center, GeoPoint):
            location = {"longitude": center.longitude, "latitude": center.latitude}
        else:
            location = {"member": self._enc(center)}
        rows = await self._redis.geosearch(
            self.key,
            **location,
            radius=radius,
            width=width,
            height=height,
            unit=unit.value,
            sort=sort,
            count=limit,
            any=any_match and limit is not None,
            withdist=with_distance,
            withcoord=with_point,
        )
        return [self._result(row, with_distance, with_point) for row in rows]

    def _result(self, row: Any, with_distance: bool, with_point: bool) -> GeoResult[T]:
        if not (with_distance or with_point):
            return GeoResult(self._dec(row))
        # redis-py returns [member, dist?, (lon, lat)?] in that order
        member, *rest = row
        distance = float(rest.pop(0)) if with_distance else None
        point = None
        if with_point:
            lon, lat = rest.pop(0)
            point = GeoPoint(longitude=lon, latitude=lat)
        return GeoResult(self._dec(member), distance, point)

    async def nearby(
        self,
        center: GeoPoint | T,
        radius: float,
        unit: GeoUnit = GeoUnit.KM,
        limit: int | None = None,
    ) -> list[GeoResult[T]]:
        """Members within *radius* of *center*, nearest first."""
        return await self.search(center, radius=radius, unit=unit, limit=limit)

    async def within_box(
        self,
        center: GeoPoint | T,
        width: float,
        height: float,
        unit: GeoUnit = GeoUnit.KM,
        limit: int | None = None,
    ) -> list[GeoResult[T]]:
        """Members inside a *width* x *height* box centered on *center*, nearest first."""
        return await self.search(center, width=width, height=height, unit=unit, limit=limit)
