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
    add_rules(session, "MDL-07")
    assert pricing.price_list(workshop, MODEL_ID).model_names == {}  # no vehicle yet: the UI shows the code
    add_vehicle(session, add_owner(session))  # MDL-03, VF6 Plus
    out = pricing.price_list(workshop, MODEL_ID)
    assert out.models == [MODEL_ID, "MDL-07"]
    assert out.model_names == {MODEL_ID: "VF6 Plus"}
