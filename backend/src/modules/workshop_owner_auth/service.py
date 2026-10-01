"""Workshop-owner auth — application service (FEAT-AUTH-004).

Owns:
    - API-301 logout: ``last_logout_at`` + audit + durable revoke hand-off.
    - API-302 session check: account state for a token already verified with
      ``check_revoked=True``.
    - Audit writes (ENT-301) for sign-in (called by the onboarding module
      through its ``SignInAuditor`` port) and for the revoke worker.

Firebase is never called here: token verification happens in the route
dependency and ``revoke_refresh_tokens`` in the Celery worker.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import UserStatus
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.modules.workshop_owner_onboarding.domain import compute_expires_at, compute_next_step

from . import errors, schemas
from .domain import AuthEventResult, AuthEventType, RequestContext, WorkshopAuthEvent
from .ports import RevokeEnqueueError, WorkshopSessionRevoker

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class WorkshopAuthService:
    def __init__(
        self,
        session: Session,
        revoker: WorkshopSessionRevoker | None = None,
        *,
        onboarding_retention_days: int = 15,
        event_retention_days: int = 60,
    ) -> None:
        self._db = session
        self._revoker = revoker
        self._onboarding_retention_days = onboarding_retention_days
        self._event_retention_days = event_retention_days

    def find_owner_by_firebase_uid(self, uid: str | None) -> WorkshopOwner | None:
        if not uid:
            return None
        return self._db.exec(select(WorkshopOwner).where(WorkshopOwner.firebase_uid == uid)).first()

    # ==================================================================
    # Sign-in audit (SignInAuditor port of workshop_owner_onboarding)
    # The caller owns the transaction: these only add rows to the session.
    # ==================================================================
    def record_login(self, owner_id: UUID, context: RequestContext) -> None:
        self._add_event(owner_id, AuthEventType.LOGIN, AuthEventResult.SUCCESS, context)

    def record_login_denied(self, owner_id: UUID, reason: str, context: RequestContext) -> None:
        self._add_event(
            owner_id, AuthEventType.LOGIN_DENIED, AuthEventResult.DENIED, context, reason=reason
        )

    # ==================================================================
    # API-301 — logout
    # ==================================================================
    def logout(self, claims: dict, context: RequestContext) -> None:
        """Record the logout and hand the revoke off to the worker.

        A locked account may still log out (BR-304). Without a workshop_owner
        row we still revoke the verified uid but write nothing (EDGE-304).
        Raises ``AuthProviderUnavailableError`` if the revoke cannot be enqueued.
        """
        if self._revoker is None:
            raise RuntimeError("WorkshopAuthService.logout requires a revoker")
        uid = claims.get("uid")
        owner = self.find_owner_by_firebase_uid(uid)
        try:
            if owner is not None:
                owner.last_logout_at = _now()
                self._db.add(owner)
                self._add_event(owner.id, AuthEventType.LOGOUT, AuthEventResult.SUCCESS, context)
            # Commit only once the revoke task is durably accepted.
            self._revoker.enqueue_revoke(
                uid=uid, owner_id=owner.id if owner else None, trace_id=context.trace_id
            )
            self._db.commit()
        except RevokeEnqueueError as exc:
            self._db.rollback()
            raise errors.AuthProviderUnavailableError() from exc
        except Exception as exc:  # noqa: BLE001 — record/enqueue failure → 503
            self._db.rollback()
            logger.exception("workshop logout failed uid=%s", uid)
            raise errors.AuthProviderUnavailableError() from exc
        logger.info("workshop logout accepted uid=%s owner=%s", uid, getattr(owner, "id", None))

    # ==================================================================
    # API-302 — session check
    # ==================================================================
    def session(self, claims: dict) -> schemas.SessionData:
        owner = self.find_owner_by_firebase_uid(claims.get("uid"))
        if owner is None:
            raise errors.WorkshopAuthError(
                "Tài khoản chủ xưởng chưa được khởi tạo. Vui lòng đăng nhập lại.",
                code="WORKSHOP_OWNER_NOT_REGISTERED",
            )
        if owner.status != UserStatus.ACTIVE:
            raise errors.WorkshopAuthError(
                "Tài khoản của bạn đang bị khoá. Vui lòng liên hệ hỗ trợ.",
                code="ACCOUNT_SUSPENDED" if owner.status == UserStatus.SUSPENDED else "ACCOUNT_INACTIVE",
            )
        profile_completed = owner.profile_completed_at is not None
        return schemas.SessionData(
            owner_id=owner.id,
            email=owner.email,
            account_status=owner.status.name,
            onboarding=schemas.OnboardingStateOut(
                status=owner.onboarding_status.name,
                next_step=compute_next_step(owner.onboarding_status, profile_completed).value,
                profile_completed=profile_completed,
                profile_completed_at=owner.profile_completed_at,
                completed_at=owner.onboarding_completed_at,
                expires_at=compute_expires_at(
                    _aware(owner.created_at), owner.onboarding_status, self._onboarding_retention_days
                ),
            ),
            last_login_at=owner.last_login_at,
            last_logout_at=owner.last_logout_at,
        )

    # ==================================================================
    # Worker callbacks / jobs
    # ==================================================================
    def record_revoke_result(
        self,
        *,
        owner_id: UUID | None,
        success: bool,
        reason: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        if owner_id is None or self._db.get(WorkshopOwner, owner_id) is None:
            logger.info("revoke result without workshop owner; audit skipped (success=%s)", success)
            return
        self._add_event(
            owner_id,
            AuthEventType.SESSION_REVOKED if success else AuthEventType.SESSION_REVOKE_FAILED,
            AuthEventResult.SUCCESS if success else AuthEventResult.FAILED,
            RequestContext(trace_id=trace_id),
            reason=reason,
        )
        self._db.commit()

    def purge_events(self) -> int:
        """Delete audit rows older than the retention period (BR-ENT-305)."""
        cutoff = _now() - timedelta(days=self._event_retention_days)
        old = [
            e for e in self._db.exec(select(WorkshopAuthEvent)).all() if _aware(e.created_at) < cutoff
        ]
        for event in old:
            self._db.delete(event)
        self._db.commit()
        return len(old)

    # ==================================================================
    # Helpers
    # ==================================================================
    def _add_event(
        self,
        owner_id: UUID,
        event_type: AuthEventType,
        result: AuthEventResult,
        context: RequestContext,
        *,
        reason: str | None = None,
    ) -> None:
        ctx = context.clipped()
        self._db.add(
            WorkshopAuthEvent(
                owner_id=owner_id,
                event_type=event_type,
                result=result,
                reason=reason[:64] if reason else None,
                auth_provider=ctx.auth_provider,
                ip_address=ctx.ip_address,
                user_agent=ctx.user_agent,
                trace_id=ctx.trace_id,
                created_at=_now(),
            )
        )
