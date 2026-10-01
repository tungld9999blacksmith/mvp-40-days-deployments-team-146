"""Celery tasks for maintenance reminders (FEAT-NOTI-001, JOB-NOTI-001).

- ``reminder.send_all`` - beat job: enqueue one task per eligible vehicle.
- ``reminder.remind_vehicle`` - decide and send the reminder of one vehicle.

One task per vehicle keeps a failing vehicle from blocking the others. Failed
deliveries are retried by the next daily run (no backoff, BR-508).
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
    from src.config import get_settings
    from src.infrastructure.supabase.db import get_session
    from src.modules.notification.dependency import build_notification_service
    from src.modules.notification.reminder_service import MaintenanceReminderService
    from src.modules.user_vehicle.dependency import get_due_config
    from src.modules.user_vehicle.service import UserVehicleService

    settings = get_settings()
    session = next(get_session())
    try:
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
    finally:
        session.close()


@celery.task(name="reminder.remind_vehicle")
def remind_vehicle_task(user_vehicle_id: str) -> str:
    outcome = asyncio.run(_run_reminder(UUID(user_vehicle_id)))
    return outcome.reason or outcome.status


@celery.task(name="reminder.send_all")
def send_all_reminders_task() -> int:
    from src.infrastructure.supabase.db import get_session
    from src.modules.notification.reminder_service import list_eligible_vehicle_ids

    session = next(get_session())
    try:
        ids = list_eligible_vehicle_ids(session)
    finally:
        session.close()
    for vehicle_id in ids:
        remind_vehicle_task.delay(str(vehicle_id))
    logger.info("enqueued maintenance reminders for %s vehicles", len(ids))
    return len(ids)
