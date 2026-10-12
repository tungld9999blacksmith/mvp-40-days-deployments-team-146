"""The additive migration preserves preferences and is reversible on SQLite."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory


def test_merged_migration_history_has_one_head_and_keeps_both_feature_branches():
    backend = Path(__file__).resolve().parents[2]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    script = ScriptDirectory.from_config(cfg)

    assert len(script.get_heads()) == 1
    reachable = {revision.revision for revision in script.walk_revisions()}
    assert {
        "a9c4e2f6b8d1",
        "c7d9b1e3f5a2",
        "e4b6c8d0f2a3",
        "f2a4c6e8b0d3",
        "d5b2e8f4a1c7",
        "e1c5a7b9d3f2",
        "f2e6c8a1b4d9",
    }.issubset(reachable)


def test_upgrade_downgrade_preserves_existing_preferences():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/a9c4e2f6b8d1_personalized_reminders.py"
    spec = importlib.util.spec_from_file_location("usage_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as db:
        db.execute(sa.text("CREATE TABLE vehicle_user (user_id INTEGER PRIMARY KEY)"))
        db.execute(
            sa.text(
                "CREATE TABLE user_notification_setting (user_id INTEGER PRIMARY KEY, reminder_lead_days INTEGER, reminders_enabled BOOLEAN)"
            )
        )
        db.execute(sa.text("INSERT INTO user_notification_setting VALUES (1, 7, 1)"))
        with Operations.context(MigrationContext.configure(db)):
            revision.upgrade()
        assert db.execute(
            sa.text("SELECT reminder_lead_days, personalized_reminders_enabled FROM user_notification_setting")
        ).one() == (7, 0)
        assert "reminder_personalization_event" in sa.inspect(db).get_table_names()
        with Operations.context(MigrationContext.configure(db)):
            revision.downgrade()
        assert db.execute(sa.text("SELECT reminder_lead_days FROM user_notification_setting")).scalar_one() == 7
        assert "reminder_personalization_event" not in sa.inspect(db).get_table_names()
        with Operations.context(MigrationContext.configure(db)):
            revision.upgrade()
    engine.dispose()


def test_metrics_migration_is_reversible_and_recreates_indexes():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/c7d9b1e3f5a2_reminder_metrics.py"
    spec = importlib.util.spec_from_file_location("usage_metrics_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as db:
        with Operations.context(MigrationContext.configure(db)):
            revision.upgrade()
            assert "reminder_booking_attribution" in sa.inspect(db).get_table_names()
            assert any(
                index["column_names"] == ["calculated_at"]
                for index in sa.inspect(db).get_indexes("reminder_policy_evaluation")
            )
            revision.downgrade()
            assert "reminder_policy_evaluation" not in sa.inspect(db).get_table_names()
            revision.upgrade()
    engine.dispose()


def test_schedule_migration_preserves_feed_and_seeds_only_retryable_pending_rows():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/e4b6c8d0f2a3_reminder_send_schedule.py"
    spec = importlib.util.spec_from_file_location("schedule_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as db:
        db.exec_driver_sql("CREATE TABLE email_outbox (first_attempt_at DATETIME, accepted_at DATETIME)")
        db.exec_driver_sql(
            "CREATE TABLE user_notification_setting (user_id INTEGER PRIMARY KEY, reminder_lead_days INTEGER)"
        )
        db.exec_driver_sql("INSERT INTO user_notification_setting VALUES (1,7)")
        db.exec_driver_sql(
            "CREATE TABLE reminder_delivery (id INTEGER PRIMARY KEY, status VARCHAR(20), error_code VARCHAR(64))"
        )
        db.exec_driver_sql(
            "INSERT INTO reminder_delivery VALUES (1,'pending',NULL),(2,'sent',NULL),(3,'failed','TIMEOUT'),(4,'failed','PERSONALIZATION_REVOKED')"
        )
        with Operations.context(MigrationContext.configure(db)):
            revision.upgrade()
            assert db.exec_driver_sql(
                "SELECT reminder_lead_days, timezone, preferred_send_time FROM user_notification_setting"
            ).one() == (7, "Asia/Ho_Chi_Minh", None)
            assert db.exec_driver_sql(
                "SELECT id FROM reminder_delivery WHERE next_eligible_send_at IS NOT NULL ORDER BY id"
            ).scalars().all() == [1, 3]
            revision.downgrade()
            assert db.exec_driver_sql("SELECT reminder_lead_days FROM user_notification_setting").scalar_one() == 7
            revision.upgrade()
    engine.dispose()


def test_trip_migration_is_reversible_and_constraints_reject_invalid_distance():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/f2a4c6e8b0d3_vehicle_trip_plan.py"
    spec = importlib.util.spec_from_file_location("trip_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as db:
        db.exec_driver_sql("CREATE TABLE vehicle_user (user_id INTEGER PRIMARY KEY)")
        db.exec_driver_sql("CREATE TABLE user_vehicle (id CHAR(32) PRIMARY KEY)")
        with Operations.context(MigrationContext.configure(db)):
            revision.upgrade()
            assert "vehicle_trip_plan" in sa.inspect(db).get_table_names()
            revision.downgrade()
            assert "vehicle_trip_plan" not in sa.inspect(db).get_table_names()
            revision.upgrade()
            constraints = sa.inspect(db).get_check_constraints("vehicle_trip_plan")
            assert {c["name"] for c in constraints} == {"ck_trip_distance", "ck_trip_dates"}
    engine.dispose()
