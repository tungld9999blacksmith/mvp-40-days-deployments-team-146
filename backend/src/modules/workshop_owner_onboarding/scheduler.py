"""Workshop-owner onboarding — Celery-backed ``VerificationRetryScheduler``."""

from __future__ import annotations

from uuid import UUID

from .ports import VerificationRetryScheduler


class CeleryVerificationRetryScheduler(VerificationRetryScheduler):
    def schedule(self, attempt_id: UUID, *, delay_seconds: int) -> None:
        # Imported lazily so the API process never needs the broker at import time.
        from src.infrastructure.celery.tasks.workshop_tasks import retry_workshop_verification_task

        retry_workshop_verification_task.apply_async(
            args=[str(attempt_id)], countdown=delay_seconds
        )
