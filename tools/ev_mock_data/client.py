"""Tiny HTTP client for mock-ev-system (standard library only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class MockApiError(Exception):
    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class MockClient:
    def __init__(self, base_url: str, admin_token: str = "", timeout: float = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.admin_token = admin_token
        self.timeout = timeout

    def request(
        self, method: str, path: str, params: dict[str, Any] | None = None, body: Any = None, raw_text: bool = False
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.admin_token:
            headers["X-Admin-Token"] = self.admin_token
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(raw).get("detail", raw)
            except (json.JSONDecodeError, AttributeError):
                detail = raw
            raise MockApiError(exc.code, detail) from exc
        if raw_text:
            return raw
        return json.loads(raw) if raw else None

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self.request("GET", path, params)

    def get_text(self, path: str, params: dict[str, Any] | None = None) -> str:
        return self.request("GET", path, params, raw_text=True)

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, body=body if body is not None else {})

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    # ── admin helpers ────────────────────────────────────────────────
    def entities(self) -> list[dict]:
        return self.get("/admin/entities")

    def all_records(self, entity: str, filters: dict[str, str] | None = None, page: int = 1000) -> list[dict]:
        """Read every record of an entity, page by page."""
        items: list[dict] = []
        offset = 0
        while True:
            res = self.get(f"/admin/data/{entity}", {**(filters or {}), "limit": page, "offset": offset})
            items.extend(res["items"])
            offset += page
            if offset >= res["total"]:
                return items

    def import_data(self, data: dict[str, list[dict]], mode: str = "upsert") -> dict:
        return self.post("/admin/import", {"mode": mode, "data": data})
