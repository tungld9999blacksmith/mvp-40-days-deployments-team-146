"""Location search — domain errors.

Codes and HTTP statuses follow ``docs/specs/platform/location-search.api.md`` §6 and §1.1.
"""

from __future__ import annotations


class LocationError(Exception):
    code: str = "LOCATION_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class InvalidRequestError(LocationError):
    code = "INVALID_REQUEST"

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message, details={"field": field} if field else None)


class CallerNotRegisteredError(LocationError):
    """Valid Firebase token, but neither a vehicle owner nor a workshop owner account."""

    code = "FORBIDDEN"

    def __init__(self) -> None:
        super().__init__("Sign in and register before searching locations.")


class AccountLockedError(LocationError):
    code = "ACCOUNT_LOCKED"

    def __init__(self) -> None:
        super().__init__("This account is locked.")


class LocationNotFoundError(LocationError):
    code = "LOCATION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Location was not found.")


class LocationOutOfCoverageError(LocationError):
    code = "LOCATION_OUT_OF_COVERAGE"

    def __init__(self) -> None:
        super().__init__("Only locations in Vietnam are supported.")


class RateLimitExceededError(LocationError):
    code = "RATE_LIMIT_EXCEEDED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many requests. Please slow down and retry later.",
            details={"retryAfterSeconds": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class LocationProviderUnavailableError(LocationError):
    code = "LOCATION_PROVIDER_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Location service is temporarily unavailable.")


ERROR_STATUS: dict[str, int] = {
    InvalidRequestError.code: 422,
    CallerNotRegisteredError.code: 403,
    AccountLockedError.code: 403,
    LocationNotFoundError.code: 404,
    LocationOutOfCoverageError.code: 422,
    RateLimitExceededError.code: 429,
    LocationProviderUnavailableError.code: 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
