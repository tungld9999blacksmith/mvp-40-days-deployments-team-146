"""Celery tasks for maintenance reminders (FEAT-NOTI-001, JOB-NOTI-001).

- ``reminder.send_all`` - beat job: enqueue one task per eligible vehicle.
- ``reminder.remind_vehicle`` - decide and send the reminder of one vehicle.

One task per vehicle keeps a failing vehicle from blocking the others. Failed
email attempts use minute retries with provider backoff; other channels retain
their daily retry policy.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from src.celery_tasks import celery

logger = logging.getLogger(__name__)


class _NoopScheduler:
    """The reminder job only reads the due status; it never enqueues an OEM sync."""

    def schedule(self, *args, **kwargs) -> None:
        return None


async def _run_reminder(user_vehicle_id: UUID):
    from sqlmodel import Session

    from src.config import get_settings
    from src.infrastructure.supabase.db import engine
    from src.modules.notification.dependency import build_notification_service
    from src.modules.notification.reminder_service import MaintenanceReminderService
    from src.modules.user_vehicle.dependency import get_due_config
    from src.modules.user_vehicle.service import UserVehicleService

    settings = get_settings()
    with Session(engine) as session:
        config = get_due_config()
        vehicles = UserVehicleService(session, _NoopScheduler(), config=config)
        service = MaintenanceReminderService(
            session,
            build_notification_service(session),
            lambda vehicle, now: vehicles.calculate(vehicle, now=now),
            default_lead_days=settings.reminder_default_lead_days,
            due_soon_km=config.due_soon_km,
            max_attempts=settings.reminder_max_attempts,
            app_url=settings.frontend_url,
        )
        return await service.remind(user_vehicle_id)


@celery.task(name="reminder.remind_vehicle")
def remind_vehicle_task(user_vehicle_id: str) -> str:
    outcome = asyncio.run(_run_reminder(UUID(user_vehicle_id)))
    return outcome.reason or outcome.status


@celery.task(name="reminder.send_all")
def send_all_reminders_task() -> int:
    from sqlmodel import Session

    from src.infrastructure.supabase.db import engine
    from src.modules.notification.reminder_service import list_eligible_vehicle_ids

    with Session(engine) as session:
        ids = list_eligible_vehicle_ids(session)
    for vehicle_id in ids:
        remind_vehicle_task.delay(str(vehicle_id))
    logger.info("enqueued maintenance reminders for %s vehicles", len(ids))
    return len(ids)


@celery.task(name="reminder.retry_emails")
def retry_emails_task() -> int:
    """Minute tick for due retries/crash recovery, not a second full-vehicle scan."""
    from sqlalchemy import or_
    from sqlmodel import Session, select

    from src.common.core.notification import DeliveryStatus, ReminderDelivery
    from src.common.core.notification.email import EmailOutbox
    from src.infrastructure.supabase.db import engine
    from src.modules.oem_integration.service import utc_now

    now = utc_now()
    with Session(engine) as db:
        ids = set(
            db.exec(
                select(EmailOutbox.user_vehicle_id)
                .join(ReminderDelivery, ReminderDelivery.id == EmailOutbox.delivery_id)
                .where(
                    ReminderDelivery.status != DeliveryStatus.SENT,
                    EmailOutbox.delivery_state == "pending",
                    or_(EmailOutbox.next_attempt_at <= now, EmailOutbox.lease_until <= now),
                )
            ).all()
        )
    for vehicle_id in ids:
        remind_vehicle_task.delay(str(vehicle_id))
    return len(ids)


@celery.task(name="reminder.purge_email_payloads")
def purge_email_payloads_task() -> int:
    from sqlmodel import Session

    from src.config import get_settings
    from src.infrastructure.supabase.db import engine
    from src.modules.notification.email_service import MaintenanceEmailAdapter

    with Session(engine) as db:
        return MaintenanceEmailAdapter(db, get_settings()).purge_payloads()
