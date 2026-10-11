"""Location search — provider-neutral value objects (API-SPEC-PLATFORM-LOC-001 §1.3, §5.3).

Adapters (AWS / fake) return these; the service and the HTTP schemas never see a
provider's raw JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# Mainland Vietnam bounding box: [west, south, east, north] (WGS 84).
VIETNAM_BBOX: tuple[float, float, float, float] = (102.14, 8.18, 109.47, 23.39)


class PlaceType(StrEnum):
    POI = "POI"
    STREET = "STREET"
    ADDRESS = "ADDRESS"
    AREA = "AREA"


@dataclass(frozen=True)
class LatLng:
    lat: float
    lng: float

    def in_vietnam(self) -> bool:
        west, south, east, north = VIETNAM_BBOX
        return south <= self.lat <= north and west <= self.lng <= east


@dataclass(frozen=True)
class Highlight:
    start: int
    end: int


@dataclass(frozen=True)
class LocationSuggestion:
    place_id: str
    title: str
    address: str | None
    place_type: PlaceType
    position: LatLng | None
    distance_meters: int | None
    highlights: list[Highlight] = field(default_factory=list)


@dataclass(frozen=True)
class PlaceDetail:
    place_id: str
    title: str
    place_type: PlaceType
    address_line: str
    street: str | None
    ward: str | None
    district: str | None
    province: str | None  # one of the 34 current provinces, or None
    province_raw: str | None
    country_code: str
    position: LatLng
    provider: str
