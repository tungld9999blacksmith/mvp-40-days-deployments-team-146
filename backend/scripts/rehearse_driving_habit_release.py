"""Offline P1/P2/P3 shadow -> canary -> rollback exercise.

Runs real domain services on disposable SQLite. All dates, owners and ODOs are
fixtures. Fourteen simulated days are not fourteen days of live evidence.
Never connects to configured DB/Redis, changes .env or sends real email.
"""

import argparse
import asyncio
import json
import sys
from contextlib import ExitStack
from datetime import UTC, date, datetime, timedelta
from html import escape
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlmodel import select  # noqa: E402

from src import config as app_config  # noqa: E402
from src.common.core.maintenance import Reminder  # noqa: E402
from src.common.core.maintenance.reminder import ReminderChannel  # noqa: E402
from src.common.core.notification import DeliveryStatus, ReminderDelivery, ReminderPolicyEvaluation  # noqa: E402
from src.common.core.notification.email import EmailOutbox  # noqa: E402
from src.common.core.vehicle import VehicleOdometerReading, VehicleOemSync  # noqa: E402
from src.config import Settings  # noqa: E402
from src.modules.notification.channels import NotificationService  # noqa: E402
from src.modules.notification.email_service import MaintenanceEmailAdapter  # noqa: E402
from src.modules.notification.metrics_service import aggregate_metrics  # noqa: E402
from src.modules.notification.reminder_service import MaintenanceReminderService  # noqa: E402
from src.modules.notification.schemas import ChannelChangeIn, NotificationSettingsUpdateIn  # noqa: E402
from src.modules.notification.settings_service import NotificationSettingsService  # noqa: E402
from src.modules.trip_planning.schemas import TripPlanIn  # noqa: E402
from src.modules.trip_planning.service import TripPlanningService  # noqa: E402
from src.modules.user_vehicle.domain import today_vn  # noqa: E402
from src.modules.user_vehicle.service import UserVehicleService  # noqa: E402
from src.modules.vehicle_usage.service import PERSONALIZATION_POLICY_VERSION  # noqa: E402
from tests._maintenance import make_session  # noqa: E402
from tests._user_vehicle import (  # noqa: E402
    RecordingScheduler,
    add_odometer,
    add_owner,
    add_rules,
    add_vehicle,
    mark_synced,
)


