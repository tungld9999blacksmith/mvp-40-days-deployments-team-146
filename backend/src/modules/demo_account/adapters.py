"""Demo account module — adapters for the ports (Firebase Admin, mock-ev-system admin API)."""

from __future__ import annotations

from uuid import UUID

import httpx

from src.modules.oem_integration.ports import SyncLock

from .errors import DemoAccountUnavailableError
from .identity import DEMO_CLAIM
from .ports import DemoIdentityProvider, DemoOwnerAdmin


class FirebaseDemoIdentity(DemoIdentityProvider):
    def ensure_user(self, uid: str, *, email: str, display_name: str) -> None:
        from firebase_admin import auth

        try:
            auth.get_user(uid)
        except auth.UserNotFoundError:
            try:
                auth.create_user(uid=uid, email=email, email_verified=True, display_name=display_name)
            except auth.UidAlreadyExistsError:
                pass  # created by a concurrent request
        # Persistent claim as well, so every refreshed ID token keeps it.
        auth.set_custom_user_claims(uid, {DEMO_CLAIM: True})

    def mint_token(self, uid: str) -> str:
        from firebase_admin import auth

        token = auth.create_custom_token(uid, {DEMO_CLAIM: True})
        return token.decode() if isinstance(token, bytes) else token


class HttpDemoOwnerAdmin(DemoOwnerAdmin):
    def __init__(self, base_url: str, *, admin_token: str = "", timeout_seconds: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-Admin-Token": admin_token} if admin_token else {}
        self._timeout = timeout_seconds

    async def reset_demo_owner(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/admin/demo-owner/reset", headers=self._headers)
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise DemoAccountUnavailableError(f"manufacturer demo owner reset failed: {exc}") from exc


class NoSyncLock(SyncLock):
    """The demo seed holds the account lock already; its vehicles cannot be synced twice at once."""

    async def acquire(self, user_vehicle_id: UUID) -> bool:
        return True

    async def release(self, user_vehicle_id: UUID) -> None:
        return None
