"""mock-ev-system demo account: the owner behind EV Care's shared "Dùng thử ngay" account."""

from datetime import date

from fastapi.testclient import TestClient
from mock_ev_system import models as mock_models
from mock_ev_system.db import get_session
from mock_ev_system.demo_account import NATIONAL_ID, OWNER_ID, VEHICLES, ensure_demo_owner
from mock_ev_system.main import app
from mock_ev_system.models import Owner, ServiceHistory, Vehicle, VehicleUsage, Warranty
from mock_ev_system.seed import seed_all
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

MOCK_TABLES = [
    obj.__table__
    for obj in vars(mock_models).values()
    if isinstance(obj, type) and issubclass(obj, SQLModel) and hasattr(obj, "__table__")
]
TODAY = date(2026, 10, 11)


def _engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=MOCK_TABLES)
    with Session(engine) as session:
        seed_all(session)
    return engine


def _demo_vehicles(session: Session) -> list[Vehicle]:
    stmt = select(Vehicle).where(Vehicle.current_owner_id == OWNER_ID).order_by(Vehicle.vehicle_id)
    return list(session.exec(stmt).all())


def test_creates_vf3_vf8_and_vf_wild_once(monkeypatch):
    monkeypatch.delenv("MOCK_DEMO_OWNER_EMAIL", raising=False)
    with Session(_engine()) as session:
        assert ensure_demo_owner(session, today=TODAY) is True
        assert ensure_demo_owner(session, today=TODAY) is False  # idempotent

        owner = session.get(Owner, OWNER_ID)
        assert owner.email == "demo@evcare.invalid"
        vehicles = _demo_vehicles(session)
        assert [v.model_id for v in vehicles] == ["MDL-09", "MDL-05", "MDL-08"]
        assert all(len(v.vin) == 17 for v in vehicles)
        ids = [v.vehicle_id for v in vehicles]
        assert len(session.exec(select(VehicleUsage).where(VehicleUsage.vehicle_id.in_(ids))).all()) == 3
        assert session.exec(select(Warranty).where(Warranty.vehicle_id.in_(ids))).first() is not None
        # Only the VF8 has been serviced (at 15.000 km).
        history = session.exec(select(ServiceHistory).where(ServiceHistory.vehicle_id.in_(ids))).all()
        assert [(h.vehicle_id, h.km_at_service) for h in history] == [("VEH-DEMO-2", 15_100)]


def test_reset_drops_later_rows_and_moves_dates(monkeypatch):
    monkeypatch.delenv("MOCK_DEMO_OWNER_EMAIL", raising=False)
    with Session(_engine()) as session:
        ensure_demo_owner(session, today=date(2026, 1, 1))
        session.add(
            ServiceHistory(
                order_id="SH-LATER",
                vehicle_id="VEH-DEMO-1",
                service_center_id=session.exec(select(ServiceHistory)).first().service_center_id,
                service_date=date(2026, 2, 1),
                km_at_service=5_000,
                items_done="Sửa chữa",
            )
        )
        usage = session.get(VehicleUsage, "VEH-DEMO-1")
        usage.current_km = 9_999
        session.add(usage)
        session.commit()

        assert ensure_demo_owner(session, reset=True, today=TODAY) is True

        assert session.get(ServiceHistory, "SH-LATER") is None
        assert session.get(VehicleUsage, "VEH-DEMO-1").current_km == VEHICLES[0].current_km
        vf3 = session.get(Vehicle, "VEH-DEMO-1")
        assert (TODAY - vf3.manufacture_date).days == VEHICLES[0].age_days


def test_empty_email_turns_the_demo_owner_off(monkeypatch):
    monkeypatch.setenv("MOCK_DEMO_OWNER_EMAIL", "")
    with Session(_engine()) as session:
        assert ensure_demo_owner(session, today=TODAY) is False
        assert session.get(Owner, OWNER_ID) is None


def test_demo_vehicle_passes_the_ownership_check_and_admin_reset(monkeypatch):
    monkeypatch.delenv("MOCK_DEMO_OWNER_EMAIL", raising=False)
    monkeypatch.delenv("MOCK_ADMIN_TOKEN", raising=False)
    engine = _engine()
    with Session(engine) as session:
        ensure_demo_owner(session, today=TODAY)

    def session_dep():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = session_dep
    try:
        client = TestClient(app)
        spec = VEHICLES[2]
        resp = client.post(
            "/vehicles/verify-ownership",
            json={
                "vin": spec.vin,
                "license_plate": spec.license_plate,
                "model_id": spec.model_id,
                "email": "demo@evcare.invalid",
                "national_id": NATIONAL_ID,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["verified"] is True

        assert client.post("/admin/demo-owner/reset").json() == {"status": "reset"}
    finally:
        app.dependency_overrides.clear()
