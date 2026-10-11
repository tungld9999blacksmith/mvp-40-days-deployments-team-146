"""Amazon Location Service — Places API v2 SearchText client, standard library only.

Docs: https://docs.aws.amazon.com/location/latest/APIReference/API_geoplaces_SearchText.html
Auth: an Amazon Location API key allowed to call ``geo-places:SearchText`` (passed as ``?key=``).
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path
from typing import Any

from places import SearchClient
from provinces import fold

SEARCH_URL = "https://places.geo.{region}.amazonaws.com/v2/search-text"

# Mainland Vietnam bounding box: [west, south, east, north].
VIETNAM_BBOX = [102.14, 8.18, 109.47, 23.39]

# Amazon has no "car_repair only" request filter for SearchText, so generic queries are filtered
# afterwards on these words in the category ids / names (or, without categories, in the place name).
AUTOMOTIVE_WORDS = {"car", "cars", "auto", "automobile", "automotive", "vehicle", "vehicles", "garage", "gara"}
NAME_HINTS = ("gara", "garage", "o to", "oto", "auto", "vinfast")
NON_CAR_HINTS = ("xe may", "motorcycle", "motorbike", "xe dap", "bicycle")


def _words(text: str | None) -> set[str]:
    return set(re.split(r"[^a-z0-9]+", fold(text))) - {""}


class AwsPlacesClient(SearchClient):
    source = "aws"
    label = "Amazon Location Service — Places v2 SearchText"
    auth_hint = (
        "Check the Amazon Location API key: it must allow 'geo-places:SearchText' and belong to "
        "--aws-region (AWS_LOCATION_REGION)."
    )

    def __init__(
        self,
        api_key: str,
        cache_dir: Path,
        *,
        region: str = "ap-southeast-1",
        intended_use: str = "Storage",
        with_contact: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(cache_dir, **kwargs)
        self.api_key = api_key
        self.region = region
        self.intended_use = intended_use
        self.with_contact = with_contact

    def _cache_extra(self) -> list[Any]:
        return [self.region, self.intended_use, self.with_contact]

    def _fetch(
        self, query: str, *, repair_only: bool, max_pages: int, bbox: list[float] | None = None
    ) -> list[dict[str, Any]]:
        """One request returning up to ``max_pages`` × 20 results (SearchText allows 100 per page)."""
        body: dict[str, Any] = {
            "QueryText": query,
            "MaxResults": 20 * max_pages,
            "Language": "vi",
            "Filter": {"BoundingBox": bbox or VIETNAM_BBOX, "IncludeCountries": ["VNM"]},
            # Results are saved to a database, which Amazon only allows for IntendedUse=Storage.
            "IntendedUse": self.intended_use,
        }
        if self.with_contact:
            body["AdditionalFeatures"] = ["Contact"]
        url = f"{SEARCH_URL.format(region=self.region)}?key={urllib.parse.quote(self.api_key, safe='')}"
        data = self._post(url, body, {})
        return data.get("ResultItems") or []

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        address = raw.get("Address") or {}
        position = raw.get("Position") or []
        categories = raw.get("Categories") or []
        category_words: set[str] = set()
        for cat in categories:
            for key in ("Id", "Name", "LocalizedName"):
                category_words |= _words(cat.get(key))
        name = (raw.get("Title") or "").strip()
        place: dict[str, Any] = {
            "source": self.source,
            "id": raw.get("PlaceId"),
            "name": name,
            "address": address.get("Label"),
            "latitude": position[1] if len(position) == 2 else None,
            "longitude": position[0] if len(position) == 2 else None,
            "country": ((address.get("Country") or {}).get("Code2") or "").upper() or None,
            "admin_area": (address.get("Region") or {}).get("Name"),
            "categories": [cat.get("Id") for cat in categories if cat.get("Id")],
            "automotive": _is_automotive(name, category_words, bool(categories)),
            "dealer": bool({"dealer", "dealers", "dealership"} & category_words),
            "closed": False,  # SearchText exposes no business status
            "maps_uri": None,
        }
        phones = (raw.get("Contacts") or {}).get("Phones") or []
        if phones and phones[0].get("Value"):
            place["phone"] = phones[0]["Value"]
        return place


def _is_automotive(name: str, category_words: set[str], has_categories: bool) -> bool:
    folded = fold(name)
    if any(hint in folded for hint in NON_CAR_HINTS):
        return False
    if has_categories:
        return bool(AUTOMOTIVE_WORDS & category_words)
    return any(hint in folded for hint in NAME_HINTS)
