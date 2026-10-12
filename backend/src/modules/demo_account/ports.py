"""Demo account module — ports (Firebase identity, manufacturer admin)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class DemoIdentityProvider(ABC):
    """Creates the demo Firebase user once and mints custom tokens for it."""

    @abstractmethod
    def ensure_user(self, uid: str, *, email: str, display_name: str) -> None: ...

    @abstractmethod
    def mint_token(self, uid: str) -> str: ...


class DemoOwnerAdmin(ABC):
    """Puts the manufacturer's demo owner back to its initial data (mock-ev-system admin API)."""

    @abstractmethod
    async def reset_demo_owner(self) -> None: ...
