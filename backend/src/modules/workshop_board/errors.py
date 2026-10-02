"""Workshop Board — domain errors (us-037 §10)."""

from __future__ import annotations


class BoardError(Exception):
    code: str = "BOARD_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


class InvalidRequestError(BoardError):
    code = "INVALID_REQUEST"


class ReasonRequiredError(BoardError):
    code = "REASON_REQUIRED"

    def __init__(self, message: str = "A reason is required for this action.") -> None:
        super().__init__(message)


class OnboardingRequiredError(BoardError):
    code = "ONBOARDING_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Please finish onboarding and link a workshop first.")


class WorkshopInactiveError(BoardError):
    code = "WORKSHOP_INACTIVE"

    def __init__(self) -> None:
        super().__init__("The workshop is not active; changes are not allowed.")


class BookingNotFoundError(BoardError):
    code = "BOOKING_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Booking was not found.")


class InvalidStatusTransitionError(BoardError):
    code = "INVALID_STATUS_TRANSITION"

    def __init__(self, current: str, allowed: list[str]) -> None:
        super().__init__(
            "The booking cannot move to that status.",
            details={"currentStatus": current.upper(), "allowedActions": allowed},
        )


class CheckInNotTodayError(BoardError):
    code = "CHECK_IN_NOT_TODAY"

    def __init__(self, booking_date: str) -> None:
        super().__init__("Check-in is only possible on the booking date.", details={"bookingDate": booking_date})


class ConfirmDeadlinePassedError(BoardError):
    code = "CONFIRM_DEADLINE_PASSED"

    def __init__(self) -> None:
        super().__init__("The confirmation deadline has passed.")


class NoShowTooEarlyError(BoardError):
    code = "NO_SHOW_TOO_EARLY"

    def __init__(self, allowed_from: str) -> None:
        super().__init__(
            "No-show can only be recorded after the grace period.",
            details={"allowedFrom": allowed_from},
        )


class BlockExceedsFreeCapacityError(BoardError):
    code = "BLOCK_EXCEEDS_FREE_CAPACITY"

    def __init__(self, max_block: int) -> None:
        super().__init__("Cannot block more slots than are free.", details={"maxBlock": max_block})


class BlockDateOutOfRangeError(BoardError):
    code = "BLOCK_DATE_OUT_OF_RANGE"

    def __init__(self) -> None:
        super().__init__("The date is outside the range that can be blocked.")


class SlotOutOfHoursError(BoardError):
    code = "SLOT_OUT_OF_HOURS"

    def __init__(self) -> None:
        super().__init__("The time slot is outside the workshop operating hours.")


class ServiceUnavailableError(BoardError):
    code = "SERVICE_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("The service is temporarily unavailable. Please try again.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "REASON_REQUIRED": 400,
    "ONBOARDING_REQUIRED": 403,
    "WORKSHOP_INACTIVE": 403,
    "BOOKING_NOT_FOUND": 404,
    "INVALID_STATUS_TRANSITION": 409,
    "CHECK_IN_NOT_TODAY": 409,
    "CONFIRM_DEADLINE_PASSED": 409,
    "NO_SHOW_TOO_EARLY": 409,
    "BLOCK_EXCEEDS_FREE_CAPACITY": 409,
    "BLOCK_DATE_OUT_OF_RANGE": 422,
    "SLOT_OUT_OF_HOURS": 422,
    "SERVICE_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
