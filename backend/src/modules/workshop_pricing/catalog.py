"""Model display names from the manufacturer catalog, for the price list's model picker.

The schedule only knows opaque codes (MDL-02). The catalog names every model, including
the ones no owner has verified yet. It changes rarely, so a successful read is kept for
TTL_SECONDS. When the manufacturer is slow or down the price list still loads: the last
names read are kept, and the outage is remembered for FAILURE_TTL_SECONDS so the page
does not wait out the timeout on every visit. FALLBACK_NAMES covers a cold start.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from src.modules.vehicle_owner_onboarding.ports import OemVehicleGateway

logger = logging.getLogger(__name__)

TTL_SECONDS = 600.0
FAILURE_TTL_SECONDS = 30.0
TIMEOUT_SECONDS = 2.0

# The manufacturer's models (mock-ev-system seed), lowest priority: verified vehicles and
# the live catalog override them. A model missing here still shows its code.
FALLBACK_NAMES: dict[str, str] = {
    "MDL-01": "VF5 Plus",
    "MDL-02": "VF6 Eco",
    "MDL-03": "VF6 Plus",
    "MDL-04": "VF7 Eco",
    "MDL-05": "VF8 Eco",
    "MDL-06": "VF8 Plus",
    "MDL-07": "VF9 Plus",
    "MDL-08": "VF Wild Plus",
    "MDL-09": "VF3 Eco",
    "MDL-10": "VF2 Eco",
    "MDL-11": "VF7 Plus",
    "MDL-12": "VF9 Eco",
}

_cache: tuple[float, dict[str, str]] | None = None  # (read at, names) of the last successful read
_failed_at: float | None = None


def display_name(model: dict) -> str:
    return " ".join(str(part) for part in (model.get("model_name"), model.get("trim")) if part)


async def catalog_names(gateway: OemVehicleGateway, *, clock: Callable[[], float] = time.monotonic) -> dict[str, str]:
    """``{"MDL-02": "VF6 Eco", ...}``; the last names read (or ``{}``) when the catalog cannot be read."""
    global _cache, _failed_at
    now = clock()
    last = _cache[1] if _cache is not None else {}
    if _cache is not None and now - _cache[0] < TTL_SECONDS:
        return last
    if _failed_at is not None and now - _failed_at < FAILURE_TTL_SECONDS:
        return last
    try:
        models = await asyncio.wait_for(gateway.list_models(), TIMEOUT_SECONDS)
    except Exception as exc:  # noqa: BLE001 — names are cosmetic, the price list must still load
        _failed_at = now
        logger.warning(
            "Price list: manufacturer catalog unavailable for %.0fs, using fallback names: %r", FAILURE_TTL_SECONDS, exc
        )
        return last
    names = {m["model_id"]: name for m in models if m.get("model_id") and (name := display_name(m))}
    _failed_at = None
    if names:
        _cache = (now, names)
    return names


def clear_cache() -> None:
    global _cache, _failed_at
    _cache = None
    _failed_at = None
