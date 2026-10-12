"""scripts/seed_maintenance_rules.py — building maintenance_rule rows from the mock-ev-system dump."""

from __future__ import annotations

import importlib.util
import unicodedata
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
    assert len(per_model) == 12  # MDL-01…MDL-12
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


# ── safety-critical items (data/knowledge/raw/lich_bao_duong_ALL.md) ──────────
@pytest.mark.parametrize(
    "name",
    [
        "Kiểm tra hệ thống phanh",
        "Thay má phanh trước",
        "Kiểm tra lốp & áp suất",
        "Cân bằng & đảo lốp",
        "Thay lốp (bộ 4)",
        "Góc đặt bánh xe",
        "Vô lăng & các đăng lái",
        "Dầu trợ lực lái",
        "Đèn, còi, gạt nước kính chắn gió và nước rửa kính",
        "Dây an toàn, khóa cài & bộ neo",
        "KIỂM TRA PHANH",
    ],
)
def test_safety_items_from_the_schedule_document(name):
    assert seed.is_safety_item(name)


@pytest.mark.parametrize(
    "name",
    [
        # The diacritic-folding keyword list took "lại" for "lái" and "lớp" for "lốp".
        "Kiểm tra lại hệ thống điều hoà",
        "Phủ lớp ceramic",
        "Lái thử sau sửa chữa",
        "Thay dầu đến hạn",
        # Groups the team left out of the safety list.
        "Kiểm tra hệ thống treo",
        "Kiểm tra pin cao áp & hệ thống BMS",
        "Cân chỉnh hệ thống ADAS",
        "Thay lọc gió điều hòa",
    ],
)
def test_items_outside_the_safety_groups(name):
    assert not seed.is_safety_item(name)


def test_decomposed_unicode_names_still_match():
    assert seed.is_safety_item(unicodedata.normalize("NFD", "Thay lốp (bộ 4)"))


def test_rules_carry_the_safety_flag():
    rows, _ = seed.build_rules(_dump(), models=["MDL-01"])

    assert [(r["item_name"], r["is_safety_critical"]) for r in rows] == [
        ("Kiểm tra phanh", True),
        ("Kiểm tra lốp", True),
        ("Thay lọc gió", False),
    ]


def test_safety_only_changes_just_the_flags_that_differ():
    from sqlmodel import select

    from src.common.core.maintenance.maintenance_rule import MaintenanceRule
    from tests._maintenance import make_session

    for session in make_session():
        for model_id, code, name, flag in [
            ("MDL-01", "MI_001", "Kiểm tra hệ thống phanh", False),
            ("MDL-01", "MI_002", "Kiểm tra lại hệ thống điều hoà", True),
            ("MDL-01", "MI_003", "Thay lọc gió điều hòa", False),
            ("MDL-02", "MI_001", "Kiểm tra hệ thống phanh", False),
        ]:
            session.add(
                MaintenanceRule(
                    model_id=model_id,
                    odo_milestone=15000,
                    month_milestone=12,
                    item_code=code,
                    item_name=name,
                    is_safety_critical=flag,
                    estimated_cost=Decimal(100000),
                    estimated_duration_minutes=30,
                )
            )
        session.commit()

        changes = seed.safety_changes(session, {"MDL-01"})
        assert sorted((code, new) for _, code, _, new in changes) == [("MI_001", True), ("MI_002", False)]
        assert seed.apply_safety_flags(session, changes) == 2

        flags = {(r.model_id, r.item_code): r.is_safety_critical for r in session.exec(select(MaintenanceRule))}
        assert flags == {
            ("MDL-01", "MI_001"): True,
            ("MDL-01", "MI_002"): False,
            ("MDL-01", "MI_003"): False,
            ("MDL-02", "MI_001"): False,  # not selected
        }
        assert seed.safety_changes(session, {"MDL-01"}) == []
