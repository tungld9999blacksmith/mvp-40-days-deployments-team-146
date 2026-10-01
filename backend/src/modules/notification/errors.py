"""Notification module - domain errors (API-NOTI-001..002).

Mapped to the shared error envelope by the handler in ``main.py``.
"""

from __future__ import annotations


class NotificationError(Exception):
    code: str = "NOTIFICATION_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class InvalidRequestError(NotificationError):
    code = "INVALID_REQUEST"

    def __init__(self, message: str = "The request body is invalid.") -> None:
        super().__init__(message)


class InvalidLeadDaysError(NotificationError):
    code = "INVALID_LEAD_DAYS"

    def __init__(self, minimum: int, maximum: int) -> None:
        super().__init__(f"reminderLeadDays must be between {minimum} and {maximum}.")


class ChannelNotAvailableError(NotificationError):
    code = "CHANNEL_NOT_AVAILABLE"

    def __init__(self, channel: str) -> None:
        super().__init__(f"The channel {channel} is not available yet.")


class NoChannelEnabledError(NotificationError):
    code = "NO_CHANNEL_ENABLED"

    def __init__(self) -> None:
        super().__init__("Reminders are on but no notification channel is enabled.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "INVALID_LEAD_DAYS": 422,
    "CHANNEL_NOT_AVAILABLE": 422,
    "NO_CHANNEL_ENABLED": 422,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
