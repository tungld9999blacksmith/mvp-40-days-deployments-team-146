"""Celery tasks of the transactional outbox (infrastructure/outbox).

- ``outbox.dispatch`` — handle due events sequentially (up to OUTBOX_BATCH_SIZE).
  Runs on beat every OUTBOX_DISPATCH_INTERVAL_SECONDS and right after each commit
  that published an event. Concurrent runs are safe: claims use SKIP LOCKED.
- ``outbox.purge`` — delete succeeded events older than OUTBOX_RETENTION_DAYS.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import timedelta

from src.celery_tasks import celery

logger = logging.getLogger(__name__)

# Modules that register outbox handlers on import (``register_handler(...)``).
# The worker imports them before dispatching; an event without a handler is retried.
OUTBOX_HANDLER_MODULES: tuple[str, ...] = ()


def load_handler_modules() -> None:
    for name in OUTBOX_HANDLER_MODULES:
        importlib.import_module(name)


@celery.task(name="outbox.dispatch", ignore_result=True)
def dispatch_outbox_task() -> dict:
    from src.infrastructure.outbox import build_outbox_dispatcher

    load_handler_modules()
    return asyncio.run(build_outbox_dispatcher().run_once()).as_dict()


@celery.task(name="outbox.purge")
def purge_outbox_task() -> int:
    from src.config import get_settings
    from src.infrastructure.outbox import build_outbox_dispatcher

    deleted = build_outbox_dispatcher().purge_succeeded(timedelta(days=get_settings().outbox_retention_days))
    if deleted:
        logger.info("purged %s succeeded outbox events", deleted)
    return deleted
