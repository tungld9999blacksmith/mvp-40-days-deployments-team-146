"""Isolated PostgreSQL migration and two-worker claim test, with fake HTTP only.

Creates a unique temporary schema, never sends mail or changes public data.
Run with the repository .venv Python. Requires the configured PostgreSQL DB.
"""

import asyncio
import importlib.util
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlmodel import Session, select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from src.common.core.maintenance import Reminder
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import ReminderDelivery, UserNotificationChannel
from src.common.core.notification.email import EmailOutbox
from src.config import get_settings
from src.modules.notification.channels import DeliveryResult, NotificationService
from src.modules.notification.email_service import MaintenanceEmailAdapter
from src.modules.notification.reminder_service import MaintenanceReminderService
from src.modules.user_vehicle.service import UserVehicleService
from tests._maintenance import TABLES
from tests._user_vehicle import (
    add_odometer,
    add_owner,
    add_rules,
    add_vehicle,
    mark_synced,
)
from tests.test_modules.test_reminder_service import TWO_DAYS_BEFORE


def run():
    cfg = get_settings().model_copy(
        update={
            "email_mode": "resend",
            "resend_api_key": "test-only",
            "resend_webhook_secret": "test-only",
            "email_from": "EV Care <test@example.com>",
        }
    )
    engine = sa.create_engine(
        cfg.sqlalchemy_database_url, connect_args={"connect_timeout": 8}, pool_size=4
    )
    schema = "p146_email_it_" + uuid4().hex
    assert re.fullmatch(r"p146_email_it_[0-9a-f]{32}", schema)

    @sa.event.listens_for(engine, "begin")
    def isolate(db):
        db.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')

    with engine.begin() as db:
        db.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    report = {}
    try:
        metadata = sa.MetaData()
        for source in TABLES:
            if source.name.startswith("email_"):
                continue
            table = source.to_metadata(metadata)
            if table.name == "reminder":
                table._columns.remove(table.c.details)
                table._columns.remove(table.c.resolution_reason)
        path = ROOT / "backend/alembic/versions/e7a9c2b4d6f8_email_outbox.py"
        spec = importlib.util.spec_from_file_location("email_revision", path)
        revision = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(revision)
        with engine.begin() as db:
            # Force creation inside our schema; public tables are also visible.
            metadata.create_all(db, checkfirst=False)
            with Operations.context(MigrationContext.configure(db)):
                revision.upgrade()
                revision.downgrade()
                revision.upgrade()
            report["migration_upgrade_downgrade_upgrade"] = True
        with Session(engine) as db:
            owner = add_owner(db)
            owner.email_verified = True
            db.add(owner)
            vehicle = add_vehicle(db, owner)
            add_rules(db)
            add_odometer(db, vehicle, 5000, TWO_DAYS_BEFORE)
            mark_synced(db, vehicle, TWO_DAYS_BEFORE)
            db.add(
                UserNotificationChannel(
                    user_id=owner.user_id, channel=ReminderChannel.EMAIL
                )
            )
            db.commit()
            vehicle_id = vehicle.id

        entered, release = Event(), Event()
        calls = []

        class Transport:
            async def send(self, recipient, message):
                calls.append(message.delivery_id)
                entered.set()
                assert release.wait(20), "Concurrent test timed out"
                return DeliveryResult.sent("isolated-provider-1")

        transport = Transport()

        def attempt():
            with Session(engine) as db:
                adapter = MaintenanceEmailAdapter(
                    db, cfg, transport=transport, clock=lambda: TWO_DAYS_BEFORE
                )
                vehicles = UserVehicleService(db, Mock(), clock=lambda: TWO_DAYS_BEFORE)
                service = MaintenanceReminderService(
                    db,
                    NotificationService([adapter]),
                    lambda vehicle, now: vehicles.calculate(vehicle, now=now),
                    clock=lambda: TWO_DAYS_BEFORE,
                )
                return asyncio.run(service.remind(vehicle_id))

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(attempt)
            try:
                assert entered.wait(20), "First worker never reached transport"
                second = pool.submit(attempt)
                second.result(timeout=20)
            finally:
                release.set()
            first.result(timeout=20)
        with Session(engine) as restarted:
            assert len(restarted.exec(select(Reminder)).all()) == 1
            delivery = restarted.exec(select(ReminderDelivery)).one()
            outbox = restarted.exec(select(EmailOutbox)).one()
            assert (
                delivery.attempts == 1
                and outbox.provider_message_id == "isolated-provider-1"
            )
            assert len(calls) == 1
        report["concurrent_workers_single_send"] = True
        report["restart_saved_delivery"] = True
    finally:
        with engine.begin() as db:
            db.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        engine.dispose()
        report["temporary_schema_removed"] = True
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