async def rehearse(db):
    assert db.bind.dialect.name == "sqlite" and db.bind.url.database in {None, "", ":memory:"}
    cfg = Settings(
        _env_file=None,
        app_env="test",
        oem_sync_mode="oem",  # Fixture readings only; no OEM gateway is instantiated.
        email_mode="mock",
        personalized_reminders_mode="shadow",
        agent_memory_read_enabled=False,
    )
    end_day = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()
    end = datetime.combine(end_day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=1)
    start = end - timedelta(days=13)
    now = [start]
    roles = ["forecast", "trip", "excluded", "rollback", "removed", "deleted", "revoked", "baseline"]
    usage_roles = {"forecast", "excluded", "revoked"}
    fleet, owners = {}, {}
    network_attempts = []

    def forbid_network(*args, **kwargs):
        network_attempts.append(True)
        raise AssertionError("Offline rehearsal attempted a network connection")

    with ExitStack() as guards:
        guards.enter_context(patch.object(app_config, "get_settings", lambda: cfg))
        guards.enter_context(patch("socket.create_connection", side_effect=forbid_network))
        guards.enter_context(patch("socket.socket.connect", side_effect=forbid_network))
        guards.enter_context(patch("httpx.Client.send", side_effect=forbid_network))
        guards.enter_context(patch("httpx.AsyncClient.send", side_effect=forbid_network))
        settings = NotificationSettingsService(
            db,
            available_channels={ReminderChannel.EMAIL},
            default_lead_days=7,
            email_mode="mock",
            clock=lambda: now[0],
        )
        add_rules(db)
        for index, role in enumerate(roles):
            owner = add_owner(db, uid=f"fixture-{role}", email=f"{role}@example.com")
            owner.email_verified = True
            db.add(owner)
            vehicle = add_vehicle(
                db, owner, vin=f"RHSR0000000000{index:03d}", external_vehicle_id=f"FIXTURE-{role}", with_warranty=False
            )
            vehicle.manufacture_date = date(2026, 1, 1)
            db.add(vehicle)
            db.commit()
            settings.update(
                owner,
                NotificationSettingsUpdateIn(
                    reminders_enabled=True,
                    reminder_lead_days=7,
                    preferred_send_time="19:00",
                    channels=[ChannelChangeIn(channel="EMAIL", enabled=True)],
                    personalized_reminders_enabled=role in usage_roles,
                    personalization_policy_version=PERSONALIZATION_POLICY_VERSION,
                ),
            )
            base, speed = (10000, 100) if role in usage_roles else (11600, 0) if role == "baseline" else (10800, 0)
            for day in range(28, -1, -1):
                add_odometer(db, vehicle, base - speed * day, start - timedelta(days=day))
            mark_synced(db, vehicle, start)
            fleet[role], owners[role] = vehicle, owner

        vehicles = UserVehicleService(db, RecordingScheduler(), clock=lambda: now[0])
        trips = TripPlanningService(db, vehicles, clock=lambda: now[0])
        job = MaintenanceReminderService(
            db,
            NotificationService([MaintenanceEmailAdapter(db, cfg, clock=lambda: now[0])]),
            lambda vehicle, at: vehicles.calculate(vehicle, now=at),
            clock=lambda: now[0],
        )

        def reminder(role):
            return db.exec(select(Reminder).where(Reminder.user_vehicle_id == fleet[role].id)).one()

        def delivery(role):
            return db.exec(select(ReminderDelivery).where(ReminderDelivery.reminder_id == reminder(role).id)).one()

        def cohort(selected):
            cfg.personalized_reminders_canary_user_ids = ",".join(str(owners[role].user_id) for role in selected)

        for role in {"trip", "excluded", "rollback", "removed", "deleted"}:
            trips.put(
                fleet[role],
                TripPlanIn(departure_date=today_vn(end) + timedelta(days=3), distance_km=1500, reminder_enabled=True),
            )

        # Drive the real evaluator on each simulated day, not seeded telemetry.
        for day in range(14):
            now[0] = start + timedelta(days=day)
            for role, vehicle in fleet.items():
                if day:
                    latest = (10000 + 100 * day) if role in usage_roles else 11600 if role == "baseline" else 10800
                    add_odometer(db, vehicle, latest, now[0])
                    sync = db.get(VehicleOemSync, vehicle.id)
                    sync.usage_synced_at = sync.service_history_synced_at = sync.last_attempt_at = now[0]
                    db.add(sync)
                    db.commit()
                outcome = await job.remind(vehicle.id)
                if role != "baseline":
                    assert outcome.created_level is None
            if day == 0:
                assert delivery("baseline").attempts == 0
                now[0] += timedelta(hours=11)
                assert await job.dispatch_delivery(delivery("baseline").id) == 1
                assert await job.dispatch_delivery(delivery("baseline").id) == 0

        now[0] = end
        evaluations = db.exec(select(ReminderPolicyEvaluation)).all()
        for role in usage_roles:
            days = {
                row.evaluation_day
                for row in evaluations
                if row.user_vehicle_id == fleet[role].id and row.mode == "shadow"
            }
            assert len(days) == 14
        assert len(evaluations) == 42
        assert len(db.exec(select(Reminder)).all()) == 1
        shadow = aggregate_metrics(db, now=now[0] + timedelta(seconds=1))
        assert shadow["shadowChangedDecisions"] > 0
        phase_results = [
            {"phase": "shadow", "simulatedDays": 14, "evaluations": 42, "featureReminders": 0, "baselineMockEmails": 1}
        ]

        # Only selected fixture owners enter canary; excluded consent remains.
        cfg.personalized_reminders_mode = "on"
        included = [role for role in roles if role not in {"excluded", "baseline"}]
        cohort(included)
        for role in roles:
            outcome = await job.remind(fleet[role].id)
            if role in included:
                assert outcome.created_level and outcome.created_level.name == "EARLY", role
                assert delivery(role).attempts == 0
                assert await job.dispatch_delivery(delivery(role).id) == 0
            else:
                assert outcome.created_level is None
        assert not settings.get(owners["trip"]).personalized_reminders_enabled
        assert reminder("trip").details["trip"]["distanceKm"] == 1500
        assert reminder("forecast").details["personalization"]
        ids = {role: (reminder(role).id, delivery(role).id) for role in included}
        phase_results.append(
            {
                "phase": "canary",
                "includedOwners": 6,
                "excludedOwners": 2,
                "pendingFeatureDeliveries": 6,
                "earlySends": 0,
            }
        )

        # Stop one pending trip by removing its owner; stop another by erasure.
        included.remove("removed")
        cohort(included)
        trips.delete(fleet["deleted"])
        settings.update(owners["revoked"], NotificationSettingsUpdateIn(personalized_reminders_enabled=False))
        assert delivery("deleted").error_code == "SCHEDULE_CANCELLED"
        assert delivery("revoked").error_code == "PERSONALIZATION_REVOKED"
        now[0] += timedelta(hours=11)
        assert await job.dispatch_delivery(delivery("removed").id) == 0
        assert await job.dispatch_delivery(delivery("deleted").id) == 0
        assert await job.dispatch_delivery(delivery("revoked").id) == 0
        assert await job.dispatch_delivery(delivery("trip").id) == 1
        assert await job.dispatch_delivery(delivery("forecast").id) == 1
        assert await job.dispatch_delivery(delivery("trip").id) == 0
        assert await job.dispatch_delivery(delivery("forecast").id) == 0

        # Mode off rechecks a pending trip at delivery time, then keeps its IDs.
        cfg.personalized_reminders_mode = "off"
        assert await job.dispatch_delivery(delivery("rollback").id) == 0
        assert delivery("rollback").attempts == 0
        assert delivery("rollback").error_code == "SCHEDULE_CANCELLED"
        cfg.personalized_reminders_mode = "on"
        for role, (reminder_id, delivery_id) in ids.items():
            await job.remind(fleet[role].id)
            assert reminder(role).id == reminder_id and delivery(role).id == delivery_id
            assert await job.dispatch_delivery(delivery_id) == 0
        assert len(db.exec(select(ReminderDelivery)).all()) == 7

        # Retention erasure keeps the accepted receipt but removes trip facts.
        trip_delivery_id = delivery("trip").id
        trips.delete(fleet["trip"])
        assert "trip" not in reminder("trip").details
        assert db.get(EmailOutbox, trip_delivery_id).payload is None
        assert delivery("trip").status == DeliveryStatus.SENT
        phase_results.append(
            {
                "phase": "rollback_and_reentry",
                "cancelledFeatureDeliveries": 4,
                "featureMockEmails": 2,
                "duplicateSends": 0,
                "stableIds": True,
                "sentReceiptRetainedAfterErasure": True,
            }
        )

        all_deliveries = db.exec(select(ReminderDelivery)).all()
        sent = [row for row in all_deliveries if row.status == DeliveryStatus.SENT]
        assert len(sent) == 3 and all(row.attempts == 1 for row in sent)
        assert sum(row.attempts for row in all_deliveries) == 3
        assert all(db.get(EmailOutbox, row.id).mode == "mock" for row in sent)
        assert not network_attempts
        report = aggregate_metrics(db, now=now[0] + timedelta(seconds=1))
        report.update(
            status="passed",
            dataset="disposable-fixture",
            database="SQLite :memory:",
            simulationOnly=True,
            realRolloutReady=False,
            liveShadowDaysObserved=0,
            simulatedShadowDays=14,
            configuredDatabaseWrites=0,
            externalProviderCalls=0,
            networkAttempts=len(network_attempts),
            environmentFileModified=False,
            fixtureOwners=len(owners),
            fixtureVehicles=len(fleet),
            fixtureOdoReadings=len(db.exec(select(VehicleOdometerReading)).all()),
            mockAcceptedEmails=3,
            actualFeatureEmails=0,
            phases=phase_results,
            checks={
                "shadowDoesNotActivateForecastOrTrips": True,
                "baselineContinuesInShadow": True,
                "dailyShadowEvidenceRecordedByEvaluator": True,
                "canaryLimitsForecastAndTripOwners": True,
                "tripConsentDoesNotGrantUsageConsent": True,
                "schedulePreventsEarlySending": True,
                "cohortRemovalStopsPendingTrip": True,
                "usageConsentRevocationStopsPendingForecast": True,
                "tripDeletionStopsPendingDelivery": True,
                "offStopsPendingTrip": True,
                "reentryPreservesIdsAndDoesNotReplay": True,
                "tripErasurePreservesSentReceipt": True,
            },
        )
        report["notes"] += [
            "Every owner, ODO reading and calendar day is simulated in disposable SQLite.",
            "This is not live OEM history, elapsed live shadow time, production latency or release approval.",
            "Recorded attempts and accepted receipts in this report use mock email only.",
        ]
        return report


