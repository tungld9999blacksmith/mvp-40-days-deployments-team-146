"""
Seed ``maintenance_rule`` (ENT-401) for every vehicle model from mock-ev-system.

The source is mock-ev-system's dump (``maintenance_schedules`` + ``maintenance_items``).
The mock only lists items for the MDL-01 milestones ("các model khác tương tự", see
``mock_ev_system/seed.py``), so a milestone without items of its own reuses the items
of the same km milestone from the first model that has them. ``item_code`` comes
from the mock ``item_id`` (``MI-001`` -> ``MI_001``) so it keeps matching ``service_price``.

Upsert on (model_id, odo_milestone, item_code): safe to run again; by default rows are
never deleted. ``--replace`` makes the selected models match the source exactly: in one
transaction it deletes their rules that the source no longer has, then upserts. Use it
when the schedule itself changes (e.g. 10k/20k/40k -> 15k/30k/45k); a plain upsert
would leave the old milestones next to the new ones. With ``--replace`` the dry run also
lists the bookings, quotes and reminders that point at a milestone being dropped; they
are kept as history and are not changed. Deleting a rule sets ``quote_item.maintenance_rule_id``
to NULL (quotes keep their name/price snapshot) and cascades to ``maintenance_rule_source``.

Run from backend/ (reads the root .env):
    python scripts/seed_maintenance_rules.py                 # dry run: print the plan
    python scripts/seed_maintenance_rules.py --apply         # write to the database
    python scripts/seed_maintenance_rules.py --models MDL-01 MDL-05 --apply
    python scripts/seed_maintenance_rules.py --source other-dump.json --duration 45
    python scripts/seed_maintenance_rules.py --replace       # dry run + inventory of what gets dropped
    python scripts/seed_maintenance_rules.py --replace --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = BACKEND_DIR / "mock-ev-system" / "seed-data" / "ev-mock-dump.json"
DEFAULT_DURATION_MINUTES = 30
ITEM_CODE_RE = re.compile(r"^[A-Z0-9_]{2,50}$")  # ck_maintenance_rule_item_code_format


def load_dump(path: Path) -> dict[str, list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return raw.get("data", raw)


def item_code(item_id: str) -> str:
    code = re.sub(r"[^A-Z0-9]+", "_", item_id.upper()).strip("_")
    if not ITEM_CODE_RE.match(code):
        raise ValueError(f"Cannot derive a valid item_code from item_id {item_id!r}")
    return code


def build_rules(
    dump: dict[str, list[dict[str, Any]]],
    *,
    models: list[str] | None = None,
    duration_minutes: int = DEFAULT_DURATION_MINUTES,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (rule rows, warnings) for the requested models (default: every model)."""
    schedules = sorted(dump.get("maintenance_schedules", []), key=lambda s: (s["model_id"], s["milestone_km"]))
    items_by_schedule: dict[str, list[dict[str, Any]]] = {}
    for item in sorted(dump.get("maintenance_items", []), key=lambda i: i["item_id"]):
        items_by_schedule.setdefault(item["schedule_id"], []).append(item)

    # Template per km milestone: items of the first model (by model_id) that has any.
    template: dict[int, tuple[str, list[dict[str, Any]]]] = {}
    for schedule in schedules:
        own = items_by_schedule.get(schedule["schedule_id"])
        if own and schedule["milestone_km"] not in template:
            template[schedule["milestone_km"]] = (schedule["model_id"], own)

    model_ids = models or sorted(
        {m["model_id"] for m in dump.get("vehicle_models", [])} | {s["model_id"] for s in schedules}
    )
    known = {s["model_id"] for s in schedules}
    warnings = [
        f"{model_id}: no maintenance_schedules in the source" for model_id in model_ids if model_id not in known
    ]

    rows: list[dict[str, Any]] = []
    for schedule in schedules:
        model_id, km = schedule["model_id"], schedule["milestone_km"]
        if model_id not in model_ids:
            continue
        items = items_by_schedule.get(schedule["schedule_id"])
        if not items:
            if km not in template:
                warnings.append(f"{model_id} @ {km} km: no items for this milestone in any model, skipped")
                continue
            items = template[km][1]
        for item in items:
            rows.append(
                {
                    "model_id": model_id,
                    "odo_milestone": km,
                    "month_milestone": schedule["milestone_months"],
                    "item_code": item_code(item["item_id"]),
                    "item_name": item["item_name"],
                    "is_covered_by_warranty": bool(item.get("is_covered_by_warranty", False)),
                    "estimated_cost": Decimal(str(item.get("reference_price") or 0)),
                    "estimated_duration_minutes": duration_minutes,
                }
            )
    return rows, warnings


