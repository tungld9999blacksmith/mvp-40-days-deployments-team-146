"""Auth module — concrete ``SessionRevoker`` backed by Celery.

Hands the refresh-token revoke off to the durable ``auth.revoke_session`` task.
If the broker cannot accept the task, raises ``RevokeEnqueueError`` so the
service can answer ``503`` (EF-104).
"""

from __future__ import annotations

import logging

from .ports import RevokeEnqueueError

logger = logging.getLogger(__name__)


class CelerySessionRevoker:
    """Enqueue the revoke via Celery (Redis broker)."""

    def enqueue_revoke(self, *, uid: str, user_id: int, trace_id: str | None = None) -> None:
        # Imported lazily to avoid a hard Celery/broker dependency at import time.
        from src.infrastructure.celery.tasks.auth_tasks import revoke_session_task

        try:
            revoke_session_task.delay(uid, user_id, trace_id)
        except Exception as exc:  # noqa: BLE001 — broker unreachable, etc.
            logger.warning("could not enqueue revoke task uid=%s: %s", uid, exc)
            raise RevokeEnqueueError(str(exc)) from exc
