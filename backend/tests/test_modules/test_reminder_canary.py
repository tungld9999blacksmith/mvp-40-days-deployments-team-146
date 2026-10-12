from datetime import timedelta

import pytest
from pydantic import ValidationError
from sqlmodel import select

from src.common.core.notification import ReminderDelivery, ReminderPolicyEvaluation
from src.common.core.notification.email import EmailOutbox
from src.config import Settings
from src.modules.notification.channels import DeliveryResult, NotificationMessage
from src.modules.user_vehicle.service import UserVehicleService
from tests._user_vehicle import RecordingScheduler
from tests.test_modules import test_personalized_reminders as personalization_tests
from tests.test_modules.test_main_email_reminders import Transport, service
from tests.test_modules.test_personalized_reminders import configure_usage, settings_service


@pytest.fixture
def setup(monkeypatch):
    yield from personalization_tests.setup.__wrapped__(monkeypatch)


@pytest.mark.parametrize("value", ["0", "-1", "owner@example.com", "1,,2", "1.5", "１"])
def test_invalid_canary_list_is_rejected_at_startup(value):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, personalized_reminders_canary_user_ids=value)


def test_canary_list_is_normalized_and_cannot_override_off_or_shadow():
    cfg = Settings(_env_file=None, personalized_reminders_canary_user_ids=" 2,1,2 ")
    assert cfg.personalized_reminders_canary_user_ids == "1,2"
    assert cfg.personalized_reminders_mode_for(1) == "shadow"
    cfg.personalized_reminders_mode = "off"
    assert cfg.personalized_reminders_mode_for(1) == "off"
    cfg.personalized_reminders_mode = "on"
    assert cfg.personalized_reminders_mode_for(1) == "on"
    assert cfg.personalized_reminders_mode_for(3) == "shadow"


@pytest.mark.asyncio
@pytest.mark.parametrize("included", [True, False])
async def test_canary_job_ui_and_evaluation_use_same_owner_mode(setup, included):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    cfg.personalized_reminders_canary_user_ids = str(owner.user_id if included else owner.user_id + 100)
    vehicles = UserVehicleService(db, RecordingScheduler(), clock=lambda: now[0])
    status = vehicles.get_maintenance_status(vehicle)
    assert status.maintenance_forecast.reminder_recommended is included
    assert settings_service(db).get(owner).personalization_mode == ("on" if included else "shadow")
    transport = Transport()
    cfg.email_mode = "resend"
    job, _ = service(db, cfg, now, transport)
    outcome = await job.remind(vehicle.id)
    assert len(transport.calls) == int(included)
    assert (outcome.created_level is not None) is included
    evaluation = db.exec(select(ReminderPolicyEvaluation)).one()
    assert evaluation.mode == ("on" if included else "shadow")
    assert evaluation.candidate_level == "EARLY"


@pytest.mark.asyncio
async def test_removing_owner_from_canary_stops_retry_without_revoking_consent(setup):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    cfg.personalized_reminders_canary_user_ids = str(owner.user_id)
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"))
    job, _ = service(db, cfg, now, transport)
    await job.remind(vehicle.id)
    cfg.personalized_reminders_canary_user_ids = str(owner.user_id + 100)
    now[0] += timedelta(minutes=6)
    await job.remind(vehicle.id)
    assert len(transport.calls) == 1
    assert settings_service(db).get(owner).personalized_reminders_enabled


@pytest.mark.asyncio
async def test_cohort_does_not_grant_consent_for_owner(setup):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    from src.modules.notification.schemas import NotificationSettingsUpdateIn

    settings_service(db).update(owner, NotificationSettingsUpdateIn(personalized_reminders_enabled=False))
    cfg.personalized_reminders_canary_user_ids = str(owner.user_id)
    job, _ = service(db, cfg, now)
    assert (await job.remind(vehicle.id)).created_level is None
    assert (
        UserVehicleService(db, RecordingScheduler(), clock=lambda: now[0])
        .get_maintenance_status(vehicle)
        .maintenance_forecast.status
        == "DISABLED"
    )


@pytest.mark.asyncio
async def test_excluded_owner_still_receives_baseline_reminder(setup):
    db, owner, vehicle, cfg, now = setup
    cfg.personalized_reminders_mode = "on"
    cfg.personalized_reminders_canary_user_ids = str(owner.user_id + 100)
    cfg.email_mode = "resend"
    transport = Transport()
    job, _ = service(db, cfg, now, transport)
    assert (await job.remind(vehicle.id)).deliveries_sent == 1
    assert len(transport.calls) == 1
    assert settings_service(db).get(owner).personalization_mode == "shadow"
    assert not db.exec(select(ReminderPolicyEvaluation)).all()  # No usage consent in this fixture.


@pytest.mark.asyncio
async def test_adapter_rechecks_cohort_before_retrying_frozen_predictive_email(setup):
    db, owner, vehicle, cfg, now = setup
    configure_usage(db, owner, vehicle, cfg, now)
    cfg.personalized_reminders_canary_user_ids = str(owner.user_id)
    cfg.email_mode = "resend"
    transport = Transport(DeliveryResult.failed("TIMEOUT"))
    job, adapter = service(db, cfg, now, transport)
    await job.remind(vehicle.id)
    delivery = db.exec(select(ReminderDelivery)).one()
    frozen = db.exec(select(EmailOutbox)).one().payload
    cfg.personalized_reminders_canary_user_ids = str(owner.user_id + 100)
    now[0] += timedelta(minutes=6)
    result = await adapter.send(owner.user_id, NotificationMessage(**frozen))
    assert result.deferred
    assert len(transport.calls) == 1
    assert db.get(ReminderDelivery, delivery.id).attempts == 1
