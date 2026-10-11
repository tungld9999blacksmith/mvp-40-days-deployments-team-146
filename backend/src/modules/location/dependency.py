"""Location search — dependency injection, caller check and rate limits (spec §1.1, §5.1, §9)."""

from __future__ import annotations

import logging
import math
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from redis.exceptions import RedisError
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import UserStatus, VehicleUser
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.config import get_settings
from src.infrastructure.redis.dependency import get_redis_toolkit
from src.infrastructure.redis.errors import RateLimitError
from src.infrastructure.redis.ratelimit import Algorithm, Rate
from src.infrastructure.redis.toolkit import RedisToolkit
from src.infrastructure.supabase.db import get_session
from src.modules.oauth.dependency import verify_firebase_token

from . import errors
from .ports import PlaceSearchProvider
from .service import LocationService

logger = logging.getLogger(__name__)


# ── Provider (one per process: the AWS adapter keeps a pooled HTTP client) ──
@lru_cache
def get_place_search_provider() -> PlaceSearchProvider:
    """DI seam — LOCATION_PROVIDER picks the adapter (spec §5.1)."""
    s = get_settings()
    if s.location_provider == "aws":
        from src.infrastructure.location import AwsGrabPlacesProvider

        return AwsGrabPlacesProvider(
            s.aws_location_places_api_key,
            region=s.aws_location_region,
            timeout_seconds=s.location_timeout_seconds,
            reverse_radius_meters=s.location_reverse_radius_meters,
        )
    from src.infrastructure.location import FakePlacesProvider

    return FakePlacesProvider()


async def close_place_search_provider() -> None:
    """Release the provider's HTTP pool at shutdown (only if it was ever built)."""
    if get_place_search_provider.cache_info().currsize:
        await get_place_search_provider().aclose()
        get_place_search_provider.cache_clear()


def get_location_service(
    provider: Annotated[PlaceSearchProvider, Depends(get_place_search_provider)],
) -> LocationService:
    return LocationService(provider)


# ── Caller (§1.1): a registered vehicle owner or workshop owner, any onboarding state ──
def require_location_caller(
    claims: Annotated[dict, Depends(verify_firebase_token)],
    session: Annotated[Session, Depends(get_session)],
) -> str:
    """Return the Firebase uid. Onboarding users are allowed; unknown or locked accounts are not."""
    uid = claims.get("uid")
    if not uid:
        raise errors.CallerNotRegisteredError()
    for model in (VehicleUser, WorkshopOwner):
        account = session.exec(select(model).where(model.firebase_uid == uid)).first()
        if account is not None:
            if account.status != UserStatus.ACTIVE:
                raise errors.AccountLockedError()
            return uid
    raise errors.CallerNotRegisteredError()


# ── Rate limits (§9): token bucket keyed by uid, fail-open on Redis errors ──
async def _check_rate(toolkit: RedisToolkit, name: str, per_minute: int, uid: str) -> None:
    limiter = toolkit.rate_limiter(
        f"location:{name}", Rate.per_minute(per_minute, burst=max(1, per_minute // 3)), Algorithm.TOKEN_BUCKET
    )
    try:
        result = await limiter.try_acquire(uid)
    except (RedisError, RateLimitError, OSError):
        logger.warning("location rate limiter %s unavailable; allowing the request", name, exc_info=True)
        return
    if not result.allowed:
        raise errors.RateLimitExceededError(max(1, math.ceil(result.retry_after)))


async def suggest_caller(
    uid: Annotated[str, Depends(require_location_caller)],
    toolkit: Annotated[RedisToolkit, Depends(get_redis_toolkit)],
) -> str:
    await _check_rate(toolkit, "suggest", get_settings().location_suggest_rate_per_minute, uid)
    return uid


async def detail_caller(
    uid: Annotated[str, Depends(require_location_caller)],
    toolkit: Annotated[RedisToolkit, Depends(get_redis_toolkit)],
) -> str:
    await _check_rate(toolkit, "detail", get_settings().location_detail_rate_per_minute, uid)
    return uid
