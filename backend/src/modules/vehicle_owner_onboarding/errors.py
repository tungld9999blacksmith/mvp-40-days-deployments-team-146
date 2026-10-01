"""Onboarding module — domain / application exceptions.

The service raises these instead of returning HTTP responses; the route layer
(and a global handler) maps each to an error code + HTTP status. Never import
FastAPI here.

Hierarchy:
    OnboardingError
      ├─ AccountLockedError          -> 403 (ACCOUNT_SUSPENDED / ACCOUNT_INACTIVE)
      ├─ EmailAlreadyLinkedError     -> 409
      ├─ UserNotRegisteredError      -> 404
      ├─ PhoneAlreadyInUseError      -> 409
      ├─ ConsentRequiredError        -> 400
      ├─ InvalidProfileError         -> 400
      ├─ OnboardingStateError        -> 409  (already completed / profile incomplete / in progress)
      ├─ VehicleAlreadyLinkedError   -> 409
      ├─ VerificationAttemptsExceededError -> 429
      ├─ IdempotencyKeyReuseError    -> 422
      └─ OemUnavailableError         -> 503
"""

from __future__ import annotations


class OnboardingError(Exception):
    """Base class for onboarding errors. Carries a machine-readable code."""

    code: str = "ONBOARDING_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class AccountLockedError(OnboardingError):
    """Account status is inactive or suspended (EDGE-004)."""

    def __init__(self, *, suspended: bool) -> None:
        code = "ACCOUNT_SUSPENDED" if suspended else "ACCOUNT_INACTIVE"
        super().__init__("The account is not allowed to sign in.", code=code)


class EmailAlreadyLinkedError(OnboardingError):
    code = "EMAIL_ALREADY_LINKED"

    def __init__(self) -> None:
        super().__init__("This email is already linked to another account.")


class UserNotRegisteredError(OnboardingError):
    code = "USER_NOT_REGISTERED"

    def __init__(self) -> None:
        super().__init__("Account has not been initialized. Please sign in first.")


class PhoneAlreadyInUseError(OnboardingError):
    code = "PHONE_ALREADY_IN_USE"

    def __init__(self) -> None:
        super().__init__("This phone number is already used by another account.")


class ConsentRequiredError(OnboardingError):
    code = "CONSENT_REQUIRED"

    def __init__(self, message: str = "Required consent was not granted.") -> None:
        super().__init__(message)


class InvalidProfileError(OnboardingError):
    code = "INVALID_FIELD_FORMAT"

    def __init__(self, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class OnboardingStateError(OnboardingError):
    """Wrong onboarding state for the requested operation."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message, code=code)


class VehicleAlreadyLinkedError(OnboardingError):
    code = "VEHICLE_ALREADY_LINKED"

    def __init__(self) -> None:
        super().__init__("This vehicle is already registered by another account.")


class VerificationAttemptsExceededError(OnboardingError):
    code = "VERIFICATION_ATTEMPTS_EXCEEDED"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Too many failed verification attempts. Try again later.")
        self.retry_after_seconds = retry_after_seconds


class IdempotencyKeyReuseError(OnboardingError):
    code = "IDEMPOTENCY_KEY_REUSED"

    def __init__(self) -> None:
        super().__init__("The idempotency key was reused with a different payload.")


class OemUnavailableError(OnboardingError):
    code = "OEM_UNAVAILABLE"

    def __init__(self) -> None:
        super().__init__("The manufacturer system is temporarily unavailable.")


# Maps a machine-readable error code to its HTTP status. Codes not listed here
# fall back to 400 (see the exception handler).
ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "INVALID_FIELD_FORMAT": 400,
    "CONSENT_REQUIRED": 400,
    "EMAIL_NOT_VERIFIED": 403,
    "UNSUPPORTED_SIGN_IN_PROVIDER": 403,
    "ACCOUNT_SUSPENDED": 403,
    "ACCOUNT_INACTIVE": 403,
    "ONBOARDING_REQUIRED": 403,
    "USER_NOT_REGISTERED": 404,
    "EMAIL_ALREADY_LINKED": 409,
    "PHONE_ALREADY_IN_USE": 409,
    "NATIONAL_ID_ALREADY_IN_USE": 409,
    "ONBOARDING_ALREADY_COMPLETED": 409,
    "PROFILE_INCOMPLETE": 409,
    "VERIFICATION_IN_PROGRESS": 409,
    "VEHICLE_ALREADY_LINKED": 409,
    "IDEMPOTENCY_KEY_REUSED": 422,
    "VERIFICATION_ATTEMPTS_EXCEEDED": 429,
    "OEM_UNAVAILABLE": 503,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
