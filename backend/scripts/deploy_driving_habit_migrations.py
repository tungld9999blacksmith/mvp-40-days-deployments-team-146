"""Deploy additive feature migrations without rewriting an unknown base history.

Default is read-only validation. --apply requires an explicit Phase 2 target.
The base alembic_version is NEVER changed. A separate version table tracks the
same four feature revisions. Stop on partial/untracked feature schema.
"""

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from src.common.core import conversation, identity, maintenance, notification, vehicle, workshop  # noqa: E402
from src.config import get_settings  # noqa: E402

VERSION_TABLE = "alembic_version_driving_habit"
REVISIONS = ["a9c4e2f6b8d1", "c7d9b1e3f5a2", "e4b6c8d0f2a3", "f2a4c6e8b0d3"]
FEATURE_TABLES = {
    "reminder_personalization_event",
    "reminder_policy_evaluation",
    "reminder_booking_attribution",
    "vehicle_trip_plan",
}
ADDED_COLUMNS = {
    "user_notification_setting": {
        "personalized_reminders_enabled",
        "personalization_policy_version",
        "personalization_consent_at",
        "personalization_revoked_at",
        "preferred_send_time",
        "quiet_hours_start",
        "quiet_hours_end",
        "timezone",
    },
    "reminder_delivery": {"next_eligible_send_at", "schedule_expires_at", "lease_until", "claim_token"},
    "email_outbox": {"uncertain_attempt_at"},
}
BASE_MODELS = [
    identity.VehicleUser,
    vehicle.UserVehicle,
    vehicle.VehicleOdometerReading,
    vehicle.VehicleOemSync,
    vehicle.VehicleServiceRecord,
    maintenance.MaintenanceRule,
    maintenance.Booking,
    maintenance.Reminder,
    notification.UserNotificationSetting,
    notification.UserNotificationChannel,
    notification.ReminderDelivery,
    notification.EmailOutbox,
    notification.EmailVehicleGate,
    notification.EmailSuppression,
    notification.EmailWebhookEvent,
    conversation.AgentMemorySetting,
    conversation.AgentUserMemory,
    workshop.Workshop,
]


def inspect_target(db):
    inspector = sa.inspect(db)
    tables = set(inspector.get_table_names())
    missing, incompatible = {}, {}
    for model in BASE_MODELS:
        table = model.__table__
        expected = {c.name: c for c in table.columns if c.name not in ADDED_COLUMNS.get(table.name, set())}
        actual = {c["name"]: c for c in inspector.get_columns(table.name)} if table.name in tables else {}
        absent = sorted(set(expected) - set(actual))
        if absent:
            missing[table.name] = absent
        wrong = []
        for name in set(expected) & set(actual):
            expected_type, actual_type = expected[name].type, actual[name]["type"]

            # Enum/varchar and integer sizes are compatible inputs here. Never
            # coerce UUID IDs, temporal data, JSON or boolean fields silently.
            def group(t):
                if isinstance(t, (sa.String, sa.Enum)):
                    return "text"
                return "integer" if isinstance(t, sa.Integer) else t._type_affinity.__name__

            if (
                db.dialect.name == "sqlite"
                and isinstance(expected_type, sa.Uuid)
                and isinstance(actual_type, sa.CHAR)
                and actual_type.length == 32
            ):
                continue
            if group(expected_type) != group(actual_type):
                wrong.append(name)
        if wrong:
            incompatible[table.name] = sorted(wrong)
    base = (
        db.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all()
        if "alembic_version" in tables
        else []
    )
    feature = (
        db.execute(sa.text(f"SELECT version_num FROM {VERSION_TABLE}")).scalars().all()
        if VERSION_TABLE in tables
        else []
    )
    tracked = len(feature) == 1 and feature[0] in REVISIONS
    untracked = sorted(FEATURE_TABLES & tables) if not tracked else []
    if not tracked:
        for table, columns in ADDED_COLUMNS.items():
            if table in tables:
                present = {c["name"] for c in inspector.get_columns(table)} & columns
                untracked.extend(f"{table}.{c}" for c in sorted(present))
    conflict = bool(feature and not tracked) or bool(untracked)
    return {
        "baseRevisions": base,
        "featureRevisions": feature,
        "missingBaseColumns": missing,
        "incompatibleBaseColumns": incompatible,
        "untrackedFeatureObjects": untracked,
        "compatible": not (missing or incompatible or conflict),
    }


def apply_feature_migrations(db):
    if db.dialect.name == "postgresql":
        db.execute(sa.text("SELECT pg_advisory_xact_lock(14620261011)"))
    before = inspect_target(db)
    if not before["compatible"]:
        raise ValueError("FEATURE_BASE_SCHEMA_INCOMPATIBLE")
    # A canonical head uses canonical history; this fallback never forks a
    # database that is already known to the repository migration graph.
    if before["baseRevisions"] and before["baseRevisions"][0] in REVISIONS:
        raise ValueError("USE_CANONICAL_ALEMBIC_UPGRADE")
    version = sa.Table(VERSION_TABLE, sa.MetaData(), sa.Column("version_num", sa.String(32), primary_key=True))
    version.create(db, checkfirst=True)
    current = before["featureRevisions"][0] if before["featureRevisions"] else None
    start = REVISIONS.index(current) + 1 if current else 0
    applied = []
    with Operations.context(MigrationContext.configure(db)):
        for revision_id in REVISIONS[start:]:
            paths = list((ROOT / "backend/alembic/versions").glob(f"{revision_id}_*.py"))
            assert len(paths) == 1
            spec = importlib.util.spec_from_file_location(f"feature_revision_{revision_id}", paths[0])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.upgrade()
            db.execute(version.delete())
            db.execute(version.insert().values(version_num=revision_id))
            applied.append(revision_id)
    after = inspect_target(db)
    if before["baseRevisions"] != after["baseRevisions"]:
        raise ValueError("BASE_HISTORY_CHANGED")
    return {"before": before, "after": after, "applied": applied, "baseHistoryPreserved": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--phase2-target-confirmed", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.apply and not args.phase2_target_confirmed:
        parser.error("--apply requires --phase2-target-confirmed")
    cfg = get_settings()
    engine = sa.create_engine(cfg.sqlalchemy_database_url, connect_args={"connect_timeout": 10})
    report = {"generatedAt": datetime.now(UTC).isoformat(), "readOnly": not args.apply, "versionTable": VERSION_TABLE}
    try:
        with engine.begin() as db:
            if not args.apply:
                db.execute(sa.text("SET TRANSACTION READ ONLY"))
            db.execute(sa.text("SET LOCAL search_path TO public"))
            db.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
            db.execute(sa.text("SET LOCAL statement_timeout = '30s'"))
            result = apply_feature_migrations(db) if args.apply else inspect_target(db)
        report.update(status="applied" if args.apply else "checked", result=result)
    except Exception as exc:
        report.update(status="failed", errorType=type(exc).__name__)
        if isinstance(exc, ValueError):
            report["code"] = str(exc)
        original = getattr(exc, "orig", None)
        if getattr(original, "pgcode", None):
            report["databaseCode"] = original.pgcode
    finally:
        engine.dispose()
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    return int(report["status"] == "failed")


if __name__ == "__main__":
    raise SystemExit(main())
