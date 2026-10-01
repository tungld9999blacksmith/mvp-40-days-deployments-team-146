"""Celery tasks for booking by capacity (FEAT-BOOK-001, F6).

- ``booking.cancel_unconfirmed`` — cancel ``pending`` bookings past the
  workshop-confirm deadline (BR-015), freeing their slots. Runs every few
  minutes; also covers holds the workshop never accepted (manual mode).
- ``booking_reminder.send_due`` — 24h appointment reminders (us-033 JOB-BR-001).

The task opens its own DB session + Redis toolkit in the worker process.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager

from src.celery_tasks import celery

logger = logging.getLogger(__name__)


@contextmanager
def _service():
    from src.infrastructure.redis.dependency import get_redis_toolkit
    from src.infrastructure.supabase.db import get_session
    from src.modules.booking.dependency import get_booking_config
    from src.modules.booking.location import get_location_finder
    from src.modules.booking.service import BookingService

    session = next(get_session())
    try:
        yield BookingService(
            session, get_redis_toolkit(), get_location_finder(), config=get_booking_config()
        )
    finally:
        session.close()


@celery.task(name="booking.cancel_unconfirmed")
def cancel_unconfirmed_bookings_task() -> int:
    with _service() as service:
        cancelled = service.cancel_unconfirmed()
    if cancelled:
        logger.info("cancelled %s unconfirmed bookings past the workshop deadline", cancelled)
    return cancelled


async def _run_reminder_job():
    from src.infrastructure.supabase.db import get_session
    from src.modules.booking.reminders import BookingReminderJob, reminder_config
    from src.modules.notification.dependency import build_notification_service

    session = next(get_session())
    try:
        job = BookingReminderJob(session, build_notification_service(session), reminder_config())
        return await job.run()
    finally:
        session.close()


@celery.task(name="booking_reminder.send_due")
def send_due_booking_reminders_task() -> dict:
    """us-033 JOB-BR-001 — reconcile, send due 24h reminders, retry transient failures."""
    return asyncio.run(_run_reminder_job()).as_dict()