RuleKey = tuple[str, int, str]  # (model_id, odo_milestone, item_code)


def stale_keys(existing: set[RuleKey], rows: list[dict[str, Any]], models: set[str]) -> set[RuleKey]:
    """Keys of the selected models that exist now but are missing from ``rows``."""
    wanted = {(r["model_id"], r["odo_milestone"], r["item_code"]) for r in rows}
    return {key for key in existing if key[0] in models and key not in wanted}


def dropped_milestones(existing: set[RuleKey], rows: list[dict[str, Any]], models: set[str]) -> dict[str, set[int]]:
    """Per model, the milestones (km) that exist now and that ``rows`` no longer has at all."""
    kept: dict[str, set[int]] = {}
    for r in rows:
        kept.setdefault(r["model_id"], set()).add(r["odo_milestone"])
    dropped: dict[str, set[int]] = {}
    for model_id, km, _ in existing:
        if model_id in models and km not in kept.get(model_id, set()):
            dropped.setdefault(model_id, set()).add(km)
    return dropped


def existing_keys(session: Any, models: set[str]) -> set[RuleKey]:
    from sqlmodel import select

    from src.common.core.maintenance.maintenance_rule import MaintenanceRule

    stmt = select(MaintenanceRule.model_id, MaintenanceRule.odo_milestone, MaintenanceRule.item_code).where(
        MaintenanceRule.model_id.in_(models)
    )
    return {(m, int(km), code) for m, km, code in session.exec(stmt).all()}


def replace_inventory(session: Any, stale: set[RuleKey], dropped: dict[str, set[int]]) -> dict[str, int]:
    """Count the rows that reference what ``--replace`` removes (read only)."""
    from sqlalchemy import text

    counts = {"quote_items_unlinked": 0, "rule_sources_deleted": 0, "bookings": 0, "quotes": 0, "reminders": 0}
    if stale:
        params = {f"m{i}": m for i, (m, _, _) in enumerate(stale)}
        params |= {f"k{i}": km for i, (_, km, _) in enumerate(stale)}
        params |= {f"c{i}": c for i, (_, _, c) in enumerate(stale)}
        match = " OR ".join(
            f"(r.model_id = :m{i} AND r.odo_milestone = :k{i} AND r.item_code = :c{i})" for i in range(len(stale))
        )
        counts["quote_items_unlinked"] = session.execute(
            text(
                f"SELECT count(*) FROM quote_item qi JOIN maintenance_rule r ON r.id = qi.maintenance_rule_id WHERE {match}"
            ),
            params,
        ).scalar_one()
        counts["rule_sources_deleted"] = session.execute(
            text(
                f"SELECT count(*) FROM maintenance_rule_source s JOIN maintenance_rule r ON r.id = s.maintenance_rule_id WHERE {match}"
            ),
            params,
        ).scalar_one()
    for model_id, kms in dropped.items():
        p = {"model": model_id, "kms": list(kms)}
        counts["bookings"] += session.execute(
            text(
                "SELECT count(*) FROM booking b JOIN user_vehicle v ON v.id = b.user_vehicle_id "
                "WHERE v.external_model_id = :model AND b.odo_milestone = ANY(:kms)"
            ),
            p,
        ).scalar_one()
        counts["quotes"] += session.execute(
            text(
                "SELECT count(*) FROM quote q JOIN user_vehicle v ON v.id = q.user_vehicle_id "
                "WHERE v.external_model_id = :model AND q.odo_milestone = ANY(:kms)"
            ),
            p,
        ).scalar_one()
        counts["reminders"] += session.execute(
            text(
                "SELECT count(*) FROM reminder r JOIN user_vehicle v ON v.id = r.user_vehicle_id "
                "WHERE v.external_model_id = :model AND r.target_odo_milestone = ANY(:kms)"
            ),
            p,
        ).scalar_one()
    return counts


