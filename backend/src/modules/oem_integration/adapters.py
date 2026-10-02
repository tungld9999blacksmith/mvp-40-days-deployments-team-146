"""OEM integration module — Celery scheduler and Redis-backed lock / event store."""

from __future__ import annotations

import logging
from uuid import UUID

from redis.asyncio import Redis

from src.common.core.vehicle import OemSyncTrigger

from .ports import SyncLock, SyncScheduler, WebhookEventStore

logger = logging.getLogger(__name__)

SYNC_LOCK_TTL_SECONDS = 60
EVENT_ID_TTL_SECONDS = 7 * 24 * 3600
DEBOUNCE_TTL_SECONDS = 10


class CelerySyncScheduler(SyncScheduler):
    def schedule(self, user_vehicle_id: UUID, trigger: OemSyncTrigger, *, delay_seconds: int = 0) -> None:
        # Imported lazily so the API process never needs the broker at import time.
        from src.infrastructure.celery.tasks.oem_sync_tasks import sync_vehicle_oem_data_task

        sync_vehicle_oem_data_task.apply_async(args=[str(user_vehicle_id), trigger.value], countdown=delay_seconds)


class RedisSyncLock(SyncLock):
    """``SET NX EX`` lock per vehicle (API spec JOB-VEH-001 §2 step 1)."""

    def __init__(self, redis: Redis, *, key_prefix: str) -> None:
        self._redis = redis
        self._prefix = key_prefix

    def _key(self, user_vehicle_id: UUID) -> str:
        return f"{self._prefix}:oem:sync:lock:{user_vehicle_id}"

    async def acquire(self, user_vehicle_id: UUID) -> bool:
        return bool(await self._redis.set(self._key(user_vehicle_id), "1", nx=True, ex=SYNC_LOCK_TTL_SECONDS))

    async def release(self, user_vehicle_id: UUID) -> None:
        await self._redis.delete(self._key(user_vehicle_id))


class RedisWebhookEventStore(WebhookEventStore):
    def __init__(self, redis: Redis, *, key_prefix: str) -> None:
        self._redis = redis
        self._prefix = key_prefix

    async def claim_event(self, event_id: str) -> bool:
        key = f"{self._prefix}:oem:webhook:event:{event_id}"
        return bool(await self._redis.set(key, "1", nx=True, ex=EVENT_ID_TTL_SECONDS))

    async def claim_debounce(self, user_vehicle_id: UUID) -> bool:
        key = f"{self._prefix}:oem:webhook:debounce:{user_vehicle_id}"
        return bool(await self._redis.set(key, "1", nx=True, ex=DEBOUNCE_TTL_SECONDS))
