from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlmodel import select

from src.common.core.maintenance import Reminder
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import DeliveryStatus, ReminderDelivery, UserNotificationChannel
from src.common.core.notification.email import EmailOutbox
from src.common.core.vehicle import VehicleOdometerReading, VehicleTripPlan
from src.config import Settings
from src.modules.notification.channels import NotificationService
from src.modules.notification.email_service import MaintenanceEmailAdapter
from src.modules.notification.policy_service import decide_reminder
from src.modules.notification.reminder_service import MaintenanceReminderService
from src.modules.notification.schemas import NotificationSettingsUpdateIn
from src.modules.notification.settings_service import NotificationSettingsService
from src.modules.trip_planning.domain import advise_trip
from src.modules.trip_planning.schemas import TripPlanIn
from src.modules.trip_planning.service import TripPlanningService, trip_trigger
from src.modules.user_vehicle.domain import DueStatus, today_vn
from src.modules.user_vehicle.errors import UserVehicleError
from src.modules.user_vehicle.service import UserVehicleService
from tests._maintenance import make_session
from tests._user_vehicle import add_odometer, add_owner, add_rules, add_vehicle, mark_synced


@pytest.fixture
def trip_setup(monkeypatch):
    gen = make_session()
    db = next(gen)
    cfg = Settings(
        _env_file=None,
        app_env="test",
        personalized_reminders_mode="on",
        oem_sync_mode="oem",
        email_mode="mock",
        agent_memory_read_enabled=False,
    )
    monkeypatch.setattr("src.config.get_settings", lambda: cfg)
    now = [datetime(2026, 10, 11, 1, tzinfo=UTC)]
    owner = add_owner(db)
    owner.email_verified = True
    db.add(owner)
    vehicle = add_vehicle(db, owner, with_warranty=False)
    vehicle.manufacture_date = date(2026, 1, 1)
    db.add(vehicle)
    db.commit()
    add_rules(db)
    add_odometer(db, vehicle, 10800, now[0])
    mark_synced(db, vehicle, now[0])
    db.add(UserNotificationChannel(user_id=owner.user_id, channel=ReminderChannel.EMAIL))
    db.commit()
    vehicles = UserVehicleService(db, Mock(), clock=lambda: now[0])
    trips = TripPlanningService(db, vehicles, clock=lambda: now[0])
    NotificationSettingsService(
        db, available_channels={ReminderChannel.EMAIL}, default_lead_days=2, clock=lambda: now[0]
    ).update(owner, NotificationSettingsUpdateIn(reminder_lead_days=7, preferred_send_time="19:00"))
    yield db, owner, vehicle, cfg, now, vehicles, trips
    gen.close()


def payload(now, *, days=3, distance=1500, enabled=True):
    return TripPlanIn(
        departure_date=today_vn(now[0]) + timedelta(days=days), distance_km=distance, reminder_enabled=enabled
    )


def job(db, cfg, now, vehicles):
    return MaintenanceReminderService(
        db,
        NotificationService([MaintenanceEmailAdapter(db, cfg, clock=lambda: now[0])]),
        lambda v, at: vehicles.calculate(v, now=at),
        clock=lambda: now[0],
    )


def test_trip_projection_does_not_change_observed_odo_or_due_status(trip_setup):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    before = vehicles.calculate(vehicle)
    saved = trips.put(vehicle, payload(now))
    assert saved.data.advice.status == "MAINTENANCE_RECOMMENDED"
    assert saved.data.advice.projected_trip_end_km == 12300
    assert saved.data.advice.reasons == ["TRIP_KM_MILESTONE"]
    assert vehicles.calculate(vehicle) == before
    assert len(db.exec(select(VehicleOdometerReading)).all()) == 1
    assert not db.exec(select(Reminder)).all()


@pytest.mark.parametrize("distance,status", [(1199, "NO_MILESTONE_CROSSING"), (1200, "MAINTENANCE_RECOMMENDED")])
def test_exact_milestone_boundary(trip_setup, distance, status):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    assert trips.put(vehicle, payload(now, distance=distance)).data.advice.status == status


def test_time_deadline_with_missing_or_stale_odo(trip_setup):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    trips.put(vehicle, payload(now, distance=10))
    trip = db.exec(select(VehicleTripPlan)).one()
    result = vehicles.calculate(vehicle)
    result = replace(result, odometer=None, next_milestone=replace(result.next_milestone, due_date=trip.departure_date))
    advice = advise_trip(trip, result, today=today_vn(now[0]))
    assert advice.reasons == ["TRIP_TIME_DEADLINE"] and advice.projected_trip_end_km is None
    result = replace(
        result,
        odometer=replace(vehicles.calculate(vehicle).odometer, is_stale=True),
        next_milestone=vehicles.calculate(vehicle).next_milestone,
    )
    assert advise_trip(trip, result, today=today_vn(now[0])).status == "ODO_UNAVAILABLE"


@pytest.mark.parametrize(
    "changes",
    [
        {"distanceKm": 0},
        {"distanceKm": 20001},
        {"distanceKm": True},
        {"reminderEnabled": "true"},
        {"returnDate": "2026-10-10"},
        {"userId": 2},
    ],
)
def test_invalid_trip_input(changes):
    with pytest.raises(ValidationError):
        TripPlanIn.model_validate({"departureDate": "2026-10-12", "distanceKm": 1000} | changes)


@pytest.mark.parametrize("days", [-1, 366])
def test_invalid_departure_is_atomic(trip_setup, days):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    with pytest.raises(UserVehicleError):
        trips.put(vehicle, payload(now, days=days))
    assert not db.exec(select(VehicleTripPlan)).all()


