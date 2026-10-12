"""Read-only release preflight. Never migrates, opts in users or sends reminders.

Run the ODO audit first, then pass its aggregate JSON via --audit. This report
checks technical prerequisites; real forecast accuracy still needs review.
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, func, inspect, text  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from src.common.core.notification import ReminderPolicyEvaluation, UserNotificationSetting  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.modules.vehicle_usage.domain import utc  # noqa: E402
from src.modules.vehicle_usage.service import PERSONALIZATION_POLICY_VERSION  # noqa: E402

REQUIRED_TABLES = {
    "user_notification_setting",
    "reminder_personalization_event",
    "reminder_policy_evaluation",
    "reminder_booking_attribution",
    "reminder_delivery",
    "email_outbox",
    "vehicle_trip_plan",
}
REQUIRED_COLUMNS = {
    "personalized_reminders_enabled",
    "personalization_policy_version",
    "personalization_consent_at",
    "personalization_revoked_at",
    "preferred_send_time",
    "quiet_hours_start",
    "quiet_hours_end",
    "timezone",
}
MIGRATION_HEAD = "f2a4c6e8b0d3"
REQUIRED_DELIVERY_COLUMNS = {"next_eligible_send_at", "schedule_expires_at", "claim_token", "lease_until"}


def inspect_readiness(db, cfg, audit, *, now):
    inspector = inspect(db.connection())
    tables = set(inspector.get_table_names())
    missing_tables = sorted(REQUIRED_TABLES - tables)
    columns = (
        {row["name"] for row in inspector.get_columns("user_notification_setting")}
        if "user_notification_setting" in tables
        else set()
    )
    missing_columns = sorted(REQUIRED_COLUMNS - columns)
    delivery_columns = (
        {row["name"] for row in inspector.get_columns("reminder_delivery")} if "reminder_delivery" in tables else set()
    )
    missing_delivery_columns = sorted(REQUIRED_DELIVERY_COLUMNS - delivery_columns)
    outbox_ready = "email_outbox" in tables and "uncertain_attempt_at" in {
        row["name"] for row in inspector.get_columns("email_outbox")
    }
    revisions = (
        db.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        if "alembic_version" in tables
        else []
    )
    feature_revisions = (
        db.execute(text("SELECT version_num FROM alembic_version_driving_habit")).scalars().all()
        if "alembic_version_driving_habit" in tables
        else []
    )
    schema_ready = (
        not missing_tables
        and not missing_columns
        and not missing_delivery_columns
        and outbox_ready
        and (MIGRATION_HEAD in revisions or MIGRATION_HEAD in feature_revisions)
    )
    cohort = {int(part) for part in cfg.personalized_reminders_canary_user_ids.split(",") if part}
    consent_count = cohort_consent_count = shadow_vehicles = 0
    consent_inspectable = not missing_columns and "user_notification_setting" in tables
    if consent_inspectable:
        statement = select(UserNotificationSetting.user_id).where(
            UserNotificationSetting.personalized_reminders_enabled.is_(True),
            UserNotificationSetting.personalization_policy_version == PERSONALIZATION_POLICY_VERSION,
            UserNotificationSetting.personalization_consent_at.is_not(None),
        )
        owners = set(db.exec(statement).all())
        consent_count = len(owners)
        cohort_consent_count = len(owners & cohort) if cohort else len(owners)
        if schema_ready:
            # No owner identifiers or raw observations leave this report.
            shadow = (
                select(
                    ReminderPolicyEvaluation.user_vehicle_id,
                    func.count(func.distinct(ReminderPolicyEvaluation.evaluation_day)),
                )
                .where(
                    ReminderPolicyEvaluation.mode == "shadow",
                    ReminderPolicyEvaluation.user_id.in_(owners & cohort if cohort else owners),
                    ReminderPolicyEvaluation.calculated_at >= now - timedelta(days=30),
                    ReminderPolicyEvaluation.calculated_at <= now,
                )
                .group_by(ReminderPolicyEvaluation.user_vehicle_id)
            )
            shadow_vehicles = sum(days >= 14 for _, days in db.exec(shadow).all())
    try:
        audit_at = utc(datetime.fromisoformat(audit["auditedAt"]))
        audit_fresh = timedelta(0) <= utc(now) - audit_at <= timedelta(hours=1)
    except (KeyError, TypeError, ValueError):
        audit_fresh = False
    history_ready = bool(
        audit_fresh
        and audit.get("status") == "ok"
        and not audit.get("truncated")
        and audit.get("candidateVehicles", 0) > 0
        and not audit.get("staticOdometer", True)
    )
    checks = {
        "migrationsApplied": schema_ready,
        "realOemSource": not cfg.uses_static_odometer(),
        "freshAuditHasHistoryCandidates": history_ready,
        "cohortHasExplicitConsent": cohort_consent_count > 0,
        "canaryCohortConfigured": bool(cohort),
        "shadowVehicleHas14ObservationDays": shadow_vehicles > 0,
    }
    technical_shadow = schema_ready and checks["realOemSource"] and cohort_consent_count > 0
    technical_canary = all(checks.values())
    return {
        "checkedAt": utc(now).isoformat(),
        "status": "review_required" if technical_canary else "hold",
        "configuredMode": cfg.personalized_reminders_mode,
        "readOnly": True,
        "externalProviderCalls": 0,
        "configuredDatabaseMigrationsAppliedByThisRun": False,
        "canStartShadowTechnical": technical_shadow,
        "canaryTechnicalChecksPassed": technical_canary,
        "canStartCanary": False,
        "checks": checks,
        "currentRevisions": revisions,
        "missingTables": missing_tables,
        "missingSettingColumns": missing_columns,
        "missingDeliveryColumns": missing_delivery_columns,
        "emailUncertaintyColumnPresent": outbox_ready,
        "configuredCohortOwnerCount": len(cohort),
        "consentChecked": consent_inspectable,
        "optInOwnerCount": consent_count if consent_inspectable else None,
        "cohortOptInOwnerCount": cohort_consent_count if consent_inspectable else None,
        "shadowVehiclesWith14Days": shadow_vehicles if schema_ready else None,
        "pendingReviews": [
            "Confirm a separate Phase 2 deployment target",
            "Review real OEM backtest accuracy and full fleet latency",
            "Review cohort-specific shadow evidence and acceptance criteria",
        ],
        "featureMigrationRevisions": feature_revisions,
        "migrationTracking": "feature_stream" if MIGRATION_HEAD in feature_revisions else "canonical",
        "notes": [
            "History candidates are an aggregate audit signal, not a guarantee of eligible forecast for each cohort vehicle.",
            "An empty cohort is for full rollout; canary requires an explicit owner list.",
            "Shadow preserves baseline sending; EMAIL_MODE=resend may still send baseline emails when running the actual worker.",
            "This command only reads metadata and aggregate records. It does not call any provider or start workers.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase2-target-confirmed", action="store_true")
    args = parser.parse_args()
    cfg = get_settings()
    engine = create_engine(
        cfg.sqlalchemy_database_url,
        connect_args={"connect_timeout": 5} if cfg.sqlalchemy_database_url.startswith("postgresql") else {},
    )
    try:
        audit = json.loads(args.audit.read_text(encoding="utf-8"))
        with Session(engine) as db:
            if engine.dialect.name == "postgresql":
                db.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
                db.connection().exec_driver_sql("SET LOCAL search_path TO public")
                db.connection().exec_driver_sql("SET LOCAL statement_timeout = 5000")
            report = inspect_readiness(db, cfg, audit, now=datetime.now(UTC))
            report["phase2TargetConfirmed"] = args.phase2_target_confirmed
            if args.phase2_target_confirmed:
                report["pendingReviews"].remove("Confirm a separate Phase 2 deployment target")
    except Exception as exc:
        report = {
            "status": "unavailable",
            "errorType": type(exc).__name__,
            "readOnly": True,
            "canStartCanary": False,
            "externalProviderCalls": 0,
        }
    finally:
        engine.dispose()
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    # A successful audit is not a release approval. Holds are useful output.
    return 1 if report["status"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
