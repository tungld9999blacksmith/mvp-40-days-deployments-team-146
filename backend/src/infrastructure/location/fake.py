"""Offline place provider — tests, local dev without an AWS key, demo mode (LOCATION_PROVIDER=fake).

A small fixed catalog; matching ignores accents and case, so "cau giay" finds "Cầu Giấy".
"""

from __future__ import annotations

import math
from dataclasses import replace

from src.common.geo import fold
from src.modules.location.domain import Highlight, LatLng, LocationSuggestion, PlaceDetail, PlaceType
from src.modules.location.ports import PlaceNotFoundError

PROVIDER_NAME = "fake"


def _place(place_id: str, title: str, place_type: PlaceType, street: str | None, ward: str, province: str,
           lat: float, lng: float) -> PlaceDetail:  # fmt: skip
    line = ", ".join(p for p in (street, ward, province, "Việt Nam") if p)
    return PlaceDetail(
        place_id=place_id,
        title=title,
        place_type=place_type,
        address_line=line,
        street=street,
        ward=ward,
        district=None,
        province=province,
        province_raw=province,
        country_code="VN",
        position=LatLng(lat=lat, lng=lng),
        provider=PROVIDER_NAME,
    )


CATALOG: tuple[PlaceDetail, ...] = (
    _place("fake-cau-giay", "Cầu Giấy", PlaceType.AREA, None, "Phường Cầu Giấy", "Hà Nội", 21.0362, 105.7906),
    _place(
        "fake-cv-cau-giay",
        "Công viên Cầu Giấy",
        PlaceType.POI,
        "Đường Cầu Giấy",
        "Phường Cầu Giấy",
        "Hà Nội",
        21.0301,
        105.7939,
    ),  # fmt: skip
    _place(
        "fake-vf-thang-long",
        "VinFast Thăng Long",
        PlaceType.POI,
        "Số 1 Phạm Văn Bạch",
        "Phường Cầu Giấy",
        "Hà Nội",
        21.0303,
        105.7915,
    ),  # fmt: skip
    _place(
        "fake-hoan-kiem",
        "Hồ Hoàn Kiếm",
        PlaceType.POI,
        "Đinh Tiên Hoàng",
        "Phường Hoàn Kiếm",
        "Hà Nội",
        21.0285,
        105.8542,
    ),  # fmt: skip
    _place(
        "fake-ben-thanh",
        "Chợ Bến Thành",
        PlaceType.POI,
        "Lê Lợi",
        "Phường Bến Thành",
        "TP. Hồ Chí Minh",
        10.7725,
        106.6980,
    ),  # fmt: skip
    _place(
        "fake-q7",
        "VinFast Quận 7",
        PlaceType.POI,
        "Nguyễn Văn Linh",
        "Phường Tân Hưng",
        "TP. Hồ Chí Minh",
        10.7295,
        106.7213,
    ),  # fmt: skip
    _place(
        "fake-cau-rong", "Cầu Rồng", PlaceType.POI, "Nguyễn Văn Linh", "Phường Hải Châu", "Đà Nẵng", 16.0611, 108.2270
    ),  # fmt: skip
)


def _distance_m(a: LatLng, b: LatLng) -> int:
    r = 6_371_000.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(h)))


class FakePlacesProvider:
    name = PROVIDER_NAME

    def __init__(self, catalog: tuple[PlaceDetail, ...] = CATALOG) -> None:
        self._catalog = catalog

    async def aclose(self) -> None:
        return None

    async def suggest(self, query: str, *, near: LatLng | None, limit: int) -> list[LocationSuggestion]:
        needle = fold(query)
        hits: list[LocationSuggestion] = []
        for place in self._catalog:
            title = fold(place.title)
            if needle not in title and needle not in fold(place.address_line):
                continue
            start = title.find(needle)
            hits.append(
                LocationSuggestion(
                    place_id=place.place_id,
                    title=place.title,
                    address=place.address_line,
                    place_type=place.place_type,
                    position=place.position,
                    distance_meters=_distance_m(near, place.position) if near else None,
                    # Folding keeps one character per letter, so indexes match the original title.
                    highlights=[Highlight(start, start + len(needle))] if start >= 0 else [],
                )
            )
        if near is not None:
            hits.sort(key=lambda s: s.distance_meters or 0)
        return hits[:limit]

    async def get_place(self, place_id: str) -> PlaceDetail:
        for place in self._catalog:
            if place.place_id == place_id:
                return place
        raise PlaceNotFoundError(place_id)

    async def reverse(self, position: LatLng) -> PlaceDetail:
        nearest = min(self._catalog, key=lambda p: _distance_m(position, p.position))
        if _distance_m(position, nearest.position) > 5_000:
            raise PlaceNotFoundError(f"{position.lat:.3f},{position.lng:.3f}")
        return replace(nearest, position=position)
