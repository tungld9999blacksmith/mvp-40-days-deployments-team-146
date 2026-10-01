"""Caller identity of the conversation REST routes (Q-621).

``get_current_user_id`` verifies the Firebase ID token and maps it to the
vehicle owner's ``user_id``; ``X-User-Id`` is a non-production fallback only.
"""

from __future__ import annotations

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from firebase_admin import auth as firebase_auth

from src.common.core.identity.vehicle_user import UserStatus, VehicleUser
from src.config import get_settings
from src.modules.conversation import errors
from src.modules.conversation.dependency import get_current_user_id
from tests._onboarding import make_session


def _bearer(token: str = "id-token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def session():
    yield from make_session()


@pytest.fixture
def owner(session) -> VehicleUser:
    user = VehicleUser(firebase_uid="uid-owner", email="owner@example.com", auth_provider="google.com")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def verify_as(monkeypatch):
    def _set(uid: str | None):
        def fake_verify(token, check_revoked=False, clock_skew_seconds=0):
            if uid is None:
                raise firebase_auth.InvalidIdTokenError("bad token")
            return {"uid": uid}

        monkeypatch.setattr(firebase_auth, "verify_id_token", fake_verify)

    return _set


def test_token_maps_to_owner_user_id(session, owner, verify_as):
    verify_as("uid-owner")
    assert get_current_user_id(_bearer(), session, x_user_id=None) == owner.user_id


def test_token_wins_over_dev_header(session, owner, verify_as):
    verify_as("uid-owner")
    assert get_current_user_id(_bearer(), session, x_user_id=999) == owner.user_id


def test_invalid_token_is_unauthorized(session, owner, verify_as):
    verify_as(None)
    with pytest.raises(errors.Unauthorized):
        get_current_user_id(_bearer(), session, x_user_id=None)


def test_unknown_uid_is_forbidden(session, owner, verify_as):
    verify_as("uid-workshop-owner")
    with pytest.raises(errors.Forbidden):
        get_current_user_id(_bearer(), session, x_user_id=None)


def test_suspended_owner_is_forbidden(session, owner, verify_as):
    owner.status = UserStatus.SUSPENDED
    session.add(owner)
    session.commit()
    verify_as("uid-owner")
    with pytest.raises(errors.Forbidden):
        get_current_user_id(_bearer(), session, x_user_id=None)


def test_dev_header_outside_production(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "development")
    assert get_current_user_id(None, session, x_user_id=7) == 7


def test_dev_header_rejected_in_production(session, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    with pytest.raises(errors.Unauthorized):
        get_current_user_id(None, session, x_user_id=7)


def test_no_identity_is_unauthorized(session):
    with pytest.raises(errors.Unauthorized):
        get_current_user_id(None, session, x_user_id=None)
