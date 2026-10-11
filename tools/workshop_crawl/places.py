"""Shared base for the place-search clients (Google Places, Amazon Location) — standard library only.

Every client returns *normalized places*, so the crawler never sees a provider's raw format:

    {
        "source": "google" | "aws",
        "id": str,                    # provider place id
        "name": str,
        "address": str | None,
        "latitude": float | None,
        "longitude": float | None,
        "country": str | None,        # ISO 3166-1 alpha-2, e.g. "VN"
        "admin_area": str | None,     # province as the provider names it (old or new name)
        "categories": list[str],      # provider category ids
        "automotive": bool,           # categorized as a car repair shop / dealer
        "dealer": bool,               # categorized as a car dealer
        "closed": bool,               # permanently closed
        "maps_uri": str | None,
        # optional (contact lookups only): "phone", "rating", "rating_count"
    }

Every query is cached on disk (raw provider response, one file per query), so re-running a crawl
never pays twice for the same query.
"""

from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class PlacesError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"Places API HTTP {status}: {detail}")
        self.status = status


class SearchClient:
    """Cache + retrying JSON POST; subclasses implement ``_fetch`` (raw items) and ``normalize``."""

    source = ""
    label = ""
    # Printed when the provider rejects the credentials (HTTP 400/401/403).
    auth_hint = ""

    def __init__(self, cache_dir: Path, *, timeout: float = 30, page_delay: float = 0.4) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.page_delay = page_delay
        self.requests_made = 0
        self.cache_hits = 0

    # ------------------------------------------------------------------ public
    def search(
        self, query: str, *, repair_only: bool, max_pages: int, bbox: list[float] | None = None
    ) -> list[dict[str, Any]]:
        """Normalized places for *query*. ``repair_only`` asks the provider for car repair shops only;
        ``bbox`` ([west, south, east, north]) narrows the search from all of Vietnam to that box."""
        cache_file = self._cache_file(query, repair_only, max_pages, bbox)
        if cache_file.exists():
            self.cache_hits += 1
            raw = json.loads(cache_file.read_text(encoding="utf-8"))
        else:
            raw = self._fetch(query, repair_only=repair_only, max_pages=max_pages, bbox=bbox)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        return [self.normalize(item) for item in raw]

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    # --------------------------------------------------------------- protected
    def _fetch(
        self, query: str, *, repair_only: bool, max_pages: int, bbox: list[float] | None = None
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    def _cache_extra(self) -> list[Any]:
        """Settings that change the response (fields, language...) — part of the cache key."""
        return []

    def _cache_file(self, query: str, repair_only: bool, max_pages: int, bbox: list[float] | None = None) -> Path:
        # No bbox (all of Vietnam) keeps the original key, so existing cache files stay valid.
        parts = [query, repair_only, max_pages, *self._cache_extra()] + ([bbox] if bbox else [])
        key = json.dumps(parts, ensure_ascii=False)
        return self.cache_dir / f"{hashlib.sha1(key.encode('utf-8'), usedforsecurity=False).hexdigest()}.json"

    def _post(self, url: str, body: dict[str, Any], headers: dict[str, str], attempts: int = 4) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", **headers},
        )
        for attempt in range(attempts):
            self.requests_made += 1
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                retryable = exc.code == 429 or exc.code >= 500
                if not retryable or attempt == attempts - 1:
                    raise PlacesError(exc.code, error_message(detail)) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt == attempts - 1:
                    raise PlacesError(0, str(exc)) from exc
            time.sleep(2**attempt)
        raise AssertionError("unreachable")


def error_message(detail: str) -> str:
    """Google: {"error": {"message"}}; AWS: {"message"} or {"Message"}."""
    try:
        data = json.loads(detail)
    except ValueError:
        return detail[:500]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return str(error["message"])
        for key in ("message", "Message"):
            if data.get(key):
                return str(data[key])
    return detail[:500]
