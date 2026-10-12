"""Demo account module — dependency injection (composition root)."""

from __future__ import annotations

import logging
import math
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from redis.exceptions import RedisError
from sqlmodel import Session

from src.common.client_ip import client_key, resolve_client_ip
from src.config import Settings, get_settings
from src.infrastructure.oem.gateway import HttpOemVehicleDataGateway, HttpOemVehicleGateway
from src.infrastructure.redis import RedisToolkit, get_redis_toolkit
from src.infrastructure.redis.errors import RateLimitError
from src.infrastructure.redis.ratelimit import Rate
from src.infrastructure.supabase.db import get_session

from .adapters import FirebaseDemoIdentity, HttpDemoOwnerAdmin, NoSyncLock
from .errors import DemoLoginDisabledError, DemoRateLimitedError
from .service import DemoAccountService

logger = logging.getLogger(__name__)


def make_syncer(settings: Settings):
    """OEM sync of one demo vehicle, run inline (the seed wants the due status right away)."""

    async def sync(session: Session, user_vehicle_id: UUID):
        from src.common.core.vehicle import OemSyncTrigger
        from src.modules.oem_integration.service import OemVehicleSyncService

        gateway = HttpOemVehicleDataGateway.from_settings(settings)
        service = OemVehicleSyncService(session, gateway, NoSyncLock())
        return await service.sync(user_vehicle_id, OemSyncTrigger.INITIAL)

    return sync


def build_demo_service(session: Session, settings: Settings) -> DemoAccountService:
    """Shared by the API, the reset job and the reset script."""
    return DemoAccountService(
        session,
        email=settings.demo_account_email,
        reset_interval_hours=settings.demo_reset_interval_hours,
        gateway=HttpOemVehicleGateway.from_settings(settings),
        identity=FirebaseDemoIdentity(),
        owner_admin=HttpDemoOwnerAdmin(
            settings.oem_api_base_url,
            admin_token=settings.oem_admin_token,
            timeout_seconds=settings.oem_api_timeout_seconds,
        ),
        syncer=make_syncer(settings),
    )


def require_demo_login_enabled() -> None:
    if not get_settings().demo_login_enabled:
        raise DemoLoginDisabledError()


async def limit_demo_sessions(
    request: Request,
    toolkit: Annotated[RedisToolkit, Depends(get_redis_toolkit)],
) -> None:
    """Sign-ins per client IP and hour; fails open when Redis is down (like the location limits)."""
    settings = get_settings()
    limiter = toolkit.rate_limiter("demo:session", Rate.per_hour(settings.demo_session_rate_limit_per_hour))
    ip = resolve_client_ip(request, trust_forwarded=settings.rate_limit_trust_forwarded)
    try:
        result = await limiter.try_acquire(client_key(ip))
    except (RedisError, RateLimitError, OSError):
        logger.warning("demo session rate limiter unavailable; allowing the request", exc_info=True)
        return
    if not result.allowed:
        raise DemoRateLimitedError(max(1, math.ceil(result.retry_after)))


def get_demo_service(session: Annotated[Session, Depends(get_session)]) -> DemoAccountService:
    return build_demo_service(session, get_settings())
