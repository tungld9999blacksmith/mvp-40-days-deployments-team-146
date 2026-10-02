"""Celery tasks for workshop-owner auth (FEAT-AUTH-004).

- ``workshop_auth.revoke_session`` — revoke the Firebase refresh tokens of a
  uid after logout and audit the outcome (retry transient errors).
- ``workshop_auth.purge_events`` — delete audit rows older than 60 days.

Each task opens its own DB session in the worker process.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from uuid import UUID

from src.celery_tasks import celery

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_RETRY_BACKOFF_SECONDS = 10


@contextmanager
def _service():
    from src.infrastructure.supabase.db import get_session
    from src.modules.workshop_owner_auth.dependency import build_workshop_auth_service

    session = next(get_session())
    try:
        yield build_workshop_auth_service(session)
    finally:
        session.close()


def _record(owner_id: str | None, *, success: bool, reason: str | None, trace_id: str | None) -> None:
    with _service() as service:
        service.record_revoke_result(
            owner_id=UUID(owner_id) if owner_id else None,
            success=success,
            reason=reason,
            trace_id=trace_id,
        )


@celery.task(
    name="workshop_auth.revoke_session",
    bind=True,
    max_retries=_MAX_RETRIES,
    default_retry_delay=_RETRY_BACKOFF_SECONDS,
    acks_late=True,
)
def revoke_workshop_session_task(self, uid: str, owner_id: str | None, trace_id: str | None = None) -> None:
    # Lazy: importing this module must not require Firebase credentials.
    from firebase_admin import auth

    import src.infrastructure.firebase.oauth.setup  # noqa: F401  (initializes Admin app)

    try:
        auth.revoke_refresh_tokens(uid)
    except Exception as exc:  # noqa: BLE001 — audit every failed try, then retry
        logger.warning("workshop revoke_refresh_tokens failed uid=%s: %s", uid, exc)
        _record(owner_id, success=False, reason=type(exc).__name__[:64], trace_id=trace_id)
        raise self.retry(exc=exc) from exc

    logger.info("revoked refresh tokens uid=%s trace_id=%s", uid, trace_id)
    _record(owner_id, success=True, reason=None, trace_id=trace_id)


@celery.task(name="workshop_auth.purge_events")
def purge_workshop_auth_events_task() -> int:
    with _service() as service:
        deleted = service.purge_events()
    logger.info("purged %s workshop auth events", deleted)
    return deleted
