"""Real SQL reminder/email services with recorded transport and versioned consent."""

from datetime import timedelta

import pytest
from sqlmodel import Session, select

from src.common.core.maintenance import Reminder
from src.common.core.maintenance.reminder import ReminderChannel
from src.common.core.notification import ReminderDelivery, ReminderPersonalizationEvent, UserNotificationSetting
from src.common.core.notification.email import EmailOutbox
from src.modules.notification.channels import DeliveryResult
from src.modules.notification.context_service import ReminderContextService
from src.modules.notification.schemas import NotificationSettingsUpdateIn
from src.modules.notification.settings_service import NotificationSettingsService
from src.modules.user_vehicle.service import UserVehicleService
from src.modules.vehicle_usage.service import PERSONALIZATION_POLICY_VERSION
from tests._user_vehicle import RecordingScheduler, add_odometer
from tests.test_modules import test_main_email_reminders as email_tests
from tests.test_modules.test_main_email_reminders import Transport, service


@pytest.fixture
def setup(monkeypatch):
    yield from email_tests.setup.__wrapped__(monkeypatch)


def settings_service(db):
    return NotificationSettingsService(db, available_channels={ReminderChannel.EMAIL}, default_lead_days=2)


def configure_usage(db, owner, vehicle, cfg, now):
    cfg.oem_sync_mode = "oem"
    cfg.personalized_reminders_mode = "on"
    now[0] -= timedelta(days=30)  # Official time deadline must be outside the 7-day window.
    for delta in range(28, -1, -1):
        add_odometer(db, vehicle, 10800 - 200 * delta, now[0] - timedelta(days=delta))
    # Remove fixture's future ODO; retain a known high-water anchor in this scenario.
    from sqlalchemy import delete

    from src.common.core.vehicle import VehicleOdometerReading

    db.execute(
        delete(VehicleOdometerReading).where(
            VehicleOdometerReading.user_vehicle_id == vehicle.id, VehicleOdometerReading.recorded_at > now[0]
        )
    )
    db.commit()
    settings_service(db).update(
        owner,
        NotificationSettingsUpdateIn(
            reminder_lead_days=7,
            personalized_reminders_enabled=True,
            personalization_policy_version=PERSONALIZATION_POLICY_VERSION,
        ),
    )


@pytest.mark.asyncio
async def test_predictive_reminder_passes_email_eligibility_and_is_idempotent(setup):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    cfg.email_mode = "resend"
    transport = Transport()
    reminders, _ = service(db, cfg, now, transport)
    result = await reminders.remind(vehicle.id)
    assert result.deliveries_sent == 1
    assert len(transport.calls) == 1
    assert "200 km/ngày" in transport.calls[0][1]["body"]
    reminder = db.exec(select(Reminder)).one()
    assert reminder.details["triggerReasons"] == ["PREDICTED_KM_WINDOW"]
    with Session(db.bind) as restarted:
        again, _ = service(restarted, cfg, now, transport)
        await again.remind(vehicle.id)
        assert len(transport.calls) == 1
        assert restarted.exec(select(ReminderDelivery)).one().attempts == 1


@pytest.mark.asyncio
async def test_opt_out_cancels_pending_retry_and_hides_old_forecast(setup):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"))
    reminders, _ = service(db, cfg, now, transport)
    await reminders.remind(vehicle.id)
    settings_service(db).update(owner, NotificationSettingsUpdateIn(personalized_reminders_enabled=False))
    now[0] += timedelta(minutes=6)
    await reminders.remind(vehicle.id)
    assert len(transport.calls) == 1
    outbox = db.exec(select(EmailOutbox)).one()
    assert outbox.delivery_state == "cancelled" and outbox.payload is None
    vehicles = UserVehicleService(db, RecordingScheduler(), clock=lambda: now[0])
    assert vehicles.get_maintenance_status(vehicle).maintenance_forecast.status == "DISABLED"
    context = ReminderContextService(db, vehicles).get(owner, db.exec(select(Reminder)).one().id)
    assert "personalization" not in context["details"]


@pytest.mark.asyncio
async def test_erasure_removes_sent_payload_and_snapshots_but_preserves_source(setup):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    reminders, _ = service(db, cfg, now)
    await reminders.remind(vehicle.id)
    from src.common.core.vehicle import VehicleOdometerReading

    count = len(db.exec(select(VehicleOdometerReading)).all())
    settings_service(db).delete_personalization_data(owner)
    assert len(db.exec(select(VehicleOdometerReading)).all()) == count
    assert "personalization" not in db.exec(select(Reminder)).one().details
    assert db.exec(select(EmailOutbox)).one().payload is None
    assert db.get(UserNotificationSetting, owner.user_id).personalized_reminders_enabled is False
    assert [
        event.action
        for event in db.exec(
            select(ReminderPersonalizationEvent).order_by(ReminderPersonalizationEvent.occurred_at)
        ).all()
    ] == ["GRANTED", "REVOKED", "DERIVED_DATA_DELETED"]