@pytest.mark.parametrize(
    "mode,enabled,days,expected",
    [
        ("on", True, 3, True),
        ("shadow", True, 3, False),
        ("off", True, 3, False),
        ("on", False, 3, False),
        ("on", True, 8, False),
    ],
)
def test_trip_reminder_mode_optin_and_window(trip_setup, mode, enabled, days, expected):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    cfg.personalized_reminders_mode = mode
    trips.put(vehicle, payload(now, days=days, enabled=enabled))
    assert bool(trip_trigger(db, vehicle, vehicles.calculate(vehicle), now[0])) == expected


@pytest.mark.asyncio
async def test_trip_reminder_is_scheduled_once_and_uses_email_final_guard(trip_setup):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    trips.put(vehicle, payload(now))
    worker = job(db, cfg, now, vehicles)
    assert (await worker.remind(vehicle.id)).created_level
    assert (await worker.remind(vehicle.id)).created_level is None
    reminder = db.exec(select(Reminder)).one()
    delivery = db.exec(select(ReminderDelivery)).one()
    assert reminder.details["trip"]["distanceKm"] == 1500 and delivery.attempts == 0
    now[0] += timedelta(hours=11)
    assert await worker.dispatch_delivery(delivery.id) == 1
    assert await worker.dispatch_delivery(delivery.id) == 0
    outbox = db.exec(select(EmailOutbox)).one()
    assert "Chuyến đi" in outbox.payload["body"]
    assert outbox.accepted_at and delivery.attempts == 1


@pytest.mark.asyncio
async def test_edit_cancels_frozen_trip_delivery_but_repeated_save_does_not(trip_setup):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    data = payload(now)
    trips.put(vehicle, data)
    worker = job(db, cfg, now, vehicles)
    await worker.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    trips.put(vehicle, data)
    assert delivery.status == DeliveryStatus.PENDING
    trips.put(vehicle, payload(now, distance=50))
    assert delivery.error_code == "SCHEDULE_CANCELLED" and delivery.next_eligible_send_at is None
    now[0] += timedelta(hours=11)
    assert await worker.dispatch_delivery(delivery.id) == 0


@pytest.mark.asyncio
async def test_delete_erases_trip_snapshot_preserves_sent_receipt(trip_setup):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    trips.put(vehicle, payload(now))
    worker = job(db, cfg, now, vehicles)
    await worker.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    now[0] += timedelta(hours=11)
    await worker.dispatch_delivery(delivery.id)
    trips.delete(vehicle)
    assert trips.get(vehicle).data is None
    assert db.exec(select(Reminder)).one().details.get("trip") is None
    assert db.exec(select(EmailOutbox)).one().payload is None
    assert db.get(ReminderDelivery, delivery.id).status == DeliveryStatus.SENT


def test_expired_trip_and_overdue_priority(trip_setup):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    trips.put(vehicle, payload(now))
    trip = db.exec(select(VehicleTripPlan)).one()
    result = vehicles.calculate(vehicle)
    assert advise_trip(trip, result, today=trip.departure_date + timedelta(days=1)).status == "DEPARTED"
    decision = decide_reminder(
        replace(result, due_status=DueStatus.OVERDUE),
        lead_days=7,
        due_soon_km=500,
        today=today_vn(now[0]),
        trip=trip_trigger(db, vehicle, result, now[0]),
    )
    assert decision.level.value == "expired" and decision.trip is None


def test_transferred_vehicle_does_not_expose_old_trip(trip_setup):
    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    trips.put(vehicle, payload(now))
    other = add_owner(db, uid="uid-other", email="other@example.com")
    vehicle.user_id = other.user_id
    db.add(vehicle)
    db.commit()
    assert trips.get(vehicle).data is None


def test_saved_preferences_are_used_only_with_memory_read_permission(trip_setup):
    from src.common.core.conversation import ChatMessage, Conversation, MessageRole
    from src.modules.agent_memory.preferences import PreferenceService

    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    cfg.agent_memory_write_enabled = True
    cfg.agent_memory_read_enabled = True
    conversation = Conversation(user_id=owner.user_id, user_vehicle_id=vehicle.id)
    db.add(conversation)
    db.commit()
    message = ChatMessage(
        seq=1,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="Hãy nhớ tôi thích bảo dưỡng thứ ba buổi sáng",
    )
    db.add(message)
    db.commit()
    prefs = PreferenceService(db, cfg)
    prefs.remember(
        owner.user_id,
        vehicle.id,
        conversation.id,
        message.id,
        "preferred_service_window",
        {"day": "tuesday", "period": "morning"},
    )
    saved = trips.put(vehicle, payload(now))
    assert saved.data.advice.preferred_service_window["suggestedDate"] == "2026-10-13"
    prefs.set_enabled(owner.user_id, False)
    assert trips.get(vehicle).data.advice.preferred_service_window is None


def test_trip_agent_tool_respects_session_vehicle_and_owner(trip_setup):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from src.agents.tools.maintenance_tools import build_maintenance_tools

    db, owner, vehicle, cfg, now, vehicles, trips = trip_setup
    trips.put(vehicle, payload(now))

    @contextmanager
    def open_session():
        yield db

    provider = SimpleNamespace(open_session=open_session, user_vehicle_service=lambda session: vehicles)
    tool = build_maintenance_tools(provider)[1]
    config = {"configurable": {"user_id": owner.user_id, "user_vehicle_id": str(vehicle.id)}}
    assert tool.invoke({}, config=config)["data"]["distance_km"] == 1500
    stranger = add_owner(db, uid="uid-stranger", email="stranger@example.com")
    config["configurable"]["user_id"] = stranger.user_id
    assert tool.invoke({}, config=config)["error_code"] == "VEHICLE_NOT_FOUND"
