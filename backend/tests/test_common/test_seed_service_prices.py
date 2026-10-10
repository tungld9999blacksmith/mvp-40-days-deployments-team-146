"""scripts/seed_service_prices.py — demo service_price rows for every active workshop."""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("seed_service_prices", SCRIPTS / "seed_service_prices.py")
prices = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prices)


def _rule(model: str, code: str, cost: str, covered: bool = False, km: int = 15000) -> dict:
    return {
        "model_id": model,
        "odo_milestone": km,
        "item_code": code,
        "item_name": f"Hạng mục {code}",
        "is_covered_by_warranty": covered,
        "estimated_cost": Decimal(cost),
    }


def test_one_price_per_workshop_model_item_including_covered_items():
    rules = [
        _rule("MDL-01", "MI_003", "150000"),
        _rule("MDL-01", "MI_003", "150000", km=30000),  # same item at another milestone
        _rule("MDL-01", "MI_002", "0", covered=True),
        _rule("MDL-05", "MI_003", "150000"),
    ]

    rows = prices.build_prices(rules, ["w1", "w2"], set())

    # Covered items are charged once the warranty has expired, so they need a price too.
    assert sorted((r["workshop_id"], r["model_id"], r["item_code"]) for r in rows) == [
        ("w1", "MDL-01", "MI_002"),
        ("w1", "MDL-01", "MI_003"),
        ("w1", "MDL-05", "MI_003"),
        ("w2", "MDL-01", "MI_002"),
        ("w2", "MDL-01", "MI_003"),
        ("w2", "MDL-05", "MI_003"),
    ]
    assert {r["price"] for r in rows if r["item_code"] == "MI_002"} == {Decimal(0)}


def test_existing_prices_are_never_overwritten():
    rules = [_rule("MDL-04", "MI_003", "150000"), _rule("MDL-04", "MI_005", "350000")]

    rows = prices.build_prices(rules, ["w1"], {("w1", "MDL-04", "MI_003")})

    assert [(r["model_id"], r["item_code"]) for r in rows] == [("MDL-04", "MI_005")]


def test_prices_use_the_workshop_factor_rounded_to_10000():
    assert prices.demo_price(Decimal("350000"), Decimal("1.05")) == Decimal("370000")
    assert prices.demo_price(Decimal("150000"), Decimal("0.95")) == Decimal("140000")
    assert prices.demo_price(Decimal("0"), Decimal("1.10")) == Decimal("0")


def test_workshop_factor_is_stable_and_from_the_allowed_set():
    factor = prices.price_factor("e18893e3-b098-4f9a-b43c-7d36a521a169")

    assert factor in prices.FACTORS
    assert prices.price_factor("e18893e3-b098-4f9a-b43c-7d36a521a169") == factor
