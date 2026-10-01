"""OEM integration module — webhook errors (API-VEH-004).

Mapped to the shared error envelope by the handler in ``main.py``.
"""

from __future__ import annotations


class OemWebhookError(Exception):
    code: str = "OEM_WEBHOOK_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class WebhookSignatureInvalidError(OemWebhookError):
    code = "WEBHOOK_SIGNATURE_INVALID"

    def __init__(self) -> None:
        super().__init__("Missing or invalid webhook signature.")


class WebhookTimestampExpiredError(OemWebhookError):
    code = "WEBHOOK_TIMESTAMP_EXPIRED"

    def __init__(self) -> None:
        super().__init__("Webhook timestamp is missing or outside the allowed window.")


class InvalidWebhookRequestError(OemWebhookError):
    code = "INVALID_REQUEST"

    def __init__(self, message: str = "Invalid webhook payload.") -> None:
        super().__init__(message)


class UnsupportedEventTypeError(OemWebhookError):
    code = "UNSUPPORTED_EVENT_TYPE"

    def __init__(self, event_type: str) -> None:
        super().__init__(f"Unsupported event type: {event_type}.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "WEBHOOK_SIGNATURE_INVALID": 401,
    "WEBHOOK_TIMESTAMP_EXPIRED": 401,
    "UNSUPPORTED_EVENT_TYPE": 422,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
