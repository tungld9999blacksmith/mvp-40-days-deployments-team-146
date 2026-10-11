"""Location search — HTTP schemas (API-SPEC-PLATFORM-LOC-001 §1.3). JSON fields are camelCase."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from .domain import LatLng, LocationSuggestion, PlaceDetail


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class LatLngOut(CamelModel):
    lat: float
    lng: float

    @classmethod
    def of(cls, p: LatLng) -> LatLngOut:
        return cls(lat=p.lat, lng=p.lng)


class HighlightOut(CamelModel):
    start: int
    end: int


class LocationSuggestionOut(CamelModel):
    place_id: str
    title: str
    address: str | None
    place_type: str
    position: LatLngOut | None
    distance_meters: int | None
    highlights: list[HighlightOut]

    @classmethod
    def of(cls, s: LocationSuggestion) -> LocationSuggestionOut:
        return cls(
            place_id=s.place_id,
            title=s.title,
            address=s.address,
            place_type=s.place_type.value,
            position=LatLngOut.of(s.position) if s.position else None,
            distance_meters=s.distance_meters,
            highlights=[HighlightOut(start=h.start, end=h.end) for h in s.highlights],
        )


class SuggestData(CamelModel):
    query: str
    items: list[LocationSuggestionOut]


class SuggestEnvelope(CamelModel):
    data: SuggestData


class PlaceDetailOut(CamelModel):
    """Maps 1-1 onto ``LocationIn`` (API-003) and the workshop onboarding address."""

    place_id: str
    title: str
    place_type: str
    address_line: str
    street: str | None
    ward: str | None
    district: str | None
    province: str | None
    province_raw: str | None
    country_code: str
    position: LatLngOut
    provider: str

    @classmethod
    def of(cls, p: PlaceDetail) -> PlaceDetailOut:
        return cls(
            place_id=p.place_id,
            title=p.title,
            place_type=p.place_type.value,
            address_line=p.address_line,
            street=p.street,
            ward=p.ward,
            district=p.district,
            province=p.province,
            province_raw=p.province_raw,
            country_code=p.country_code,
            position=LatLngOut.of(p.position),
            provider=p.provider,
        )


class PlaceDetailEnvelope(CamelModel):
    data: PlaceDetailOut
