"""Workshop price list (bao-gia-hai-tang D14): quick start from reference prices, no overlapping periods."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from src.modules.workshop_pricing import errors
from src.modules.workshop_pricing import schemas as s
from src.modules.workshop_pricing.service import WorkshopPricingService, overlaps, scaled
from tests._maintenance import add_workshop, make_session
from tests._user_vehicle import MODEL_ID, add_rules

NOW = datetime(2026, 10, 3, 2, 0, tzinfo=UTC)


@pytest.fixture
def world():
    for session in make_session():
        add_rules(session)  # BRAKE_INSPECTION, BATTERY_CHECK, BRAKE_FLUID — reference 100,000 each
        yield session, add_workshop(session), WorkshopPricingService(session, clock=lambda: NOW)


def test_overlap_and_rounding():
    assert overlaps(None, None, date(2026, 1, 1), date(2026, 1, 1))
    assert overlaps(date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 31), None)
    assert not overlaps(date(2026, 1, 1), date(2026, 1, 31), date(2026, 2, 1), None)
    assert scaled(Decimal(123_456), Decimal(10)) == 136_000
    assert scaled(Decimal(100_000), Decimal(-50)) == 50_000


def test_copy_reference_then_edit(world):
    session, workshop, pricing = world
    out = pricing.copy_reference(workshop, s.CopyReferenceRequest(model_id=MODEL_ID, percent=Decimal(15)))
    assert out.created == 3 and out.skipped_item_codes == []
    assert {i.item_code: i.current_price for i in out.price_list.items} == {
        "BATTERY_CHECK": 115_000,
        "BRAKE_FLUID": 115_000,
        "BRAKE_INSPECTION": 115_000,
    }
    # Running it again changes nothing: every item already has a price in that period.
    again = pricing.copy_reference(workshop, s.CopyReferenceRequest(model_id=MODEL_ID))
    assert again.created == 0 and len(again.skipped_item_codes) == 3

    row = out.price_list.items[0].prices[0]
    edited = pricing.update(workshop, row.price_id, s.PriceUpdateRequest(price=99_000, valid_to=date(2026, 12, 31)))
    assert edited.items[0].current_price == 99_000


def test_writes_reject_overlap_negative_and_unknown_items(world):
    session, workshop, pricing = world
    pricing.create(
        workshop, s.PriceCreateRequest(model_id=MODEL_ID, item_code="BRAKE_FLUID", price=1, valid_to=date(2026, 12, 31))
    )
    with pytest.raises(errors.PeriodOverlapError):
        pricing.create(
            workshop,
            s.PriceCreateRequest(model_id=MODEL_ID, item_code="BRAKE_FLUID", price=2, valid_from=date(2026, 12, 31)),
        )
    pricing.create(
        workshop, s.PriceCreateRequest(model_id=MODEL_ID, item_code="BRAKE_FLUID", price=2, valid_from=date(2027, 1, 1))
    )
    with pytest.raises(errors.InvalidRequestError):
        pricing.create(workshop, s.PriceCreateRequest(model_id=MODEL_ID, item_code="NOT_IN_SCHEDULE", price=1))
    with pytest.raises(errors.InvalidRequestError):
        pricing.create(
            workshop,
            s.PriceCreateRequest(
                model_id=MODEL_ID,
                item_code="BRAKE_INSPECTION",
                price=1,
                valid_from=date(2027, 1, 2),
                valid_to=date(2027, 1, 1),
            ),
        )
    with pytest.raises(ValueError):
        s.PriceCreateRequest(model_id=MODEL_ID, item_code="BRAKE_FLUID", price=-1)
    with pytest.raises(errors.ModelNotFoundError):
        pricing.price_list(workshop, "MDL-404")
    assert pricing.price_list(workshop, None).model_id == MODEL_ID  # first visit
    other = add_workshop(session, name="Other")
    row = pricing.price_list(workshop, MODEL_ID).items[1].prices[0]
    with pytest.raises(errors.PriceNotFoundError):
        pricing.update(other, row.price_id, s.PriceUpdateRequest(price=1))


# Regression: ISSUE-003 — the same service was listed once per milestone code
# Found by /qa on 2026-10-10
# Report: .gstack/qa-reports/run-20261009T201844Z/qa-report-localhost-2026-10-10.md
def test_one_row_per_service_and_one_price_for_all_its_codes(world):
    from src.common.core.maintenance.maintenance_rule import MaintenanceRule

    session, workshop, pricing = world
    for km, code in ((12_000, "MI_005"), (24_000, "MI_010")):
        session.add(
            MaintenanceRule(
                model_id=MODEL_ID,
                odo_milestone=km,
                month_milestone=km // 1000,
                item_code=code,
                item_name="Thay lọc gió điều hòa",
                estimated_cost=350_000,
                estimated_duration_minutes=15,
            )
        )
    session.commit()
    filters = [i for i in pricing.price_list(workshop, MODEL_ID).items if i.item_name == "Thay lọc gió điều hòa"]
    assert len(filters) == 1 and filters[0].item_codes == ["MI_005", "MI_010"] and filters[0].priced_codes == 0

    out = pricing.set_prices(
        workshop, s.PriceSetRequest(model_id=MODEL_ID, item_codes=["MI_005", "MI_010"], price=330_000)
    )
    item = next(i for i in out.items if i.item_name == "Thay lọc gió điều hòa")
    assert item.current_price == 330_000 and item.priced_codes == 2 and not item.mixed_prices
    # Setting again updates today's rows instead of adding overlapping ones.
    out = pricing.set_prices(
        workshop, s.PriceSetRequest(model_id=MODEL_ID, item_codes=["MI_005", "MI_010"], price=300_000)
    )
    item = next(i for i in out.items if i.item_name == "Thay lọc gió điều hòa")
    assert item.current_price == 300_000 and len(item.prices) == 2
    with pytest.raises(errors.InvalidRequestError):
        pricing.set_prices(workshop, s.PriceSetRequest(model_id=MODEL_ID, item_codes=["NOPE"], price=1))


# Regression: design review 2026-10-10 FINDING-001 — the model picker showed "MDL-01…MDL-07"
def test_model_names_come_from_verified_vehicles(world):
    from tests._user_vehicle import add_owner, add_vehicle

    session, workshop, pricing = world
    add_rules(session, "MDL-99")
    assert pricing.price_list(workshop, MODEL_ID).model_names == {MODEL_ID: "VF6 Plus"}  # static table
    vehicle = add_vehicle(session, add_owner(session))  # MDL-03
    vehicle.trim = "Plus 2025"
    session.add(vehicle)
    session.commit()
    out = pricing.price_list(workshop, MODEL_ID)
    assert out.models == [MODEL_ID, "MDL-99"]
    assert out.model_names == {MODEL_ID: "VF6 Plus 2025"}  # the snapshot beats the static table; MDL-99 shows its code


# Regression: the picker showed "MDL-02", "MDL-03" for VF6 Eco/Plus because no owner had verified one.
def test_catalog_names_cover_models_without_a_vehicle(world):
    from tests._user_vehicle import add_owner, add_vehicle

    session, workshop, _ = world
    add_rules(session, "MDL-07")
    add_vehicle(session, add_owner(session))  # MDL-03 snapshot "VF6 Plus"
    pricing = WorkshopPricingService(
        session, clock=lambda: NOW, catalog_names={"MDL-07": "VF9 Plus", MODEL_ID: "VF6 Plus (catalog)"}
    )
    assert pricing.price_list(workshop, MODEL_ID).model_names == {MODEL_ID: "VF6 Plus (catalog)", "MDL-07": "VF9 Plus"}


class _Gateway:
    def __init__(self, models=None, error: Exception | None = None):
        self.models, self.error, self.calls = models or [], error, 0

    async def list_models(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.models


def test_catalog_names_are_cached_and_tolerate_an_outage():
    import asyncio

    from src.modules.workshop_pricing import catalog

    catalog.clear_cache()
    down = _Gateway(error=TimeoutError("down"))
    assert asyncio.run(catalog.catalog_names(down, clock=lambda: 0)) == {}

    up = _Gateway(
        [
            {"model_id": "MDL-02", "model_name": "VF6", "trim": "Eco"},
            {"model_id": "MDL-08", "model_name": "VF Wild", "trim": "Plus"},
        ]
    )
    start = catalog.FAILURE_TTL_SECONDS + 1
    assert asyncio.run(catalog.catalog_names(up, clock=lambda: start)) == {
        "MDL-02": "VF6 Eco",
        "MDL-08": "VF Wild Plus",
    }
    asyncio.run(catalog.catalog_names(up, clock=lambda: start + catalog.TTL_SECONDS - 1))
    assert up.calls == 1  # still fresh
    asyncio.run(catalog.catalog_names(up, clock=lambda: start + catalog.TTL_SECONDS + 1))
    assert up.calls == 2
    catalog.clear_cache()


# Regression: with the manufacturer down every price-list request waited out the 2 s timeout (~2.8 s each).
def test_catalog_outage_is_remembered_briefly():
    import asyncio

    from src.modules.workshop_pricing import catalog

    catalog.clear_cache()
    down = _Gateway(error=TimeoutError())
    asyncio.run(catalog.catalog_names(down, clock=lambda: 0))
    assert asyncio.run(catalog.catalog_names(down, clock=lambda: catalog.FAILURE_TTL_SECONDS - 1)) == {}
    assert down.calls == 1  # no second wait while the outage is remembered
    asyncio.run(catalog.catalog_names(down, clock=lambda: catalog.FAILURE_TTL_SECONDS + 1))
    assert down.calls == 2  # then it tries again
    catalog.clear_cache()


def test_catalog_outage_keeps_the_last_names_read():
    import asyncio

    from src.modules.workshop_pricing import catalog

    catalog.clear_cache()
    up = _Gateway([{"model_id": "MDL-02", "model_name": "VF6", "trim": "Eco"}])
    asyncio.run(catalog.catalog_names(up, clock=lambda: 0))
    down = _Gateway(error=TimeoutError())
    later = catalog.TTL_SECONDS + 1
    assert asyncio.run(catalog.catalog_names(down, clock=lambda: later)) == {"MDL-02": "VF6 Eco"}
    assert asyncio.run(catalog.catalog_names(down, clock=lambda: later + 1)) == {"MDL-02": "VF6 Eco"}
    assert down.calls == 1
    catalog.clear_cache()


# Regression: the owner guard's SELECT left the transaction open while the price list waited on
# the manufacturer (up to 2 s), pinning a pooled connection "idle in transaction" (see P1).
def test_price_list_waits_on_the_manufacturer_without_an_open_transaction(world):
    import asyncio

    from sqlmodel import select

    from src.common.core.workshop import Workshop
    from src.modules.workshop_pricing import catalog
    from src.modules.workshop_pricing.route import get_catalog_names

    session, workshop, _ = world
    session.exec(select(Workshop).where(Workshop.id == workshop.id)).first()  # as get_owner_workshop does
    assert session.in_transaction()
    seen: list[bool] = []

    class Gateway(_Gateway):
        async def list_models(self):
            seen.append(session.in_transaction())
            return await super().list_models()

    catalog.clear_cache()
    names = asyncio.run(get_catalog_names(Gateway([{"model_id": "MDL-02", "model_name": "VF6"}]), session))
    assert names == {"MDL-02": "VF6"} and seen == [False]
    assert workshop.name  # loaded rows stay usable
    catalog.clear_cache()


# Regression: with the manufacturer down and no verified vehicle, the picker showed bare "MDL-07".
def test_static_names_cover_an_outage(world):
    session, workshop, pricing = world  # no catalog names, no vehicle
    add_rules(session, "MDL-07")
    add_rules(session, "MDL-99")
    out = pricing.price_list(workshop, MODEL_ID)
    assert out.model_names == {MODEL_ID: "VF6 Plus", "MDL-07": "VF9 Plus"}  # MDL-99 is unknown: its code


def test_picker_lists_models_by_name_then_bare_codes():
    from src.modules.workshop_pricing.service import picker_order

    names = {
        "MDL-01": "VF5 Plus",
        "MDL-07": "VF9 Plus",
        "MDL-08": "VF Wild Plus",
        "MDL-09": "VF3 Eco",
        "MDL-12": "VF9 Eco",
    }
    models = ["MDL-01", "MDL-07", "MDL-08", "MDL-09", "MDL-12", "MDL-99"]
    assert picker_order(models, names) == ["MDL-09", "MDL-01", "MDL-12", "MDL-07", "MDL-08", "MDL-99"]
