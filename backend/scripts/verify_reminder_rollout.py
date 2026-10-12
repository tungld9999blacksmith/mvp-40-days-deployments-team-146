"""Offline shadow/on/off rehearsal with real SQL services and disposable fixtures.

No configured database, Redis, OEM, Firebase, LLM or email provider calls.
"""

import argparse
import asyncio
import json
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from report_reminder_metrics import dashboard_html  # noqa: E402
from sqlmodel import select  # noqa: E402

from src import config as app_config  # noqa: E402
from src.common.core.maintenance import Booking, BookingStatus, Reminder  # noqa: E402
from src.config import Settings  # noqa: E402
from src.modules.notification.booking_attribution import confirm_booking_origin, stage_booking_origin  # noqa: E402
from src.modules.notification.channels import NotificationService  # noqa: E402
from src.modules.notification.metrics_service import aggregate_metrics  # noqa: E402
from src.modules.notification.reminder_service import MaintenanceReminderService  # noqa: E402
from src.modules.notification.schemas import NotificationSettingsUpdateIn  # noqa: E402
from src.modules.notification.settings_service import NotificationSettingsService  # noqa: E402
from src.modules.user_vehicle.service import UserVehicleService  # noqa: E402
from src.modules.vehicle_usage.service import PERSONALIZATION_POLICY_VERSION  # noqa: E402
from tests._maintenance import add_workshop, make_session  # noqa: E402
from tests._user_vehicle import (  # noqa: E402
    RecordingScheduler,
    add_odometer,
    add_owner,
    add_rules,
    add_vehicle,
    mark_synced,
)


async def verify(db, fleet_size=4):
    cfg = Settings(
        _env_file=None, app_env="test", oem_sync_mode="oem", email_mode="mock", personalized_reminders_mode="shadow"
    )
    original = app_config.get_settings
    app_config.get_settings = lambda: cfg
    try:
        now = datetime.now(UTC)
        owner = add_owner(db)
        prefs = NotificationSettingsService(db, available_channels=set(), default_lead_days=7)
        prefs.update(
            owner,
            NotificationSettingsUpdateIn(
                reminder_lead_days=7,
                personalized_reminders_enabled=True,
                personalization_policy_version=PERSONALIZATION_POLICY_VERSION,
            ),
        )
        add_rules(db)
        fleet = []
        for index in range(fleet_size):
            speed = [200, 20, 0, None][index % 4]
            vehicle = add_vehicle(
                db, owner, vin=f"RLLV0000000000{index:03d}", external_vehicle_id=f"FIXTURE-{index}", with_warranty=False
            )
            vehicle.manufacture_date = date(2026, 1, 1)
            db.add(vehicle)
            db.commit()
            for day in [0] if speed is None else range(28, -1, -1):
                add_odometer(db, vehicle, 10800 - (speed or 0) * day, now - timedelta(days=day))
            mark_synced(db, vehicle, now)
            fleet.append(vehicle)
        vehicles = UserVehicleService(db, RecordingScheduler(), clock=lambda: now)
        job = MaintenanceReminderService(
            db, NotificationService([]), lambda vehicle, at: vehicles.calculate(vehicle, now=at), clock=lambda: now
        )
        started = perf_counter()
        for vehicle in fleet:
            assert (await job.remind(vehicle.id)).created_level is None
        elapsed = (perf_counter() - started) * 1000
        await job.remind(fleet[0].id)
        shadow = aggregate_metrics(db, now=now + timedelta(seconds=1))
        assert shadow["evaluationCount"] == fleet_size and shadow["shadowChangedDecisions"] == fleet_size // 4
        cfg.personalized_reminders_mode = "on"
        cfg.personalized_reminders_canary_user_ids = str(owner.user_id + 100)
        assert prefs.get(owner).personalization_mode == "shadow"
        assert not vehicles.get_maintenance_status(fleet[0]).maintenance_forecast.reminder_recommended
        assert (await job.remind(fleet[0].id)).created_level is None
        cfg.personalized_reminders_canary_user_ids = str(owner.user_id)
        assert prefs.get(owner).personalization_mode == "on"
        assert (await job.remind(fleet[0].id)).created_level.name == "EARLY"
        reminder = db.exec(select(Reminder)).one()
        cfg.personalized_reminders_canary_user_ids = str(owner.user_id + 100)
        assert (await job.remind(fleet[0].id)).created_level is None
        assert prefs.get(owner).personalized_reminders_enabled
        cfg.personalized_reminders_mode = "off"
        assert vehicles.get_maintenance_status(fleet[0]).maintenance_forecast.status == "DISABLED"
        assert (await job.remind(fleet[0].id)).created_level is None
        workshop = add_workshop(db)
        booking = Booking(
            booking_code="FIXTURE-ORIGIN",
            user_id=owner.user_id,
            user_vehicle_id=fleet[0].id,
            workshop_id=workshop.id,
            booking_date=now.date() + timedelta(days=3),
            time_slot=time(9),
            odo_milestone=12000,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()
        stage_booking_origin(db, booking, now, reminder.id)
        confirm_booking_origin(db, booking, now)
        db.commit()
        report = aggregate_metrics(db, now=now + timedelta(seconds=1))
        assert report["directConfirmedBookings"] == 1 and report["recordedProviderAttempts"] == 0
        assert report["evaluatedVehicleCount"] == fleet_size and report["forecastCoverage"] == 0.75
        report.update(
            dataset="disposable-fixture",
            externalProviderCalls=0,
            realRolloutReady=False,
            rolloutChecks={
                "shadowPreservesBaseline": True,
                "dailyEvaluationIdempotent": True,
                "onCreatesPredictiveReminder": True,
                "canaryExcludedOwnerUsesShadow": True,
                "canaryIncludedOwnerCreatesPrediction": True,
                "canaryRemovalStopsPrediction": True,
                "offRestoresBaseline": True,
                "fixtureFleetSize": len(fleet),
                "fixtureDailyScanMs": round(elapsed, 2),
            },
        )
        return report
    finally:
        app_config.get_settings = original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--fleet-size", type=int, choices=[4, 40, 400], default=4)
    args = parser.parse_args()
    generator = make_session()
    db = next(generator)
    try:
        report = asyncio.run(verify(db, args.fleet_size))
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        args.html.write_text(dashboard_html(report), encoding="utf-8")
        print(json.dumps({"status": "passed", "dataset": report["dataset"], "externalProviderCalls": 0}))
    finally:
        engine = db.bind
        generator.close()
        engine.dispose()


if __name__ == "__main__":
    main()
