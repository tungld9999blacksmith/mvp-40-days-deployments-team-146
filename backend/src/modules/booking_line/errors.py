"""Two-tier booking pricing — domain errors (docs/designs/bao-gia-hai-tang.md).

Mapped to the shared error envelope by the handler in ``main.py``. The three
``BOOKING_LINES_*`` / ``ACTUAL_COST_MISMATCH`` errors are raised by the booking
state machine, so the Workshop Board surfaces them unchanged.
"""

from __future__ import annotations


class BookingLineError(Exception):
    code: str = "BOOKING_LINE_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


class InvalidRequestError(BookingLineError):
    code = "INVALID_REQUEST"


class BookingNotFoundError(BookingLineError):
    code = "BOOKING_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Booking was not found.")


class LineNotFoundError(BookingLineError):
    code = "LINE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("The price line was not found.")


class NotTwoTierError(BookingLineError):
    code = "NOT_TWO_TIER"

    def __init__(self) -> None:
        super().__init__("This booking does not use two-tier pricing.")


class BookingStatusInvalidError(BookingLineError):
    code = "BOOKING_STATUS_INVALID"

    def __init__(self, current: str) -> None:
        super().__init__(
            "The booking is not in a status that allows this action.", details={"currentStatus": current.upper()}
        )


class StageNotAllowedError(BookingLineError):
    code = "STAGE_NOT_ALLOWED"

    def __init__(self, current: str | None) -> None:
        super().__init__(
            "Extra items can only be proposed while inspecting, servicing or waiting for parts.",
            details={"currentStage": current.upper() if current else None},
        )


class ReasonRequiredError(BookingLineError):
    code = "REASON_REQUIRED"

    def __init__(self, message: str = "A reason of 10-500 characters is required.") -> None:
        super().__init__(message)


class LineChangedError(BookingLineError):
    """The line moved on since the caller saw it (edited, withdrawn or already decided)."""

    code = "LINE_CHANGED"

    def __init__(self, line: dict) -> None:
        super().__init__("This item changed since you last saw it. Please review it again.", details={"line": line})


class SafetyConfirmationRequiredError(BookingLineError):
    code = "SAFETY_CONFIRMATION_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Declining a safety item needs one more confirmation.")


class PhotoInvalidError(BookingLineError):
    code = "PHOTO_INVALID"

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message, details={"reason": reason})


class LinesUnconfirmedError(BookingLineError):
    """D8 — START while a package line still waits for its reference price to be confirmed."""

    code = "BOOKING_LINES_UNCONFIRMED"

    def __init__(self, count: int) -> None:
        super().__init__(f"Còn {count} dòng chưa xác nhận giá.", details={"count": count})


class LinesUnsettledError(BookingLineError):
    """D6 — COMPLETE while a line still waits for the workshop or the owner."""

    code = "BOOKING_LINES_UNSETTLED"

    def __init__(self, count: int) -> None:
        super().__init__(f"Còn {count} hạng mục chưa chốt giá.", details={"count": count})


class ActualCostMismatchError(BookingLineError):
    code = "ACTUAL_COST_MISMATCH"

    def __init__(self, expected: str) -> None:
        super().__init__(
            "The total is computed from the approved lines and cannot be changed.", details={"actualCost": expected}
        )


class ServiceUnavailableError(BookingLineError):
    code = "SERVICE_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("The service is temporarily unavailable. Please try again.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "BOOKING_NOT_FOUND": 404,
    "LINE_NOT_FOUND": 404,
    "NOT_TWO_TIER": 409,
    "BOOKING_STATUS_INVALID": 409,
    "STAGE_NOT_ALLOWED": 409,
    "LINE_CHANGED": 409,
    "BOOKING_LINES_UNCONFIRMED": 409,
    "BOOKING_LINES_UNSETTLED": 409,
    "ACTUAL_COST_MISMATCH": 409,
    "REASON_REQUIRED": 422,
    "SAFETY_CONFIRMATION_REQUIRED": 422,
    "PHOTO_INVALID": 422,
    "SERVICE_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
