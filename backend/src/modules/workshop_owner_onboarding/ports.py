"""Workshop-owner onboarding — ports (abstractions the service depends on).

Concrete implementations:
    - ``OemServiceCenterGateway`` → ``infrastructure/oem/gateway.py``
    - ``VerificationRetryScheduler`` → ``scheduler.py`` (Celery)
    - ``SignInAuditor`` → ``workshop_owner_auth.service.WorkshopAuthService``
Both are wired in ``dependency.py`` and replaced by stubs in tests.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol
from uuid import UUID

from ev_contracts import ManagerVerifyRequest, ManagerVerifyResponse

from src.common.request_context import RequestContext


class OemTimeoutError(Exception):
    """The manufacturer did not answer (timeout / connection error / 5xx).

    Treated as "still pending" (EF-202) and retried in the background.
    """


class OemServiceCenterGateway(ABC):
    @abstractmethod
    async def verify_manager(self, request: ManagerVerifyRequest) -> ManagerVerifyResponse:
        """Verify (email, national id) and return the service center it manages.

        Raises:
            OemTimeoutError: transport timeout / connection error / 5xx.
        """


class VerificationRetryScheduler(ABC):
    @abstractmethod
    def schedule(self, attempt_id: UUID, *, delay_seconds: int) -> None:
        """Run ``WorkshopOnboardingService.retry_verification(attempt_id)`` later.

        Implementations must not raise for a transient broker failure; the
        reconciler job re-enqueues attempts whose ``next_retry_at`` has passed.
        """


class SignInAuditor(Protocol):
    """Writes sign-in audit events (FEAT-AUTH-004, ENT-301).

    Implemented by ``workshop_owner_auth``. Methods only add rows to the
    shared DB session; the onboarding service owns the commit, so the audit
    row lands in the same transaction as ``last_login_at`` (BR-ENT-303).
    """

    def record_login(self, owner_id: UUID, context: RequestContext) -> None: ...

    def record_login_denied(self, owner_id: UUID, reason: str, context: RequestContext) -> None: ...


class NullSignInAuditor:
    """No-op auditor (default when no audit sink is wired)."""

    def record_login(self, owner_id: UUID, context: RequestContext) -> None:
        return None

    def record_login_denied(self, owner_id: UUID, reason: str, context: RequestContext) -> None:
        return None
