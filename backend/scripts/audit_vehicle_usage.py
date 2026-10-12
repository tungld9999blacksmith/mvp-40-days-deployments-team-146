"""Read-only, aggregate ODO readiness audit; never prints IDs or connection URLs."""

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import get_settings  # noqa: E402
from src.modules.vehicle_usage.domain import utc  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cfg = get_settings()
    report = {"auditedAt": datetime.now(UTC).isoformat(), "staticOdometer": cfg.uses_static_odometer()}
    engine = create_engine(
        cfg.sqlalchemy_database_url,
        connect_args={"connect_timeout": 5} if cfg.sqlalchemy_database_url.startswith("postgresql") else {},
    )
    try:
        now = datetime.now(UTC)
        with engine.connect() as db:
            if engine.dialect.name == "postgresql":
                db.execute(text("SET TRANSACTION READ ONLY"))
                db.execute(text("SET LOCAL statement_timeout = '5000ms'"))
            rows = db.execute(
                text(
                    "SELECT user_vehicle_id, odo_km, recorded_at FROM vehicle_odometer_reading "
                    "WHERE recorded_at >= :cutoff ORDER BY user_vehicle_id, recorded_at LIMIT 100001"
                ),
                {"cutoff": now - timedelta(days=30)},
            ).all()
        groups = defaultdict(list)
        for vehicle_id, km, at in rows[:100000]:
            groups[vehicle_id].append((km, utc(datetime.fromisoformat(at) if isinstance(at, str) else at)))
        ready, stale, decreases, gaps, accelerated = 0, 0, 0, 0, 0
        for readings in groups.values():
            span = (readings[-1][1] - readings[0][1]).total_seconds() / 86400
            is_stale = now - readings[-1][1] > timedelta(days=7)
            stale += is_stale
            days = len({(at + timedelta(hours=7)).date() for _, at in readings})
            has_gap = any(b[1] - a[1] > timedelta(days=7) for a, b in zip(readings, readings[1:]))
            has_decrease = any(b[0] < a[0] for a, b in zip(readings, readings[1:]))
            gaps += has_gap
            decreases += has_decrease
            fast = span >= 1 and (readings[-1][0] - readings[0][0]) / span > cfg.usage_max_daily_km
            accelerated += fast
            ready += days >= 3 and span >= 14 and not (is_stale or has_gap or has_decrease or fast)
        report.update(
            status="ok",
            sampledReadings=min(len(rows), 100000),
            truncated=len(rows) > 100000,
            vehiclesWithRecentReadings=len(groups),
            candidateVehicles=ready,
            staleVehicles=stale,
            vehiclesWithDecreases=decreases,
            vehiclesWithGaps=gaps,
            acceleratedVehicles=accelerated,
        )
    except Exception as exc:
        # Exceptions can embed credentials or the SQL connection string.
        report.update(status="unavailable", errorType=type(exc).__name__)
    finally:
        engine.dispose()
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
