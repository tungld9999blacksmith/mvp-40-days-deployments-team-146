"""HTTP adapters for the EV manufacturer system (mock-ev-system in dev).

Implements ``OemVehicleGateway`` (vehicle owners), ``OemServiceCenterGateway``
(workshop owners) and ``OemVehicleDataGateway`` (odometer / service-history sync)
using httpx. Transport problems (timeout,
connection error, 5xx) are surfaced as ``OemTimeoutError`` so the service can
treat them as "pending" (EF-002) rather than a business failure.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import httpx
from ev_contracts import (
    ManagerVerifyRequest,
    ManagerVerifyResponse,
    OwnershipVerifyRequest,
    OwnershipVerifyResponse,
)

from src.modules.oem_integration.ports import (
    OemUnavailableError,
    OemVehicleDataGateway,
    OemVehicleNotFoundError,
    ServiceHistoryEntry,
    UsageSnapshot,
)
from src.modules.vehicle_owner_onboarding.ports import OemTimeoutError, OemVehicleGateway
from src.modules.workshop_owner_onboarding.ports import OemServiceCenterGateway
from src.modules.workshop_owner_onboarding.ports import (
    OemTimeoutError as ServiceCenterOemTimeoutError,
)

logger = logging.getLogger(__name__)


class HttpOemVehicleGateway(OemVehicleGateway):
    def __init__(self, base_url: str, *, timeout_seconds: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def list_models(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/models")
                resp.raise_for_status()
                return resp.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            logger.warning("OEM list_models transport error: %s", exc)
            raise OemTimeoutError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise OemTimeoutError(str(exc)) from exc
            raise

    async def verify_ownership(self, request: OwnershipVerifyRequest) -> OwnershipVerifyResponse:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/vehicles/verify-ownership",
                    json=request.model_dump(),
                )
                resp.raise_for_status()
                return OwnershipVerifyResponse.model_validate(resp.json())
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            logger.warning("OEM verify_ownership transport error: %s", exc)
            raise OemTimeoutError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            # 5xx is treated as a transient OEM outage; other 4xx are unexpected.
            if exc.response.status_code >= 500:
                raise OemTimeoutError(str(exc)) from exc
            logger.error("OEM verify_ownership unexpected status: %s", exc)
            raise OemTimeoutError(str(exc)) from exc


class HttpOemServiceCenterGateway(OemServiceCenterGateway):
    """Workshop-owner side of the OEM API (FEAT-AUTH-003)."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def verify_manager(self, request: ManagerVerifyRequest) -> ManagerVerifyResponse:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/service-centers/verify-manager",
                    json=request.model_dump(),
                )
                resp.raise_for_status()
                return ManagerVerifyResponse.model_validate(resp.json())
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            # Any transport / HTTP failure is a transient outage for the caller:
            # the attempt stays pending and is retried in the background.
            logger.warning("OEM verify_manager failed: %s", exc)
            raise ServiceCenterOemTimeoutError(str(exc)) from exc


class HttpOemVehicleDataGateway(OemVehicleDataGateway):
    """Odometer + service history reads for the OEM sync job (FEAT-VEH-001, O6/O7)."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 8.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def _get(self, path: str) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}{path}")
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise OemUnavailableError(str(exc)) from exc
        if resp.status_code >= 500:
            raise OemUnavailableError(f"HTTP {resp.status_code} on {path}")
        return resp

    async def get_usage(self, vehicle_id: str) -> UsageSnapshot | None:
        resp = await self._get(f"/vehicles/{vehicle_id}/usage")
        if resp.status_code == 404:
            # The mock answers 404 both for an unknown vehicle and for a vehicle
            # without usage data; only the former is an error.
            if "no usage data" in resp.text.lower():
                return None
            raise OemVehicleNotFoundError(vehicle_id)
        if resp.status_code != 200:
            raise OemUnavailableError(f"HTTP {resp.status_code} on usage")
        body = resp.json()
        return UsageSnapshot(
            current_km=int(body["current_km"]),
            data_source=str(body.get("data_source") or "telematics"),
            last_updated_at=datetime.fromisoformat(body["last_updated_at"]),
        )

    async def get_service_history(self, vehicle_id: str) -> list[ServiceHistoryEntry]:
        resp = await self._get(f"/vehicles/{vehicle_id}/service-history")
        if resp.status_code == 404:
            raise OemVehicleNotFoundError(vehicle_id)
        if resp.status_code != 200:
            raise OemUnavailableError(f"HTTP {resp.status_code} on service-history")
        return [
            ServiceHistoryEntry(
                order_id=str(row["order_id"]),
                service_center_id=row.get("service_center_id"),
                service_date=date.fromisoformat(row["service_date"]),
                km_at_service=row.get("km_at_service"),
                items_done=row.get("items_done"),
                is_periodic=bool(row.get("is_periodic", True)),
            )
            for row in resp.json()
        ]
