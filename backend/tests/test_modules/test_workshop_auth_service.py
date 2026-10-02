"""Service-level tests for workshop-owner auth (FEAT-AUTH-004).

Sign-in audit (through the onboarding service's ``SignInAuditor`` port),
logout, session check, revoke-result audit and retention purge.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlmodel import select

from src.common.core.identity.vehicle_user import UserStatus
from src.common.core.identity.workshop_owner import WorkshopOwner
from src.common.request_context import RequestContext
from src.modules.workshop_owner_auth import errors
from src.modules.workshop_owner_auth.domain import (
    AuthEventResult,
    AuthEventType,
    WorkshopAuthEvent,
)
from src.modules.workshop_owner_auth.ports import RevokeEnqueueError
from src.modules.workshop_owner_auth.service import WorkshopAuthService
from src.modules.workshop_owner_onboarding import errors as onboarding_errors
from tests._workshop_onboarding import claims, make_service, make_session

CTX = RequestContext(ip_address="113.190.1.10", user_agent="Mozilla/5.0 Chrome", trace_id="req-1")


class StubRevoker:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def enqueue_revoke(self, *, uid: str, owner_id: UUID | None, trace_id: str | None = None) -> None:
        if self.fail:
            raise RevokeEnqueueError("broker down")
        self.calls.append({"uid": uid, "owner_id": owner_id, "trace_id": trace_id})


@pytest.fixture
def session():
    yield from make_session()


def _auth(session, revoker: StubRevoker | None = None) -> WorkshopAuthService:
    return WorkshopAuthService(session, revoker or StubRevoker())


def _events(session) -> list[WorkshopAuthEvent]:
    return list(session.exec(select(WorkshopAuthEvent).order_by(WorkshopAuthEvent.created_at)).all())


def _onboarding(session):
    return make_service(session, auditor=_auth(session))


# ======================================================================
# Sign-in audit (API-201)
# ======================================================================
def test_sign_in_writes_login_event_with_request_context(session):
    _onboarding(session).sign_in(claims(), CTX)

    [event] = _events(session)
    owner = session.exec(select(WorkshopOwner)).one()
    assert event.owner_id == owner.id
    assert (event.event_type, event.result) == (AuthEventType.LOGIN, AuthEventResult.SUCCESS)
    assert (event.ip_address, event.user_agent, event.trace_id) == ("113.190.1.10", "Mozilla/5.0 Chrome", "req-1")
    assert event.auth_provider == "google.com"


def test_every_sign_in_is_logged(session):
    service = _onboarding(session)
    service.sign_in(claims(), CTX)
    service.sign_in(claims(), CTX)
    assert [e.event_type for e in _events(session)] == [AuthEventType.LOGIN, AuthEventType.LOGIN]


@pytest.mark.parametrize(
    "status,reason",
    [(UserStatus.SUSPENDED, "account_suspended"), (UserStatus.INACTIVE, "account_inactive")],
)
def test_locked_sign_in_is_denied_and_logged(session, status, reason):
    service = _onboarding(session)
    service.sign_in(claims(), CTX)
    owner = session.exec(select(WorkshopOwner)).one()
    owner.status = status
    session.add(owner)
    session.commit()

    with pytest.raises(onboarding_errors.AccountLockedError):
        service.sign_in(claims(), CTX)

    denied = _events(session)[-1]
    assert (denied.event_type, denied.result, denied.reason) == (
        AuthEventType.LOGIN_DENIED,
        AuthEventResult.DENIED,
        reason,
    )


def test_sign_in_rejected_before_account_exists_is_not_logged(session):
    with pytest.raises(onboarding_errors.WorkshopOnboardingError):
        _onboarding(session).sign_in(claims(email_verified=False), CTX)
    assert _events(session) == []


def test_audit_never_contains_email_or_token(session):
    _onboarding(session).sign_in(claims(), CTX)
    event = _events(session)[0]
    stored = " ".join(str(v) for v in event.model_dump().values())
    assert claims()["email"] not in stored


# ======================================================================
# API-301 — logout
# ======================================================================
def test_logout_records_and_enqueues_revoke(session):
    _onboarding(session).sign_in(claims(), CTX)
    revoker = StubRevoker()
    _auth(session, revoker).logout(claims(), CTX)

    owner = session.exec(select(WorkshopOwner)).one()
    assert owner.last_logout_at is not None
    assert _events(session)[-1].event_type == AuthEventType.LOGOUT
    assert revoker.calls == [{"uid": "ws-uid-1", "owner_id": owner.id, "trace_id": "req-1"}]


def test_locked_owner_can_still_log_out(session):
    _onboarding(session).sign_in(claims(), CTX)
    owner = session.exec(select(WorkshopOwner)).one()
    owner.status = UserStatus.SUSPENDED
    session.add(owner)
    session.commit()

    _auth(session).logout(claims(), CTX)
    assert _events(session)[-1].event_type == AuthEventType.LOGOUT


def test_logout_without_workshop_account_still_revokes(session):
    revoker = StubRevoker()
    _auth(session, revoker).logout(claims(uid="unknown"), CTX)
    assert revoker.calls[0]["owner_id"] is None
    assert _events(session) == []


def test_logout_enqueue_failure_rolls_back_and_raises_503(session):
    _onboarding(session).sign_in(claims(), CTX)
    with pytest.raises(errors.AuthProviderUnavailableError):
        _auth(session, StubRevoker(fail=True)).logout(claims(), CTX)

    owner = session.exec(select(WorkshopOwner)).one()
    assert owner.last_logout_at is None
    assert [e.event_type for e in _events(session)] == [AuthEventType.LOGIN]


# ======================================================================
# Worker callback + retention
# ======================================================================
def test_record_revoke_result(session):
    _onboarding(session).sign_in(claims(), CTX)
    owner = session.exec(select(WorkshopOwner)).one()
    service = _auth(session)

    service.record_revoke_result(owner_id=owner.id, success=False, reason="UnavailableError", trace_id="t")
    service.record_revoke_result(owner_id=owner.id, success=True, trace_id="t")
    service.record_revoke_result(owner_id=None, success=True)  # no owner → skipped

    failed, revoked = _events(session)[-2:]
    assert (failed.event_type, failed.result, failed.reason) == (
        AuthEventType.SESSION_REVOKE_FAILED,
        AuthEventResult.FAILED,
        "UnavailableError",
    )
    assert (revoked.event_type, revoked.result) == (AuthEventType.SESSION_REVOKED, AuthEventResult.SUCCESS)
    assert len(_events(session)) == 3


def test_purge_events_keeps_last_60_days(session):
    _onboarding(session).sign_in(claims(), CTX)
    _onboarding(session).sign_in(claims(), CTX)
    old = _events(session)[0]
    old.created_at = datetime.now(UTC) - timedelta(days=61)
    session.add(old)
    session.commit()

    assert _auth(session).purge_events() == 1
    assert len(_events(session)) == 1


# ======================================================================
# API-302 — session check
# ======================================================================
def test_session_returns_account_state(session):
    _onboarding(session).sign_in(claims(), CTX)
    data = _auth(session).session(claims())
    assert data.account_status == "ACTIVE"
    assert data.onboarding.next_step == "PROFILE"
    assert data.last_login_at is not None


def test_session_errors(session):
    service = _auth(session)
    with pytest.raises(errors.WorkshopAuthError) as exc:
        service.session(claims())
    assert exc.value.code == "WORKSHOP_OWNER_NOT_REGISTERED"

    _onboarding(session).sign_in(claims(), CTX)
    owner = session.exec(select(WorkshopOwner)).one()
    owner.status = UserStatus.INACTIVE
    session.add(owner)
    session.commit()
    with pytest.raises(errors.WorkshopAuthError) as exc:
        service.session(claims())
    assert exc.value.code == "ACCOUNT_INACTIVE"
