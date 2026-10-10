"""Frozen outbox migration can upgrade, preserve data and roll back."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_email_migration_upgrade_downgrade_preserves_reminder():
    path = Path(__file__).resolve().parents[2] / "alembic/versions/e7a9c2b4d6f8_email_outbox.py"
    spec = importlib.util.spec_from_file_location("email_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as db:
        for ddl in (
            "CREATE TABLE vehicle_user (user_id INTEGER PRIMARY KEY)",
            "CREATE TABLE user_vehicle (id CHAR(32) PRIMARY KEY)",
            "CREATE TABLE reminder_delivery (id CHAR(32) PRIMARY KEY)",
            "CREATE TABLE reminder (id INTEGER PRIMARY KEY)",
            "INSERT INTO reminder (id) VALUES (1)",
        ):
            db.execute(sa.text(ddl))
        with Operations.context(MigrationContext.configure(db)):
            revision.upgrade()
        tables = sa.inspect(db).get_table_names()
        assert {"email_outbox", "email_vehicle_gate", "email_suppression", "email_webhook_event"} <= set(tables)
        assert db.execute(sa.text("SELECT id, details, resolution_reason FROM reminder")).one() == (1, None, None)
        assert len(sa.inspect(db).get_indexes("email_outbox")) == 5
        with Operations.context(MigrationContext.configure(db)):
            revision.downgrade()
        assert db.execute(sa.text("SELECT id FROM reminder")).scalar_one() == 1
        assert "email_outbox" not in sa.inspect(db).get_table_names()
    engine.dispose()
