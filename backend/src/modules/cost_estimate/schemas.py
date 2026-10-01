"""Cost-estimate module — response schemas (camelCase JSON, ``{"data": ...}`` envelope).

Shapes follow ``docs/specs/sprint-2/api/us-045-sprint-2-spec.api.md``.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from src.common.money import Money

from .domain import CURRENCY, ESTIMATE_LABEL


class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, protected_namespaces=()
    )


# ── API-EST-01 milestones ───────────────────────────────────────────────────
class MilestoneOptionOut(CamelModel):
    odo_milestone: int
    month_milestone: int
    item_count: int
    is_next: bool


class MilestonesData(CamelModel):
    model_id: str | None
    next_odo_milestone: int | None
    milestones: list[MilestoneOptionOut]


class MilestonesEnvelope(CamelModel):
    data: MilestonesData


# ── API-EST-02 estimate ─────────────────────────────────────────────────────
class EstimateMilestoneOut(CamelModel):
    odo_milestone: int
    month_milestone: int
    is_next: bool


class EstimateWorkshopOut(CamelModel):
    workshop_id: UUID
    name: str
    selected_by: str


class EstimateItemOut(CamelModel):
    maintenance_rule_id: UUID
    item_code: str
    item_name: str
    covered: bool
    price: Money
    price_source: str | None


class EstimateData(CamelModel):
    status: str
    user_vehicle_id: UUID | None = None
    model_id: str | None = None
    milestone: EstimateMilestoneOut | None = None
    workshop: EstimateWorkshopOut | None = None
    warranty_status: str | None = None
    items: list[EstimateItemOut] = []
    covered_count: int = 0
    chargeable_total: Money | None = None
    has_reference_price: bool = False
    currency: str = CURRENCY
    estimate_label: str = ESTIMATE_LABEL
    computed_at: datetime | None = None


class EstimateEnvelope(CamelModel):
    data: EstimateData


# ── API-EST-03 compare ──────────────────────────────────────────────────────
class CompareErrorOut(CamelModel):
    code: str


class CompareFailureOut(CamelModel):
    workshop_id: UUID
    error: CompareErrorOut


class CompareData(CamelModel):
    estimates: list[EstimateData | CompareFailureOut]


class CompareEnvelope(CamelModel):
    data: CompareData
