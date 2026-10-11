"""
Seed active demo workshops into the backend DB from the workshop_crawl output, without
going through Firebase onboarding.

An active workshop must have an owner (W-09) and ``workshop_owner.firebase_uid`` is required,
so each workshop gets a placeholder owner whose uid is ``seed:<center_id>``. No Firebase user
has that uid, so nobody can sign in as it: the workshop takes bookings (confirmation mode
``auto``) but has no Workshop Portal user. Name, region, type and coordinates come from the
crawled place (the same records imported into mock-ev-system's ``service_center``, so
``external_center_id`` matches the OEM). Operating hours are a fixed demo schedule.

The crawl has no phone numbers, and the hotline is shown to vehicle owners as a "call" button, so
it is left empty rather than invented (the UI hides the button). The placeholder owner never
completed a profile (no ``profile_completed_at``), so the DB does not require its phone either.

Workshops whose ``external_center_id`` already exists are skipped (onboarded or seeded before),
so a re-run is safe. Run ``seed_service_prices.py --apply`` afterwards to give them prices.

Run from backend/ (reads the root .env):
    python scripts/seed_workshops.py                         # dry run: print the plan
    python scripts/seed_workshops.py --apply                 # insert the missing workshops
    python scripts/seed_workshops.py --region "Hà Nội" --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import time
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
DEFAULT_SOURCE = BACKEND_DIR.parent / "tools" / "workshop_crawl" / "data" / "workshops.json"

SEED_UID_PREFIX = "seed:"
SEED_AUTH_PROVIDER = "seed"
TECHNICIANS = (3, 4, 5, 6)

# ISO weekday → (open, close); ``None`` means closed. Mon–Sat 08:00–17:30, Sun 08:00–12:00.
DEMO_HOURS: dict[int, tuple[time, time] | None] = {
    **{day: (time(8, 0), time(17, 30)) for day in range(1, 7)},
    7: (time(8, 0), time(12, 0)),
}


def load_records(path: Path, region: str | None = None) -> list[dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))["workshops"]
    if region:
        records = [r for r in records if r["region"] == region]
    return records


def technicians_for(center_id: str) -> int:
    """Fixed demo headcount for a workshop, stable across runs and machines."""
    digest = hashlib.sha256(center_id.encode()).digest()
    return TECHNICIANS[digest[0] % len(TECHNICIANS)]


def operating_hours() -> list[dict[str, Any]]:
    rows = []
    for day, hours in sorted(DEMO_HOURS.items()):
        open_time, close_time = hours if hours else (None, None)
        rows.append({"day_of_week": day, "is_closed": hours is None, "open_time": open_time, "close_time": close_time})
    return rows


def build_plan(
    records: list[dict[str, Any]],
    existing_center_ids: set[str],
    existing_emails: set[str],
    existing_national_ids: set[str],
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    """(workshops to insert, [(center_id, reason skipped)]) for the crawled records."""
    plan: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []
    emails, national_ids = set(existing_emails), set(existing_national_ids)
    for r in records:
        center_id = r["center_id"]
        if center_id in existing_center_ids:
            skipped.append((center_id, "workshop already exists"))
            continue
        if r.get("latitude") is None or r.get("longitude") is None:
            skipped.append((center_id, "no coordinates"))
            continue
        email, national_id = r["manager_email"].lower(), r["manager_national_id"]
        if email in emails or national_id in national_ids:
            skipped.append((center_id, f"owner email/national id already used ({email})"))
            continue
        emails.add(email)
        national_ids.add(national_id)
        plan.append(
            {
                "owner": {
                    "firebase_uid": f"{SEED_UID_PREFIX}{center_id}",
                    "email": email,
                    "auth_provider": SEED_AUTH_PROVIDER,
                    "display_name": r["name"][:255],
                    "full_name": r["name"][:150],
                    "national_id": national_id,
                },
                "workshop": {
                    "external_center_id": center_id,
                    "name": r["name"][:150],
                    "region": r["region"],
                    "type": r["type"],
                    "address": r["address"],
                    "latitude": r["latitude"],
                    "longitude": r["longitude"],
                    "total_technicians": technicians_for(center_id),
                },
                "hours": operating_hours(),
            }
        )
    return plan, skipped


def _session():
    from dotenv import load_dotenv

    sys.path.insert(0, str(BACKEND_DIR))
    load_dotenv(BACKEND_DIR.parent / ".env")
    from sqlmodel import Session

    from src.infrastructure.supabase.db import engine

    return Session(engine)


def apply_plan(session: Any, plan: list[dict[str, Any]]) -> None:
    from datetime import UTC, datetime
    from decimal import Decimal

    from src.common.core.identity import WorkshopOwner
    from src.common.core.identity.workshop_owner import WorkshopOwnerOnboardingStatus
    from src.common.core.workshop import (
        BookingConfirmationMode,
        ServiceCenterType,
        Workshop,
        WorkshopOperatingHour,
        WorkshopStatus,
    )

    now = datetime.now(UTC)
    for item in plan:
        owner = WorkshopOwner(
            **item["owner"],
            onboarding_status=WorkshopOwnerOnboardingStatus.ACTIVE,
            onboarding_completed_at=now,
        )
        session.add(owner)
        session.flush()
        w = item["workshop"]
        workshop = Workshop(
            **{**w, "type": ServiceCenterType(w["type"])},
            status=WorkshopStatus.ACTIVE,
            booking_confirmation_mode=BookingConfirmationMode.AUTO,
            owner_id=owner.id,
            hotline="",
            onboarded_at=now,
            oem_synced_at=now,
        )
        workshop.latitude = Decimal(str(w["latitude"]))
        workshop.longitude = Decimal(str(w["longitude"]))
        session.add(workshop)
        session.flush()
        session.add_all(WorkshopOperatingHour(workshop_id=workshop.id, **h) for h in item["hours"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed active demo workshops from the workshop_crawl output.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="workshops.json (default: %(default)s)")
    parser.add_argument("--region", help='Only this region, e.g. "Hà Nội"')
    parser.add_argument("--apply", action="store_true", help="Insert the missing workshops (default: dry run)")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    records = load_records(args.source, args.region)
    with _session() as session:
        from sqlmodel import select

        from src.common.core.identity import WorkshopOwner
        from src.common.core.workshop import Workshop

        center_ids = set(session.exec(select(Workshop.external_center_id)).all())
        emails = {e.lower() for e in session.exec(select(WorkshopOwner.email)).all()}
        national_ids = {n for n in session.exec(select(WorkshopOwner.national_id)).all() if n}
        plan, skipped = build_plan(records, center_ids, emails, national_ids)

        print(f"Source: {args.source} ({len(records)} records)")
        for item in plan:
            w = item["workshop"]
            print(f"  + {w['external_center_id']} {w['name']} | {w['region']} | {w['total_technicians']} technicians")
        for center_id, reason in skipped:
            print(f"  - {center_id}: {reason}")
        print(f"  total: {len(plan)} workshops to insert, {len(skipped)} skipped")
        if not args.apply:
            print("Dry run — add --apply to write.")
            return 0
        apply_plan(session, plan)
        session.commit()
    print(f"Applied: {len(plan)} workshops inserted. Next: python scripts/seed_service_prices.py --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
