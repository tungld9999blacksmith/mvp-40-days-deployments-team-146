"""Celery tasks for the manufacturer data sync (FEAT-VEH-001, JOB-VEH-001).

- ``oem.sync_vehicle`` — sync odometer + service history of one vehicle
  (webhook, initial sync after verification, self-heal from API-VEH-003).
- ``oem.sync_all_vehicles`` — beat job: enqueue a sync for every verified,
  active vehicle (trigger ``poll``).

Each run opens its own DB session and Redis connection in the worker process.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from src.celery_tasks import celery

logger = logging.getLogger(__name__)

RETRY_DELAYS_SECONDS = (30, 120, 600)


async def _run_sync(user_vehicle_id: UUID, trigger_value: str):
    from redis.asyncio import Redis

    from src.common.core.vehicle import OemSyncTrigger
    from src.config import get_settings
    from src.infrastructure.oem.gateway import HttpOemVehicleDataGateway
    from src.infrastructure.supabase.db import get_session
    from src.modules.oem_integration.adapters import RedisSyncLock
    from src.modules.oem_integration.service import OemVehicleSyncService

    settings = get_settings()
    redis = Redis.from_url(settings.redis_connection_url)
    session = next(get_session())
    try:
        service = OemVehicleSyncService(
            session,
            HttpOemVehicleDataGateway(settings.oem_api_base_url, timeout_seconds=settings.oem_api_timeout_seconds),
            RedisSyncLock(redis, key_prefix=settings.redis_key_prefix),
            failure_alert_threshold=settings.oem_sync_alert_failures,
        )
        return await service.sync(user_vehicle_id, OemSyncTrigger(trigger_value))
    finally:
        session.close()
        await redis.aclose()


@celery.task(name="oem.sync_vehicle", bind=True, acks_late=True, max_retries=len(RETRY_DELAYS_SECONDS))
def sync_vehicle_oem_data_task(self, user_vehicle_id: str, trigger: str) -> str:
    outcome = asyncio.run(_run_sync(UUID(user_vehicle_id), trigger))
    # A poll is retried by the next poll; webhook / initial syncs retry on outage.
    if outcome.status == "failed" and trigger != "poll" and self.request.retries < self.max_retries:
        raise self.retry(countdown=RETRY_DELAYS_SECONDS[self.request.retries])
    return outcome.status


@celery.task(name="oem.sync_all_vehicles")
def sync_all_vehicles_task() -> int:
    from src.infrastructure.supabase.db import get_session
    from src.modules.oem_integration.service import list_eligible_vehicle_ids

    session = next(get_session())
    try:
        ids = list_eligible_vehicle_ids(session)
    finally:
        session.close()
    for vehicle_id in ids:
        sync_vehicle_oem_data_task.delay(str(vehicle_id), "poll")
    logger.info("enqueued OEM sync for %s vehicles", len(ids))
    return len(ids)
