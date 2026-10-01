"""Error hierarchy for the Redis toolkit. Callers catch these, never redis-py exceptions."""


class RedisToolkitError(Exception):
    """Base exception for every error raised by infrastructure/redis."""


class SerializationError(RedisToolkitError):
    """A value could not be encoded to / decoded from bytes."""


class CacheError(RedisToolkitError):
    """Misconfigured cache call (missing loader/writer, bad key template, ...)."""


class LockError(RedisToolkitError):
    """Base class for distributed-lock errors."""


class LockAcquireError(LockError):
    """The lock could not be acquired within the wait timeout."""


class LockNotOwnedError(LockError):
    """Release/extend was attempted on a lock this holder no longer owns (expired or stolen)."""


class QueueError(RedisToolkitError):
    """Distributed queue operation failed."""


class RateLimitError(RedisToolkitError):
    """Base class for rate-limiter errors."""


class RateLimitExceededError(RateLimitError):
    """
    A caller went over its quota.

    Carries the decision so an HTTP layer can build a 429 response
    (limit / remaining / Retry-After) without re-querying Redis.
    """

    def __init__(
        self,
        identity: str,
        *,
        limit: int,
        remaining: int,
        retry_after: float,
        reset_after: float,
    ) -> None:
        self.identity = identity
        self.limit = limit
        self.remaining = remaining
        self.retry_after = retry_after
        self.reset_after = reset_after
        super().__init__(f"Rate limit exceeded for {identity!r}: retry after {retry_after:.3f}s")
