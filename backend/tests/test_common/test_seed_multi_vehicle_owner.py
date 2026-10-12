"""scripts/seed_multi_vehicle_owner.py — link the other manufacturer vehicles of a dev owner (issue #27)."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ev_contracts import OwnershipVerifyFailureReason, OwnershipVerifyRequest, OwnershipVerifyResponse
from sqlmodel import select

from src.common.core.identity.vehicle_user import OnboardingStatus, VehicleUser
from src.common.core.vehicle import OemSyncTrigger
from src.common.core.vehicle.user_vehicle import UserVehicle, VehicleLinkStatus, VehicleVerificationStatus
from src.modules.vehicle_owner_onboarding.domain import VehicleWarranty
from src.modules.vehicle_owner_onboarding.ports import OemTimeoutError
from tests._onboarding import (
    GOOGLE_EMAIL,
    NATIONAL_ID,
    StubOemGateway,
    failure_response,
    make_session,
    verified_response,
)
from tests._user_vehicle import RecordingScheduler

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
_spec = importlib.util.spec_from_file_location("seed_multi_vehicle_owner", SCRIPTS / "seed_multi_vehicle_owner.py")
seed = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = seed  # dataclasses resolve annotations through sys.modules
_spec.loader.exec_module(seed)

FIRST_VIN = "VF6PLUS2024000001"
SECOND_VIN = "VF8ECO20230000001"
THIRD_VIN = "VF5PLUS2024000001"
OEM_VEHICLES = [
    {"vehicle_id": "VEH-006", "vin": FIRST_VIN, "license_plate": "29A-444.44", "model_id": "MDL-03"},
    {"vehicle_id": "VEH-002", "vin": SECOND_VIN, "license_plate": "30A-678.90", "model_id": "MDL-05"},
    {"vehicle_id": "VEH-001", "vin": THIRD_VIN, "license_plate": "30A-123.45", "model_id": "MDL-01"},
]


class PerVinGateway(StubOemGateway):
    """Verifies every VIN except the ones told to fail or time out."""

    def __init__(self, *, rejected: set[str] = frozenset(), unavailable: set[str] = frozenset()) -> None:
        super().__init__()
        self.rejected = rejected
        self.unavailable = unavailable
        self.requests: list[OwnershipVerifyRequest] = []

    async def verify_ownership(self, request: OwnershipVerifyRequest) -> OwnershipVerifyResponse:
        self.requests.append(request)
        if request.vin in self.unavailable:
            raise OemTimeoutError("down")
        if request.vin in self.rejected:
            return failure_response(OwnershipVerifyFailureReason.PLATE_MISMATCH)
        return verified_response()


async def _fetch(_owner_id: str) -> list[dict]:
    return OEM_VEHICLES


@pytest.fixture
def session():
    yield from make_session()


@pytest.fixture
def owner(session) -> VehicleUser:
    user = VehicleUser(
        firebase_uid="uid-1",
        email=GOOGLE_EMAIL,
        national_id=NATIONAL_ID,
        external_owner_id="OWN-004",
        onboarding_status=OnboardingStatus.ACTIVE,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    first = UserVehicle(
        user_id=user.user_id,
        vin=FIRST_VIN,
        license_plate="29A44444",
        declared_model_id="MDL-03",
        verification_status=VehicleVerificationStatus.VERIFIED,
        created_at=datetime.now(UTC) - timedelta(days=30),
    )
    session.add(first)
    session.commit()
    return user


def _active_vins(session, owner) -> list[str]:
    rows = session.exec(
        select(UserVehicle).where(
            UserVehicle.user_id == owner.user_id, UserVehicle.link_status == VehicleLinkStatus.ACTIVE
        )
    ).all()
    return sorted(v.vin for v in rows)


async def _run(session, gateway, scheduler=None, **kwargs) -> int:
    return await seed.run(
        session,
        email=GOOGLE_EMAIL,
        fetch_owner_vehicles=_fetch,
        gateway=gateway,
        scheduler=scheduler,
        **{"undo": False, "apply": True, **kwargs},
    )


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(session, owner):
    gateway = PerVinGateway()

    assert await _run(session, gateway, apply=False) == 0

    assert gateway.requests == []
    assert _active_vins(session, owner) == [FIRST_VIN]


@pytest.mark.asyncio
async def test_apply_links_the_missing_vehicles_once(session, owner):
    gateway = PerVinGateway()
    scheduler = RecordingScheduler()

    assert await _run(session, gateway, scheduler) == 0
    assert _active_vins(session, owner) == sorted([FIRST_VIN, SECOND_VIN, THIRD_VIN])
    # Same ownership check as onboarding: the owner's email and national id.
    assert {(r.vin, r.email, r.national_id) for r in gateway.requests} == {
        (SECOND_VIN, GOOGLE_EMAIL, NATIONAL_ID),
        (THIRD_VIN, GOOGLE_EMAIL, NATIONAL_ID),
    }
    new = session.exec(select(UserVehicle).where(UserVehicle.vin == SECOND_VIN)).one()
    assert new.verification_status == VehicleVerificationStatus.VERIFIED
    assert new.license_plate == "30A67890"
    assert session.exec(select(VehicleWarranty).where(VehicleWarranty.user_vehicle_id == new.id)).all()
    added = session.exec(select(UserVehicle).where(UserVehicle.vin.in_([SECOND_VIN, THIRD_VIN]))).all()
    assert sorted((str(call_id), trigger) for call_id, trigger, _ in scheduler.calls) == sorted(
        (str(v.id), OemSyncTrigger.INITIAL) for v in added
    )

    again = PerVinGateway()
    assert await _run(session, again) == 0
    assert again.requests == []
    assert len(session.exec(select(UserVehicle)).all()) == 3


@pytest.mark.asyncio
async def test_vin_filter_links_only_the_named_vehicles(session, owner):
    gateway = PerVinGateway()

    assert await _run(session, gateway, only_vins={THIRD_VIN}) == 0

    assert [r.vin for r in gateway.requests] == [THIRD_VIN]
    assert _active_vins(session, owner) == sorted([FIRST_VIN, THIRD_VIN])


@pytest.mark.asyncio
async def test_failed_vins_are_skipped_and_reported(session, owner, capsys):
    gateway = PerVinGateway(rejected={SECOND_VIN}, unavailable={THIRD_VIN})

    assert await _run(session, gateway) == 1

    assert _active_vins(session, owner) == [FIRST_VIN]
    out = capsys.readouterr().out
    assert f"FAILED   {SECOND_VIN}: PLATE_MISMATCH" in out
    assert f"FAILED   {THIRD_VIN}: manufacturer unavailable" in out


@pytest.mark.asyncio
async def test_undo_keeps_the_oldest_and_relink_reuses_rows(session, owner):
    await _run(session, PerVinGateway())
    rows_before = {v.vin: v.id for v in session.exec(select(UserVehicle)).all()}

    assert await _run(session, PerVinGateway(), undo=True, apply=False) == 0
    assert len(_active_vins(session, owner)) == 3

    assert await _run(session, PerVinGateway(), undo=True) == 0
    assert _active_vins(session, owner) == [FIRST_VIN]

    assert await _run(session, PerVinGateway()) == 0
    assert _active_vins(session, owner) == sorted([FIRST_VIN, SECOND_VIN, THIRD_VIN])
    assert {v.vin: v.id for v in session.exec(select(UserVehicle)).all()} == rows_before


@pytest.mark.asyncio
async def test_owner_must_have_finished_onboarding(session, owner):
    owner.onboarding_status = OnboardingStatus.PENDING_VEHICLE_VERIFICATION
    session.add(owner)
    session.commit()

    with pytest.raises(seed.SeedError, match="has not finished onboarding"):
        await _run(session, PerVinGateway())
