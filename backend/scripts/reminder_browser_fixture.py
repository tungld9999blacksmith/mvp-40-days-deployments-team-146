"""Loopback-only browser test app using real services and disposable SQLite.

Never import this fixture from src.main. Identity/scheduler are fixture doubles;
SQL domain services, HTTP notification routes and UI requests remain real.
No Redis, Firebase cloud, LLM, OEM HTTP or external email provider is used.
"""

import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Annotated

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from src import config as app_config  # noqa: E402
from src.config import Settings  # noqa: E402
from src.infrastructure.supabase.db import get_session  # noqa: E402
from src.modules.notification import dependency as notification_dep  # noqa: E402
from src.modules.notification.channels import NotificationService  # noqa: E402
from src.modules.notification.email_service import MaintenanceEmailAdapter  # noqa: E402
from src.modules.notification.errors import NotificationError  # noqa: E402
from src.modules.notification.errors import status_for as notification_status
from src.modules.notification.reminder_service import MaintenanceReminderService  # noqa: E402
from src.modules.notification.route import feed_router
from src.modules.notification.route import router as settings_router  # noqa: E402
from src.modules.notification.schemas import NotificationSettingsUpdateIn  # noqa: E402
from src.modules.notification.settings_service import NotificationSettingsService  # noqa: E402
from src.modules.oauth.dependency import verify_firebase_token  # noqa: E402
from src.modules.trip_planning.service import TripPlanningService  # noqa: E402
from src.modules.user_vehicle.dependency import get_user_vehicle_service  # noqa: E402
from src.modules.user_vehicle.errors import UserVehicleError  # noqa: E402
from src.modules.user_vehicle.errors import status_for as vehicle_status
from src.modules.user_vehicle.route import get_trip_service  # noqa: E402
from src.modules.user_vehicle.route import router as vehicle_router  # noqa: E402
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

cfg = Settings(_env_file=None, app_env="test", oem_sync_mode="oem", email_mode="mock", personalized_reminders_mode="on")
app_config.get_settings = lambda: cfg
notification_dep.get_settings = lambda: cfg
app = FastAPI(title="Disposable reminder browser fixture")
for router in (settings_router, feed_router, vehicle_router):
    app.include_router(router, prefix="/api/v1")
seed_session = None
engine = None
session_lock = Lock()
owner = vehicle = None
now = datetime.now(UTC)


def seed(scenario="disabled"):
    global seed_session, engine, owner, vehicle, now
    if seed_session:
        seed_session.close()
        engine.dispose()
    generator = make_session()
    seed_session = next(generator)
    # Keep generator alive for the lifetime of this disposable schema.
    app.state.session_generator = generator
    engine = seed_session.bind
    now = datetime.now(UTC)
    cfg.oem_sync_mode = "static" if scenario == "static" else "oem"
    cfg.personalized_reminders_mode = "shadow" if scenario == "shadow" else "on"
    owner = add_owner(seed_session)
    owner.email_verified = True
    vehicle = add_vehicle(seed_session, owner, with_warranty=False)
    vehicle.manufacture_date = date(2026, 1, 1)
    seed_session.add(owner)
    seed_session.add(vehicle)
    seed_session.commit()
    add_rules(seed_session)
    for day in [0] if scenario == "insufficient" else range(28, -1, -1):
        add_odometer(seed_session, vehicle, 10800 - 200 * day, now - timedelta(days=day))
    mark_synced(seed_session, vehicle, now)
    NotificationSettingsService(seed_session, available_channels=set(), default_lead_days=2).update(
        owner,
        NotificationSettingsUpdateIn(
            reminder_lead_days=7,
            personalized_reminders_enabled=scenario not in {"disabled", "trip"},
            personalization_policy_version=PERSONALIZATION_POLICY_VERSION,
        ),
    )


def session():
    # StaticPool shares one SQLite connection; overlapping HTTP sessions must
    # not roll back each other's transactions. Production uses a real DB pool.
    with session_lock, Session(engine) as db:
        yield db


def vehicles(db: Annotated[Session, Depends(get_session)]):
    return UserVehicleService(db, RecordingScheduler(), clock=lambda: now)


def notifier(db: Annotated[Session, Depends(get_session)]):
    return NotificationService([MaintenanceEmailAdapter(db, cfg, clock=lambda: now)])


def settings_service(db: Annotated[Session, Depends(get_session)]):
    from src.common.core.maintenance.reminder import ReminderChannel

    return NotificationSettingsService(
        db, available_channels={ReminderChannel.EMAIL}, default_lead_days=2, email_mode="mock", clock=lambda: now
    )


app.dependency_overrides[get_session] = session
app.dependency_overrides[verify_firebase_token] = lambda: {"uid": "uid-1"}
app.dependency_overrides[get_user_vehicle_service] = vehicles
app.dependency_overrides[get_trip_service] = lambda db=Depends(get_session): TripPlanningService(
    db, UserVehicleService(db, RecordingScheduler(), clock=lambda: now), clock=lambda: now
)
app.dependency_overrides[notification_dep.get_notification_service] = notifier
app.dependency_overrides[notification_dep.get_notification_settings_service] = settings_service


async def error_handler(request, exc):
    status = notification_status(exc.code) if isinstance(exc, NotificationError) else vehicle_status(exc.code)
    return JSONResponse(status_code=status, content={"error": {"code": exc.code, "message": str(exc)}})


app.add_exception_handler(NotificationError, error_handler)
app.add_exception_handler(UserVehicleError, error_handler)


@app.get("/api/v1/__fixture/info")
def info():
    return {"vehicleId": str(vehicle.id), "clock": now.isoformat(), "mode": cfg.personalized_reminders_mode}


@app.post("/api/v1/__fixture/reset")
def reset(scenario: str = "disabled"):
    assert scenario in {"disabled", "available", "insufficient", "static", "shadow", "trip"}
    seed(scenario)
    return info()


@app.post("/api/v1/__fixture/remind")
async def remind(db: Annotated[Session, Depends(get_session)]):
    from src.common.core.maintenance import Reminder

    service = UserVehicleService(db, RecordingScheduler(), clock=lambda: now)
    job = MaintenanceReminderService(db, notifier(db), lambda v, at: service.calculate(v, now=at), clock=lambda: now)
    await job.remind(vehicle.id)
    reminder = db.exec(select(Reminder)).first()
    return {"reminderId": str(reminder.id) if reminder else None}


seed()


@app.post("/api/v1/__fixture/advance")
def advance(minutes: int):
    global now
    assert 0 <= minutes <= 8 * 24 * 60
    now += timedelta(minutes=minutes)
    return info()


@app.post("/api/v1/__fixture/dispatch")
async def dispatch(db: Annotated[Session, Depends(get_session)]):
    from src.modules.notification.reminder_service import list_due_delivery_ids

    vehicles_service = UserVehicleService(db, RecordingScheduler(), clock=lambda: now)
    job = MaintenanceReminderService(
        db, notifier(db), lambda v, at: vehicles_service.calculate(v, now=at), clock=lambda: now
    )
    count = 0
    for delivery_id in list_due_delivery_ids(db, now):
        count += await job.dispatch_delivery(delivery_id)
    return {"sent": count}
