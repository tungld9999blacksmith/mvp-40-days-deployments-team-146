import pytest
import sqlalchemy as sa

from scripts.deploy_driving_habit_migrations import (
    ADDED_COLUMNS,
    FEATURE_TABLES,
    REVISIONS,
    apply_feature_migrations,
    inspect_target,
)
from tests._user_vehicle import TABLES, _make_sqlite_compatible


def legacy_engine():
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    for source in TABLES:
        if source.name in FEATURE_TABLES:
            continue
        table = source.to_metadata(metadata)
        for name in ADDED_COLUMNS.get(table.name, set()):
            table._columns.remove(table.c[name])
        if table.name == "reminder_delivery":
            for index in list(table.indexes):
                if index.name == "ix_reminder_delivery_due":
                    table.indexes.remove(index)
        _make_sqlite_compatible(table)
    metadata.create_all(engine)
    with engine.begin() as db:
        db.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
        db.exec_driver_sql("INSERT INTO alembic_version VALUES ('unknown_base')")
    return engine


def test_feature_stream_preserves_unknown_base_and_second_apply_is_noop():
    engine = legacy_engine()
    with engine.begin() as db:
        assert inspect_target(db)["compatible"]
        result = apply_feature_migrations(db)
        assert result["applied"] == REVISIONS
        assert result["baseHistoryPreserved"] and result["after"]["baseRevisions"] == ["unknown_base"]
        assert result["after"]["featureRevisions"] == [REVISIONS[-1]]
        assert apply_feature_migrations(db)["applied"] == []
    engine.dispose()


def test_partial_untracked_feature_schema_is_rejected_without_stamp():
    engine = legacy_engine()
    with engine.begin() as db:
        db.exec_driver_sql("ALTER TABLE user_notification_setting ADD COLUMN timezone VARCHAR(64)")
        assert not inspect_target(db)["compatible"]
        with pytest.raises(ValueError, match="INCOMPATIBLE"):
            apply_feature_migrations(db)
        assert "alembic_version_driving_habit" not in sa.inspect(db).get_table_names()
        assert db.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "unknown_base"
    engine.dispose()


def test_missing_baseline_column_is_rejected_without_changes():
    engine = legacy_engine()
    with engine.begin() as db:
        db.exec_driver_sql("ALTER TABLE user_vehicle RENAME COLUMN license_plate TO unknown_column")
        with pytest.raises(ValueError, match="INCOMPATIBLE"):
            apply_feature_migrations(db)
        assert "alembic_version_driving_habit" not in sa.inspect(db).get_table_names()
        assert db.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one() == "unknown_base"
    engine.dispose()
