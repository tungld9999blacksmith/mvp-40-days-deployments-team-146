"""Amazon Location Service — Places API v2 adapter (GrabMaps data in ap-southeast-1 / ap-southeast-5).

Spec: ``docs/specs/platform/location-search.api.md`` §5.2–5.3.

- Auth: a server-side API key passed as ``?key=``. A logging filter masks it in httpx's
  request log; this module never logs a URL itself.
- GrabMaps regions do not support ``Autocomplete`` / ``Geocode``, ``IntendedUse`` on
  ``GetPlace``, nor several request fields — the requests below only use supported ones.
- Coordinates: AWS uses ``[lng, lat]``; everything leaving this module is ``LatLng``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from typing import Any

import httpx

from src.common.geo import normalize_province, province_in_address
from src.modules.location.domain import (
    VIETNAM_BBOX,
    Highlight,
    LatLng,
    LocationSuggestion,
    PlaceDetail,
    PlaceType,
)
from src.modules.location.ports import PlaceNotFoundError, PlaceOutOfCoverageError, ProviderUnavailableError

logger = logging.getLogger(__name__)

PROVIDER_NAME = "aws-grabmaps"
GRABMAPS_REGIONS = ("ap-southeast-1", "ap-southeast-5")
LANGUAGE = "vi"
RETRY_BACKOFF_SECONDS = 0.2

_PLACE_TYPES: dict[str, PlaceType] = {
    "PointOfInterest": PlaceType.POI,
    "Street": PlaceType.STREET,
    "Intersection": PlaceType.STREET,
    "PointAddress": PlaceType.ADDRESS,
    "InterpolatedAddress": PlaceType.ADDRESS,
    "SecondaryAddress": PlaceType.ADDRESS,
    "InferredSecondaryAddress": PlaceType.ADDRESS,
}


class _MaskApiKeyFilter(logging.Filter):
    """httpx logs every request URL at INFO; hide the ``key=`` query value."""

    _pattern = re.compile(r"([?&]key=)[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(self._pattern.sub(r"\1***", str(a)) for a in record.args)
        record.msg = self._pattern.sub(r"\1***", str(record.msg))
        return True


def _install_key_mask() -> None:
    for name in ("httpx", "httpcore"):
        target = logging.getLogger(name)
        if not any(isinstance(f, _MaskApiKeyFilter) for f in target.filters):
            target.addFilter(_MaskApiKeyFilter())


# ---------------------------------------------------------------------------
# AWS JSON → domain
# ---------------------------------------------------------------------------
def _position(raw: Any) -> LatLng | None:
    if isinstance(raw, list | tuple) and len(raw) == 2:
        return LatLng(lat=float(raw[1]), lng=float(raw[0]))
    return None


def _country_code(address: dict[str, Any]) -> str | None:
    country = address.get("Country") or {}
    code = country.get("Code2")
    if code:
        return str(code).upper()
    return {"VNM": "VN"}.get(str(country.get("Code3") or "").upper())


def _place_type(raw: str | None) -> PlaceType:
    return _PLACE_TYPES.get(raw or "", PlaceType.AREA)


def _name(value: Any) -> str | None:
    """Address parts are strings, or objects like ``{"Name": ..., "Code": ...}``."""
    if isinstance(value, dict):
        value = value.get("Name")
    text = str(value).strip() if value else ""
    return text or None


def _address_line(address: dict[str, Any], title: str) -> str:
    label = _name(address.get("Label"))
    if label:
        return label
    parts = [
        _street(address),
        _name(address.get("SubDistrict")),
        _name(address.get("District")),
        _name(address.get("Locality")),
        _name(address.get("Region")),
    ]
    return ", ".join(p for p in parts if p) or title


def _street(address: dict[str, Any]) -> str | None:
    parts = [_name(address.get("AddressNumber")), _name(address.get("Street"))]
    return " ".join(p for p in parts if p) or None


def to_suggestion(item: dict[str, Any]) -> LocationSuggestion | None:
    """A Suggest result item, or None for query refinements / places outside Vietnam."""
    if item.get("SuggestResultItemType") != "Place":
        return None
    place = item.get("Place") or {}
    address = place.get("Address") or {}
    place_id = place.get("PlaceId")
    if not place_id or _country_code(address) not in (None, "VN"):
        return None
    title = str(item.get("Title") or "").strip()
    highlights = [
        Highlight(start=int(h["StartIndex"]), end=int(h["EndIndex"]))
        for h in ((item.get("Highlights") or {}).get("Title") or [])
        if "StartIndex" in h and "EndIndex" in h
    ]
    distance = place.get("Distance")
    return LocationSuggestion(
        place_id=str(place_id),
        title=title,
        address=_name(address.get("Label")),
        place_type=_place_type(place.get("PlaceType")),
        position=_position(place.get("Position")),
        distance_meters=int(distance) if distance is not None else None,
        highlights=highlights,
    )


def to_place_detail(raw: dict[str, Any], *, position: LatLng | None = None) -> PlaceDetail | None:
    """A GetPlace / ReverseGeocode item, or None when it has no usable position.

    ``position`` overrides the place's own coordinates (reverse: keep the user's point).
    """
    address = raw.get("Address") or {}
    point = position or _position(raw.get("Position"))
    if point is None or not raw.get("PlaceId"):
        return None
    title = str(raw.get("Title") or "").strip()
    line = _address_line(address, title)
    province_raw = _name(address.get("Region"))
    return PlaceDetail(
        place_id=str(raw["PlaceId"]),
        title=title or line,
        place_type=_place_type(raw.get("PlaceType")),
        address_line=line,
        street=_street(address),
        # [Q-03] best-effort mapping until confirmed with real GrabMaps samples.
        ward=_name(address.get("SubDistrict")) or _name(address.get("District")),
        district=_name(address.get("Locality")) or _name(address.get("SubRegion")),
        province=normalize_province(province_raw) or province_in_address(line),
        province_raw=province_raw,
        country_code=_country_code(address) or "VN",
        position=point,
        provider=PROVIDER_NAME,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------
class AwsGrabPlacesProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str,
        *,
        region: str = "ap-southeast-1",
        timeout_seconds: float = 3.0,
        reverse_radius_meters: int = 500,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("AWS_LOCATION_PLACES_API_KEY is required when LOCATION_PROVIDER=aws")
        if region not in GRABMAPS_REGIONS:
            logger.warning(
                "AWS_LOCATION_REGION=%s does not serve GrabMaps data (only %s)", region, ", ".join(GRABMAPS_REGIONS)
            )
        self._key = api_key
        self._base = f"https://places.geo.{region}.amazonaws.com/v2"
        self._radius = max(1, min(reverse_radius_meters, 100_000))  # GrabMaps caps QueryRadius at 100 km
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        _install_key_mask()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def suggest(self, query: str, *, near: LatLng | None, limit: int) -> list[LocationSuggestion]:
        body: dict[str, Any] = {
            "QueryText": query,
            "MaxResults": limit,
            "Language": LANGUAGE,
            "AdditionalFeatures": ["Core"],
            "Filter": {"IncludeCountries": ["VNM"]},
        }
        # BiasPosition and Filter.BoundingBox are mutually exclusive.
        if near is not None:
            body["BiasPosition"] = [near.lng, near.lat]
        else:
            body["Filter"]["BoundingBox"] = list(VIETNAM_BBOX)
        # IntendedUse omitted: Suggest only allows SingleUse (results must not be stored or cached).
        data = await self._request("POST", "/suggest", "Suggest", json=body)
        items = (to_suggestion(item) for item in data.get("ResultItems") or [])
        return [s for s in items if s is not None][:limit]

    async def get_place(self, place_id: str) -> PlaceDetail:
        path = f"/place/{urllib.parse.quote(place_id, safe='')}"
        # intended-use omitted: GrabMaps regions do not support it on GetPlace (spec Q-01).
        data = await self._request("GET", path, "GetPlace", params={"language": LANGUAGE}, not_found_on_400=True)
        if _country_code(data.get("Address") or {}) not in (None, "VN"):
            raise PlaceOutOfCoverageError(place_id)
        detail = to_place_detail(data)
        if detail is None:
            raise PlaceNotFoundError(place_id)
        return detail

    async def reverse(self, position: LatLng) -> PlaceDetail:
        body = {
            "QueryPosition": [position.lng, position.lat],
            "QueryRadius": self._radius,
            "MaxResults": 1,
            "Language": LANGUAGE,
            "IntendedUse": "Storage",  # the address is usually saved (user_location / workshop)
        }
        data = await self._request("POST", "/reverse-geocode", "ReverseGeocode", json=body)
        for item in data.get("ResultItems") or []:
            detail = to_place_detail(item, position=position)
            if detail is not None:
                return detail
        raise PlaceNotFoundError(f"{position.lat:.3f},{position.lng:.3f}")

    async def _request(
        self,
        method: str,
        path: str,
        operation: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        not_found_on_400: bool = False,
    ) -> dict[str, Any]:
        query = {**(params or {}), "key": self._key}
        for attempt in range(2):  # one retry on throttling / 5xx / timeout
            try:
                resp = await self._client.request(method, self._base + path, params=query, json=json)
            except httpx.HTTPError as exc:
                logger.warning("Amazon Location %s transport error: %s", operation, type(exc).__name__)
                if attempt == 0:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                    continue
                raise ProviderUnavailableError(f"{operation}: {type(exc).__name__}") from exc

            error_type = resp.headers.get("x-amzn-ErrorType", "").split(":")[0]
            if resp.is_success:
                logger.info(
                    "Amazon Location %s ok pricing_bucket=%s",
                    operation,
                    resp.headers.get("x-amz-geo-pricing-bucket", "-"),
                )
                return resp.json()
            if resp.status_code == 404 or (not_found_on_400 and resp.status_code == 400):
                raise PlaceNotFoundError(operation)
            if resp.status_code in (401, 403):
                logger.error(
                    "Amazon Location %s rejected the API key (HTTP %s %s): misconfigured key, region or permissions",
                    operation,
                    resp.status_code,
                    error_type,
                )
                raise ProviderUnavailableError(f"{operation}: access denied", misconfigured=True)
            retryable = resp.status_code == 429 or resp.status_code >= 500
            logger.warning("Amazon Location %s failed: HTTP %s %s", operation, resp.status_code, error_type)
            if retryable and attempt == 0:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS)
                continue
            raise ProviderUnavailableError(f"{operation}: HTTP {resp.status_code}")
        raise AssertionError("unreachable")
