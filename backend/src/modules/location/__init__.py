"""Location search platform — keyword suggest, place detail, reverse geocode (API-LOC-001..003).

Spec: ``docs/specs/platform/location-search.api.md``.
"""

from .errors import LocationError, status_for

__all__ = ["LocationError", "status_for"]