def upsert_rules(session: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert or update ``rows`` and commit; return (inserted, updated)."""
    inserted, updated = _upsert(session, rows)
    session.commit()
    return inserted, updated


def replace_rules(session: Any, rows: list[dict[str, Any]], models: set[str]) -> tuple[int, int, int]:
    """Make ``models`` match ``rows`` in one transaction; return (deleted, inserted, updated)."""
    from sqlalchemy import delete, tuple_

    from src.common.core.maintenance.maintenance_rule import MaintenanceRule

    stale = stale_keys(existing_keys(session, models), rows, models)
    try:
        if stale:
            session.exec(
                delete(MaintenanceRule).where(
                    tuple_(MaintenanceRule.model_id, MaintenanceRule.odo_milestone, MaintenanceRule.item_code).in_(
                        stale
                    )
                )
            )
        inserted, updated = _upsert(session, rows)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return len(stale), inserted, updated


def _upsert(session: Any, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert or update ``rows`` without committing; return (inserted, updated)."""
    from sqlalchemy import func, tuple_
    from sqlalchemy.dialects.postgresql import insert
    from sqlmodel import select

    from src.common.core.maintenance.maintenance_rule import MaintenanceRule

    if not rows:
        return 0, 0
    keys = {(r["model_id"], r["odo_milestone"], r["item_code"]) for r in rows}
    existing = set(
        session.exec(
            select(MaintenanceRule.model_id, MaintenanceRule.odo_milestone, MaintenanceRule.item_code).where(
                tuple_(MaintenanceRule.model_id, MaintenanceRule.odo_milestone, MaintenanceRule.item_code).in_(keys)
            )
        ).all()
    )
    stmt = insert(MaintenanceRule.__table__).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="ux_maintenance_rule_model_milestone_code",
        set_={
            "month_milestone": stmt.excluded.month_milestone,
            "item_name": stmt.excluded.item_name,
            "is_covered_by_warranty": stmt.excluded.is_covered_by_warranty,
            "estimated_cost": stmt.excluded.estimated_cost,
            "estimated_duration_minutes": stmt.excluded.estimated_duration_minutes,
            "updated_at": func.now(),
        },
    )
    session.exec(stmt)
    updated = len(keys & existing)
    return len(keys) - updated, updated


def _print_plan(rows: list[dict[str, Any]], warnings: list[str]) -> None:
    per_model = Counter(r["model_id"] for r in rows)
    milestones: dict[str, set[int]] = {}
    for r in rows:
        milestones.setdefault(r["model_id"], set()).add(r["odo_milestone"])
    for model_id in sorted(per_model):
        kms = ", ".join(f"{km // 1000}k" for km in sorted(milestones[model_id]))
        print(f"  {model_id}: {per_model[model_id]:>3} rules  ({kms})")
    print(f"  total: {len(rows)} rules")
    for warning in warnings:
        print(f"  WARN {warning}", file=sys.stderr)


def _print_replace(stale: set[RuleKey], dropped: dict[str, set[int]], counts: dict[str, int]) -> None:
    print(f"Replace: {len(stale)} rules to delete")
    for model_id in sorted(dropped):
        kms = ", ".join(f"{km // 1000}k" for km in sorted(dropped[model_id]))
        print(f"  {model_id}: milestones dropped ({kms})")
    print(
        "  references kept as history: "
        f"{counts['bookings']} bookings, {counts['quotes']} quotes, {counts['reminders']} reminders"
    )
    print(
        f"  quote_item.maintenance_rule_id set to NULL: {counts['quote_items_unlinked']}; "
        f"maintenance_rule_source deleted: {counts['rule_sources_deleted']}"
    )


def _session():
    sys.path.insert(0, str(BACKEND_DIR))
    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR.parent / ".env")
    from sqlmodel import Session

    from src.infrastructure.supabase.db import engine

    return Session(engine)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed maintenance_rule for every vehicle model from mock-ev-system.")
    parser.add_argument(
        "--source", type=Path, default=DEFAULT_SOURCE, help="mock-ev-system dump JSON (default: %(default)s)"
    )
    parser.add_argument("--models", nargs="+", help="Only these model ids, e.g. MDL-01 MDL-05")
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_MINUTES,
        help="estimated_duration_minutes per item (default %(default)s)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete rules of the selected models that the source no longer has (one transaction)",
    )
    parser.add_argument("--apply", action="store_true", help="Write to the database (default: dry run)")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    if args.duration <= 0:
        parser.error("--duration must be > 0")

    rows, warnings = build_rules(load_dump(args.source), models=args.models, duration_minutes=args.duration)
    print(f"Source: {args.source}")
    _print_plan(rows, warnings)
    models = {r["model_id"] for r in rows}

    if args.replace:
        # The dry run reads the database (read only) to list what would be dropped.
        with _session() as session:
            existing = existing_keys(session, models)
            stale = stale_keys(existing, rows, models)
            dropped = dropped_milestones(existing, rows, models)
            _print_replace(stale, dropped, replace_inventory(session, stale, dropped))
            session.rollback()
            if args.apply:
                deleted, inserted, updated = replace_rules(session, rows, models)
                print(f"Applied: {deleted} deleted, {inserted} inserted, {updated} updated.")
                return 0
    if not args.apply:
        print("Dry run — add --apply to write.")
        return 0

    with _session() as session:
        inserted, updated = upsert_rules(session, rows)
    print(f"Applied: {inserted} inserted, {updated} updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
