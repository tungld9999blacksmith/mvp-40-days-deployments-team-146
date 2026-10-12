"""mock-ev-system POST /admin/import."""

from fastapi.testclient import TestClient
from mock_ev_system import models as mock_models
from mock_ev_system.db import get_session
from mock_ev_system.main import app
from mock_ev_system.models import MaintenanceSchedule, VehicleModel
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

MOCK_TABLES = [
    obj.__table__
    for obj in vars(mock_models).values()
    if isinstance(obj, type) and issubclass(obj, SQLModel) and hasattr(obj, "__table__")
]


# Regression: importing maintenance_schedules failed with "Incompatible collection type:
# builtin_function_or_method" because SQLModel read the `items` relationship off the dict.
def test_import_a_model_with_its_schedule():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine, tables=MOCK_TABLES)

    def session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = session
    try:
        resp = TestClient(app).post(
            "/admin/import",
            json={
                "mode": "insert",
                "data": {
                    "vehicle_models": [
                        {
                            "model_id": "MDL-09",
                            "model_name": "VF3",
                            "trim": "Eco",
                            "battery_capacity_kwh": 18.64,
                            "motor_power_kw": 30.0,
                            "production_year": 2024,
                        }
                    ],
                    "maintenance_schedules": [
                        {
                            "schedule_id": "MS-041",
                            "model_id": "MDL-09",
                            "milestone_km": 15000,
                            "milestone_months": 12,
                            "description": "Bảo dưỡng định kỳ 15.000km / 12 tháng",
                        }
                    ],
                },
            },
        )
        bad = TestClient(app).post(
            "/admin/import",
            json={"mode": "insert", "data": {"vehicle_models": [{"model_id": "MDL-10", "model_name": "VF2"}]}},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert resp.status_code == 200, resp.text
    assert bad.status_code == 422 and bad.json()["detail"]["entity"] == "vehicle_models"
    with Session(engine) as s:
        assert s.get(VehicleModel, "MDL-09").model_name == "VF3"
        assert s.get(MaintenanceSchedule, "MS-041").milestone_km == 15000
