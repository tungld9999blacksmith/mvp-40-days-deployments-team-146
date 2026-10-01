"""Page result types and the opaque cursor codec.

Three strategies are supported:

- **Offset** (``OffsetPage``): ``page`` / ``page_size`` → ``LIMIT/OFFSET``.
  Simple, supports jumping to page N and a total count; slow on deep pages and
  unstable when rows are inserted between requests.
- **Keyset** (``KeysetPage``): the caller passes the sort-key values of the
  last row it saw (``after={"created_at": ..., "id": ...}``) and gets the rows
  strictly after it. Fast on any depth; keys are visible to the caller.
- **Cursor** (``CursorPage``): keyset pagination wrapped in an opaque,
  URL-safe token that also carries the direction, so the client can walk
  both forward (``next_cursor``) and backward (``prev_cursor``).
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from .errors import InvalidCursorError

T = TypeVar("T")

Direction = Literal["next", "prev"]


@dataclass(frozen=True, slots=True)
class OffsetPage(Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int | None = None  # None when the count was skipped

    @property
    def total_pages(self) -> int | None:
        if self.total is None:
            return None
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool | None:
        if self.total is None:
            return None
        return self.page * self.page_size < self.total

    @property
    def has_previous(self) -> bool:
        return self.page > 1


@dataclass(frozen=True, slots=True)
class KeysetPage(Generic[T]):
    items: list[T]
    limit: int
    has_next: bool
    # Sort-key values of the last item; pass back as ``after`` for the next page.
    next_key: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CursorPage(Generic[T]):
    items: list[T]
    limit: int
    has_next: bool
    has_previous: bool
    next_cursor: str | None = None
    prev_cursor: str | None = None


# ── Cursor codec ───────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Cursor:
    values: dict[str, Any]
    direction: Direction = "next"
    # Fingerprint of the sort order the cursor was issued for.
    sort_key: str = ""


def sort_fingerprint(fields: Sequence[tuple[str, bool]]) -> str:
    return ",".join(("-" if descending else "") + name for name, descending in fields)


def encode_cursor(cursor: Cursor) -> str:
    payload = {
        "v": {name: _encode_value(value) for name, value in cursor.values.items()},
        "d": cursor.direction,
        "s": cursor.sort_key,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token: str) -> Cursor:
    try:
        padded = token + "=" * (-len(token) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        values = {name: _decode_value(value) for name, value in payload["v"].items()}
        direction = payload["d"]
        sort_key = payload["s"]
    except (
        binascii.Error,
        UnicodeDecodeError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
        InvalidOperation,
    ) as exc:
        raise InvalidCursorError("Malformed cursor") from exc
    if direction not in ("next", "prev") or not isinstance(sort_key, str):
        raise InvalidCursorError("Malformed cursor")
    return Cursor(values=values, direction=direction, sort_key=sort_key)


# Values are tagged so they round-trip with their Python type; JSON alone
# would turn UUID / datetime / Decimal into strings and break comparisons.
def _encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return _encode_value(value.value)
    if isinstance(value, UUID):
        return {"t": "uuid", "v": str(value)}
    if isinstance(value, datetime):  # before date: datetime is a date subclass
        return {"t": "datetime", "v": value.isoformat()}
    if isinstance(value, date):
        return {"t": "date", "v": value.isoformat()}
    if isinstance(value, time):
        return {"t": "time", "v": value.isoformat()}
    if isinstance(value, Decimal):
        return {"t": "decimal", "v": str(value)}
    raise TypeError(f"Cannot encode {type(value).__name__} in a cursor")


_DECODERS = {
    "uuid": UUID,
    "datetime": datetime.fromisoformat,
    "date": date.fromisoformat,
    "time": time.fromisoformat,
    "decimal": Decimal,
}


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict):
        decoder = _DECODERS.get(value.get("t"))
        if decoder is None:
            raise ValueError("Unknown cursor value type")
        return decoder(value["v"])
    return value
