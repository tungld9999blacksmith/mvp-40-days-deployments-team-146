"""Service progress — domain errors (us-057 §6)."""

from __future__ import annotations


class ProgressError(Exception):
    code: str = "PROGRESS_ERROR"

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class BookingNotFoundError(ProgressError):
    code = "BOOKING_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Booking was not found.")


class BookingNotInProgressError(ProgressError):
    code = "BOOKING_NOT_IN_PROGRESS"

    def __init__(self, status: str) -> None:
        super().__init__(
            "Progress can only be updated while the car is being serviced.",
            details={"bookingStatus": status.upper()},
        )


class ProgressChangedError(ProgressError):
    code = "PROGRESS_CHANGED"

    def __init__(self, current: str | None) -> None:
        super().__init__(
            "The progress was updated elsewhere. Please reload.",
            details={"currentStage": current.upper() if current else None},
        )


class InvalidStageTransitionError(ProgressError):
    code = "INVALID_STAGE_TRANSITION"

    def __init__(self, next_stages: list[str]) -> None:
        super().__init__(
            "This stage cannot follow the current one.",
            details={"nextStages": [s.upper() for s in next_stages]},
        )


class NoteRequiredError(ProgressError):
    code = "NOTE_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Waiting for parts needs a note of 10-500 characters.")


class FeatureDisabledError(ProgressError):
    code = "FEATURE_DISABLED"

    def __init__(self) -> None:
        super().__init__("Service progress is not enabled.")


ERROR_STATUS: dict[str, int] = {
    "BOOKING_NOT_FOUND": 404,
    "FEATURE_DISABLED": 404,
    "BOOKING_NOT_IN_PROGRESS": 409,
    "PROGRESS_CHANGED": 409,
    "INVALID_STAGE_TRANSITION": 422,
    "NOTE_REQUIRED": 422,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
