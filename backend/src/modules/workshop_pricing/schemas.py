"""Workshop price list — request/response schemas (camelCase JSON, ``{"data": ...}`` envelope)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from src.common.money import Money

_PRICE = {"ge": 0, "le": 999_999_999.99, "decimal_places": 2}


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, protected_namespaces=())


class PriceRowOut(CamelModel):
    price_id: UUID
    price: Money
    valid_from: date | None
    valid_to: date | None


class PriceItemOut(CamelModel):
    """One service of the model. The schedule repeats a service under one code per milestone
    (MI_005, MI_010, … for the same filter), so the list groups codes by name (QA ISSUE-003)."""

    item_code: str  # first code of the group
    item_codes: list[str]
    item_name: str
    reference_price: Money  # highest reference of the group
    reference_price_min: Money
    # Price valid today for every code of the group, or None.
    current_price: Money | None
    # Codes with a price valid today; < len(item_codes) means some milestones still use the reference.
    priced_codes: int
    # The codes have different prices today.
    mixed_prices: bool = False
    prices: list[PriceRowOut]


class PriceListOut(CamelModel):
    model_id: str
    items: list[PriceItemOut]
    priced_count: int
    models: list[str]


class PriceListEnvelope(CamelModel):
    data: PriceListOut


class PriceCreateRequest(CamelModel):
    model_id: str = Field(max_length=64)
    item_code: str = Field(max_length=50)
    price: Money = Field(**_PRICE)
    valid_from: date | None = None
    valid_to: date | None = None


class PriceSetRequest(CamelModel):
    """Set today's price of a service for all its codes (each milestone of the schedule)."""

    model_id: str = Field(max_length=64)
    item_codes: list[str] = Field(min_length=1, max_length=20)
    price: Money = Field(**_PRICE)


class PriceUpdateRequest(CamelModel):
    price: Money = Field(**_PRICE)
    valid_from: date | None = None
    valid_to: date | None = None


class CopyReferenceRequest(CamelModel):
    model_id: str = Field(max_length=64)
    # -50 % … +200 % of the reference price, rounded to 1,000 đ.
    percent: Decimal = Field(default=Decimal(0), ge=-50, le=200, decimal_places=1)
    valid_from: date | None = None
    valid_to: date | None = None


class CopyReferenceOut(CamelModel):
    created: int
    skipped_item_codes: list[str]
    price_list: PriceListOut


class CopyReferenceEnvelope(CamelModel):
    data: CopyReferenceOut
