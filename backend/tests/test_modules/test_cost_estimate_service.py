"""Service tests for the maintenance cost estimate (FEAT-COST-001, us-045).

In-memory SQLite; the F3 next milestone is injected as a plain function.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session

from src.common.core.workshop import Workshop, WorkshopStatus
from src.common.core.workshop.service_price import ServicePrice
from src.modules.booking.location import SimpleTextLocationFinder
from src.modules.cost_estimate import errors
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.vehicle_owner_onboarding.domain import (
    VehicleWarranty,
    WarrantyComponent,
    WarrantyStatus,
)
from tests._maintenance import add_workshop, make_session
from tests._user_vehicle import (
    MODEL_ID,
    NOW,
    PURCHASE_DATE,
    add_owner,
    add_rules,
    add_vehicle,
)


@pytest.fixture
def session():
    yield from make_session()


def _workshop(session: Session, name: str = "VinFast Smart City", status=WorkshopStatus.ACTIVE) -> Workshop:
    return add_workshop(session, name=name, status=status)


def _price(session: Session, workshop: Workshop, code: str, price: int, *, valid_from=None, valid_to=None):
    session.add(
        ServicePrice(
            workshop_id=workshop.id,
            model_id=MODEL_ID,
            item_code=code,
            item_name=code,
            price=price,
            valid_from=valid_from,
            valid_to=valid_to,
        )
    )
    session.commit()


def _chassis(session: Session, vehicle, end: date):
    session.add(
        VehicleWarranty(
            user_vehicle_id=vehicle.id,
            external_warranty_id="WAR-CH",
            component=WarrantyComponent.CHASSIS,
            start_date=PURCHASE_DATE,
            end_date=end,
            oem_status=WarrantyStatus.ACTIVE,
        )
    )
    session.commit()


def _service(session: Session, next_km: int | None = 12_000) -> CostEstimationService:
    return CostEstimationService(session, SimpleTextLocationFinder(), lambda _v: next_km, clock=lambda: NOW)


def test_milestones_mark_next(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    data = _service(session).list_milestones(vehicle)
    assert data.next_odo_milestone == 12_000
    assert [(m.odo_milestone, m.item_count, m.is_next) for m in data.milestones] == [
        (12_000, 2, True),
        (24_000, 1, False),
    ]


def test_estimate_sums_only_chargeable_items(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    _chassis(session, vehicle, date(2030, 1, 1))
    ws = _workshop(session)
    _price(session, ws, "BRAKE_INSPECTION", 300_000)
    _price(session, ws, "BATTERY_CHECK", 999_000)  # covered → ignored

    data = _service(session).estimate_for_request(user, vehicle, odo_milestone=None, workshop_id=ws.id)

    assert data.status == "READY" and data.warranty_status == "ACTIVE"
    assert data.milestone.is_next and data.workshop.selected_by == "REQUEST"
    by_code = {i.item_code: i for i in data.items}
    assert by_code["BATTERY_CHECK"].covered and by_code["BATTERY_CHECK"].price == 0
    assert by_code["BRAKE_INSPECTION"].price_source == "WORKSHOP_PRICE"
    assert data.chargeable_total == Decimal(300_000)
    assert data.covered_count == 1 and data.has_reference_price is False
    # Money serializes as a JSON number, not a string.
    assert data.model_dump(mode="json", by_alias=True)["chargeableTotal"] == 300_000


def test_expired_price_uses_reference_and_expired_warranty_charges_all(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    _chassis(session, vehicle, date(2026, 1, 1))  # expired before NOW
    ws = _workshop(session)
    _price(session, ws, "BRAKE_INSPECTION", 300_000, valid_to=date(2026, 9, 27))  # yesterday

    data = _service(session).estimate_for_request(user, vehicle, odo_milestone=12_000, workshop_id=ws.id)

    assert data.warranty_status == "EXPIRED"
    assert all(not i.covered for i in data.items)
    assert all(i.price_source == "REFERENCE_PRICE" for i in data.items)
    assert data.chargeable_total == Decimal(200_000)  # 2 × reference 100,000
    assert data.has_reference_price


def test_no_rule_returns_no_numbers(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    data = _service(session).estimate_for_request(user, vehicle, odo_milestone=None, workshop_id=None)
    assert data.status == "NO_RULE" and data.chargeable_total is None and data.items == []


def test_unknown_milestone_lists_valid_ones(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    ws = _workshop(session)
    with pytest.raises(errors.MilestoneNotFoundError) as exc:
        _service(session).estimate_for_request(user, vehicle, odo_milestone=13_000, workshop_id=ws.id)
    assert exc.value.details == {"validMilestones": [12_000, 24_000]}
    with pytest.raises(errors.MilestoneRequiredError):
        _service(session, next_km=None).estimate_for_request(user, vehicle, odo_milestone=None, workshop_id=ws.id)


def test_default_workshop_preferred_then_required(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    with pytest.raises(errors.WorkshopRequiredError):
        _service(session).estimate_for_request(user, vehicle, odo_milestone=None, workshop_id=None)

    ws = _workshop(session)
    user.preferred_workshop_id = ws.id
    session.add(user)
    session.commit()
    data = _service(session).estimate_for_request(user, vehicle, odo_milestone=None, workshop_id=None)
    assert data.workshop.selected_by == "PREFERRED"


def test_inactive_workshop_and_foreign_vehicle(session):
    user = add_owner(session)
    other = add_owner(session, uid="uid-2", email="o2@example.com")
    vehicle = add_vehicle(session, user)
    add_rules(session)
    inactive = _workshop(session, "Closed", status=WorkshopStatus.INACTIVE)
    with pytest.raises(errors.WorkshopNotFoundError):
        _service(session).estimate_for_request(user, vehicle, odo_milestone=None, workshop_id=inactive.id)
    with pytest.raises(errors.VehicleNotFoundError):
        _service(session).get_owned_active_vehicle(other, vehicle.id)


def test_compare_sorts_by_total_and_reports_failures(session):
    user = add_owner(session)
    vehicle = add_vehicle(session, user)
    add_rules(session)
    cheap, pricey = _workshop(session, "Cheap"), _workshop(session, "Pricey")
    closed = _workshop(session, "Closed", status=WorkshopStatus.INACTIVE)
    _price(session, cheap, "BRAKE_INSPECTION", 50_000)
    _price(session, pricey, "BRAKE_INSPECTION", 500_000)

    data = _service(session).compare(user, vehicle, odo_milestone=12_000, workshop_ids=[pricey.id, closed.id, cheap.id])
    assert [e.workshop.name for e in data.estimates[:2]] == ["Cheap", "Pricey"]
    assert data.estimates[2].error.code == "WORKSHOP_NOT_FOUND"

    with pytest.raises(errors.InvalidRequestError):
        _service(session).compare(user, vehicle, odo_milestone=None, workshop_ids=[cheap.id])
