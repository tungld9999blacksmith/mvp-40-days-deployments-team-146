"""Onboarding module — ports (abstractions the service depends on).

The concrete manufacturer gateway lives in
``infrastructure/oem/`` and is wired in ``dependency.py``. The service depends
only on this interface, so it can be swapped for a stub in tests or a real
OEM SDK later without touching business logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ev_contracts import OwnershipVerifyRequest, OwnershipVerifyResponse


class OemTimeoutError(Exception):
    """The manufacturer system did not respond within the timeout budget.

    The service treats this as "pending" (EF-002), not a business failure.
    """


class OemVehicleGateway(ABC):
    """Client contract for the EV manufacturer system."""

    @abstractmethod
    async def list_models(self) -> list[dict]:
        """Return the manufacturer's vehicle models for the model dropdown."""
        ...

    @abstractmethod
    async def verify_ownership(
        self, request: OwnershipVerifyRequest
    ) -> OwnershipVerifyResponse:
        """Verify a user owns a vehicle and return its spec + warranties.

        Raises:
            OemTimeoutError: transport timeout / connection error / 5xx.
        """
        ...
