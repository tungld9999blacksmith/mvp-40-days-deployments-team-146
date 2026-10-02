"""Cost-estimate module — the deterministic estimate formula (BR-1001, BR-1004).

Pure logic only (no DB), shared by API-EST-02/03 and TOOL-301 through
``CostEstimationService`` so both always produce the same numbers (BR-1006).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

ESTIMATE_LABEL = "Chi phí ước tính"  # BR-1005 — always shown with the total
CURRENCY = "VND"


class EstimateStatus(StrEnum):
    READY = "READY"
    NO_RULE = "NO_RULE"  # BR-1009 — never show a number without a rule


class WarrantyState(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"  # no chassis warranty data — treated as still covered (Q-1001)


class PriceSource(StrEnum):
    WORKSHOP_PRICE = "WORKSHOP_PRICE"
    REFERENCE_PRICE = "REFERENCE_PRICE"


class WorkshopSelection(StrEnum):
    REQUEST = "REQUEST"
    PREFERRED = "PREFERRED"
    NEAREST = "NEAREST"


@dataclass(frozen=True)
class RuleLine:
    maintenance_rule_id: UUID
    item_code: str
    item_name: str
    is_covered_by_warranty: bool
    reference_price: Decimal


@dataclass(frozen=True)
class EstimateLine:
    maintenance_rule_id: UUID
    item_code: str
    item_name: str
    covered: bool
    price: Decimal
    price_source: PriceSource | None


@dataclass(frozen=True)
class EstimateTotals:
    lines: list[EstimateLine]
    covered_count: int
    chargeable_total: Decimal
    has_reference_price: bool


def warranty_state(chassis_end_date: date | None, today: date) -> WarrantyState:
    """AF-1004: the vehicle is under warranty while the chassis warranty runs."""
    if chassis_end_date is None:
        return WarrantyState.UNKNOWN
    return WarrantyState.ACTIVE if chassis_end_date >= today else WarrantyState.EXPIRED


def compute_estimate(
    rules: list[RuleLine],
    workshop_prices: dict[str, Decimal],
    state: WarrantyState,
) -> EstimateTotals:
    """BR-1001: covered items cost 0; others use the workshop price, else the reference."""
    under_warranty = state != WarrantyState.EXPIRED
    lines: list[EstimateLine] = []
    for rule in sorted(rules, key=lambda r: r.item_code):
        covered = rule.is_covered_by_warranty and under_warranty
        if covered:
            lines.append(EstimateLine(rule.maintenance_rule_id, rule.item_code, rule.item_name, True, Decimal(0), None))
            continue
        price = workshop_prices.get(rule.item_code)
        source = PriceSource.WORKSHOP_PRICE
        if price is None:  # BR-1004 #2 — fall back to the schedule's reference price
            price, source = rule.reference_price, PriceSource.REFERENCE_PRICE
        lines.append(EstimateLine(rule.maintenance_rule_id, rule.item_code, rule.item_name, False, price, source))
    return EstimateTotals(
        lines=lines,
        covered_count=sum(1 for line in lines if line.covered),
        chargeable_total=sum((line.price for line in lines if not line.covered), Decimal(0)),
        has_reference_price=any(line.price_source == PriceSource.REFERENCE_PRICE for line in lines),
    )
