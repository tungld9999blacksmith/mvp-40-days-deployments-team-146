"""Verify migration and concurrent predictive mail in an isolated temporary schema.

All business rows live in a unique schema, provider calls are recorded locally,
and the schema is removed in finally. The configured public data is untouched.
"""

import argparse
import asyncio
import importlib.util
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event
from time import perf_counter
from unittest.mock import Mock
from uuid import uuid4

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from src import config as app_config  # noqa: E402
from src.common.core.maintenance import Reminder  # noqa: E402
from src.common.core.maintenance.reminder import ReminderChannel  # noqa: E402
from src.common.core.notification import ReminderDelivery, UserNotificationChannel  # noqa: E402
from src.common.core.vehicle import OemSyncTrigger, VehicleOdometerReading  # noqa: E402
from src.config import Settings  # noqa: E402
from src.modules.notification.channels import (  # noqa: E402
    DeliveryResult,
    NotificationChannelAdapter,
    NotificationService,
)
from src.modules.notification.email_service import MaintenanceEmailAdapter  # noqa: E402
from src.modules.notification.reminder_service import MaintenanceReminderService  # noqa: E402
from src.modules.notification.schemas import NotificationSettingsUpdateIn  # noqa: E402
from src.modules.notification.settings_service import NotificationSettingsService  # noqa: E402
from src.modules.user_vehicle.service import UserVehicleService  # noqa: E402
from src.modules.vehicle_usage.domain import Reading, calculate_forecast  # noqa: E402
from src.modules.vehicle_usage.service import (
    PERSONALIZATION_POLICY_VERSION,  # noqa: E402
    VehicleUsageService,  # noqa: E402
)
from tests._user_vehicle import TABLES, add_odometer, add_owner, add_rules, add_vehicle, mark_synced  # noqa: E402


