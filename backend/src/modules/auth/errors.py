"""Auth module — domain / application exceptions (FEAT-AUTH-002).

The service raises these instead of returning HTTP responses; a global handler
(see ``main.py``) maps each to an error code + HTTP status using the shared
error envelope. Never import FastAPI here.

Hierarchy:
    AuthError
      └─ AuthProviderUnavailableError  -> 503 (AUTH_PROVIDER_UNAVAILABLE)

Token errors (``UNAUTHORIZED`` / ``INVALID_TOKEN`` → 401) are raised by the
``verify_firebase_token`` dependency as ``HTTPException`` and are not modelled
here.
"""

from __future__ import annotations


class AuthError(Exception):
    """Base class for auth errors. Carries a machine-readable code."""

    code: str = "AUTH_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class AuthProviderUnavailableError(AuthError):
    """Could not verify the token or record/enqueue the logout task (EF-104)."""

    code = "AUTH_PROVIDER_UNAVAILABLE"

    def __init__(
        self,
        message: str = (
            "Không thể thu hồi phiên lúc này. Vui lòng thử lại; "
            "phiên trên thiết bị đã được đăng xuất."
        ),
    ) -> None:
        super().__init__(message)


# Maps a machine-readable error code to its HTTP status. Codes not listed here
# fall back to 500 (see the exception handler).
ERROR_STATUS: dict[str, int] = {
    "AUTH_PROVIDER_UNAVAILABLE": 503,
    "INTERNAL_SERVER_ERROR": 500,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 500)
