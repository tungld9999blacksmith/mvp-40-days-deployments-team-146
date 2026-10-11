"""mock-ev-system service centers: optional location (tools/workshop_crawl) and the paginated listing."""

import pytest
from fastapi.testclient import TestClient
from mock_ev_system import db as mock_db
from mock_ev_system import models as mock_models
from mock_ev_system.db import get_session
from mock_ev_system.main import app
from mock_ev_system.models import CenterType, ServiceCenter
from mock_ev_system.routers.lookup import _center_out
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

MOCK_TABLES = [
    obj.__table__
    for obj in vars(mock_models).values()
    if isinstance(obj, type) and issubclass(obj, SQLModel) and hasattr(obj, "__table__")
]

# service_center as written by seed-data/ev-mock-dump.sql before the location columns existed.
OLD_SCHEMA = """
CREATE TABLE service_center (
    center_id VARCHAR NOT NULL, name VARCHAR NOT NULL, region VARCHAR NOT NULL,
    type VARCHAR(12) NOT NULL, manager_email VARCHAR NOT NULL, manager_national_id VARCHAR NOT NULL,
    PRIMARY KEY (center_id)
);
INSERT INTO "service_center" VALUES('SC-01','VinFast Thăng Long','Hà Nội','dealer','a@example.com','001190000101');
"""


def test_old_dump_gets_location_columns(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    raw = engine.raw_connection()
    raw.driver_connection.executescript(OLD_SCHEMA)
    raw.close()
    monkeypatch.setattr(mock_db, "engine", engine)

    mock_db._add_missing_columns(MOCK_TABLES)

    with Session(engine) as session:
        center = session.exec(select(ServiceCenter)).one()
        assert center.name == "VinFast Thăng Long"
        assert (center.address, center.latitude, center.longitude, center.place_id) == (None, None, None, None)
        center.latitude, center.longitude = 21.0285, 105.8048
        session.add(center)
        session.commit()
        assert session.exec(select(ServiceCenter)).one().latitude == 21.0285


def test_lookup_returns_location():
    center = ServiceCenter(
        center_id="GM-1",
        name="Gara A",
        region="Hà Nội",
        type=CenterType.service_only,
        manager_email="m@example.com",
        manager_national_id="001",
        address="1 Phố Huế, Hà Nội",
        latitude=21.01,
        longitude=105.85,
    )
    out = _center_out(center)
    assert (out["address"], out["latitude"], out["longitude"]) == ("1 Phố Huế, Hà Nội", 21.01, 105.85)


# ── GET /service-centers — pagination + filters ─────────────────────


@pytest.fixture
def listing_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    ServiceCenter.__table__.create(engine)
    rows = [
        ("GM-1", "VinFast Long Biên", "Hà Nội", CenterType.dealer, "1 Nguyễn Văn Cừ, Long Biên, Hà Nội"),
        ("GM-2", "Gara Minh Phát", "Hà Nội", CenterType.service_only, "12 Phố Huế, Hai Bà Trưng, Hà Nội"),
        ("GM-3", "Gara An Khang", "Hà Nội", CenterType.service_only, None),
        ("GM-4", "VinFast Quận 7", "TP. Hồ Chí Minh", CenterType.dealer, "Nguyễn Văn Linh, Quận 7"),
        ("GM-5", "Gara Sông Hàn", "Đà Nẵng", CenterType.service_only, "Bạch Đằng, Hải Châu"),
    ]
    with Session(engine) as session:
        for cid, name, region, kind, address in rows:
            session.add(
                ServiceCenter(
                    center_id=cid,
                    name=name,
                    region=region,
                    type=kind,
                    manager_email=f"{cid.lower()}@example.com",
                    manager_national_id="001",
                    address=address,
                )
            )
        session.commit()

    def isolated_session():
        with Session(engine) as session:
            yield session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_session] = isolated_session
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def _ids(resp) -> list[str]:
    return [c["center_id"] for c in resp.json()["items"]]


def test_listing_paginates_sorted_by_region_then_name(listing_client):
    first = listing_client.get("/service-centers", params={"page_size": 2})
    body = first.json()
    assert (body["total"], body["page"], body["page_size"], body["total_pages"]) == (5, 1, 2, 3)
    # Đà Nẵng < Hà Nội < TP. Hồ Chí Minh (accent-folded); names sorted inside a region.
    assert _ids(first) == ["GM-5", "GM-3"]
    assert _ids(listing_client.get("/service-centers", params={"page_size": 2, "page": 2})) == ["GM-2", "GM-1"]
    assert _ids(listing_client.get("/service-centers", params={"page_size": 2, "page": 3})) == ["GM-4"]
    assert _ids(listing_client.get("/service-centers", params={"page_size": 2, "page": 9})) == []


def test_listing_filters_ignore_accents_and_case(listing_client):
    assert _ids(listing_client.get("/service-centers", params={"region": "ha noi"})) == ["GM-3", "GM-2", "GM-1"]
    assert _ids(listing_client.get("/service-centers", params={"q": "VINFAST"})) == ["GM-1", "GM-4"]
    assert _ids(listing_client.get("/service-centers", params={"q": "pho hue"})) == ["GM-2"]  # address match
    resp = listing_client.get("/service-centers", params={"region": "Hà Nội", "type": "dealer"})
    assert _ids(resp) == ["GM-1"] and resp.json()["total"] == 1


def test_listing_validates_paging(listing_client):
    assert listing_client.get("/service-centers", params={"page": 0}).status_code == 422
    assert listing_client.get("/service-centers", params={"page_size": 101}).status_code == 422
    assert listing_client.get("/service-centers", params={"type": "garage"}).status_code == 422
