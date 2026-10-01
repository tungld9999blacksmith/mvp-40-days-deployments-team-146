"""OEM integration module — ports (abstractions the services depend on).

Concrete adapters: ``infrastructure/oem/gateway.py`` (HTTP), ``scheduler.py``
(Celery) and ``stores.py`` (Redis). Tests replace them with in-memory stubs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from src.common.core.vehicle import OemSyncTrigger


class OemUnavailableError(Exception):
    """Timeout, connection error or 5xx from the manufacturer system."""


class OemVehicleNotFoundError(Exception):
    """The manufacturer does not know the vehicle id (HTTP 404 "Vehicle not found")."""


@dataclass(frozen=True)
class UsageSnapshot:
    """``GET /vehicles/{vehicle_id}/usage`` of the manufacturer."""

    current_km: int
    data_source: str
    last_updated_at: datetime


@dataclass(frozen=True)
class ServiceHistoryEntry:
    """One row of ``GET /vehicles/{vehicle_id}/service-history``."""

    order_id: str
    service_center_id: str | None
    service_date: date
    km_at_service: int | None
    items_done: str | None
    is_periodic: bool = True  # False = repair outside the periodic schedule (Q-304)


class OemVehicleDataGateway(ABC):
    """Read side of the manufacturer API used by the sync job (O6, O7)."""

    @abstractmethod
    async def get_usage(self, vehicle_id: str) -> UsageSnapshot | None:
        """Current odometer snapshot; ``None`` when the manufacturer has no usage data.

        Raises:
            OemVehicleNotFoundError: unknown vehicle id.
            OemUnavailableError: transport error / timeout / 5xx.
        """

    @abstractmethod
    async def get_service_history(self, vehicle_id: str) -> list[ServiceHistoryEntry]:
        """All service records of the vehicle (may be empty).

        Raises:
            OemVehicleNotFoundError: unknown vehicle id.
            OemUnavailableError: transport error / timeout / 5xx.
        """


class SyncLock(ABC):
    """Per-vehicle mutual exclusion so two syncs of one vehicle never overlap."""

    @abstractmethod
    async def acquire(self, user_vehicle_id: UUID) -> bool: ...

    @abstractmethod
    async def release(self, user_vehicle_id: UUID) -> None: ...


class SyncScheduler(ABC):
    """Enqueues a background sync of one vehicle (Celery in production)."""

    @abstractmethod
    def schedule(
        self, user_vehicle_id: UUID, trigger: OemSyncTrigger, *, delay_seconds: int = 0
    ) -> None: ...


class WebhookEventStore(ABC):
    """Idempotency + debounce state for incoming webhooks."""

    @abstractmethod
    async def claim_event(self, event_id: str) -> bool:
        """Return ``True`` the first time an event id is seen, ``False`` for duplicates."""

    @abstractmethod
    async def claim_debounce(self, user_vehicle_id: UUID) -> bool:
        """Return ``True`` when no sync for this vehicle was scheduled in the debounce window."""
