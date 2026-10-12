"""Celery task for the shared demo account ("Dùng thử ngay", modules/demo_account).

- ``demo_account.reset_if_due`` — hourly beat job: wipe and re-seed the account once
  ``DEMO_RESET_INTERVAL_HOURS`` have passed since the last reset. A failed run (e.g.
  mock-ev-system down) changes nothing and is simply retried by the next beat.

Scheduled only when ``DEMO_LOGIN_ENABLED`` is on.
"""

from __future__ import annotations

import asyncio
import logging

from src.celery_tasks import celery

logger = logging.getLogger(__name__)


async def _reset_if_due(force: bool) -> bool:
    from src.config import get_settings
    from src.infrastructure.supabase.db import get_session
    from src.modules.demo_account.dependency import build_demo_service

    session = next(get_session())
    try:
        return await build_demo_service(session, get_settings()).reset_if_due(force=force)
    finally:
        session.close()


@celery.task(name="demo_account.reset_if_due")
def reset_demo_account_task(force: bool = False) -> bool:
    try:
        return asyncio.run(_reset_if_due(force))
    except Exception:  # noqa: BLE001 — the next hourly run tries again
        logger.exception("demo account reset failed")
        return False