def dashboard(report):
    rows = "".join(f"<tr><td>{escape(key)}</td><td>Đạt</td></tr>" for key in report["checks"])
    phases = "".join(
        f"<li><strong>{escape(phase['phase'])}</strong><pre>{escape(json.dumps(phase, indent=2))}</pre></li>"
        for phase in report["phases"]
    )
    return f"""<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>EV Care — Diễn tập rollout P1–P3</title><style>body{{font:16px system-ui;max-width:960px;margin:24px auto;padding:16px;color:#152b21;background:#f3f8f5}}table{{width:100%;border-collapse:collapse}}td{{border:1px solid #b7ccbf;padding:10px;overflow-wrap:anywhere}}pre{{white-space:pre-wrap}}.notice{{padding:16px;background:#fff3d0;border-radius:12px}}</style>
<h1>Diễn tập shadow → canary → rollback</h1><p class="notice">Dữ liệu thử SQLite tạm. 14 ngày mô phỏng, 0 ngày shadow thật. Chưa đủ điều kiện rollout thật.</p>
<p>8 tài khoản, 8 xe · 3 email mock · 0 email thật · không thay đổi .env/database nghiệp vụ.</p><ol>{phases}</ol><table><caption>Kiểm tra P1, P2, P3</caption>{rows}</table></html>"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--html", type=Path, required=True)
    args = parser.parse_args()
    generator = make_session()
    db = next(generator)
    engine = db.bind
    try:
        report = asyncio.run(rehearse(db))
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        args.html.write_text(dashboard(report), encoding="utf-8")
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "simulatedShadowDays": 14,
                    "checksPassed": len(report["checks"]),
                    "mockAcceptedEmails": 3,
                    "externalProviderCalls": 0,
                    "realRolloutReady": False,
                }
            )
        )
    finally:
        generator.close()
        engine.dispose()


if __name__ == "__main__":
    main()
