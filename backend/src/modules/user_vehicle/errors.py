"""User-vehicle module — domain errors (API-VEH-001..003).

Mapped to the shared error envelope by the handler in ``main.py``.
"""

from __future__ import annotations


class UserVehicleError(Exception):
    code: str = "USER_VEHICLE_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class UserNotRegisteredError(UserVehicleError):
    code = "USER_NOT_REGISTERED"

    def __init__(self) -> None:
        super().__init__("Account has not been initialized. Please sign in first.")


class ForbiddenError(UserVehicleError):
    code = "FORBIDDEN"

    def __init__(self) -> None:
        super().__init__("This account is not allowed to access vehicle-owner resources.")


class AccountLockedError(UserVehicleError):
    def __init__(self, *, suspended: bool) -> None:
        super().__init__(
            "The account is not allowed to use this feature.",
            code="ACCOUNT_SUSPENDED" if suspended else "ACCOUNT_INACTIVE",
        )


class OnboardingRequiredError(UserVehicleError):
    code = "ONBOARDING_REQUIRED"

    def __init__(self) -> None:
        super().__init__("Onboarding must be completed before using this feature.")


class VehicleNotFoundError(UserVehicleError):
    """Missing vehicle or a vehicle of another account (AC-008: never reveal which)."""

    code = "VEHICLE_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("Vehicle was not found.")


class VehicleNotActiveError(UserVehicleError):
    code = "VEHICLE_NOT_ACTIVE"

    def __init__(self) -> None:
        super().__init__("The vehicle is not verified or no longer linked to this account.")


ERROR_STATUS: dict[str, int] = {
    "FORBIDDEN": 403,
    "ACCOUNT_SUSPENDED": 403,
    "ACCOUNT_INACTIVE": 403,
    "ONBOARDING_REQUIRED": 403,
    "USER_NOT_REGISTERED": 404,
    "VEHICLE_NOT_FOUND": 404,
    "VEHICLE_NOT_ACTIVE": 409,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