@pytest.mark.asyncio
async def test_shadow_and_static_sources_never_extend_send_window(setup):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    cfg.personalized_reminders_mode = "shadow"
    reminders, _ = service(db, cfg, now)
    assert (await reminders.remind(vehicle.id)).created_level is None
    cfg.personalized_reminders_mode = "on"
    cfg.oem_sync_mode = "static"
    assert (await reminders.remind(vehicle.id)).created_level is None


@pytest.mark.asyncio
async def test_durable_shadow_comparison_is_daily_and_erased_with_derived_data(setup):
    from src.common.core.notification import ReminderPolicyEvaluation
    from src.modules.notification.metrics_service import aggregate_metrics

    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    cfg.personalized_reminders_mode = "shadow"
    reminders, _ = service(db, cfg, now)
    await reminders.remind(vehicle.id)
    await reminders.remind(vehicle.id)
    evaluation = db.exec(select(ReminderPolicyEvaluation)).one()
    assert evaluation.baseline_level is None and evaluation.actual_level is None
    assert evaluation.candidate_level == "EARLY"
    metrics = aggregate_metrics(db, now=now[0])
    assert metrics["shadowCount"] == metrics["shadowChangedDecisions"] == 1
    assert metrics["recordedProviderAttempts"] == 0
    settings_service(db).delete_personalization_data(owner)
    assert db.exec(select(ReminderPolicyEvaluation)).all() == []


def test_consent_is_explicit_versioned_and_idempotent(setup):
    db, owner, vehicle, cfg, now = setup
    from src.modules.notification.errors import NotificationError

    with pytest.raises(NotificationError):
        settings_service(db).update(owner, NotificationSettingsUpdateIn(personalized_reminders_enabled=True))
    assert db.get(UserNotificationSetting, owner.user_id) is None
    payload = NotificationSettingsUpdateIn(
        personalized_reminders_enabled=True, personalization_policy_version=PERSONALIZATION_POLICY_VERSION
    )
    settings_service(db).update(owner, payload)
    settings_service(db).update(owner, payload)
    assert len(db.exec(select(ReminderPersonalizationEvent)).all()) == 1
    settings_service(db).update(owner, NotificationSettingsUpdateIn(reminders_enabled=False))
    assert db.get(UserNotificationSetting, owner.user_id).personalized_reminders_enabled


def test_forecast_rechecks_consent_changed_by_another_session(setup):
    from src.modules.vehicle_usage.service import VehicleUsageService

    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    vehicles = UserVehicleService(db, RecordingScheduler(), clock=lambda: now[0])
    usage = VehicleUsageService(db, cfg)
    due = vehicles.calculate(vehicle, now=now[0])
    assert usage.forecast(vehicle, due, now[0]).status == "AVAILABLE"
    with Session(db.bind) as other:
        setting = other.get(UserNotificationSetting, owner.user_id)
        setting.personalized_reminders_enabled = False
        other.add(setting)
        other.commit()
    assert usage.forecast(vehicle, due, now[0]).status == "DISABLED"


@pytest.mark.asyncio
async def test_forecast_error_keeps_fixed_reminders_working(setup, monkeypatch):
    import src.modules.vehicle_usage.service as usage_module

    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    add_odometer(db, vehicle, 11600, now[0] + timedelta(minutes=1))
    now[0] += timedelta(minutes=1)

    def unavailable(*args, **kwargs):
        raise ValueError("Invalid usage input")

    monkeypatch.setattr(usage_module, "calculate_forecast", unavailable)
    vehicles = UserVehicleService(db, RecordingScheduler(), clock=lambda: now[0])
    assert vehicles.get_maintenance_status(vehicle).maintenance_forecast.status == "CALCULATION_ERROR"
    reminders, _ = service(db, cfg, now)
    assert (await reminders.remind(vehicle.id)).deliveries_sent == 1
    assert "personalization" not in db.exec(select(Reminder)).one().details


@pytest.mark.asyncio
async def test_erasure_between_forecast_and_insert_does_not_recreate_snapshot(setup, monkeypatch):
    from src.modules.vehicle_usage.service import VehicleUsageService

    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    original = VehicleUsageService.forecast
    erased = False

    def revoke_before_insert(usage, *args):
        nonlocal erased
        forecast = original(usage, *args)
        if not erased:
            erased = True
            settings_service(db).delete_personalization_data(owner)
        return forecast

    monkeypatch.setattr(VehicleUsageService, "forecast", revoke_before_insert)
    reminders, _ = service(db, cfg, now)
    assert (await reminders.remind(vehicle.id)).created_level is None
    assert db.exec(select(Reminder)).all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("rollback_mode", ["off", "shadow"])
async def test_rollout_rollback_stops_predictive_retry_without_resetting_delivery_history(setup, rollback_mode):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"))
    reminders, _ = service(db, cfg, now, transport)
    await reminders.remind(vehicle.id)
    cfg.personalized_reminders_mode = rollback_mode
    now[0] += timedelta(minutes=6)
    outcome = await reminders.remind(vehicle.id)
    assert outcome.created_level is None and len(transport.calls) == 1
    assert db.exec(select(ReminderDelivery)).one().attempts == 1
    assert db.exec(select(Reminder)).one().details["personalization"]