def run():
    configured = app_config.get_settings()
    if not configured.sqlalchemy_database_url.startswith("postgresql"):
        return {"status": "skipped", "reason": "Configured database is not PostgreSQL"}
    engine = sa.create_engine(configured.sqlalchemy_database_url, connect_args={"connect_timeout": 8}, pool_size=4)
    read_engine = sa.create_engine(
        configured.sqlalchemy_database_url,
        connect_args={"connect_timeout": 8},
        isolation_level="AUTOCOMMIT",
        skip_autocommit_rollback=True,
        pool_size=2,
        max_overflow=2,
    )
    schema = "p146_usage_it_" + uuid4().hex
    assert re.fullmatch(r"p146_usage_it_[0-9a-f]{32}", schema)

    # Qualify every ORM/Core table, including autocommit forecast SELECTs.
    # Session SET search_path leaks across Supabase transaction-pool clients.
    # Schema translation makes isolation independent of pool session affinity.
    read_engine = read_engine.execution_options(schema_translate_map={None: schema})
    engine = engine.execution_options(schema_translate_map={None: schema}, usage_read_engine=read_engine)

    with engine.begin() as db:
        db.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    cfg = Settings(
        _env_file=None,
        app_env="test",
        oem_sync_mode="oem",
        personalized_reminders_mode="on",
        email_mode="resend",
        resend_api_key="recording-only",
        resend_webhook_secret="recording-only",
        email_from="EV Care <test@example.com>",
        email_app_url="http://localhost:5173",
    )
    original = app_config.get_settings
    app_config.get_settings = lambda: cfg
    try:
        metadata = sa.MetaData()
        for source in TABLES:
            if source.name in {
                "reminder_personalization_event",
                "reminder_policy_evaluation",
                "reminder_booking_attribution",
                "vehicle_trip_plan",
            }:
                continue
            table = source.to_metadata(metadata)
            if table.name == "email_outbox":
                table._columns.remove(table.c.uncertain_attempt_at)
            # Chat is only an FK target here; full-text search's migration-owned
            # public function must never be reached through this isolated schema.
            if table.name == "chat_message":
                table.c.search_vector.computed = None
                table.c.search_vector.server_default = None
            if table.name == "user_notification_setting":
                for name in (
                    "personalized_reminders_enabled",
                    "personalization_policy_version",
                    "personalization_consent_at",
                    "personalization_revoked_at",
                    "preferred_send_time",
                    "quiet_hours_start",
                    "quiet_hours_end",
                    "timezone",
                ):
                    table._columns.remove(table.c[name])
            if table.name == "reminder_delivery":
                for index in list(table.indexes):
                    if index.name == "ix_reminder_delivery_due":
                        table.indexes.remove(index)
                for name in ("next_eligible_send_at", "schedule_expires_at", "claim_token", "lease_until"):
                    table._columns.remove(table.c[name])
        path = ROOT / "backend/alembic/versions/a9c4e2f6b8d1_personalized_reminders.py"
        spec = importlib.util.spec_from_file_location("usage_revision", path)
        revision = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(revision)
        next_spec = importlib.util.spec_from_file_location(
            "usage_metrics_revision", ROOT / "backend/alembic/versions/c7d9b1e3f5a2_reminder_metrics.py"
        )
        metrics_revision = importlib.util.module_from_spec(next_spec)
        next_spec.loader.exec_module(metrics_revision)
        schedule_spec = importlib.util.spec_from_file_location(
            "usage_schedule_revision", ROOT / "backend/alembic/versions/e4b6c8d0f2a3_reminder_send_schedule.py"
        )
        schedule_revision = importlib.util.module_from_spec(schedule_spec)
        schedule_spec.loader.exec_module(schedule_revision)
        trip_spec = importlib.util.spec_from_file_location(
            "trip_revision", ROOT / "backend/alembic/versions/f2a4c6e8b0d3_vehicle_trip_plan.py"
        )
        trip_revision = importlib.util.module_from_spec(trip_spec)
        trip_spec.loader.exec_module(trip_revision)
        from scripts.deploy_driving_habit_migrations import apply_feature_migrations

        with engine.begin() as db:
            # Migration-owned raw DDL uses a transaction-local path, never a
            # session-level setting. No public fallback for unqualified names.
            db.exec_driver_sql(f'SET LOCAL search_path TO "{schema}"')
            metadata.create_all(db, checkfirst=False)
            db.exec_driver_sql("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)")
            db.exec_driver_sql("INSERT INTO alembic_version VALUES ('unknown_fixture_base')")
            migrated = apply_feature_migrations(db)
            assert migrated["applied"] == [
                revision.revision,
                metrics_revision.revision,
                schedule_revision.revision,
                trip_revision.revision,
            ]
            with Operations.context(MigrationContext.configure(db)):
                trip_revision.downgrade()
                schedule_revision.downgrade()
                metrics_revision.downgrade()
                revision.downgrade()
            db.exec_driver_sql("DELETE FROM alembic_version_driving_habit")
            apply_feature_migrations(db)
            assert apply_feature_migrations(db)["applied"] == []
        now = datetime(2026, 9, 13, 2, tzinfo=UTC)
        with Session(engine) as db:
            owner = add_owner(db)
            owner.email_verified = True
            db.add(owner)
            vehicle = add_vehicle(db, owner)
            add_rules(db)
            for day in range(28, -1, -1):
                add_odometer(db, vehicle, 10800 - 200 * day, now - timedelta(days=day))
            mark_synced(db, vehicle, now)
            db.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.EMAIL))
            db.commit()
            NotificationSettingsService(db, available_channels={ReminderChannel.EMAIL}, default_lead_days=2).update(
                owner,
                NotificationSettingsUpdateIn(
                    reminder_lead_days=7,
                    personalized_reminders_enabled=True,
                    personalization_policy_version=PERSONALIZATION_POLICY_VERSION,
                    preferred_send_time="09:15",
                    quiet_hours={"start": "22:00", "end": "07:00"},
                ),
            )
            vehicle_id = vehicle.id
            cfg.personalized_reminders_canary_user_ids = str(owner.user_id)
        with Session(engine) as db:
            vehicle = db.get(type(vehicle), vehicle_id)
            due = UserVehicleService(db, Mock(), clock=lambda: now).calculate(vehicle, now=now)
            dense = [
                Reading(5200 + 5600 * i // 5999, now - timedelta(days=28 * (5999 - i) / 5999)) for i in range(6000)
            ]
            pure_ms, sql_ms, network_ms = [], [], []
            for _ in range(100):
                started = perf_counter()
                assert calculate_forecast(dense, due, now=now).status == "AVAILABLE"
                pure_ms.append((perf_counter() - started) * 1000)
            for _ in range(20):
                started = perf_counter()
                with read_engine.connect() as connection:
                    assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
                network_ms.append((perf_counter() - started) * 1000)
                started = perf_counter()
                assert VehicleUsageService(db, cfg).forecast(vehicle, due, now).status == "AVAILABLE"
                sql_ms.append((perf_counter() - started) * 1000)
            performance = {
                "pure6000ReadingsSamples": 100,
                "pure6000ReadingsP95Ms": round(sorted(pure_ms)[94], 2),
                "postgres29ReadingsSamples": 20,
                "postgres29ReadingsP95Ms": round(sorted(sql_ms)[18], 2),
                "postgresSelect1P95Ms": round(sorted(network_ms)[18], 2),
                "forecastSelectQueriesPerCall": 1,
                "forecastP95TargetMs": 100,
                "forecastP95TargetMet": sorted(sql_ms)[18] < 100,
            }
            dense_vehicle = add_vehicle(db, owner, vin="LVVDB11B1PE000002", external_vehicle_id="DENSE-FIXTURE")
            db.execute(
                sa.insert(VehicleOdometerReading.__table__),
                [
                    {
                        "id": uuid4(),
                        "user_vehicle_id": dense_vehicle.id,
                        "odo_km": point.odo_km,
                        "recorded_at": point.recorded_at,
                        "oem_data_source": "telematics",
                        "received_via": OemSyncTrigger.POLL,
                    }
                    for point in dense
                ],
            )
            db.commit()
            mark_synced(db, dense_vehicle, now)
            dense_due = UserVehicleService(db, Mock(), clock=lambda: now).calculate(dense_vehicle, now=now)
            dense_sql_ms = []
            for _ in range(20):
                started = perf_counter()
                assert VehicleUsageService(db, cfg).forecast(dense_vehicle, dense_due, now).status == "AVAILABLE"
                dense_sql_ms.append((perf_counter() - started) * 1000)
            performance.update(
                postgres6000ReadingsSamples=20,
                postgres6000ReadingsP95Ms=round(sorted(dense_sql_ms)[18], 2),
                postgres6000ReadingsTargetMet=sorted(dense_sql_ms)[18] < 100,
                benchmarkScope="isolated fixture, network and service latency; not production fleet SLA",
            )

            def fail_read(connection, cursor, statement, parameters, context, executemany):
                return "SELECT 1 / 0", ()

            sa.event.listen(read_engine, "before_cursor_execute", fail_read, retval=True)
            try:
                assert VehicleUsageService(db, cfg).forecast(vehicle, due, now).status == "CALCULATION_ERROR"
            finally:
                sa.event.remove(read_engine, "before_cursor_execute", fail_read)
            assert db.exec(select(sa.literal(1))).one() == 1
            assert VehicleUsageService(db, cfg).forecast(vehicle, due, now).status == "AVAILABLE"
            vehicles = UserVehicleService(db, Mock(), clock=lambda: now)
            pending_job = MaintenanceReminderService(
                db, NotificationService([]), lambda v, at: vehicles.calculate(v, now=at), clock=lambda: now
            )
            pending = asyncio.run(pending_job.remind(vehicle_id))
            assert pending.deliveries_sent == 0
            delivery_id = db.exec(select(ReminderDelivery.id)).one()
            assert db.get(ReminderDelivery, delivery_id).next_eligible_send_at == now + timedelta(minutes=15)
        now += timedelta(minutes=15)
        entered, release = Event(), Event()
        calls = []

        class RecordingTransport:
            async def send(self, recipient, message):
                calls.append(message.body)
                entered.set()
                await asyncio.to_thread(release.wait, 10)
                return DeliveryResult.sent("usage-recording-1")

        def worker():
            with Session(engine) as db:
                vehicles = UserVehicleService(db, Mock(), clock=lambda: now)
                adapter = MaintenanceEmailAdapter(db, cfg, transport=RecordingTransport(), clock=lambda: now)
                reminders = MaintenanceReminderService(
                    db, NotificationService([adapter]), lambda v, at: vehicles.calculate(v, now=at), clock=lambda: now
                )
                return asyncio.run(reminders.dispatch_delivery(delivery_id))

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(worker)
            assert entered.wait(10), "First worker did not reach the recording transport"
            second = pool.submit(worker)
            try:
                second.result(timeout=15)
            finally:
                release.set()
            first.result(timeout=15)
        with Session(engine) as db:
            reminder = db.exec(select(Reminder)).one()
            delivery = db.exec(select(ReminderDelivery)).one()
            assert reminder.details["triggerReasons"] == ["PREDICTED_KM_WINDOW"]
            assert delivery.attempts == 1 and len(calls) == 1
            assert "200 km/ngày" in calls[0]
            # The same lease guarantee applies to channels without EmailOutbox.
            owner = db.get(type(owner), owner.user_id)
            NotificationSettingsService(
                db, available_channels={ReminderChannel.SMS}, default_lead_days=2, clock=lambda: now
            ).update(
                owner,
                NotificationSettingsUpdateIn(
                    preferred_send_time="09:30",
                    channels=[{"channel": "EMAIL", "enabled": False}, {"channel": "SMS", "enabled": True}],
                ),
            )
            vehicles = UserVehicleService(db, Mock(), clock=lambda: now)
            queued = MaintenanceReminderService(
                db, NotificationService([]), lambda v, at: vehicles.calculate(v, now=at), clock=lambda: now
            )
            assert asyncio.run(queued.remind(vehicle_id)).deliveries_sent == 0
            sms_delivery_id = db.exec(
                select(ReminderDelivery.id).where(ReminderDelivery.channel == ReminderChannel.SMS)
            ).one()
        now += timedelta(minutes=15)
        entered.clear()
        release.clear()
        sms_calls = []

        class RecordedSms(NotificationChannelAdapter):
            channel = ReminderChannel.SMS

            def __init__(self, db):
                self.db = db

            async def send(self, user_id, message):
                assert not self.db.in_transaction()
                sms_calls.append(message.body)
                entered.set()
                await asyncio.to_thread(release.wait, 10)
                return DeliveryResult.sent("recorded-sms")

        def sms_worker():
            with Session(engine) as db:
                vehicles = UserVehicleService(db, Mock(), clock=lambda: now)
                dispatcher = MaintenanceReminderService(
                    db,
                    NotificationService([RecordedSms(db)]),
                    lambda v, at: vehicles.calculate(v, now=at),
                    clock=lambda: now,
                )
                return asyncio.run(dispatcher.dispatch_delivery(sms_delivery_id))

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(sms_worker)
            assert entered.wait(10)
            second = pool.submit(sms_worker)
            try:
                second.result(timeout=15)
            finally:
                release.set()
            first.result(timeout=15)
        with Session(engine) as db:
            assert db.get(ReminderDelivery, sms_delivery_id).attempts == 1 and len(sms_calls) == 1
        return {
            "status": "passed",
            "migration": "upgrade/downgrade/upgrade",
            "featureMigrationStreamVerified": True,
            "baseHistoryPreserved": True,
            "migrationRevisions": ["a9c4e2f6b8d1", "c7d9b1e3f5a2", "e4b6c8d0f2a3", "f2a4c6e8b0d3"],
            "scheduledDeliverySurvivedNewSession": True,
            "dispatchRecheckedCurrentEligibility": True,
            "workers": 2,
            "recordedProviderCalls": 1,
            "smsWorkers": 2,
            "smsRecordedTransportCalls": 1,
            "nonEmailNoTransactionOverTransport": True,
            "externalProviderCalls": 0,
            "explicitCanaryCohortUsed": True,
            "isolation": "schema-qualified ORM/Core queries and transaction-local migration path",
            "forecastReadFailureKeepsWriteTransactionUsable": True,
            "performance": performance,
        }
    finally:
        app_config.get_settings = original
        with engine.begin() as db:
            db.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        engine.dispose()
        read_engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = run()
    except Exception as exc:
        result = {"status": "failed", "errorType": type(exc).__name__}
        original = getattr(exc, "orig", None)
        if getattr(original, "pgcode", None):
            result["databaseCode"] = original.pgcode
            result["databaseMessage"] = original.diag.message_primary
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(1 if result["status"] == "failed" else 0)
