"""Location search — application service (API-LOC-001..003).

Validates input, calls the place provider and turns provider failures into domain
errors. No caching: Suggest results may not be stored (AWS terms count a cache as storage).
"""

from __future__ import annotations

import logging
import time

from . import errors
from .domain import LatLng, LocationSuggestion, PlaceDetail
from .ports import PlaceNotFoundError, PlaceOutOfCoverageError, PlaceSearchProvider, ProviderUnavailableError

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 200
MAX_PLACE_ID_LENGTH = 500


def normalize_query(raw: str | None) -> str:
    query = " ".join((raw or "").split())
    if not MIN_QUERY_LENGTH <= len(query) <= MAX_QUERY_LENGTH:
        raise errors.InvalidRequestError(f"q must be {MIN_QUERY_LENGTH}-{MAX_QUERY_LENGTH} characters long.", field="q")
    return query


def optional_point(lat: float | None, lng: float | None) -> LatLng | None:
    if (lat is None) != (lng is None):
        raise errors.InvalidRequestError("lat and lng must be sent together.", field="lat" if lat is None else "lng")
    return None if lat is None or lng is None else LatLng(lat=lat, lng=lng)


class LocationService:
    def __init__(self, provider: PlaceSearchProvider) -> None:
        self._provider = provider

    async def suggest(
        self, q: str | None, *, lat: float | None, lng: float | None, limit: int
    ) -> tuple[str, list[LocationSuggestion]]:
        query = normalize_query(q)
        near = optional_point(lat, lng)
        started = time.perf_counter()
        try:
            items = await self._provider.suggest(query, near=near, limit=limit)
        except ProviderUnavailableError as exc:
            raise errors.LocationProviderUnavailableError() from exc
        # Never log the query text itself: a home address is personal data.
        logger.info(
            "location.suggest provider=%s q_len=%d near=%s results=%d latency_ms=%d",
            self._provider.name,
            len(query),
            near is not None,
            len(items),
            (time.perf_counter() - started) * 1000,
        )
        return query, items

    async def get_place(self, place_id: str) -> PlaceDetail:
        place_id = place_id.strip()
        if not 1 <= len(place_id) <= MAX_PLACE_ID_LENGTH:
            raise errors.InvalidRequestError("placeId is invalid.", field="placeId")
        try:
            return await self._provider.get_place(place_id)
        except PlaceNotFoundError as exc:
            raise errors.LocationNotFoundError() from exc
        except PlaceOutOfCoverageError as exc:
            raise errors.LocationOutOfCoverageError() from exc
        except ProviderUnavailableError as exc:
            raise errors.LocationProviderUnavailableError() from exc

    async def reverse(self, lat: float, lng: float) -> PlaceDetail:
        point = LatLng(lat=lat, lng=lng)
        if not point.in_vietnam():
            raise errors.LocationOutOfCoverageError()
        try:
            return await self._provider.reverse(point)
        except PlaceNotFoundError as exc:
            raise errors.LocationNotFoundError() from exc
        except ProviderUnavailableError as exc:
            raise errors.LocationProviderUnavailableError() from exc
