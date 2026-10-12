"""Workshop price list (bao-gia-hai-tang D14) — the prices tier 1 snapshots at booking time.

The owner of a workshop starts from the reference prices of the maintenance
schedule (``copy_reference``: reference × (1 + percent)), then edits single rows.
Writes enforce what ``CostEstimationService._effective_prices`` only warns about:
validity periods of one (workshop, model, item) never overlap (BR-ENT-412), the
price is not negative and the item belongs to the model's maintenance schedule.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.vehicle import UserVehicle
from src.common.core.workshop import Workshop
from src.common.core.workshop.service_price import ServicePrice
from src.modules.user_vehicle.domain import today_vn

from . import errors, schemas
from .catalog import FALLBACK_NAMES

logger = logging.getLogger(__name__)

ROUND_TO = Decimal(1000)  # VND prices are quoted in thousands


def _utc_now() -> datetime:
    return datetime.now(UTC)


def overlaps(a_from: date | None, a_to: date | None, b_from: date | None, b_to: date | None) -> bool:
    """Closed periods, ``None`` = open-ended on that side."""
    return (a_from or date.min) <= (b_to or date.max) and (b_from or date.min) <= (a_to or date.max)


def picker_order(models: list[str], names: Mapping[str, str]) -> list[str]:
    """Named models by name with numbers compared as numbers (VF2 … VF9 Plus, VF Wild Plus), then bare codes."""

    def key(model_id: str) -> tuple[bool, list[str | int]]:
        parts = re.split(r"(\d+)", names.get(model_id, model_id))
        return model_id not in names, [int(p) if i % 2 else p for i, p in enumerate(parts)]

    return sorted(models, key=key)


def scaled(reference: Decimal, percent: Decimal) -> Decimal:
    value = reference * (Decimal(100) + percent) / Decimal(100)
    return max((value / ROUND_TO).quantize(Decimal(1), rounding=ROUND_HALF_UP) * ROUND_TO, Decimal(0))


class WorkshopPricingService:
    def __init__(
        self,
        session: Session,
        *,
        clock: Callable[[], datetime] = _utc_now,
        catalog_names: Mapping[str, str] | None = None,
    ) -> None:
        self._db = session
        self._clock = clock
        # "VF6 Eco" per model id from the manufacturer catalog; empty when it was unreachable.
        self._catalog_names = dict(catalog_names or {})

    # ── reads ───────────────────────────────────────────────────────────
    def models(self) -> list[str]:
        return list(self._db.exec(select(MaintenanceRule.model_id).distinct().order_by(MaintenanceRule.model_id)).all())

    def model_names(self) -> dict[str, str]:
        """Display name per model id ("VF8 Plus"): the manufacturer catalog, else the snapshot of verified
        vehicles, else the static ``FALLBACK_NAMES``.

        The schedule only knows opaque codes (MDL-01). A model that is in none of them has
        no name here and the UI falls back to its code.
        """
        model_id = func.coalesce(UserVehicle.external_model_id, UserVehicle.declared_model_id)
        rows = self._db.exec(
            select(model_id, UserVehicle.model_name, UserVehicle.trim)
            .where(UserVehicle.model_name.is_not(None))  # type: ignore[union-attr]
            .distinct()
            .order_by(model_id)
        ).all()
        names: dict[str, str] = {}
        for code, name, trim in rows:
            names.setdefault(code, " ".join(part for part in (name, trim) if part))
        return FALLBACK_NAMES | names | self._catalog_names

    def _catalog(self, model_id: str) -> dict[str, tuple[str, Decimal]]:
        """item_code → (name, reference price) of the model's schedule."""
        rows = self._db.exec(
            select(
                MaintenanceRule.item_code, func.min(MaintenanceRule.item_name), func.max(MaintenanceRule.estimated_cost)
            )
            .where(MaintenanceRule.model_id == model_id)
            .group_by(MaintenanceRule.item_code)
            .order_by(MaintenanceRule.item_code)
        ).all()
        return {code: (name, Decimal(ref)) for code, name, ref in rows}

    def price_list(self, workshop: Workshop, model_id: str | None) -> schemas.PriceListOut:
        if model_id is None:  # first visit: the first model with a schedule
            models = self.models()
            if not models:
                raise errors.ModelNotFoundError()
            model_id = models[0]
        catalog = self._catalog(model_id)
        if not catalog:
            raise errors.ModelNotFoundError()
        today = today_vn(self._clock())
        prices: dict[str, list[ServicePrice]] = {}
        for row in self._db.exec(
            select(ServicePrice)
            .where(ServicePrice.workshop_id == workshop.id, ServicePrice.model_id == model_id)
            .order_by(ServicePrice.item_code, ServicePrice.valid_from)
        ).all():
            prices.setdefault(row.item_code, []).append(row)
        groups: dict[str, list[str]] = {}
        for code, (name, _ref) in catalog.items():
            groups.setdefault(name, []).append(code)
        items = []
        for name, codes in groups.items():
            rows = [r for code in codes for r in prices.get(code, [])]
            current = {
                code: next(
                    (r.price for r in prices.get(code, []) if overlaps(r.valid_from, r.valid_to, today, today)), None
                )
                for code in codes
            }
            priced = [p for p in current.values() if p is not None]
            same = len(priced) == len(codes) and len(set(priced)) == 1
            refs = [catalog[code][1] for code in codes]
            items.append(
                schemas.PriceItemOut(
                    item_code=codes[0],
                    item_codes=codes,
                    item_name=name,
                    reference_price=max(refs),
                    reference_price_min=min(refs),
                    current_price=priced[0] if same else None,
                    priced_codes=len(priced),
                    mixed_prices=len(set(priced)) > 1,
                    prices=[self._row_out(r) for r in rows],
                )
            )
        names = self.model_names()
        models = picker_order(self.models(), names)
        return schemas.PriceListOut(
            model_id=model_id,
            items=items,
            priced_count=sum(1 for i in items if i.current_price is not None),
            models=models,
            model_names={m: names[m] for m in models if m in names},
        )

    @staticmethod
    def _row_out(row: ServicePrice) -> schemas.PriceRowOut:
        return schemas.PriceRowOut(price_id=row.id, price=row.price, valid_from=row.valid_from, valid_to=row.valid_to)

    # ── writes ──────────────────────────────────────────────────────────
    def _check_period(self, valid_from: date | None, valid_to: date | None) -> None:
        if valid_from and valid_to and valid_to < valid_from:
            raise errors.InvalidRequestError("validTo must be on or after validFrom.", details={"field": "validTo"})

    def _check_overlap(
        self,
        workshop: Workshop,
        model_id: str,
        item_code: str,
        valid_from: date | None,
        valid_to: date | None,
        *,
        exclude: UUID | None = None,
    ) -> None:
        for row in self._db.exec(
            select(ServicePrice)
            .where(
                ServicePrice.workshop_id == workshop.id,
                ServicePrice.model_id == model_id,
                ServicePrice.item_code == item_code,
            )
            .with_for_update()
        ).all():
            if row.id != exclude and overlaps(row.valid_from, row.valid_to, valid_from, valid_to):
                raise errors.PeriodOverlapError(item_code, self._row_out(row).model_dump(mode="json", by_alias=True))

    def create(self, workshop: Workshop, req: schemas.PriceCreateRequest) -> schemas.PriceListOut:
        catalog = self._catalog(req.model_id)
        if req.item_code not in catalog:
            raise errors.InvalidRequestError("The item is not in this model's schedule.", details={"field": "itemCode"})
        self._check_period(req.valid_from, req.valid_to)
        self._check_overlap(workshop, req.model_id, req.item_code, req.valid_from, req.valid_to)
        self._db.add(
            ServicePrice(
                workshop_id=workshop.id,
                model_id=req.model_id,
                item_code=req.item_code,
                item_name=catalog[req.item_code][0],
                price=Decimal(req.price),
                valid_from=req.valid_from,
                valid_to=req.valid_to,
            )
        )
        self._db.commit()
        return self.price_list(workshop, req.model_id)

    def set_prices(self, workshop: Workshop, req: schemas.PriceSetRequest) -> schemas.PriceListOut:
        """Today's price for every code of a service: update the row valid today, else add an open one."""
        catalog = self._catalog(req.model_id)
        unknown = [code for code in req.item_codes if code not in catalog]
        if unknown:
            raise errors.InvalidRequestError(
                "The item is not in this model's schedule.", details={"field": "itemCodes", "itemCodes": unknown}
            )
        today = today_vn(self._clock())
        for code in dict.fromkeys(req.item_codes):
            rows = self._db.exec(
                select(ServicePrice)
                .where(
                    ServicePrice.workshop_id == workshop.id,
                    ServicePrice.model_id == req.model_id,
                    ServicePrice.item_code == code,
                )
                .with_for_update()
            ).all()
            current = next((r for r in rows if overlaps(r.valid_from, r.valid_to, today, today)), None)
            if current is not None:
                current.price = Decimal(req.price)
                self._db.add(current)
                continue
            # No price today: open-ended from today, unless a later period already exists.
            self._check_overlap(workshop, req.model_id, code, today, None)
            self._db.add(
                ServicePrice(
                    workshop_id=workshop.id,
                    model_id=req.model_id,
                    item_code=code,
                    item_name=catalog[code][0],
                    price=Decimal(req.price),
                    valid_from=today,
                )
            )
        self._db.commit()
        return self.price_list(workshop, req.model_id)

    def update(self, workshop: Workshop, price_id: UUID, req: schemas.PriceUpdateRequest) -> schemas.PriceListOut:
        row = self._db.get(ServicePrice, price_id)
        if row is None or row.workshop_id != workshop.id:
            raise errors.PriceNotFoundError()
        self._check_period(req.valid_from, req.valid_to)
        self._check_overlap(workshop, row.model_id, row.item_code, req.valid_from, req.valid_to, exclude=row.id)
        row.price = Decimal(req.price)
        row.valid_from = req.valid_from
        row.valid_to = req.valid_to
        self._db.add(row)
        self._db.commit()
        return self.price_list(workshop, row.model_id)

    def copy_reference(self, workshop: Workshop, req: schemas.CopyReferenceRequest) -> schemas.CopyReferenceOut:
        """Quick start: reference × (1 + percent) for every item without a price in the period."""
        catalog = self._catalog(req.model_id)
        if not catalog:
            raise errors.ModelNotFoundError()
        self._check_period(req.valid_from, req.valid_to)
        existing: dict[str, list[ServicePrice]] = {}
        for row in self._db.exec(
            select(ServicePrice)
            .where(ServicePrice.workshop_id == workshop.id, ServicePrice.model_id == req.model_id)
            .with_for_update()
        ).all():
            existing.setdefault(row.item_code, []).append(row)
        created, skipped = 0, []
        for code, (name, ref) in catalog.items():
            if any(overlaps(r.valid_from, r.valid_to, req.valid_from, req.valid_to) for r in existing.get(code, [])):
                skipped.append(code)
                continue
            self._db.add(
                ServicePrice(
                    workshop_id=workshop.id,
                    model_id=req.model_id,
                    item_code=code,
                    item_name=name,
                    price=scaled(ref, Decimal(req.percent)),
                    valid_from=req.valid_from,
                    valid_to=req.valid_to,
                )
            )
            created += 1
        self._db.commit()
        logger.info(
            "workshop_pricing.copy_reference",
            extra={"workshop_id": str(workshop.id), "model_id": req.model_id, "created_count": created},
        )
        return schemas.CopyReferenceOut(
            created=created, skipped_item_codes=skipped, price_list=self.price_list(workshop, req.model_id)
        )
