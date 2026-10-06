"""Quick booking — domain errors (us-061 API §8).

Mapped by ``main.py`` through ``_domain_error_response`` so ``details`` (the new
proposal message on SLOT_FULL, the current status, …) reach the client.
"""

from __future__ import annotations


class QuickBookingError(Exception):
    code: str = "QUICK_BOOKING_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


class ProposalNotFoundError(QuickBookingError):
    """Missing, or belongs to another owner / conversation / vehicle (never reveal which)."""

    code = "PROPOSAL_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Booking proposal was not found.")


class ProposalInactiveError(QuickBookingError):
    code = "PROPOSAL_INACTIVE"

    def __init__(self, status: str) -> None:
        super().__init__("This booking proposal is no longer active.", details={"status": status.upper()})


class ProposalExpiredError(QuickBookingError):
    code = "PROPOSAL_EXPIRED"

    def __init__(self) -> None:
        super().__init__("This booking proposal has expired. Please create a new one.", details={"status": "EXPIRED"})


class ProposalInProgressError(QuickBookingError):
    code = "PROPOSAL_IN_PROGRESS"

    def __init__(self) -> None:
        super().__init__("This proposal is being confirmed. Please wait a moment.")


class ProposalAlreadyConfirmedError(QuickBookingError):
    code = "PROPOSAL_ALREADY_CONFIRMED"

    def __init__(self) -> None:
        super().__init__("This proposal was already booked. Cancel the booking from its ticket.")


class ProposalSlotFullError(QuickBookingError):
    """The slot was taken before the confirm (BR-1511); ``details.message`` carries the follow-up."""

    code = "PROPOSAL_SLOT_FULL"

    def __init__(self, *, proposal_id: str | None, message: dict) -> None:
        super().__init__(
            "The selected time slot is no longer available.",
            details={"proposalId": proposal_id, "message": message},
        )


class SlotTooSoonError(QuickBookingError):
    code = "SLOT_TOO_SOON"

    def __init__(self) -> None:
        super().__init__("The time slot starts too soon. Please choose a later one.")


class ReviseWorkshopNotOfferedError(QuickBookingError):
    code = "REVISE_WORKSHOP_NOT_OFFERED"

    def __init__(self) -> None:
        super().__init__("Choose one of the workshops offered on the card.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "PROPOSAL_NOT_FOUND": 404,
    "CONVERSATION_NOT_FOUND": 404,
    "VEHICLE_NOT_ACTIVE": 409,
    "CONVERSATION_BUSY": 409,
    "PROPOSAL_IN_PROGRESS": 409,
    "PROPOSAL_INACTIVE": 409,
    "PROPOSAL_EXPIRED": 409,
    "PROPOSAL_SLOT_FULL": 409,
    "PROPOSAL_ALREADY_CONFIRMED": 409,
    "OPEN_BOOKING_EXISTS": 409,
    "SLOT_FULL": 409,
    "SLOT_OUT_OF_HOURS": 422,
    "SLOT_TOO_SOON": 422,
    "REVISE_WORKSHOP_NOT_OFFERED": 422,
    "RATE_LIMITED": 429,
    "SERVICE_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
