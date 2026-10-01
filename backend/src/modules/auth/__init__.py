"""FEAT-AUTH-002 — Đăng nhập & Đăng xuất (Chủ xe).

Login reuses ``POST /api/v1/oauth/sign-in`` (API-001, onboarding module).
This module owns:

    - API-101 ``POST /api/v1/oauth/logout`` — record the logout, audit it and
      enqueue a durable background task that revokes the Firebase refresh
      tokens for the current uid.
    - ENT-101 ``AuthEvent`` — append-only audit log for auth events.

See ``docs/specs/sprint-1/**/us-005-sprint-1-spec.*``.
"""
