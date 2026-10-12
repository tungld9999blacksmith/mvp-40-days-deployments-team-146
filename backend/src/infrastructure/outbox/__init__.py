"""Transactional outbox: store domain events with the business change, handle them in the worker.

Producer (in the request transaction)::

    from src.infrastructure.outbox import publish
    publish(session, BookingConfirmed(booking_id=b.id), aggregate_type="booking", aggregate_id=str(b.id))
    session.commit()

Consumer (a feature module, registered at import time; list the module in
``OUTBOX_HANDLER_MODULES`` of ``celery/tasks/outbox_tasks.py``)::

    class BookingConfirmedHandler(OutboxHandler[BookingConfirmed]):
        event = BookingConfirmed
        async def handle(self, event, ctx): ...

    register_handler(BookingConfirmedHandler())

Worker: ``outbox.dispatch`` (beat every OUTBOX_DISPATCH_INTERVAL_SECONDS + a wakeup
after each publishing commit) and ``outbox.purge`` (daily). Guide: backend/guide/outbox.md.
"""

from .dispatcher import DispatcherConfig, DispatchReport, OutboxDispatcher, build_outbox_dispatcher
from .events import OutboxContext, OutboxEvent, OutboxHandler, PermanentError, RetryableError
from .models import OutboxEventRecord, OutboxStatus
from .publisher import OutboxPublisher, get_outbox_publisher, publish
from .registry import DuplicateHandlerError, OutboxRegistry, outbox_registry, register_handler

__all__ = [
    "DispatchReport",
    "DispatcherConfig",
    "DuplicateHandlerError",
    "OutboxContext",
    "OutboxDispatcher",
    "OutboxEvent",
    "OutboxEventRecord",
    "OutboxHandler",
    "OutboxPublisher",
    "OutboxRegistry",
    "OutboxStatus",
    "PermanentError",
    "RetryableError",
    "build_outbox_dispatcher",
    "get_outbox_publisher",
    "outbox_registry",
    "publish",
    "register_handler",
]
