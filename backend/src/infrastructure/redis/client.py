from __future__ import annotations

from redis.asyncio import Redis

from ...config import Settings


def create_redis_client(settings: Settings) -> Redis:
    """
    Async Redis client over a connection pool.

    `decode_responses=False`: every structure in this package works on raw bytes
    and decodes through its own `Serializer`.
    """
    return Redis.from_url(
        settings.redis_connection_url,
        max_connections=settings.redis_max_connections,
        decode_responses=False,
        health_check_interval=30,
    )
