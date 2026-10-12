"""Access tokens for the EV manufacturer API (SPEC-SEC-OEM-M2M-001 v2.0 §4.1).

``OemAccessTokenProvider`` exchanges a client assertion signed with EVCARE_PRIVATE_KEY
for an OEM-issued access token at ``POST /oauth/token``, verifies the OEM signature
with OEM_PUBLIC_KEY and caches the token in Redis (shared by the API and Celery
workers) for ``expires_in - refresh margin`` seconds. A Redis lock makes one caller
fetch while the others wait for the cache.

A Redis client is opened per call: Celery tasks run each job in a fresh event loop
and an async client cannot be shared across loops. Tokens are never logged.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from uuid import uuid4

import httpx
from ev_contracts import (
    CLIENT_ASSERTION_TYPE,
    CLIENT_CREDENTIALS_GRANT,
    OAUTH_TOKEN_PATH,
    M2MAuthError,
    create_client_assertion,
    verify_access_token,
)
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.config import Settings
from src.infrastructure.redis.client import create_redis_client

logger = logging.getLogger(__name__)

LOCK_TTL_SECONDS = 10
LOCK_POLL_SECONDS = 0.1

# Delete KEYS[1] only while it still holds ARGV[1] (our lock / the rejected token).
_COMPARE_AND_DELETE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


class OemAuthError(Exception):
    """The OEM access token could not be obtained, verified or was rejected after a refresh."""


class OemAccessTokenProvider:
    def __init__(
        self,
        base_url: str,
        *,
        private_key: str,
        oem_public_key: str,
        redis_factory: Callable[[], Redis],
        key_prefix: str,
        timeout_seconds: float = 8.0,
        refresh_margin_seconds: int = 60,
        transport: httpx.AsyncBaseTransport | None = None,
        lock_ttl_seconds: float = LOCK_TTL_SECONDS,
    ) -> None:
        self._token_url = f"{base_url.rstrip('/')}{OAUTH_TOKEN_PATH}"
        self._private_key = private_key
        self._oem_public_key = oem_public_key
        self._redis_factory = redis_factory
        self._token_key = f"{key_prefix}:oem:m2m:access_token"
        self._lock_key = f"{self._token_key}:lock"
        self._timeout = timeout_seconds
        self._margin = refresh_margin_seconds
        self._transport = transport
        self._lock_ttl = lock_ttl_seconds

    @classmethod
    def from_settings(
        cls, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> OemAccessTokenProvider | None:
        """None when EVCARE_PRIVATE_KEY is unset (dev/test without M2M auth)."""
        if not settings.evcare_private_key.strip():
            return None
        return cls(
            settings.oem_api_base_url,
            private_key=settings.evcare_private_key,
            oem_public_key=settings.oem_public_key,
            redis_factory=lambda: create_redis_client(settings),
            key_prefix=settings.redis_key_prefix,
            timeout_seconds=settings.oem_api_timeout_seconds,
            refresh_margin_seconds=settings.oem_access_token_refresh_margin_seconds,
            transport=transport,
        )

    async def get_token(self) -> str:
        """Cached access token, fetching a new one on a miss.

        Raises ``OemAuthError`` (auth/config problem) or httpx transport errors (OEM unreachable).
        """
        redis = self._redis_factory()
        try:
            return await self._cached_or_fetch(redis)
        except RedisError as exc:
            # The cache is an optimisation: without Redis every call fetches its own token.
            logger.warning("OEM token cache unavailable, fetching without cache: %s", exc)
            token, _ = await self._fetch()
            return token
        finally:
            await redis.aclose()

    async def invalidate(self, token: str) -> None:
        """Drop ``token`` from the cache unless another caller already replaced it."""
        redis = self._redis_factory()
        try:
            await redis.eval(_COMPARE_AND_DELETE, 1, self._token_key, token)
        except RedisError as exc:
            logger.warning("Could not drop the rejected OEM token from the cache: %s", exc)
        finally:
            await redis.aclose()

    async def _cached_or_fetch(self, redis: Redis) -> str:
        cached = await self._read(redis)
        if cached:
            return cached
        lock_value = uuid4().hex
        if await redis.set(self._lock_key, lock_value, nx=True, ex=int(self._lock_ttl) or 1):
            try:
                cached = await self._read(redis)
                return cached or await self._fetch_and_store(redis)
            finally:
                await redis.eval(_COMPARE_AND_DELETE, 1, self._lock_key, lock_value)
        # Another caller is fetching: wait for its token, then fall back to our own fetch.
        deadline = time.monotonic() + self._lock_ttl
        while time.monotonic() < deadline:
            await asyncio.sleep(LOCK_POLL_SECONDS)
            cached = await self._read(redis)
            if cached:
                return cached
        logger.warning("Timed out waiting for another worker's OEM token; fetching one")
        return await self._fetch_and_store(redis)

    async def _read(self, redis: Redis) -> str | None:
        value = await redis.get(self._token_key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else str(value)

    async def _fetch_and_store(self, redis: Redis) -> str:
        token, ttl = await self._fetch()
        if ttl > 0:
            await redis.set(self._token_key, token, ex=ttl)
        return token

    async def _fetch(self) -> tuple[str, int]:
        """POST the client assertion; returns (verified access token, cache TTL seconds)."""
        if not self._oem_public_key.strip():
            logger.error("OEM_PUBLIC_KEY is not configured; cannot verify OEM access tokens")
            raise OemAuthError("OEM_PUBLIC_KEY is not configured")
        try:
            assertion = create_client_assertion(self._private_key)
        except Exception as exc:  # malformed key: surface as a config error, not a crash
            logger.error("EVCARE_PRIVATE_KEY cannot sign the client assertion: %s", exc)
            raise OemAuthError("EVCARE_PRIVATE_KEY is invalid") from exc

        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            resp = await client.post(
                self._token_url,
                data={
                    "grant_type": CLIENT_CREDENTIALS_GRANT,
                    "client_assertion_type": CLIENT_ASSERTION_TYPE,
                    "client_assertion": assertion,
                },
            )
        if resp.status_code != 200:
            logger.error("OEM token endpoint refused the client assertion: HTTP %s %s", resp.status_code, resp.text)
            raise OemAuthError(f"OEM token endpoint returned HTTP {resp.status_code}")

        try:
            body = resp.json()
            token = str(body["access_token"])
            expires_in = int(body["expires_in"])
            if str(body.get("token_type", "")).lower() != "bearer":
                raise ValueError(f"unexpected token_type {body.get('token_type')!r}")
            claims = verify_access_token(token, self._oem_public_key)
        except M2MAuthError as exc:
            logger.error("OEM access token failed verification (%s): %s", exc.code, exc)
            raise OemAuthError("OEM access token failed verification") from exc
        except (ValueError, KeyError, TypeError) as exc:
            logger.error("OEM token endpoint returned an invalid body: %s", exc)
            raise OemAuthError("OEM token endpoint returned an invalid body") from exc

        # expires_in is relative, so clock skew does not matter; exp - iat caps a wrong value.
        lifetime = min(expires_in, int(claims["exp"]) - int(claims["iat"]))
        return token, lifetime - self._margin
