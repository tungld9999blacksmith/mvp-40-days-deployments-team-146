"""Celery task: durable Firebase refresh-token revoke (FEAT-AUTH-002, API-101).

The logout endpoint enqueues ``revoke_session_task``; the worker calls Firebase
``auth.revoke_refresh_tokens(uid)`` (retrying transient errors) and writes the
outcome to ``auth_event`` via ``AuthService.record_revoke_result``.

Runs in the worker process, so it opens its own DB session and ensures the
Firebase Admin app is initialized.
"""

from __future__ import annotations

import logging

from src.celery_tasks import celery

logger = logging.getLogger(__name__)

# Transient Firebase/network errors are retried; a missing user is not.
_MAX_RETRIES = 5
_RETRY_BACKOFF_SECONDS = 10


@celery.task(
    name="auth.revoke_session",
    bind=True,
    max_retries=_MAX_RETRIES,
    default_retry_delay=_RETRY_BACKOFF_SECONDS,
    acks_late=True,
)
def revoke_session_task(self, uid: str, user_id: int, trace_id: str | None = None) -> None:
    # Imported lazily so importing this module never requires Firebase creds
    # or a DB connection (e.g. when the API process registers the task).
    from firebase_admin import auth

    import src.infrastructure.firebase.oauth.setup  # noqa: F401  (initializes Admin app)

    success = False
    reason: str | None = None
    try:
        auth.revoke_refresh_tokens(uid)
        success = True
        logger.info("revoked refresh tokens uid=%s trace_id=%s", uid, trace_id)
    except Exception as exc:  # noqa: BLE001 — decide retry vs. record-failure below
        reason = type(exc).__name__[:64]
        logger.warning("revoke_refresh_tokens failed uid=%s: %s", uid, exc)
        # Record the failure so the audit trail is complete, then retry.
        _record(user_id=user_id, success=False, reason=reason, trace_id=trace_id)
        raise self.retry(exc=exc)

    _record(user_id=user_id, success=success, reason=reason, trace_id=trace_id)


def _record(*, user_id: int, success: bool, reason: str | None, trace_id: str | None) -> None:
    from src.infrastructure.supabase.db import get_session
    from src.modules.auth.revoker import CelerySessionRevoker
    from src.modules.auth.service import AuthService

    session = next(get_session())
    try:
        service = AuthService(session, CelerySessionRevoker())
        service.record_revoke_result(user_id=user_id, success=success, reason=reason, trace_id=trace_id)
    finally:
        session.close()
