"""Tests for mock-ev-system dev accounts: data generated from MOCK_DEV_OWNER_EMAILS is deterministic."""

import pytest
from mock_ev_system import models as mock_models
from mock_ev_system.dev_accounts import ensure_dev_owners
from mock_ev_system.models import Owner, ServiceHistory, Vehicle, VehicleUsage, Warranty
from mock_ev_system.seed import seed_all
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

EMAIL = "dev.owner@gmail.com"
OTHER = "someone.else@gmail.com"

# Only the mock's tables: SQLModel.metadata also holds the app's PostgreSQL-only tables.
MOCK_TABLES = [
    obj.__table__
    for obj in vars(mock_models).values()
    if isinstance(obj, type) and issubclass(obj, SQLModel) and hasattr(obj, "__table__")
]


def _generate(monkeypatch, emails: str, vehicles: int = 2, extra_owner: bool = False) -> dict:
    """Run ensure_dev_owners on a fresh seeded DB and return the rows created for EMAIL."""
    monkeypatch.setenv("MOCK_DEV_OWNER_EMAILS", emails)
    monkeypatch.setenv("MOCK_DEV_OWNER_VEHICLES", str(vehicles))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=MOCK_TABLES)
    with Session(engine) as session:
        seed_all(session)
        if extra_owner:
            session.add(
                Owner(
                    owner_id="OWN-999",
                    full_name="Extra",
                    phone="0900000000",
                    email="extra@example.com",
                    national_id="079299999999",
                )
            )
            session.commit()
        ensure_dev_owners(session)

        owner = session.exec(select(Owner).where(Owner.email == EMAIL)).one()
        vehicles = session.exec(select(Vehicle).where(Vehicle.current_owner_id == owner.owner_id)).all()
        vehicle_ids = [v.vehicle_id for v in vehicles]

        def rows(model, column):
            return sorted(
                (r.model_dump() for r in session.exec(select(model).where(column.in_(vehicle_ids))).all()),
                key=str,
            )

        return {
            "owner": owner.model_dump(),
            "vehicles": sorted((v.model_dump() for v in vehicles), key=lambda v: v["vehicle_id"]),
            "usage": rows(VehicleUsage, VehicleUsage.vehicle_id),
            "warranties": rows(Warranty, Warranty.vehicle_id),
            "services": rows(ServiceHistory, ServiceHistory.vehicle_id),
        }


def test_same_email_gives_same_data(monkeypatch):
    first = _generate(monkeypatch, EMAIL)
    assert first == _generate(monkeypatch, EMAIL)
    assert first["owner"]["owner_id"].startswith("OWN-DEV-")
    assert first["services"], "expected some service history"


def test_independent_of_order_other_emails_and_existing_rows(monkeypatch):
    alone = _generate(monkeypatch, EMAIL)
    assert alone == _generate(monkeypatch, f"{OTHER},{EMAIL}", extra_owner=True)


@pytest.mark.parametrize("today", ["2026-01-15", "2030-06-30"])
def test_independent_of_run_date(monkeypatch, today):
    import datetime as real_datetime

    from mock_ev_system import dev_accounts

    baseline = _generate(monkeypatch, EMAIL)

    class FakeDate(real_datetime.date):
        @classmethod
        def today(cls):
            return real_datetime.date.fromisoformat(today)

    monkeypatch.setattr(dev_accounts, "date", FakeDate)
    assert baseline == _generate(monkeypatch, EMAIL)


def test_reference_date_env_changes_dates_only_when_set(monkeypatch):
    baseline = _generate(monkeypatch, EMAIL)
    monkeypatch.setenv("MOCK_DEV_REFERENCE_DATE", "2030-01-01")
    later = _generate(monkeypatch, EMAIL)
    assert later["owner"] == baseline["owner"]
    assert [v["vin"] for v in later["vehicles"]] == [v["vin"] for v in baseline["vehicles"]]
    assert later["usage"] != baseline["usage"]


def test_more_vehicles_keep_the_first_ones(monkeypatch):
    two = _generate(monkeypatch, EMAIL, vehicles=2)
    three = _generate(monkeypatch, EMAIL, vehicles=3)
    assert three["owner"] == two["owner"]
    assert three["vehicles"][:2] == two["vehicles"]


def test_fixed_national_id_does_not_shift_other_fields(monkeypatch):
    generated = _generate(monkeypatch, EMAIL)
    fixed = _generate(monkeypatch, f"{EMAIL}:079200001234")
    assert fixed["owner"]["national_id"] == "079200001234"
    assert fixed["owner"]["phone"] == generated["owner"]["phone"]
    assert fixed["vehicles"] == generated["vehicles"]
