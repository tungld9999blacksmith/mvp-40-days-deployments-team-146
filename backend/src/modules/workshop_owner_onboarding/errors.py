"""Workshop-owner onboarding — domain / application exceptions (FEAT-AUTH-003).

The service raises these; the app-level handler in ``main.py`` maps each code
to an HTTP status via ``status_for`` and renders the shared error envelope.
Never import FastAPI here.
"""

from __future__ import annotations

from uuid import UUID


class WorkshopOnboardingError(Exception):
    """Base class. Carries a machine-readable code and a user-facing message."""

    code: str = "WORKSHOP_ONBOARDING_ERROR"

    def __init__(self, message: str, *, code: str | None = None, field: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        if code is not None:
            self.code = code

    def details(self) -> dict | None:
        return {"field": self.field} if self.field else None


class InvalidFieldError(WorkshopOnboardingError):
    code = "INVALID_FIELD_FORMAT"

    def __init__(self, message: str, *, field: str) -> None:
        super().__init__(message, field=field)


class ConsentRequiredError(WorkshopOnboardingError):
    code = "CONSENT_REQUIRED"


class AccountLockedError(WorkshopOnboardingError):
    """``workshop_owner.status`` is inactive or suspended (EF-205)."""

    def __init__(self, *, suspended: bool) -> None:
        super().__init__(
            "Tài khoản của bạn đang bị khoá. Vui lòng liên hệ hỗ trợ.",
            code="ACCOUNT_SUSPENDED" if suspended else "ACCOUNT_INACTIVE",
        )


class WorkshopOwnerNotRegisteredError(WorkshopOnboardingError):
    code = "WORKSHOP_OWNER_NOT_REGISTERED"

    def __init__(self) -> None:
        super().__init__("Tài khoản chủ xưởng chưa được khởi tạo. Vui lòng đăng nhập lại.")


class OnboardingStateError(WorkshopOnboardingError):
    """Wrong onboarding state for the requested operation (409 family)."""


class WorkshopAlreadyClaimedError(WorkshopOnboardingError):
    """The center returned by the manufacturer already has an active owner (EF-204).

    Raised *after* the failed attempt is persisted, so the client can still
    reference it.
    """

    code = "WORKSHOP_ALREADY_CLAIMED"

    def __init__(self, attempt_id: UUID) -> None:
        super().__init__("Xưởng này đang được quản lý bởi một tài khoản khác. Vui lòng liên hệ hãng.")
        self.attempt_id = attempt_id

    def details(self) -> dict | None:
        return {"attemptId": str(self.attempt_id)}


class VerificationAttemptsExceededError(WorkshopOnboardingError):
    code = "VERIFICATION_ATTEMPTS_EXCEEDED"

    def __init__(self, retry_after_seconds: int, max_attempts: int) -> None:
        super().__init__(f"Bạn đã xác thực thất bại quá {max_attempts} lần trong 24 giờ. Vui lòng thử lại sau.")
        self.retry_after_seconds = retry_after_seconds

    def details(self) -> dict | None:
        return {"retryAfterSeconds": self.retry_after_seconds}


class IdempotencyKeyReuseError(WorkshopOnboardingError):
    code = "IDEMPOTENCY_KEY_REUSED"

    def __init__(self) -> None:
        super().__init__("Idempotency-Key đã được dùng với nội dung khác.")


ERROR_STATUS: dict[str, int] = {
    "INVALID_REQUEST": 400,
    "INVALID_FIELD_FORMAT": 400,
    "CONSENT_REQUIRED": 400,
    "UNSUPPORTED_SIGN_IN_PROVIDER": 403,
    "EMAIL_NOT_VERIFIED": 403,
    "ACCOUNT_SUSPENDED": 403,
    "ACCOUNT_INACTIVE": 403,
    "ONBOARDING_REQUIRED": 403,
    "WORKSHOP_OWNER_NOT_REGISTERED": 404,
    "EMAIL_ALREADY_LINKED": 409,
    "PHONE_ALREADY_IN_USE": 409,
    "NATIONAL_ID_ALREADY_IN_USE": 409,
    "ONBOARDING_ALREADY_COMPLETED": 409,
    "PROFILE_INCOMPLETE": 409,
    "VERIFICATION_IN_PROGRESS": 409,
    "WORKSHOP_ALREADY_CLAIMED": 409,
    "IDEMPOTENCY_KEY_REUSED": 422,
    "VERIFICATION_ATTEMPTS_EXCEEDED": 429,
}


def status_for(code: str) -> int:
    return ERROR_STATUS.get(code, 400)
