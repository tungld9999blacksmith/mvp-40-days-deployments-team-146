"""Location search — HTTP routes (docs/specs/platform/location-search.api.md)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from . import schemas
from .dependency import detail_caller, get_location_service, suggest_caller
from .service import LocationService

router = APIRouter(prefix="/locations", tags=["location"])

Service = Annotated[LocationService, Depends(get_location_service)]


@router.get(
    "/suggest",
    response_model=schemas.SuggestEnvelope,
    summary="Suggest places while the user types (API-LOC-001)",
)
async def suggest_locations(
    _uid: Annotated[str, Depends(suggest_caller)],
    service: Service,
    q: Annotated[str, Query(max_length=400, description="Partly typed address / place, 2–200 characters")],
    lat: Annotated[float | None, Query(ge=-90, le=90, description="Bias position (with lng)")] = None,
    lng: Annotated[float | None, Query(ge=-180, le=180, description="Bias position (with lat)")] = None,
    limit: Annotated[int, Query(ge=1, le=10)] = 8,
) -> schemas.SuggestEnvelope:
    query, items = await service.suggest(q, lat=lat, lng=lng, limit=limit)
    return schemas.SuggestEnvelope(
        data=schemas.SuggestData(query=query, items=[schemas.LocationSuggestionOut.of(s) for s in items])
    )


@router.get(
    "/places/{placeId}",
    response_model=schemas.PlaceDetailEnvelope,
    summary="Address and coordinates of a suggested place (API-LOC-002)",
)
async def get_place(
    _uid: Annotated[str, Depends(detail_caller)],
    service: Service,
    place_id: Annotated[str, Path(alias="placeId", max_length=500)],
) -> schemas.PlaceDetailEnvelope:
    return schemas.PlaceDetailEnvelope(data=schemas.PlaceDetailOut.of(await service.get_place(place_id)))


@router.get(
    "/reverse",
    response_model=schemas.PlaceDetailEnvelope,
    summary="Address at a position: GPS or a dragged map pin (API-LOC-003)",
)
async def reverse_geocode(
    _uid: Annotated[str, Depends(detail_caller)],
    service: Service,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lng: Annotated[float, Query(ge=-180, le=180)],
) -> schemas.PlaceDetailEnvelope:
    return schemas.PlaceDetailEnvelope(data=schemas.PlaceDetailOut.of(await service.reverse(lat, lng)))
