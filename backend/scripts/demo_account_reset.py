"""
Reset the shared demo account ("Dùng thử ngay", src/modules/demo_account) right now.

The hourly Celery job does this every DEMO_RESET_INTERVAL_HOURS; use this script when
the account needs a clean state sooner (before a demo, after a broken seed). It wipes
everything visitors created (bookings and their workshop-side rows, chats, quotes,
notifications), resets the manufacturer's demo owner and seeds VF3, VF8 and VF Wild again.

Run from backend/ (reads the root .env). Nothing is written without ``--apply``:
    python scripts/demo_account_reset.py                   # show the state only
    python scripts/demo_account_reset.py --apply           # reset when due
    python scripts/demo_account_reset.py --apply --force   # reset now
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reset the shared demo account.")
    parser.add_argument("--force", action="store_true", help="Reset even if the interval has not passed")
    parser.add_argument("--apply", action="store_true", help="Write to the database (default: show the state)")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR.parent / ".env")

    from sqlmodel import Session

    from src.config import get_settings
    from src.infrastructure.supabase.db import engine
    from src.modules.demo_account.dependency import build_demo_service
    from src.modules.demo_account.errors import DemoAccountError
    from src.modules.demo_account.service import demo_resets_at

    settings = get_settings()
    with Session(engine) as session:
        service = build_demo_service(session, settings)
        user = service.find_user()
        next_reset = demo_resets_at(session, settings.demo_reset_interval_hours)
        print(
            f"Demo account: {'user_id ' + str(user.user_id) if user else 'not seeded yet'} ({settings.demo_account_email})"
        )
        print(f"Next scheduled reset: {next_reset.isoformat() if next_reset else 'now (never reset)'}")
        if not args.apply:
            print("Dry run: add --apply (and --force to skip the interval) to reset.")
            return 0
        try:
            done = asyncio.run(service.reset_if_due(force=args.force))
        except DemoAccountError as exc:
            print(f"ERROR: {exc.message}", file=sys.stderr)
            return 1
        print("Reset done." if done else "Not due yet: nothing changed (use --force).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
