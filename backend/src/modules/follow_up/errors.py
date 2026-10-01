"""Follow-up & support tickets — domain errors (us-041 §11)."""

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


class SupportTicketNotFoundError(FollowUpError):
    code = "SUPPORT_TICKET_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Support ticket was not found.")


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


class ResolutionNoteRequiredError(FollowUpError):
    code = "RESOLUTION_NOTE_REQUIRED"

    def __init__(self) -> None:
        super().__init__("A resolution note is required to resolve the ticket.")


class InvalidStatusTransitionError(FollowUpError):
    code = "INVALID_STATUS_TRANSITION"

    def __init__(self, current: str, allowed: list[str]) -> None:
        super().__init__(
            "The ticket cannot move to that status.",
            details={"currentStatus": current.upper(), "allowedActions": allowed},
        )


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "RESOLUTION_NOTE_REQUIRED": 400,
    "FOLLOW_UP_NOT_FOUND": 404,
    "SUPPORT_TICKET_NOT_FOUND": 404,
    "FOLLOW_UP_NOT_OPEN": 409,
    "FOLLOW_UP_ALREADY_RESPONDED": 409,
    "FOLLOW_UP_CLOSED": 409,
    "INVALID_STATUS_TRANSITION": 409,
    "SERVICE_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
