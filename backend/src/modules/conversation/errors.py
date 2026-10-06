"""Conversation module — domain errors (US-025).

Mapped to the shared error envelope by the handler in ``main.py``.
"""

from __future__ import annotations


class ConversationError(Exception):
    code: str = "CONVERSATION_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class ConversationNotFound(ConversationError):
    """Missing conversation or one owned by someone else (AC-605: never reveal which)."""

    code = "CONVERSATION_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Conversation was not found.")


class VehicleNotActive(ConversationError):
    code = "VEHICLE_NOT_ACTIVE"

    def __init__(self) -> None:
        super().__init__("The vehicle is not verified or no longer linked to this account.")


class VehicleNotFound(ConversationError):
    code = "VEHICLE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Vehicle was not found.")


class InvalidRequest(ConversationError):
    code = "INVALID_REQUEST"


class Unauthorized(ConversationError):
    code = "UNAUTHORIZED"

    def __init__(self, message: str = "Sign in to use the assistant.") -> None:
        super().__init__(message)


class Forbidden(ConversationError):
    code = "FORBIDDEN"

    def __init__(self, message: str = "You do not have permission for this action.") -> None:
        super().__init__(message)


class AuthProviderUnavailable(ConversationError):
    """Firebase could not be reached to check the token; the session may still be valid."""

    code = "AUTH_PROVIDER_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Could not verify the session right now. Please retry.")


class ConversationBusy(ConversationError):
    code = "CONVERSATION_BUSY"

    def __init__(self) -> None:
        super().__init__("A previous turn is still being processed. Please wait.")


class RateLimited(ConversationError):
    code = "RATE_LIMITED"

    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many messages. Please slow down.")
        self.retry_after = retry_after


class ExcerptNotAvailable(ConversationError):
    code = "CONVERSATION_EXCERPT_NOT_AVAILABLE"

    def __init__(self) -> None:
        super().__init__("No conversation excerpt is available for this record.")


class SemanticSearchDisabled(ConversationError):
    code = "SEMANTIC_SEARCH_DISABLED"

    def __init__(self) -> None:
        super().__init__("Semantic search over messages is disabled.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "CONVERSATION_NOT_FOUND": 404,
    "VEHICLE_NOT_FOUND": 404,
    "CONVERSATION_EXCERPT_NOT_AVAILABLE": 404,
    "SEMANTIC_SEARCH_DISABLED": 404,
    "VEHICLE_NOT_ACTIVE": 409,
    "CONVERSATION_BUSY": 409,
    "RATE_LIMITED": 429,
    "AUTH_PROVIDER_UNAVAILABLE": 503,
    "CHAT_TIMEOUT": 504,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
