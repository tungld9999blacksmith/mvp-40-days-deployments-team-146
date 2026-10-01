"""Unit tests for the pure booking logic (FEAT-BOOK-001, F6).

Covers the capacity formula (BR-005) and the location ranking (BR-002..004)
without touching the database or Redis.
"""

from __future__ import annotations

from uuid import uuid4

from src.common.core.workshop import Workshop, WorkshopStatus
from src.modules.booking.domain import (
    AnchorSource,
    LocationAnchor,
    available_from,
    haversine_km,
)
from src.modules.booking.location import SimpleTextLocationFinder


def _workshop(name: str, region: str, *, lat=None, lng=None, ident=None) -> Workshop:
    return Workshop(
        id=ident or uuid4(),
        external_center_id=f"C-{name}",
        name=name,
        region=region,
        address=f"{name} address",
        total_technicians=8,
        emergency_slots_reserved=1,
        status=WorkshopStatus.ACTIVE,
        latitude=lat,
        longitude=lng,
    )


# ── BR-005 capacity formula ────────────────────────────────────────────────
def test_capacity_matches_spec_example():
    # 8 techs − 1 emergency − 2 blocked = 5; 0 occupied → 5 remaining, available.
    remaining, available = available_from(8, 1, 2, 0)
    assert (remaining, available) == (5, True)


def test_capacity_full_when_occupied_reaches_capacity():
    remaining, available = available_from(8, 1, 2, 5)
    assert remaining == 0 and available is False


def test_capacity_never_negative():
    remaining, available = available_from(2, 0, 0, 10)
    assert remaining == 0 and available is False


# ── BR-003 haversine ────────────────────────────────────────────────────────
def test_haversine_zero_for_same_point():
    assert haversine_km(21.0, 105.8, 21.0, 105.8) == 0.0


def test_haversine_orders_by_closeness():
    origin = (21.0000, 105.8000)
    near = haversine_km(*origin, 21.0100, 105.8100)
    far = haversine_km(*origin, 21.2000, 106.0000)
    assert near < far


# ── BR-003/004 ranking ──────────────────────────────────────────────────────
def test_rank_by_distance_puts_preferred_first():
    finder = SimpleTextLocationFinder()
    near = _workshop("Near", "Hà Nội", lat=21.001, lng=105.801)
    far = _workshop("Far", "Hà Nội", lat=21.20, lng=106.0)
    preferred = _workshop("Pref", "Hà Nội", lat=21.19, lng=105.99)
    anchor = LocationAnchor(AnchorSource.SPECIFIED, latitude=21.0, longitude=105.8)

    ranked, ranked_by = finder.rank(
        anchor, [far, near, preferred], preferred_workshop_id=preferred.id, limit=5
    )

    assert ranked_by.value == "DISTANCE"
    assert ranked[0].workshop.id == preferred.id and ranked[0].is_preferred
    # Remaining ordered nearest → farthest.
    rest = [r.workshop.name for r in ranked[1:]]
    assert rest == ["Near", "Far"]


def test_rank_by_region_when_no_coordinates():
    finder = SimpleTextLocationFinder()
    hanoi = _workshop("HN Center", "Hà Nội")
    hcm = _workshop("HCM Center", "Hồ Chí Minh")
    anchor = LocationAnchor(AnchorSource.PROFILE, province="Hà Nội")

    ranked, ranked_by = finder.rank(anchor, [hanoi, hcm], preferred_workshop_id=None, limit=5)

    assert ranked_by.value == "REGION"
    assert [r.workshop.name for r in ranked] == ["HN Center"]
    assert all(r.distance_km is None for r in ranked)


def test_rank_excludes_inactive_workshops():
    finder = SimpleTextLocationFinder()
    active = _workshop("Active", "Hà Nội", lat=21.0, lng=105.8)
    inactive = _workshop("Inactive", "Hà Nội", lat=21.0, lng=105.8)
    inactive.status = WorkshopStatus.INACTIVE
    anchor = LocationAnchor(AnchorSource.SPECIFIED, latitude=21.0, longitude=105.8)

    ranked, _ = finder.rank(anchor, [active, inactive], preferred_workshop_id=None, limit=5)

    assert [r.workshop.name for r in ranked] == ["Active"]
