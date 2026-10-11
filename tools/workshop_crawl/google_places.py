"""Google Places API (New) Text Search client — standard library only.

Docs: https://developers.google.com/maps/documentation/places/web-service/text-search
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from places import SearchClient

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Pro SKU fields only (no Enterprise fields such as phone / rating) to stay in the cheaper tier.
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.addressComponents",
        "places.location",
        "places.types",
        "places.businessStatus",
        "places.googleMapsUri",
        "nextPageToken",
    ]
)
# Enterprise SKU extras, opt-in via --with-contact.
CONTACT_FIELDS = "places.nationalPhoneNumber,places.rating,places.userRatingCount"

# Mainland Vietnam bounding box — results outside it are never returned.
VIETNAM_RECT = {
    "low": {"latitude": 8.18, "longitude": 102.14},
    "high": {"latitude": 23.39, "longitude": 109.47},
}

AUTOMOTIVE_TYPES = {"car_repair", "car_dealer"}


class GooglePlacesClient(SearchClient):
    source = "google"
    label = "Google Places API (New) — Text Search"
    auth_hint = "Check the API key and that 'Places API (New)' is enabled for its project (billing on)."

    def __init__(self, api_key: str, cache_dir: Path, *, with_contact: bool = False, **kwargs: Any) -> None:
        super().__init__(cache_dir, **kwargs)
        self.api_key = api_key
        self.field_mask = FIELD_MASK + ("," + CONTACT_FIELDS if with_contact else "")

    def _cache_extra(self) -> list[Any]:
        return [self.field_mask]

    def _fetch(
        self, query: str, *, repair_only: bool, max_pages: int, bbox: list[float] | None = None
    ) -> list[dict[str, Any]]:
        """Up to ``max_pages`` × 20 places (Google caps a query at 60)."""
        rect = VIETNAM_RECT
        if bbox:
            west, south, east, north = bbox
            rect = {"low": {"latitude": south, "longitude": west}, "high": {"latitude": north, "longitude": east}}
        places: list[dict[str, Any]] = []
        page_token: str | None = None
        for page in range(max_pages):
            if page:
                time.sleep(self.page_delay)
            body: dict[str, Any] = {
                "textQuery": query,
                "languageCode": "vi",
                "regionCode": "VN",
                "pageSize": 20,
                "locationRestriction": {"rectangle": rect},
            }
            if repair_only:
                body["includedType"] = "car_repair"
                body["strictTypeFiltering"] = True
            if page_token:
                body["pageToken"] = page_token
            data = self._post(SEARCH_URL, body, {"X-Goog-Api-Key": self.api_key, "X-Goog-FieldMask": self.field_mask})
            places.extend(data.get("places") or [])
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return places

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        types = raw.get("types") or []
        location = raw.get("location") or {}
        country = _component(raw, "country")
        admin = _component(raw, "administrative_area_level_1")
        place: dict[str, Any] = {
            "source": self.source,
            "id": raw.get("id"),
            "name": ((raw.get("displayName") or {}).get("text") or "").strip(),
            "address": raw.get("formattedAddress"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "country": ((country or {}).get("shortText") or "").upper() or None,
            "admin_area": (admin or {}).get("longText") or (admin or {}).get("shortText"),
            "categories": types,
            "automotive": bool(AUTOMOTIVE_TYPES & set(types)),
            "dealer": "car_dealer" in types,
            "closed": raw.get("businessStatus") == "CLOSED_PERMANENTLY",
            "maps_uri": raw.get("googleMapsUri"),
        }
        for src, dst in (("nationalPhoneNumber", "phone"), ("rating", "rating"), ("userRatingCount", "rating_count")):
            if src in raw:
                place[dst] = raw[src]
        return place


def _component(place: dict[str, Any], kind: str) -> dict[str, Any] | None:
    for comp in place.get("addressComponents") or []:
        if kind in (comp.get("types") or []):
            return comp
    return None
