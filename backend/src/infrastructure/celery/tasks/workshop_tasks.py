"""Celery tasks for workshop-owner onboarding (FEAT-AUTH-003).

- ``workshop.retry_verification`` — re-run the OEM manager verification for a
  pending attempt after a timeout (5 retries over ~30 minutes, EF-202).
- ``workshop.reconcile_verifications`` — re-enqueue pending attempts whose
  scheduled retry was lost (broker restart, enqueue failure).
- ``workshop.purge_expired_onboarding`` — delete unfinished onboardings and
  verification logs older than the retention period (BR-208).

Each task opens its own DB session in the worker process.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from uuid import UUID

from src.celery_tasks import celery

logger = logging.getLogger(__name__)


@contextmanager
def _service():
    from src.infrastructure.supabase.db import get_session
    from src.modules.workshop_owner_onboarding.dependency import (
        build_workshop_onboarding_service,
        get_retry_scheduler,
        get_service_center_gateway,
    )

    session = next(get_session())
    try:
        yield build_workshop_onboarding_service(session, get_service_center_gateway(), get_retry_scheduler())
    finally:
        session.close()


@celery.task(name="workshop.retry_verification", acks_late=True)
def retry_workshop_verification_task(attempt_id: str) -> None:
    with _service() as service:
        asyncio.run(service.retry_verification(UUID(attempt_id)))


@celery.task(name="workshop.reconcile_verifications")
def reconcile_workshop_verifications_task() -> int:
    with _service() as service:
        ids = service.stale_pending_attempt_ids()
    for attempt_id in ids:
        retry_workshop_verification_task.delay(str(attempt_id))
    if ids:
        logger.info("re-enqueued %s stale workshop verification attempts", len(ids))
    return len(ids)


@celery.task(name="workshop.purge_expired_onboarding")
def purge_expired_workshop_onboarding_task() -> int:
    with _service() as service:
        deleted = service.purge_expired_onboarding()
    logger.info("purged %s expired workshop onboardings", deleted)
    return deleted
