"""scripts/seed_maintenance_rules.py — building maintenance_rule rows from the mock-ev-system dump."""

from __future__ import annotations

import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_maintenance_rules.py"
_spec = importlib.util.spec_from_file_location("seed_maintenance_rules", SCRIPT)
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def _dump() -> dict:
    return {
        "vehicle_models": [{"model_id": "MDL-01"}, {"model_id": "MDL-02"}, {"model_id": "MDL-09"}],
        "maintenance_schedules": [
            {"schedule_id": "MS-001", "model_id": "MDL-01", "milestone_km": 10000, "milestone_months": 6},
            {"schedule_id": "MS-002", "model_id": "MDL-01", "milestone_km": 20000, "milestone_months": 12},
            {"schedule_id": "MS-006", "model_id": "MDL-02", "milestone_km": 10000, "milestone_months": 6},
            {"schedule_id": "MS-007", "model_id": "MDL-02", "milestone_km": 30000, "milestone_months": 18},
        ],
        "maintenance_items": [
            {
                "item_id": "MI-001",
                "schedule_id": "MS-001",
                "item_name": "Kiểm tra phanh",
                "is_covered_by_warranty": True,
                "reference_price": "0",
            },
            {
                "item_id": "MI-002",
                "schedule_id": "MS-001",
                "item_name": "Kiểm tra lốp",
                "is_covered_by_warranty": False,
                "reference_price": "150000",
            },
            {
                "item_id": "MI-003",
                "schedule_id": "MS-002",
                "item_name": "Thay lọc gió",
                "is_covered_by_warranty": False,
                "reference_price": 350000.0,
            },
        ],
    }


def test_model_with_own_items_uses_them():
    rows, _ = seed.build_rules(_dump(), models=["MDL-01"])

    assert [(r["odo_milestone"], r["item_code"]) for r in rows] == [
        (10000, "MI_001"),
        (10000, "MI_002"),
        (20000, "MI_003"),
    ]
    assert rows[1]["estimated_cost"] == Decimal("150000")
    assert rows[0]["is_covered_by_warranty"] is True
    assert all(r["estimated_duration_minutes"] == seed.DEFAULT_DURATION_MINUTES for r in rows)


def test_model_without_items_reuses_same_km_template_and_codes():
    rows, warnings = seed.build_rules(_dump(), models=["MDL-02"])

    assert [(r["model_id"], r["odo_milestone"], r["month_milestone"], r["item_code"]) for r in rows] == [
        ("MDL-02", 10000, 6, "MI_001"),
        ("MDL-02", 10000, 6, "MI_002"),
    ]
    assert warnings == ["MDL-02 @ 30000 km: no items for this milestone in any model, skipped"]


def test_default_covers_every_model_and_flags_models_without_schedules():
    rows, warnings = seed.build_rules(_dump(), duration_minutes=45)

    assert {r["model_id"] for r in rows} == {"MDL-01", "MDL-02"}
    assert "MDL-09: no maintenance_schedules in the source" in warnings
    assert {r["estimated_duration_minutes"] for r in rows} == {45}


@pytest.mark.parametrize("item_id, code", [("MI-001", "MI_001"), ("mi-12", "MI_12"), ("MI 7/a", "MI_7_A")])
def test_item_code_matches_db_format(item_id, code):
    assert seed.item_code(item_id) == code


def test_item_code_rejects_unusable_id():
    with pytest.raises(ValueError):
        seed.item_code("-")


def test_bundled_dump_gives_every_model_all_milestones():
    rows, warnings = seed.build_rules(seed.load_dump(seed.DEFAULT_SOURCE))

    per_model: dict[str, set[int]] = {}
    for r in rows:
        assert seed.ITEM_CODE_RE.match(r["item_code"])
        per_model.setdefault(r["model_id"], set()).add(r["odo_milestone"])
    assert warnings == []
    assert len(per_model) == 7
    # VinFast EV schedule from 2026-01-01: every 15,000 km or 1 year.
    assert all(kms == {15000, 30000, 45000, 60000, 75000} for kms in per_model.values())


def test_bundled_dump_milestones_are_every_15000_km_or_12_months():
    rows, _ = seed.build_rules(seed.load_dump(seed.DEFAULT_SOURCE))

    assert {(r["odo_milestone"], r["month_milestone"]) for r in rows} == {
        (15000, 12),
        (30000, 24),
        (45000, 36),
        (60000, 48),
        (75000, 60),
    }


def _rows(*keys: tuple[str, int, str]) -> list[dict]:
    return [{"model_id": m, "odo_milestone": km, "item_code": code} for m, km, code in keys]


def test_replace_drops_old_milestones_of_selected_models_only():
    existing = {
        ("MDL-01", 10000, "MI_001"),
        ("MDL-01", 60000, "MI_016"),
        ("MDL-02", 10000, "MI_001"),
    }
    rows = _rows(("MDL-01", 15000, "MI_001"), ("MDL-01", 60000, "MI_016"))

    assert seed.stale_keys(existing, rows, {"MDL-01"}) == {("MDL-01", 10000, "MI_001")}
    assert seed.dropped_milestones(existing, rows, {"MDL-01"}) == {"MDL-01": {10000}}


def test_replace_drops_an_item_removed_from_a_kept_milestone():
    existing = {("MDL-01", 60000, "MI_016"), ("MDL-01", 60000, "MI_017")}
    rows = _rows(("MDL-01", 60000, "MI_016"))

    assert seed.stale_keys(existing, rows, {"MDL-01"}) == {("MDL-01", 60000, "MI_017")}
    assert seed.dropped_milestones(existing, rows, {"MDL-01"}) == {}


def test_replace_is_a_no_op_once_applied():
    rows = _rows(("MDL-01", 15000, "MI_001"), ("MDL-01", 30000, "MI_005"))
    existing = {(r["model_id"], r["odo_milestone"], r["item_code"]) for r in rows}

    assert seed.stale_keys(existing, rows, {"MDL-01"}) == set()
    assert seed.dropped_milestones(existing, rows, {"MDL-01"}) == {}
