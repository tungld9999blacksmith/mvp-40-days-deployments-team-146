"""Workshop-owner auth — Celery-backed ``WorkshopSessionRevoker``."""

from __future__ import annotations

import logging
from uuid import UUID

from .ports import RevokeEnqueueError

logger = logging.getLogger(__name__)


class CeleryWorkshopSessionRevoker:
    def enqueue_revoke(
        self, *, uid: str, owner_id: UUID | None, trace_id: str | None = None
    ) -> None:
        # Lazy import: the API process must not need the broker at import time.
        from src.infrastructure.celery.tasks.workshop_auth_tasks import revoke_workshop_session_task

        try:
            revoke_workshop_session_task.delay(uid, str(owner_id) if owner_id else None, trace_id)
        except Exception as exc:  # noqa: BLE001 — broker unreachable, etc.
            logger.warning("could not enqueue workshop revoke uid=%s: %s", uid, exc)
            raise RevokeEnqueueError(str(exc)) from exc
