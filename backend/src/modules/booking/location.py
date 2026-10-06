"""Workshop location finder — the swap point for "find workshops near X" (Q-401).

⚠️ HIGHEST-PRIORITY upgrade point (FF callout / API §3). MVP keeps this deliberately
simple: ``SimpleTextLocationFinder`` ranks by real coordinates (haversine) when the
anchor carries them, otherwise it matches the location string / province against the
workshop name & region. A later version (geocoding, road distance, routing) only has
to provide another ``WorkshopLocationFinder`` implementation — nothing else in the
booking flow changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from src.common.core.workshop import Workshop, WorkshopStatus

from .domain import LocationAnchor, RankedBy, fold_text, haversine_km


class RankingMode(StrEnum):
    DEFAULT = "DEFAULT"  # us-029 BR-003: the preferred workshop first
    DISTANCE = "DISTANCE"  # us-061 BR-1506: distance only, the preferred workshop gets no boost


@dataclass(frozen=True)
class RankedWorkshop:
    workshop: Workshop
    distance_km: float | None  # None when ranked by region (BR-004)
    is_preferred: bool


class WorkshopLocationFinder(Protocol):
    """Contract for ranking active workshops near a location anchor (BR-002..004)."""

    def rank(
        self,
        anchor: LocationAnchor,
        workshops: list[Workshop],
        *,
        preferred_workshop_id: UUID | None,
        limit: int,
        ranking: RankingMode = RankingMode.DEFAULT,
    ) -> tuple[list[RankedWorkshop], RankedBy]: ...


class SimpleTextLocationFinder:
    """MVP implementation — string match + optional haversine (no geocoding)."""

    def rank(
        self,
        anchor: LocationAnchor,
        workshops: list[Workshop],
        *,
        preferred_workshop_id: UUID | None,
        limit: int,
        ranking: RankingMode = RankingMode.DEFAULT,
    ) -> tuple[list[RankedWorkshop], RankedBy]:
        boost = ranking == RankingMode.DEFAULT
        active = [w for w in workshops if w.status == WorkshopStatus.ACTIVE]

        if anchor.has_coordinates:
            ranked_by = RankedBy.DISTANCE
            scored: list[RankedWorkshop] = []
            for w in active:
                if w.latitude is None or w.longitude is None:
                    # No coordinates → keep it but with unknown distance (EDGE-412).
                    scored.append(RankedWorkshop(w, None, w.id == preferred_workshop_id))
                    continue
                dist = haversine_km(
                    float(anchor.latitude),
                    float(anchor.longitude),
                    float(w.latitude),
                    float(w.longitude),
                )
                scored.append(RankedWorkshop(w, dist, w.id == preferred_workshop_id))
            # Preferred first (DEFAULT only), then nearest; unknown distance sinks to the end.
            scored.sort(key=lambda r: (boost and not r.is_preferred, r.distance_km is None, r.distance_km or 0.0))
            return scored[:limit], ranked_by

        # No coordinates → region / text match (BR-004), ignoring accents and case.
        ranked_by = RankedBy.REGION
        needle = fold_text(anchor.province or anchor.query)
        matched = [w for w in active if not needle or needle in fold_text(w.region) or needle in fold_text(w.name)]
        matched.sort(key=lambda w: (boost and w.id != preferred_workshop_id, (w.name or "").lower()))
        ranked = [RankedWorkshop(w, None, w.id == preferred_workshop_id) for w in matched]
        return ranked[:limit], ranked_by


def get_location_finder() -> WorkshopLocationFinder:
    """DI seam — swap the implementation here when upgrading (Q-401)."""
    return SimpleTextLocationFinder()
