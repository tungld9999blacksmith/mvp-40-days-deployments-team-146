"""Producer side: stage an event in the caller's transaction.

    publish(session, BookingConfirmed(booking_id=...), aggregate_type="booking", aggregate_id=str(id))
    session.commit()   # the business rows and the event are stored together, or neither

``publish`` never commits. After the commit, an optional wakeup enqueues
``outbox.dispatch`` so the event is handled in milliseconds instead of on the
next beat scan; a failed wakeup only costs latency (the scan picks the row up).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import event as sa_event
from sqlmodel import Session, select

from src.infrastructure.observability import current_trace_ids

from .events import OutboxEvent
from .models import OutboxEventRecord

logger = logging.getLogger(__name__)

_WAKEUP_ARMED = "outbox_wakeup_armed"

Wakeup = Callable[[], None]


class OutboxPublisher:
    def __init__(
        self,
        *,
        wakeup: Wakeup | None = None,
        max_attempts: int = 10,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._wakeup = wakeup
        self._max_attempts = max_attempts
        self._clock = clock

    def publish(
        self,
        session: Session,
        event: OutboxEvent,
        *,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        dedup_key: str | None = None,
        delay: timedelta | None = None,
        max_attempts: int | None = None,
    ) -> OutboxEventRecord:
        """Add ``event`` to ``session`` (no commit). With ``dedup_key``, an existing event is returned."""
        if dedup_key is not None:
            existing = session.exec(select(OutboxEventRecord).where(OutboxEventRecord.dedup_key == dedup_key)).first()
            if existing is not None:
                return existing
        trace = current_trace_ids()
        record = OutboxEventRecord(
            event_type=event.event_type,
            schema_version=type(event).schema_version,
            payload=event.model_dump(mode="json"),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            dedup_key=dedup_key,
            max_attempts=max_attempts or self._max_attempts,
            available_at=self._clock() + (delay or timedelta(0)),
            trace_id=trace[0] if trace else None,
        )
        session.add(record)
        # A delayed event is not due yet: waking the dispatcher now would find nothing.
        if not delay:
            self._arm_wakeup(session)
        return record

    def _arm_wakeup(self, session: Session) -> None:
        if self._wakeup is None or session.info.get(_WAKEUP_ARMED):
            return
        session.info[_WAKEUP_ARMED] = True

        def after_commit(committed: Session) -> None:
            committed.info.pop(_WAKEUP_ARMED, None)
            try:
                self._wakeup()
            except Exception:  # noqa: BLE001 — the beat scan still delivers the event
                logger.warning("outbox wakeup failed; the next scan will dispatch", exc_info=True)

        # On rollback the listener stays armed; the next commit of this session
        # fires it once, which at worst runs an empty dispatch.
        sa_event.listen(session, "after_commit", after_commit, once=True)


def celery_wakeup() -> None:
    # Imported lazily: producers must not need the broker at import time.
    from src.celery_tasks import FAIL_FAST_PUBLISH
    from src.infrastructure.celery.tasks.outbox_tasks import dispatch_outbox_task

    dispatch_outbox_task.apply_async(**FAIL_FAST_PUBLISH)


_default: OutboxPublisher | None = None


def get_outbox_publisher() -> OutboxPublisher:
    global _default
    if _default is None:
        from src.config import get_settings

        settings = get_settings()
        _default = OutboxPublisher(
            wakeup=celery_wakeup if settings.outbox_wakeup_enabled else None,
            max_attempts=settings.outbox_max_attempts,
        )
    return _default


def publish(session: Session, event: OutboxEvent, **kwargs) -> OutboxEventRecord:
    """``get_outbox_publisher().publish`` — see ``OutboxPublisher.publish`` for the arguments."""
    return get_outbox_publisher().publish(session, event, **kwargs)
