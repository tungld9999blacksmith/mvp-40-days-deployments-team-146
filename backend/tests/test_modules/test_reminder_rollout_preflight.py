"""Release preflight uses aggregates and never treats fixtures as release approval."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlmodel import Session, create_engine, select

from scripts.check_reminder_rollout import MIGRATION_HEAD, inspect_readiness
from src.common.core.notification import ReminderPolicyEvaluation, UserNotificationSetting
from src.config import Settings
from src.modules.notification.schemas import NotificationSettingsUpdateIn
from src.modules.notification.settings_service import NotificationSettingsService
from src.modules.vehicle_usage.service import PERSONALIZATION_POLICY_VERSION
from tests._user_vehicle import add_owner, add_vehicle, make_session

NOW = datetime(2026, 10, 11, 2, tzinfo=UTC)


def audit(**overrides):
    return (
        dict(auditedAt=NOW.isoformat(), status="ok", truncated=False, candidateVehicles=1, staticOdometer=False)
        | overrides
    )


def test_legacy_database_is_held_without_reading_missing_columns():
    engine = create_engine("sqlite://")
    with Session(engine) as db:
        db.execute(text("CREATE TABLE user_notification_setting (user_id INTEGER PRIMARY KEY)"))
        db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        db.execute(text("INSERT INTO alembic_version VALUES ('f8b2d6a4c1e9')"))
        db.commit()
        report = inspect_readiness(db, Settings(_env_file=None), audit(), now=NOW)
        assert report["status"] == "hold"
        assert not report["checks"]["migrationsApplied"]
        assert len(report["missingTables"]) == 6 and len(report["missingSettingColumns"]) == 8
        assert not report["canStartCanary"]
    engine.dispose()


@pytest.fixture
def ready_db():
    generator = make_session()
    db = next(generator)
    owner = add_owner(db)
    vehicle = add_vehicle(db, owner)
    NotificationSettingsService(db, available_channels=set(), default_lead_days=7).update(
        owner,
        NotificationSettingsUpdateIn(
            personalized_reminders_enabled=True, personalization_policy_version=PERSONALIZATION_POLICY_VERSION
        ),
    )
    db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
    db.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": MIGRATION_HEAD})
    for day in range(14):
        at = NOW - timedelta(days=day)
        db.add(
            ReminderPolicyEvaluation(
                user_id=owner.user_id,
                user_vehicle_id=vehicle.id,
                evaluation_day=at.date(),
                mode="shadow",
                forecast_status="AVAILABLE",
                lead_days=7,
                duration_ms=5,
                calculated_at=at,
            )
        )
    db.commit()
    cfg = Settings(
        _env_file=None,
        oem_sync_mode="oem",
        personalized_reminders_mode="on",
        personalized_reminders_canary_user_ids=str(owner.user_id),
    )
    yield db, cfg
    engine = db.bind
    generator.close()
    engine.dispose()


def test_all_technical_checks_still_require_real_evidence_review(ready_db):
    db, cfg = ready_db
    before = [row.model_dump() for row in db.exec(select(UserNotificationSetting)).all()]
    report = inspect_readiness(db, cfg, audit(), now=NOW)
    assert all(report["checks"].values())
    assert report["status"] == "review_required" and report["canStartShadowTechnical"]
    assert report["canaryTechnicalChecksPassed"] and not report["canStartCanary"]
    assert report["externalProviderCalls"] == 0 and report["readOnly"]
    assert "user_id" not in json.dumps(report) and "@" not in json.dumps(report)
    assert before == [row.model_dump() for row in db.exec(select(UserNotificationSetting)).all()]


@pytest.mark.parametrize("change", ["stale", "future", "static", "truncated", "empty", "malformed"])
def test_missing_or_untrustworthy_history_holds_canary(ready_db, change):
    db, cfg = ready_db
    overrides = {
        "stale": {"auditedAt": (NOW - timedelta(hours=2)).isoformat()},
        "future": {"auditedAt": (NOW + timedelta(minutes=1)).isoformat()},
        "static": {"staticOdometer": True},
        "truncated": {"truncated": True},
        "empty": {"candidateVehicles": 0},
        "malformed": {"auditedAt": "not-a-date"},
    }
    report = inspect_readiness(db, cfg, audit(**overrides[change]), now=NOW)
    assert not report["checks"]["freshAuditHasHistoryCandidates"]
    assert report["status"] == "hold" and not report["canaryTechnicalChecksPassed"]


@pytest.mark.parametrize(
    "change",
    [
        "outside_cohort",
        "no_cohort",
        "no_consent",
        "obsolete_consent",
        "future_shadow",
        "insufficient_shadow",
        "static_source",
    ],
)
def test_readiness_is_scoped_to_valid_consented_cohort(ready_db, change):
    db, cfg = ready_db
    setting = db.exec(select(UserNotificationSetting)).one()
    if change == "outside_cohort":
        cfg.personalized_reminders_canary_user_ids = str(setting.user_id + 100)
    elif change == "no_cohort":
        cfg.personalized_reminders_canary_user_ids = ""
    elif change == "no_consent":
        setting.personalized_reminders_enabled = False
    elif change == "obsolete_consent":
        setting.personalization_policy_version = "obsolete"
    elif change in {"future_shadow", "insufficient_shadow"}:
        rows = db.exec(select(ReminderPolicyEvaluation)).all()
        for row in rows if change == "future_shadow" else rows[:1]:
            row.calculated_at = NOW + timedelta(days=1)
            db.add(row)
    else:
        cfg.oem_sync_mode = "static"
    db.add(setting)
    db.commit()
    report = inspect_readiness(db, cfg, audit(), now=NOW)
    assert report["status"] == "hold" and not report["canaryTechnicalChecksPassed"]
