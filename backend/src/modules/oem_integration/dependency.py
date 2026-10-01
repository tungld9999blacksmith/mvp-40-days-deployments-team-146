"""OEM integration module — dependency injection (composition root)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from src.config import get_settings
from src.infrastructure.redis import get_redis_toolkit
from src.infrastructure.supabase.db import get_session

from .adapters import CelerySyncScheduler, RedisWebhookEventStore
from .ports import SyncScheduler, WebhookEventStore
from .service import OemWebhookService


def get_sync_scheduler() -> SyncScheduler:
    return CelerySyncScheduler()


def get_webhook_event_store() -> WebhookEventStore:
    settings = get_settings()
    return RedisWebhookEventStore(
        get_redis_toolkit().redis, key_prefix=settings.redis_key_prefix
    )


def get_webhook_service(
    session: Annotated[Session, Depends(get_session)],
    scheduler: Annotated[SyncScheduler, Depends(get_sync_scheduler)],
    event_store: Annotated[WebhookEventStore, Depends(get_webhook_event_store)],
) -> OemWebhookService:
    settings = get_settings()
    return OemWebhookService(
        session,
        scheduler,
        event_store,
        secret=settings.oem_webhook_secret,
        tolerance_seconds=settings.oem_webhook_tolerance_seconds,
    )
