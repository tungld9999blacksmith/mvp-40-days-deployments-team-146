"""Workshop price list — domain errors."""

from __future__ import annotations


class PricingError(Exception):
    code: str = "PRICING_ERROR"

    def __init__(self, message: str, *, code: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


class InvalidRequestError(PricingError):
    code = "INVALID_REQUEST"


class ModelNotFoundError(PricingError):
    code = "MODEL_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("This model has no maintenance schedule.")


class PriceNotFoundError(PricingError):
    code = "PRICE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("The price was not found.")


class PeriodOverlapError(PricingError):
    """BR-ENT-412 — two prices of one item may not be valid on the same day."""

    code = "PRICE_PERIOD_OVERLAP"

    def __init__(self, item_code: str, existing: dict) -> None:
        super().__init__(
            "Another price of this item is valid in the same period.",
            details={"itemCode": item_code, "existing": existing},
        )


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "MODEL_NOT_FOUND": 404,
    "PRICE_NOT_FOUND": 404,
    "PRICE_PERIOD_OVERLAP": 409,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
