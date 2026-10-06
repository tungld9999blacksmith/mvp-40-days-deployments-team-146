"""Post-service follow-up — domain errors (us-041 §11)."""

from __future__ import annotations


class FollowUpError(Exception):
    code: str = "FOLLOW_UP_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class InvalidRequestError(FollowUpError):
    code = "INVALID_REQUEST"


class FollowUpNotFoundError(FollowUpError):
    code = "FOLLOW_UP_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Follow-up was not found.")


class FollowUpNotOpenError(FollowUpError):
    code = "FOLLOW_UP_NOT_OPEN"

    def __init__(self) -> None:
        super().__init__("This follow-up is not open for answers yet.")


class FollowUpAlreadyRespondedError(FollowUpError):
    code = "FOLLOW_UP_ALREADY_RESPONDED"

    def __init__(self) -> None:
        super().__init__("You have already answered this follow-up.")


class FollowUpClosedError(FollowUpError):
    code = "FOLLOW_UP_CLOSED"

    def __init__(self, hotline: str | None) -> None:
        super().__init__("This follow-up is closed.", details={"workshopHotline": hotline})


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "FOLLOW_UP_NOT_FOUND": 404,
    "FOLLOW_UP_NOT_OPEN": 409,
    "FOLLOW_UP_ALREADY_RESPONDED": 409,
    "FOLLOW_UP_CLOSED": 409,
    "SERVICE_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
