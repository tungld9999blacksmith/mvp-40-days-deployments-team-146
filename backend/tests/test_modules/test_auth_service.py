"""Service-level tests for the auth module (FEAT-AUTH-002, API-101).

Exercise ``AuthService`` directly against an in-memory SQLite session and a
stub session revoker: logout audit + last_logout_at, enqueue, the 503 path
(EF-104), the missing-user path, and the background revoke outcome writes.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from src.modules.auth import errors
from src.modules.auth.domain import AuthEvent, AuthEventResult, AuthEventType
from src.modules.auth.service import AuthService
from tests._auth import StubRevoker, make_session, make_user


def _claims(uid: str = "uid-1") -> dict:
    return {"uid": uid, "firebase": {"sign_in_provider": "google.com"}}


def test_logout_records_audit_and_enqueues_revoke():
    session = next(make_session())
    user = make_user(session, uid="uid-1")
    revoker = StubRevoker()
    svc = AuthService(session, revoker)

    svc.logout(_claims("uid-1"), trace_id="req-1", ip_address="1.2.3.4", user_agent="EVCare/1.0")

    session.refresh(user)
    assert user.last_logout_at is not None

    events = session.exec(select(AuthEvent)).all()
    assert len(events) == 1
    assert events[0].event_type == AuthEventType.LOGOUT
    assert events[0].result == AuthEventResult.SUCCESS
    assert events[0].trace_id == "req-1"

    assert revoker.calls == [{"uid": "uid-1", "user_id": user.user_id, "trace_id": "req-1"}]


def test_logout_enqueue_failure_raises_503_and_rolls_back():
    session = next(make_session())
    user = make_user(session, uid="uid-1")
    svc = AuthService(session, StubRevoker(fail=True))

    with pytest.raises(errors.AuthProviderUnavailableError):
        svc.logout(_claims("uid-1"))

    # Nothing persisted: no audit row, no last_logout_at.
    session.refresh(user)
    assert user.last_logout_at is None
    assert session.exec(select(AuthEvent)).all() == []


def test_logout_missing_user_still_enqueues_without_audit():
    session = next(make_session())
    revoker = StubRevoker()
    svc = AuthService(session, revoker)

    svc.logout(_claims("uid-unknown"), trace_id="req-2")

    assert session.exec(select(AuthEvent)).all() == []
    assert revoker.calls == [{"uid": "uid-unknown", "user_id": 0, "trace_id": "req-2"}]


def test_record_revoke_result_success_writes_session_revoked():
    session = next(make_session())
    user = make_user(session, uid="uid-1")
    svc = AuthService(session, StubRevoker())

    svc.record_revoke_result(user_id=user.user_id, success=True, trace_id="req-3")

    event = session.exec(select(AuthEvent)).one()
    assert event.event_type == AuthEventType.SESSION_REVOKED
    assert event.result == AuthEventResult.SUCCESS


def test_record_revoke_result_failure_writes_session_revoke_failed():
    session = next(make_session())
    user = make_user(session, uid="uid-1")
    svc = AuthService(session, StubRevoker())

    svc.record_revoke_result(user_id=user.user_id, success=False, reason="FirebaseError", trace_id="req-4")

    event = session.exec(select(AuthEvent)).one()
    assert event.event_type == AuthEventType.SESSION_REVOKE_FAILED
    assert event.result == AuthEventResult.FAILED
    assert event.reason == "FirebaseError"


def test_record_revoke_result_unknown_user_is_noop():
    session = next(make_session())
    svc = AuthService(session, StubRevoker())

    svc.record_revoke_result(user_id=0, success=True)

    assert session.exec(select(AuthEvent)).all() == []
