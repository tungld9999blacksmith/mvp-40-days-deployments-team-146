"""
FastAPI integration.

`rate_limit(...)` turns a `RateLimiter` plus an `IdentityResolver` into a route
dependency. Attach it per endpoint so each one keys on the signal that suits it::

    from ...infrastructure.redis.ratelimit import identity as ident
    from ...infrastructure.redis.ratelimit import Algorithm, Rate, rate_limit
    from ...infrastructure.redis.dependency import get_redis_toolkit

    toolkit = get_redis_toolkit()

    # Anonymous, bursty: token bucket keyed by IP.
    search_limit = toolkit.rate_limiter("search", Rate(30, 60), Algorithm.TOKEN_BUCKET)
    # Sensitive: exact sliding-window log keyed by the auth token, else IP.
    login_limit = toolkit.rate_limiter("login", Rate(5, 60), Algorithm.SLIDING_WINDOW_LOG)

    @router.get("/search", dependencies=[Depends(rate_limit(search_limit, ident.by_ip()))])
    async def search(): ...

    @router.post(
        "/login",
        dependencies=[Depends(rate_limit(login_limit, ident.first_of(ident.by_api_token(), ident.by_ip())))],
    )
    async def login(): ...

On success the standard `X-RateLimit-*` headers are added to the response; when
the quota is exceeded, `RateLimitExceededError` is raised. Call `install_rate_limiting(app)`
once at startup to render that as a `429` with a `Retry-After` header.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from ..errors import RateLimitError, RateLimitExceededError
from .base import RateLimiter, RateLimitResult
from .identity import Identity, IdentityResolver, by_ip

logger = logging.getLogger(__name__)

Guard = Callable[[Request, Response], Awaitable[RateLimitResult]]


def rate_limit(
    limiter: RateLimiter,
    resolver: IdentityResolver | None = None,
    *,
    cost: int = 1,
    fail_open: bool = True,
) -> Guard:
    """
    Build a route dependency that enforces *limiter* for each request.

    Args:
        limiter: the configured `RateLimiter`.
        resolver: how to identify the caller; defaults to `by_ip()`.
        cost: units this endpoint consumes per call (e.g. a batch route may cost more).
        fail_open: if identity resolution or Redis fails, allow the request
            (log a warning) rather than reject it. Set False for endpoints where
            an unprotected call is worse than a rejected one.
    """
    resolve = resolver or by_ip()

    async def guard(request: Request, response: Response) -> RateLimitResult:
        identity = resolve(request)
        if identity is None:
            if not fail_open:
                raise RateLimitExceededError(
                    "unidentified", limit=limiter.rate.limit, remaining=0, retry_after=0.0, reset_after=0.0
                )
            logger.warning("Rate limiter %r: no identity for %s; allowing", limiter.algorithm, request.url.path)
            identity = Identity("anon", "unknown")

        try:
            result = await limiter.try_acquire(str(identity), cost)
        except RateLimitError:
            if fail_open:
                logger.exception("Rate limiter %r failed for %s; allowing", limiter.algorithm, identity)
                return RateLimitResult(True, limiter.rate.limit, limiter.rate.limit, 0.0)
            raise

        response.headers.update(result.headers)
        if not result.allowed:
            raise RateLimitExceededError(
                str(identity),
                limit=result.limit,
                remaining=result.remaining,
                retry_after=result.retry_after,
                reset_after=result.reset_after,
            )
        return result

    return guard


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceededError) -> JSONResponse:
    """Render `RateLimitExceededError` as a 429 with rate-limit headers."""
    retry_after = int(exc.retry_after) + 1
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Too many requests. Please slow down and retry later.",
                "details": {"retryAfterSeconds": retry_after},
                "traceId": request.headers.get("X-Request-ID"),
            }
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(exc.limit),
            "X-RateLimit-Remaining": str(exc.remaining),
            "X-RateLimit-Reset": str(int(exc.reset_after) + 1),
        },
    )


def install_rate_limiting(app: FastAPI) -> None:
    """Register the 429 handler for `RateLimitExceededError` on *app* (call once at startup)."""
    app.add_exception_handler(RateLimitExceededError, rate_limit_exceeded_handler)  # type: ignore[arg-type]
