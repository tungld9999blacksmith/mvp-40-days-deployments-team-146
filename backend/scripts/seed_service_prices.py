"""
Seed demo ``service_price`` rows (ENT-409) so every active workshop has a price for every
maintenance item of every model.

Demo data, not real workshop prices: each price is the item's reference price from the
mock-ev-system dump times a fixed per-workshop factor (derived from the workshop id, so a
run is repeatable), rounded to 10,000 VND. Items covered by warranty get a price too: the
estimate charges them once the vehicle's warranty has expired. Rows that already exist for (workshop, model, item_code) are
left untouched, so real prices entered by a workshop are never overwritten.

The item list comes from the same source and logic as ``seed_maintenance_rules.py``, so
run that one first when the schedule changes.

Run from backend/ (reads the root .env):
    python scripts/seed_service_prices.py              # dry run: print the plan
    python scripts/seed_service_prices.py --apply      # insert the missing prices
    python scripts/seed_service_prices.py --models MDL-05 MDL-06 --apply
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from seed_maintenance_rules import DEFAULT_SOURCE, build_rules, load_dump  # noqa: E402

FACTORS = (Decimal("0.95"), Decimal("1.00"), Decimal("1.05"), Decimal("1.10"))
ROUND_TO = Decimal("10000")

PriceKey = tuple[str, str, str]  # (workshop_id, model_id, item_code)


def price_factor(workshop_id: str) -> Decimal:
    """Fixed demo factor for a workshop, stable across runs and machines."""
    digest = hashlib.sha256(workshop_id.encode()).digest()
    return FACTORS[digest[0] % len(FACTORS)]


def demo_price(reference: Decimal, factor: Decimal) -> Decimal:
    if reference <= 0:
        return Decimal(0)
    return ((reference * factor) / ROUND_TO).quantize(Decimal(1), rounding=ROUND_HALF_UP) * ROUND_TO


def build_prices(rules: list[dict[str, Any]], workshop_ids: list[str], existing: set[PriceKey]) -> list[dict[str, Any]]:
    """Missing price rows for every (workshop, model, item_code), covered items included."""
    items: dict[tuple[str, str], dict[str, Any]] = {}
    for rule in rules:
        items.setdefault((rule["model_id"], rule["item_code"]), rule)
    rows: list[dict[str, Any]] = []
    for workshop_id in sorted(workshop_ids):
        factor = price_factor(workshop_id)
        for (model_id, code), rule in sorted(items.items()):
            if (workshop_id, model_id, code) in existing:
                continue
            rows.append(
                {
                    "workshop_id": workshop_id,
                    "model_id": model_id,
                    "item_code": code,
                    "item_name": rule["item_name"],
                    "price": demo_price(Decimal(rule["estimated_cost"]), factor),
                }
            )
    return rows


def _session():
    from dotenv import load_dotenv

    sys.path.insert(0, str(BACKEND_DIR))
    load_dotenv(BACKEND_DIR.parent / ".env")
    from sqlmodel import Session

    from src.infrastructure.supabase.db import engine

    return Session(engine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed demo service_price rows for every active workshop.")
    parser.add_argument(
        "--source", type=Path, default=DEFAULT_SOURCE, help="mock-ev-system dump JSON (default: %(default)s)"
    )
    parser.add_argument("--models", nargs="+", help="Only these model ids, e.g. MDL-05 MDL-06")
    parser.add_argument("--apply", action="store_true", help="Insert the missing prices (default: dry run)")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    rules, _ = build_rules(load_dump(args.source), models=args.models)
    with _session() as session:
        from sqlmodel import select

        from src.common.core.workshop import ServicePrice, Workshop, WorkshopStatus

        workshops = session.exec(
            select(Workshop.id, Workshop.name).where(Workshop.status == WorkshopStatus.ACTIVE)
        ).all()
        existing = {
            (str(w), m, c)
            for w, m, c in session.exec(
                select(ServicePrice.workshop_id, ServicePrice.model_id, ServicePrice.item_code)
            ).all()
        }
        rows = build_prices(rules, [str(w) for w, _ in workshops], existing)

        names = {str(w): n for w, n in workshops}
        per_workshop = Counter(r["workshop_id"] for r in rows)
        print(f"Source: {args.source}")
        for workshop_id, name in sorted(names.items(), key=lambda x: x[1]):
            print(f"  {name}: factor {price_factor(workshop_id)}, {per_workshop[workshop_id]} prices to insert")
        print(f"  total: {len(rows)} prices to insert; {len(existing)} existing rows kept")
        if not args.apply:
            print("Dry run — add --apply to write.")
            return 0
        session.add_all(ServicePrice(**row) for row in rows)
        session.commit()
    print(f"Applied: {len(rows)} inserted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
