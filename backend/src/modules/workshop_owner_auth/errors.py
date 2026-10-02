"""Workshop-owner auth — exceptions (FEAT-AUTH-004).

Mapped to the shared error envelope by the handler in ``main.py``.
"""

from __future__ import annotations


class WorkshopAuthError(Exception):
    code: str = "WORKSHOP_AUTH_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class AuthProviderUnavailableError(WorkshopAuthError):
    code = "AUTH_PROVIDER_UNAVAILABLE"

    def __init__(
        self,
        message: str = ("Không thể thu hồi phiên lúc này. Vui lòng thử lại; phiên trên thiết bị đã được đăng xuất."),
    ) -> None:
        super().__init__(message)


ERROR_STATUS: dict[str, int] = {
    "UNAUTHORIZED": 401,
    "INVALID_TOKEN": 401,
    "TOKEN_REVOKED": 401,
    "ACCOUNT_SUSPENDED": 403,
    "ACCOUNT_INACTIVE": 403,
    "WORKSHOP_OWNER_NOT_REGISTERED": 404,
    "AUTH_PROVIDER_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 500)
