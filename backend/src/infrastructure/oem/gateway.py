"""HTTP adapters for the EV manufacturer system (mock-ev-system in dev).

Implements ``OemVehicleGateway`` (vehicle owners), ``OemServiceCenterGateway``
(workshop owners) and ``OemVehicleDataGateway`` (odometer / service-history sync)
using httpx. Transport problems (timeout,
connection error, 5xx) are surfaced as ``OemTimeoutError`` so the service can
treat them as "pending" (EF-002) rather than a business failure.

Every call goes through ``OemHttpClient``, which sends the OEM-issued access token
(SPEC-SEC-OEM-M2M-001 v2.0) and refreshes it once when the OEM answers 401.
Authentication failures are logged as errors and then reported like an outage.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import httpx
from ev_contracts import (
    ManagerVerifyRequest,
    ManagerVerifyResponse,
    OwnershipVerifyRequest,
    OwnershipVerifyResponse,
)

from src.config import Settings
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

from .auth import OemAccessTokenProvider, OemAuthError

logger = logging.getLogger(__name__)


class OemHttpClient:
    """Sends OEM API requests with the cached access token; refreshes it once on 401."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 8.0,
        token_provider: OemAccessTokenProvider | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._tokens = token_provider
        self._transport = transport

    @classmethod
    def from_settings(cls, settings: Settings) -> OemHttpClient:
        return cls(
            settings.oem_api_base_url,
            timeout_seconds=settings.oem_api_timeout_seconds,
            token_provider=OemAccessTokenProvider.from_settings(settings),
        )

    async def request(self, method: str, path: str, *, json: Any = None) -> httpx.Response:
        """Raises httpx transport errors (OEM unreachable) or ``OemAuthError``."""
        url = f"{self._base_url}{path}"
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            if self._tokens is None:
                return await client.request(method, url, json=json)
            token = await self._tokens.get_token()
            resp = await client.request(method, url, json=json, headers=_bearer(token))
            if resp.status_code != 401:
                return resp
            # Expired early, OEM restarted or keys rotated: drop the cached token and retry once.
            logger.warning("OEM rejected the access token on %s %s; refreshing it", method, path)
            await self._tokens.invalidate(token)
            token = await self._tokens.get_token()
            resp = await client.request(method, url, json=json, headers=_bearer(token))
            if resp.status_code == 401:
                logger.error("OEM rejected a fresh access token on %s %s: %s", method, path, resp.text)
                raise OemAuthError(f"OEM rejected a fresh access token on {method} {path}")
            return resp


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class HttpOemVehicleGateway(OemVehicleGateway):
    def __init__(self, client: OemHttpClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> HttpOemVehicleGateway:
        return cls(OemHttpClient.from_settings(settings))

    async def list_models(self) -> list[dict]:
        try:
            resp = await self._client.request("GET", "/models")
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            logger.warning("OEM list_models transport error: %s", exc)
            raise OemTimeoutError(str(exc)) from exc
        except OemAuthError as exc:
            raise OemTimeoutError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise OemTimeoutError(str(exc)) from exc
            raise

    async def verify_ownership(self, request: OwnershipVerifyRequest) -> OwnershipVerifyResponse:
        try:
            resp = await self._client.request("POST", "/vehicles/verify-ownership", json=request.model_dump())
            resp.raise_for_status()
            return OwnershipVerifyResponse.model_validate(resp.json())
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            logger.warning("OEM verify_ownership transport error: %s", exc)
            raise OemTimeoutError(str(exc)) from exc
        except OemAuthError as exc:
            raise OemTimeoutError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            # 5xx is treated as a transient OEM outage; other 4xx are unexpected.
            if exc.response.status_code >= 500:
                raise OemTimeoutError(str(exc)) from exc
            logger.error("OEM verify_ownership unexpected status: %s", exc)
            raise OemTimeoutError(str(exc)) from exc


class HttpOemServiceCenterGateway(OemServiceCenterGateway):
    """Workshop-owner side of the OEM API (FEAT-AUTH-003)."""

    def __init__(self, client: OemHttpClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> HttpOemServiceCenterGateway:
        return cls(OemHttpClient.from_settings(settings))

    async def verify_manager(self, request: ManagerVerifyRequest) -> ManagerVerifyResponse:
        try:
            resp = await self._client.request("POST", "/service-centers/verify-manager", json=request.model_dump())
            resp.raise_for_status()
            return ManagerVerifyResponse.model_validate(resp.json())
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError, OemAuthError) as exc:
            # Any transport / HTTP / auth failure is a transient outage for the caller:
            # the attempt stays pending and is retried in the background.
            logger.warning("OEM verify_manager failed: %s", exc)
            raise ServiceCenterOemTimeoutError(str(exc)) from exc


class HttpOemVehicleDataGateway(OemVehicleDataGateway):
    """Odometer + service history reads for the OEM sync job (FEAT-VEH-001, O6/O7)."""

    def __init__(self, client: OemHttpClient) -> None:
        self._client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> HttpOemVehicleDataGateway:
        return cls(OemHttpClient.from_settings(settings))

    async def _get(self, path: str) -> httpx.Response:
        try:
            resp = await self._client.request("GET", path)
        except (httpx.TimeoutException, httpx.TransportError, OemAuthError) as exc:
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
