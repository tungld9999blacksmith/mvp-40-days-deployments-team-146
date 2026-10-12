"""Demo account module — domain exceptions, mapped to HTTP by the handler in ``main.py``.

Hierarchy:
    DemoAccountError
      ├─ DemoLoginDisabledError       -> 404 (DEMO_LOGIN_DISABLED)
      ├─ DemoRateLimitedError         -> 429 (DEMO_RATE_LIMITED)
      └─ DemoAccountUnavailableError  -> 503 (DEMO_ACCOUNT_UNAVAILABLE)
"""

from __future__ import annotations


class DemoAccountError(Exception):
    code: str = "DEMO_ACCOUNT_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class DemoLoginDisabledError(DemoAccountError):
    code = "DEMO_LOGIN_DISABLED"

    def __init__(self) -> None:
        super().__init__("Not found.")


class DemoRateLimitedError(DemoAccountError):
    code = "DEMO_RATE_LIMITED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many demo sign-ins from this address.", details={"retryAfterSeconds": retry_after_seconds}
        )
        self.retry_after_seconds = retry_after_seconds


class DemoAccountUnavailableError(DemoAccountError):
    code = "DEMO_ACCOUNT_UNAVAILABLE"

    def __init__(self, message: str = "The demo account is not available right now.") -> None:
        super().__init__(message)


ERROR_STATUS: dict[str, int] = {
    "DEMO_LOGIN_DISABLED": 404,
    "DEMO_RATE_LIMITED": 429,
    "DEMO_ACCOUNT_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
