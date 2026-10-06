"""Booking module — domain errors (FEAT-BOOK-001, F6).

Mapped to the shared error envelope by the handler in ``main.py``.
Codes and HTTP statuses follow ``docs/specs/sprint-3/api/us-029-sprint-3-spec.api.md`` §8.
"""

from __future__ import annotations


class BookingError(Exception):
    code: str = "BOOKING_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


class UserNotRegisteredError(BookingError):
    code = "USER_NOT_REGISTERED"

    def __init__(self) -> None:
        super().__init__("Account has not been initialized. Please sign in first.")


class ForbiddenError(BookingError):
    code = "FORBIDDEN"

    def __init__(self, message: str = "You do not have permission for this action.") -> None:
        super().__init__(message)


class OnboardingRequiredError(BookingError):
    code = "ONBOARDING_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Onboarding must be completed before booking.")


class VehicleNotFoundError(BookingError):
    """Missing vehicle or a vehicle of another account (AC-009: never reveal which)."""

    code = "VEHICLE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Vehicle was not found.")


class VehicleNotActiveError(BookingError):
    code = "VEHICLE_NOT_ACTIVE"

    def __init__(self) -> None:
        super().__init__("The vehicle is not verified or no longer linked to this account.")


class WorkshopNotFoundError(BookingError):
    code = "WORKSHOP_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Workshop was not found or is not active.")


class BookingNotFoundError(BookingError):
    code = "BOOKING_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Booking was not found.")


class LocationAnchorRequiredError(BookingError):
    """Neither a specified location, a profile location nor a preferred workshop (EF-004)."""

    code = "LOCATION_ANCHOR_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Please provide a location or choose a workshop to search near.")


class SlotOutOfHoursError(BookingError):
    code = "SLOT_OUT_OF_HOURS"

    def __init__(self, message: str = "The time slot is outside the workshop operating hours.") -> None:
        super().__init__(message)


class SlotFullError(BookingError):
    """The requested slot is full — comes with alternatives (BR-001, BR-008)."""

    code = "SLOT_FULL"

    def __init__(self, alternatives: list | None = None) -> None:
        super().__init__("The selected time slot is no longer available.")
        self.alternatives = alternatives or []


class OpenBookingExistsError(BookingError):
    code = "OPEN_BOOKING_EXISTS"

    def __init__(self) -> None:
        super().__init__("This vehicle already has an open booking (BR-013).")


class InvalidConfirmationTokenError(BookingError):
    code = "INVALID_CONFIRMATION_TOKEN"

    def __init__(self) -> None:
        super().__init__("The confirmation token is invalid or has already been used.")


class IdempotencyConflictError(BookingError):
    code = "IDEMPOTENCY_CONFLICT"

    def __init__(self) -> None:
        super().__init__("This request key or confirmation token was already used for a different booking request.")


class HoldExpiredError(BookingError):
    code = "HOLD_EXPIRED"

    def __init__(self) -> None:
        super().__init__("The summary card has expired. Please review the slot again.")


class HoldWindowClosedError(BookingError):
    code = "HOLD_WINDOW_CLOSED"

    def __init__(self) -> None:
        super().__init__("The hold can no longer be cancelled here; it is awaiting the workshop.")


class ServiceUnavailableError(BookingError):
    code = "SERVICE_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("Booking is temporarily unavailable. Please try again.")


class BookingNotConfirmedError(BookingError):
    code = "BOOKING_NOT_CONFIRMED"

    def __init__(self, current_status: str) -> None:
        super().__init__("The booking is not confirmed.", details={"currentStatus": current_status.upper()})


class AppointmentStartedError(BookingError):
    code = "APPOINTMENT_STARTED"

    def __init__(self) -> None:
        super().__init__("The appointment time has passed. Please contact the workshop.")


class QrNotAvailableError(BookingError):
    code = "QR_NOT_AVAILABLE"

    def __init__(self) -> None:
        super().__init__("The QR code is only available for a confirmed booking.")


class RescheduleNotAllowedError(BookingError):
    code = "RESCHEDULE_NOT_ALLOWED"

    def __init__(self, reason: str) -> None:
        super().__init__("This booking can no longer be rescheduled.", details={"reason": reason})


class RescheduleWorkshopMismatchError(BookingError):
    code = "RESCHEDULE_WORKSHOP_MISMATCH"

    def __init__(self) -> None:
        super().__init__("A booking can only be moved within the same workshop.")


class RescheduleSameSlotError(BookingError):
    code = "RESCHEDULE_SAME_SLOT"

    def __init__(self) -> None:
        super().__init__("The new slot is the same as the current one.")


class RescheduleTooLateError(BookingError):
    code = "RESCHEDULE_TOO_LATE"

    def __init__(self) -> None:
        super().__init__("It is too close to the appointment to reschedule.")


class RescheduleLimitReachedError(BookingError):
    code = "RESCHEDULE_LIMIT_REACHED"

    def __init__(self) -> None:
        super().__init__("This booking has reached the maximum number of reschedules.")


class BookingChangedError(BookingError):
    code = "BOOKING_CHANGED"

    def __init__(self) -> None:
        super().__init__("The booking was changed elsewhere. Please review it again.")


class ConfirmationTokenExpiredError(BookingError):
    code = "CONFIRMATION_TOKEN_EXPIRED"

    def __init__(self) -> None:
        super().__init__("The summary card has expired. Please review the slot again.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "ONBOARDING_REQUIRED": 403,
    "USER_NOT_REGISTERED": 404,
    "VEHICLE_NOT_FOUND": 404,
    "WORKSHOP_NOT_FOUND": 404,
    "BOOKING_NOT_FOUND": 404,
    "VEHICLE_NOT_ACTIVE": 409,
    "SLOT_FULL": 409,
    "OPEN_BOOKING_EXISTS": 409,
    "HOLD_EXPIRED": 409,
    "HOLD_WINDOW_CLOSED": 409,
    "INVALID_CONFIRMATION_TOKEN": 409,
    "IDEMPOTENCY_CONFLICT": 409,
    "BOOKING_NOT_CONFIRMED": 409,
    "APPOINTMENT_STARTED": 409,
    "QR_NOT_AVAILABLE": 409,
    "RESCHEDULE_NOT_ALLOWED": 409,
    "RESCHEDULE_TOO_LATE": 409,
    "RESCHEDULE_LIMIT_REACHED": 409,
    "BOOKING_CHANGED": 409,
    "CONFIRMATION_TOKEN_EXPIRED": 409,
    "RESCHEDULE_WORKSHOP_MISMATCH": 422,
    "RESCHEDULE_SAME_SLOT": 422,
    "FEATURE_DISABLED": 404,
    "LOCATION_ANCHOR_REQUIRED": 422,
    "SLOT_OUT_OF_HOURS": 422,
    "SERVICE_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
