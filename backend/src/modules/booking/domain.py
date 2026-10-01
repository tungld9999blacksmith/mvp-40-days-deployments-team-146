"""Booking module — domain value objects and configuration (FEAT-BOOK-001, F6).

Pure logic only (no DB/Redis), so it stays unit-testable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from uuid import UUID
from zoneinfo import ZoneInfo

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")

# Booking statuses that occupy a technician slot (BR-005). Kept as strings to
# avoid importing the ORM enum in pure-logic code.
OCCUPYING_STATUSES: tuple[str, ...] = ("pending", "confirmed", "checked_in", "in_progress")


@dataclass(frozen=True)
class BookingConfig:
    """Tunables from ``.env`` (see ``config.Settings``)."""

    slot_minutes: int = 60  # PQ-03
    hold_minutes: int = 10  # PQ-02
    nearby_limit: int = 5  # Q-402
    search_horizon_days: int = 7  # Q-403
    ws_confirm_deadline_hours: int = 12  # Q-404
    token_ttl_seconds: int = 600
    lock_ttl_seconds: int = 10
    reschedule_min_lead_minutes: int = 60  # us-053 BR-1206
    reschedule_max_count: int = 2  # us-053 BR-1207


class AnchorSource(str, Enum):
    SPECIFIED = "SPECIFIED"  # BR-002 #1 — location given in the request
    PROFILE = "PROFILE"      # BR-002 #2 — user_location primary
    PREFERRED = "PREFERRED"  # BR-002 #3 — vehicle_user.preferred_workshop_id


class RankedBy(str, Enum):
    DISTANCE = "DISTANCE"  # BR-003 — coordinates on both sides
    REGION = "REGION"      # BR-004 — province match only


@dataclass(frozen=True)
class LocationAnchor:
    """The point used to rank nearby workshops (BR-002, TERM-405)."""

    source: AnchorSource
    latitude: float | None = None
    longitude: float | None = None
    province: str | None = None
    query: str | None = None
    preferred_workshop_id: str | None = None

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres (BR-003)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def available_from(total_technicians: int, emergency_reserved: int, blocked: int, occupied: int) -> tuple[int, bool]:
    """BR-005: return (remaining, available). ``remaining`` never goes negative."""
    capacity = total_technicians - emergency_reserved - blocked
    remaining = max(capacity - occupied, 0)
    return remaining, remaining > 0


def now_vn() -> datetime:
    return datetime.now(TZ_VN)


def to_decimal(value: float | int | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def appointment_at(d: date, t: time) -> datetime:
    """Booking date + slot are Vietnam wall-clock times (us-033 §3.3)."""
    return datetime.combine(d, t, tzinfo=TZ_VN)


def qr_url(booking_id: UUID) -> str:
    """QR image by booking id — the endpoint checks ownership (us-053 §9)."""
    return f"/api/v1/bookings/{booking_id}/qr"


class RescheduleBlock(str, Enum):
    NOT_CONFIRMED = "NOT_CONFIRMED"
    TOO_CLOSE_TO_APPOINTMENT = "TOO_CLOSE_TO_APPOINTMENT"
    MAX_RESCHEDULES_REACHED = "MAX_RESCHEDULES_REACHED"


def reschedule_block(
    status: str,
    appointment: datetime,
    reschedule_count: int,
    now: datetime,
    config: BookingConfig,
) -> RescheduleBlock | None:
    """us-053 BR-1206 / BR-1207 — why the owner may not reschedule, or None."""
    if status != "confirmed":
        return RescheduleBlock.NOT_CONFIRMED
    if reschedule_count >= config.reschedule_max_count:
        return RescheduleBlock.MAX_RESCHEDULES_REACHED
    if now >= appointment - timedelta(minutes=config.reschedule_min_lead_minutes):
        return RescheduleBlock.TOO_CLOSE_TO_APPOINTMENT
    return None


def slot_starts(d: date, open_time: time, close_time: time, slot_minutes: int) -> list[time]:
    """BR-006 — every slot start that fits fully inside the operating hours of ``d``."""
    step = timedelta(minutes=slot_minutes)
    cursor = datetime.combine(d, open_time)
    end = datetime.combine(d, close_time)
    slots: list[time] = []
    while cursor + step <= end:
        slots.append(cursor.time())
        cursor += step
    return slots
