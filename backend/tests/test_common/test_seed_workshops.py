"""scripts/seed_workshops.py — active demo workshops from the workshop_crawl output, no Firebase."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from sqlmodel import select

from src.common.core.identity import WorkshopOwner
from src.common.core.workshop import (
    BookingConfirmationMode,
    Workshop,
    WorkshopOperatingHour,
    WorkshopStatus,
)
from tests._workshop_onboarding import make_session

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
_spec = importlib.util.spec_from_file_location("seed_workshops", SCRIPTS / "seed_workshops.py")
seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seed)


def _record(center_id: str, **overrides) -> dict:
    return {
        "center_id": center_id,
        "name": f"Gara {center_id}",
        "region": "Hà Nội",
        "type": "service_only",
        "address": f"1 Phố {center_id}, Hà Nội",
        "latitude": 21.0301,
        "longitude": 105.7915,
        "manager_email": f"Manager.{center_id.lower()}@workshop.example.com",
        "manager_national_id": f"0011900{center_id[-5:]}",
        **overrides,
    }


def test_placeholder_owner_cannot_be_a_firebase_user():
    plan, skipped = seed.build_plan([_record("AL-00001")], set(), set(), set())

    assert skipped == []
    owner = plan[0]["owner"]
    assert owner["firebase_uid"] == "seed:AL-00001"
    assert owner["auth_provider"] == "seed"
    assert owner["email"] == "manager.al-00001@workshop.example.com"


def test_skips_existing_workshops_missing_coordinates_and_taken_owner_identity():
    records = [
        _record("AL-00001"),
        _record("AL-00002", latitude=None),
        _record("AL-00003", manager_email="taken@example.com"),
        _record("AL-00004"),
        _record("AL-00005", manager_national_id="001190000004"),  # duplicate within the file
    ]

    plan, skipped = seed.build_plan(records, {"AL-00001"}, {"taken@example.com"}, set())

    assert [p["workshop"]["external_center_id"] for p in plan] == ["AL-00004"]
    assert [c for c, _ in skipped] == ["AL-00001", "AL-00002", "AL-00003", "AL-00005"]


def test_technician_count_is_stable_and_within_demo_range():
    assert seed.technicians_for("AL-00001") == seed.technicians_for("AL-00001")
    assert {seed.technicians_for(f"AL-{i:05d}") for i in range(50)} <= set(seed.TECHNICIANS)


def test_load_records_filters_by_region(tmp_path):
    source = tmp_path / "workshops.json"
    source.write_text(
        '{"workshops": [{"center_id": "A", "region": "Hà Nội"}, {"center_id": "B", "region": "Huế"}]}',
        encoding="utf-8",
    )

    assert [r["center_id"] for r in seed.load_records(source, "Hà Nội")] == ["A"]


def test_apply_creates_bookable_active_workshops_with_hours():
    plan, _ = seed.build_plan([_record("AL-00001"), _record("AL-00002")], set(), set(), set())

    for session in make_session():
        seed.apply_plan(session, plan)
        session.commit()

        workshops = session.exec(select(Workshop)).all()
        assert len(workshops) == 2
        for w in workshops:
            assert w.status == WorkshopStatus.ACTIVE
            assert w.booking_confirmation_mode == BookingConfirmationMode.AUTO
            assert w.latitude is not None and w.longitude is not None
            owner = session.get(WorkshopOwner, w.owner_id)
            assert owner.firebase_uid == f"seed:{w.external_center_id}"
            # CHECK constraints that exist only in the migration (not in the SQLModel tables):
            assert w.hotline is not None and w.onboarded_at is not None  # ck_workshop_owner_fields
            assert owner.onboarding_completed_at is not None  # ck_workshop_owner_active_completed
            assert owner.profile_completed_at is None or owner.phone is not None  # ck_workshop_owner_profile_complete
            hours = session.exec(select(WorkshopOperatingHour).where(WorkshopOperatingHour.workshop_id == w.id)).all()
            assert sorted(h.day_of_week for h in hours) == [1, 2, 3, 4, 5, 6, 7]
            assert not any(h.is_closed for h in hours)
