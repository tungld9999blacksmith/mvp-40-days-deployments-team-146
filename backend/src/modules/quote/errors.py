"""Quote module — domain errors (us-049 §12)."""

from __future__ import annotations


class QuoteError(Exception):
    code: str = "QUOTE_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


class InvalidRequestError(QuoteError):
    code = "INVALID_REQUEST"


class QuoteNotFoundError(QuoteError):
    code = "QUOTE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Quote was not found.")


class WorkshopInactiveError(QuoteError):
    code = "WORKSHOP_INACTIVE"

    def __init__(self) -> None:
        super().__init__("The workshop is not active.")


class NoMaintenanceRuleError(QuoteError):
    code = "NO_MAINTENANCE_RULE"

    def __init__(self) -> None:
        super().__init__("There is no maintenance schedule for this vehicle model.")


class QuoteNotDraftError(QuoteError):
    code = "QUOTE_NOT_DRAFT"

    def __init__(self, status: str) -> None:
        super().__init__("The quote is no longer a draft.", details={"status": status.upper()})


class QuoteDraftRefreshedError(QuoteError):
    code = "QUOTE_DRAFT_REFRESHED"

    def __init__(self) -> None:
        super().__init__("Prices changed; the draft was refreshed. Please review and send again.")


class QuoteAlreadyPendingError(QuoteError):
    code = "QUOTE_ALREADY_PENDING"

    def __init__(self, pending_quote_id: str | None) -> None:
        super().__init__(
            "A quote for this milestone is already waiting for the workshop.",
            details={"pendingQuoteId": pending_quote_id},
        )


class QuoteAlreadyReviewedError(QuoteError):
    code = "QUOTE_ALREADY_REVIEWED"

    def __init__(self, status: str) -> None:
        super().__init__("The quote has already been reviewed.", details={"status": status.upper()})


class CoveredItemLockedError(QuoteError):
    code = "COVERED_ITEM_LOCKED"

    def __init__(self, quote_item_id: str) -> None:
        super().__init__(
            "A warranty-covered item must stay at 0.", details={"quoteItemId": quote_item_id}
        )


class ReviewerNoteRequiredError(QuoteError):
    code = "REVIEWER_NOTE_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Please give a reason of 10-500 characters.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "FORBIDDEN": 403,
    "QUOTE_NOT_FOUND": 404,
    "VEHICLE_NOT_FOUND": 404,
    "MILESTONE_NOT_FOUND": 422,
    "QUOTE_NOT_DRAFT": 409,
    "QUOTE_DRAFT_REFRESHED": 409,
    "QUOTE_ALREADY_PENDING": 409,
    "QUOTE_ALREADY_REVIEWED": 409,
    "WORKSHOP_INACTIVE": 422,
    "NO_MAINTENANCE_RULE": 422,
    "COVERED_ITEM_LOCKED": 422,
    "REVIEWER_NOTE_REQUIRED": 422,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
