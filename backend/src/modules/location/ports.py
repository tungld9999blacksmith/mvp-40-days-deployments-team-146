"""Location search — provider port (API-SPEC-PLATFORM-LOC-001 §5.1).

Swap the place data provider (Amazon Location / GrabMaps today; Goong, VietMap… later)
by writing another ``PlaceSearchProvider``; routes and the service stay unchanged.
"""

from __future__ import annotations

from typing import Protocol

from .domain import LatLng, LocationSuggestion, PlaceDetail


class ProviderUnavailableError(Exception):
    """Transport error, timeout, throttling, 5xx or a misconfigured key — retryable for the caller."""

    def __init__(self, message: str, *, misconfigured: bool = False) -> None:
        super().__init__(message)
        self.misconfigured = misconfigured


class PlaceNotFoundError(Exception):
    """Unknown / expired place id, or nothing at the reverse-geocoded position."""


class PlaceOutOfCoverageError(Exception):
    """The place exists but lies outside Vietnam."""


class PlaceSearchProvider(Protocol):
    name: str

    async def suggest(self, query: str, *, near: LatLng | None, limit: int) -> list[LocationSuggestion]:
        """Places matching a partly typed query, best first. Only places in Vietnam."""
        ...

    async def get_place(self, place_id: str) -> PlaceDetail:
        """Full address + coordinates of one place. Raises ``PlaceNotFoundError``."""
        ...

    async def reverse(self, position: LatLng) -> PlaceDetail:
        """Address at (or nearest to) a position. Raises ``PlaceNotFoundError``."""
        ...

    async def aclose(self) -> None:
        """Release network resources (called at app shutdown)."""
        ...
