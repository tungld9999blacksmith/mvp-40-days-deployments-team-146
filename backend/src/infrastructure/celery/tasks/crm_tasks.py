"""Celery tasks for post-service care and quotes.

- ``follow_up.send_due`` — open and send due follow-ups, retry deliveries (us-041 JOB-FU-001).
- ``follow_up.close_expired`` — close follow-ups unanswered for 72h (us-041 JOB-FU-002).
- ``quote.purge_stale_drafts`` — delete drafts older than the TTL (us-049 JOB-QT-01).

Each task opens its own DB session in the worker process.
"""

from __future__ import annotations

import asyncio
import logging

from src.celery_tasks import celery

logger = logging.getLogger(__name__)


async def _run_follow_up_send() -> dict:
    from src.config import get_settings
    from src.infrastructure.supabase.db import get_session
    from src.modules.follow_up.jobs import FollowUpJobConfig, FollowUpSendJob
    from src.modules.notification.dependency import build_notification_service

    s = get_settings()
    session = next(get_session())
    try:
        job = FollowUpSendJob(
            session,
            build_notification_service(session),
            FollowUpJobConfig(
                response_window_hours=s.follow_up_response_window_hours,
                max_attempts=s.reminder_max_attempts,
                frontend_url=s.frontend_url,
            ),
        )
        return (await job.run()).__dict__
    finally:
        session.close()


@celery.task(name="follow_up.send_due")
def send_due_follow_ups_task() -> dict:
    return asyncio.run(_run_follow_up_send())


@celery.task(name="follow_up.close_expired")
def close_expired_follow_ups_task() -> int:
    from src.config import get_settings
    from src.infrastructure.supabase.db import get_session
    from src.modules.follow_up.jobs import close_expired

    session = next(get_session())
    try:
        return close_expired(
            session, response_window_hours=get_settings().follow_up_response_window_hours
        )
    finally:
        session.close()


@celery.task(name="quote.purge_stale_drafts")
def purge_stale_quote_drafts_task() -> int:
    from src.config import get_settings
    from src.infrastructure.supabase.db import get_session
    from src.modules.quote.jobs import purge_stale_drafts

    session = next(get_session())
    try:
        return purge_stale_drafts(session, ttl_days=get_settings().quote_draft_ttl_days)
    finally:
        session.close()
