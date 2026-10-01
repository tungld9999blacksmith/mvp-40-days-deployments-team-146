"""Auth module — application service (FEAT-AUTH-002).

Owns the logout use-case (API-101) and the audit writes for authentication
events (ENT-101). Firebase itself is never touched here: verifying the token is
done by the route dependency, and the actual ``revoke_refresh_tokens`` call is
performed by the background worker, which reports the outcome back through
``record_revoke_result``.

Rules:
    - Raise domain exceptions (errors.py); never return HTTP responses.
    - ``AuthEvent`` is append-only.
    - ``user_id`` is always derived from the verified token, never the client.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser

from . import errors
from .domain import AuthEvent, AuthEventResult, AuthEventType
from .ports import RevokeEnqueueError, SessionRevoker

logger = logging.getLogger(__name__)

_DEFAULT_PROVIDER = "google.com"


def _now() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def __init__(self, session: Session, revoker: SessionRevoker) -> None:
        self._db = session
        self._revoker = revoker

    # ==================================================================
    # Lookups
    # ==================================================================
    def find_user_by_firebase_uid(self, firebase_uid: str) -> VehicleUser | None:
        stmt = select(VehicleUser).where(VehicleUser.firebase_uid == firebase_uid)
        return self._db.exec(stmt).first()

    # ==================================================================
    # API-101 — logout
    # ==================================================================
    def logout(
        self,
        claims: dict,
        *,
        trace_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Record the logout, audit it and enqueue the background revoke task.

        A locked account may still log out (see spec §4). If the ``vehicle_user``
        row is missing we still enqueue a revoke for the verified uid and skip
        the profile/audit write that needs a ``user_id``.

        Raises ``AuthProviderUnavailableError`` (503) if the request cannot be
        durably recorded and enqueued; the client still clears its local session.
        """
        uid = claims.get("uid")
        provider = (claims.get("firebase") or {}).get("sign_in_provider") or _DEFAULT_PROVIDER

        user = self.find_user_by_firebase_uid(uid) if uid else None

        try:
            if user is not None:
                user.last_logout_at = _now()
                self._db.add(user)
                self._db.add(
                    AuthEvent(
                        user_id=user.user_id,
                        event_type=AuthEventType.LOGOUT,
                        result=AuthEventResult.SUCCESS,
                        auth_provider=provider,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        trace_id=trace_id,
                    )
                )
            # Enqueue durably, then commit together so we only answer 204 once
            # the task is accepted (see spec §6.3 outbox-equivalent).
            self._revoker.enqueue_revoke(
                uid=uid,
                user_id=user.user_id if user is not None else 0,
                trace_id=trace_id,
            )
            self._db.commit()
        except RevokeEnqueueError as exc:
            self._db.rollback()
            logger.warning("logout revoke enqueue failed uid=%s: %s", uid, exc)
            raise errors.AuthProviderUnavailableError() from exc
        except Exception as exc:  # noqa: BLE001 — record + enqueue failure → 503
            self._db.rollback()
            logger.exception("logout failed uid=%s", uid)
            raise errors.AuthProviderUnavailableError() from exc

        logger.info("logout accepted uid=%s user_id=%s", uid, getattr(user, "user_id", None))

    # ==================================================================
    # Background revoke outcome (called by the worker)
    # ==================================================================
    def record_revoke_result(
        self,
        *,
        user_id: int,
        success: bool,
        reason: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        """Append the outcome of the background ``revoke_refresh_tokens`` call.

        ``user_id == 0`` means the account row was absent at logout time; we
        skip the audit write since ``AuthEvent.user_id`` is a required FK.
        """
        if not user_id:
            logger.info("revoke result for unknown user_id; skipping audit (success=%s)", success)
            return
        self._db.add(
            AuthEvent(
                user_id=user_id,
                event_type=(
                    AuthEventType.SESSION_REVOKED
                    if success
                    else AuthEventType.SESSION_REVOKE_FAILED
                ),
                result=AuthEventResult.SUCCESS if success else AuthEventResult.FAILED,
                reason=reason,
                trace_id=trace_id,
            )
        )
        self._db.commit()

    # ==================================================================
    # Login audit helpers (reused by API-001 when wired in — AC-101/BR-103)
    # ==================================================================
    def record_login(
        self,
        *,
        user_id: int,
        trace_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        provider: str | None = None,
    ) -> None:
        self._db.add(
            AuthEvent(
                user_id=user_id,
                event_type=AuthEventType.LOGIN,
                result=AuthEventResult.SUCCESS,
                auth_provider=provider or _DEFAULT_PROVIDER,
                ip_address=ip_address,
                user_agent=user_agent,
                trace_id=trace_id,
            )
        )
        self._db.commit()

    def record_login_denied(
        self,
        *,
        user_id: int,
        reason: str,
        trace_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self._db.add(
            AuthEvent(
                user_id=user_id,
                event_type=AuthEventType.LOGIN_DENIED,
                result=AuthEventResult.DENIED,
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
                trace_id=trace_id,
            )
        )
        self._db.commit()
