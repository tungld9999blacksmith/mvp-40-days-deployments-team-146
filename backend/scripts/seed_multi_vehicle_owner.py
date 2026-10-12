"""
Link the other manufacturer vehicles of an EV Care owner, so the owner app shows the vehicle
picker (issue #27). Dev / QA accounts only: the in-app "add a vehicle" flow is a separate spec.

The owner must have finished onboarding (``onboarding_status = active`` with an
``external_owner_id``). The script reads the owner's vehicles from mock-ev-system
(``GET /owners/{external_owner_id}``), verifies every VIN that is not linked yet with the same
ownership check as onboarding (owner email + national id), and links it: ``link_status = active``,
the manufacturer snapshot and warranties, then the initial OEM sync. A VIN unlinked earlier gets
its old ``user_vehicle`` row back instead of a new one, so re-runs never duplicate vehicles.

Each VIN commits on its own. A VIN the manufacturer rejects or cannot answer is reported and
skipped; the exit code is then 1. A failed initial-sync enqueue is only logged: API-VEH-003
re-enqueues a lost initial sync, as after onboarding.

``--undo`` unlinks every ACTIVE vehicle of the owner except the oldest one. It also unlinks
vehicles the script did not add, hence dev / QA accounts only. Rows are unlinked, never deleted
(bookings reference them).

mock-ev-system gives each dev email two vehicles with ``MOCK_DEV_OWNER_VEHICLES=2``.

Run from backend/ (reads the root .env). Nothing is written without ``--apply``:
    python scripts/seed_multi_vehicle_owner.py --email <email>                 # plan only
    python scripts/seed_multi_vehicle_owner.py --email <email> --apply         # link the vehicles
    python scripts/seed_multi_vehicle_owner.py --email <email> --vin <VIN> --vin <VIN> --apply  # only these
    python scripts/seed_multi_vehicle_owner.py --email <email> --undo          # plan the undo
    python scripts/seed_multi_vehicle_owner.py --email <email> --undo --apply  # keep the oldest only
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ev_contracts import OwnershipVerifyRequest, normalize_plate, normalize_vin  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from src.common.core.identity.vehicle_user import OnboardingStatus, VehicleUser  # noqa: E402
from src.common.core.vehicle import OemSyncTrigger  # noqa: E402
from src.common.core.vehicle.user_vehicle import (  # noqa: E402
    UserVehicle,
    VehicleLinkStatus,
    VehicleVerificationStatus,
)
from src.modules.oem_integration.ports import SyncScheduler  # noqa: E402
from src.modules.vehicle_owner_onboarding.ports import OemTimeoutError, OemVehicleGateway  # noqa: E402
from src.modules.vehicle_owner_onboarding.service import apply_verified_vehicle  # noqa: E402

logger = logging.getLogger(__name__)

OwnerVehiclesFetcher = Callable[[str], Awaitable[list[dict[str, Any]]]]


class SeedError(Exception):
    """The owner cannot be seeded (unknown email, onboarding not finished...)."""


@dataclass(frozen=True)
class LinkStep:
    vin: str
    license_plate: str
    model_id: str
    # The owner's unlinked row for this VIN, reused instead of a new row.
    existing_id: UUID | None = None

    @property
    def action(self) -> str:
        return "reactivate" if self.existing_id else "link"


@dataclass
class SeedResult:
    linked: list[UserVehicle]
    failed: list[tuple[str, str]]


def find_owner(session: Session, email: str) -> VehicleUser:
    owner = session.exec(select(VehicleUser).where(VehicleUser.email == email.strip().lower())).first()
    if owner is None:
        raise SeedError(f"No EV Care owner with email {email}.")
    if owner.onboarding_status != OnboardingStatus.ACTIVE or not owner.external_owner_id:
        raise SeedError(f"{email} has not finished onboarding (status {owner.onboarding_status}).")
    if not owner.national_id:
        raise SeedError(f"{email} has no national id; the ownership check needs it.")
    return owner


def owner_vehicles(session: Session, owner: VehicleUser) -> list[UserVehicle]:
    stmt = select(UserVehicle).where(UserVehicle.user_id == owner.user_id).order_by(UserVehicle.created_at)
    return list(session.exec(stmt).all())


def build_link_plan(
    linked: list[UserVehicle], oem_vehicles: list[dict[str, Any]], only_vins: set[str] | None = None
) -> list[LinkStep]:
    """Manufacturer vehicles the owner has not linked yet (unlinked rows are reused), optionally only ``only_vins``."""
    active = {v.vin for v in linked if v.link_status == VehicleLinkStatus.ACTIVE}
    unlinked = {v.vin: v.id for v in linked if v.link_status == VehicleLinkStatus.UNLINKED}
    plan: list[LinkStep] = []
    for item in oem_vehicles:
        vin = normalize_vin(item["vin"])
        if vin in active or any(step.vin == vin for step in plan) or (only_vins and vin not in only_vins):
            continue
        plan.append(
            LinkStep(
                vin=vin,
                license_plate=item["license_plate"],
                model_id=item["model_id"],
                existing_id=unlinked.get(vin),
            )
        )
    return plan


def build_undo_plan(linked: list[UserVehicle]) -> list[UserVehicle]:
    """Every ACTIVE vehicle except the oldest one (``linked`` is ordered by ``created_at``)."""
    return [v for v in linked if v.link_status == VehicleLinkStatus.ACTIVE][1:]


async def link_vehicles(
    session: Session,
    owner: VehicleUser,
    plan: list[LinkStep],
    gateway: OemVehicleGateway,
    scheduler: SyncScheduler | None,
) -> SeedResult:
    result = SeedResult(linked=[], failed=[])
    for step in plan:
        request = OwnershipVerifyRequest(
            vin=step.vin,
            license_plate=step.license_plate,
            model_id=step.model_id,
            email=owner.email or "",
            national_id=owner.national_id or "",
        )
        try:
            response = await gateway.verify_ownership(request)
        except OemTimeoutError as exc:
            result.failed.append((step.vin, f"manufacturer unavailable: {exc}"))
            continue
        if not response.verified or response.vehicle is None:
            reason = response.failure_reason.value if response.failure_reason else "not verified"
            result.failed.append((step.vin, reason))
            continue

        vehicle = session.get(UserVehicle, step.existing_id) if step.existing_id else None
        if vehicle is None:
            vehicle = UserVehicle(user_id=owner.user_id, vin=step.vin, license_plate="", declared_model_id="")
        vehicle.license_plate = normalize_plate(step.license_plate)
        vehicle.declared_model_id = step.model_id
        vehicle.link_status = VehicleLinkStatus.ACTIVE
        session.add(vehicle)
        session.flush()  # assign the PK before the warranties reference it
        try:
            apply_verified_vehicle(session, vehicle, response)
            session.commit()
        except Exception as exc:  # noqa: BLE001 — report the VIN and keep going
            session.rollback()
            result.failed.append((step.vin, f"database error: {exc}"))
            continue
        session.refresh(vehicle)
        result.linked.append(vehicle)
        if scheduler is not None:
            try:
                scheduler.schedule(vehicle.id, OemSyncTrigger.INITIAL)
            except Exception:  # noqa: BLE001 — API-VEH-003 re-enqueues a lost initial sync
                logger.exception("could not enqueue initial OEM sync for %s", vehicle.id)
    return result


def apply_undo(session: Session, vehicles: list[UserVehicle]) -> None:
    for vehicle in vehicles:
        vehicle.link_status = VehicleLinkStatus.UNLINKED
        session.add(vehicle)
    session.commit()


def _describe(vehicle: UserVehicle) -> str:
    verified = (
        "verified" if vehicle.verification_status == VehicleVerificationStatus.VERIFIED else vehicle.verification_status
    )
    return f"{vehicle.vin} {vehicle.license_plate} {vehicle.model_name or vehicle.declared_model_id} ({verified})"


async def run(
    session: Session,
    *,
    email: str,
    undo: bool,
    apply: bool,
    only_vins: set[str] | None = None,
    fetch_owner_vehicles: OwnerVehiclesFetcher,
    gateway: OemVehicleGateway,
    scheduler: SyncScheduler | None,
) -> int:
    owner = find_owner(session, email)
    linked = owner_vehicles(session, owner)

    if undo:
        targets = build_undo_plan(linked)
        print(f"{len(targets)} vehicle(s) to unlink for {email}; the oldest one stays linked.")
        for vehicle in targets:
            print(f"  unlink  {_describe(vehicle)}")
        if apply and targets:
            apply_undo(session, targets)
            print("Unlinked.")
        elif not apply:
            print("Dry run: add --apply to write.")
        return 0

    plan = build_link_plan(linked, await fetch_owner_vehicles(owner.external_owner_id or ""), only_vins)
    print(f"{len(plan)} new vehicle(s) to link for {email} (manufacturer owner {owner.external_owner_id}).")
    for step in plan:
        print(f"  {step.action:<10} {step.vin} {step.license_plate} {step.model_id}")
    if not apply:
        print("Dry run: add --apply to write.")
        return 0

    result = await link_vehicles(session, owner, plan, gateway, scheduler)
    for vehicle in result.linked:
        print(f"  linked   {_describe(vehicle)}")
    for vin, reason in result.failed:
        print(f"  FAILED   {vin}: {reason}")
    print(f"{len(result.linked)} linked, {len(result.failed)} failed.")
    return 1 if result.failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Link the other manufacturer vehicles of a dev/QA owner.")
    parser.add_argument("--email", required=True, help="Google email of an onboarded EV Care owner")
    parser.add_argument("--vin", action="append", help="Only link this VIN (repeatable; default: every vehicle)")
    parser.add_argument("--undo", action="store_true", help="Unlink every vehicle except the oldest one")
    parser.add_argument("--apply", action="store_true", help="Write to the database (default: dry run)")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(BACKEND_DIR.parent / ".env")

    from src.config import get_settings
    from src.infrastructure.oem.gateway import HttpOemVehicleGateway, OemHttpClient
    from src.infrastructure.supabase.db import engine
    from src.modules.oem_integration.dependency import sync_scheduler_for

    settings = get_settings()
    oem = OemHttpClient.from_settings(settings)

    async def fetch_owner_vehicles(external_owner_id: str) -> list[dict[str, Any]]:
        resp = await oem.request("GET", f"/owners/{external_owner_id}")
        resp.raise_for_status()
        return resp.json()["vehicles"]

    gateway = HttpOemVehicleGateway(oem)
    with Session(engine) as session:
        try:
            return asyncio.run(
                run(
                    session,
                    email=args.email,
                    undo=args.undo,
                    apply=args.apply,
                    only_vins={normalize_vin(v) for v in args.vin} if args.vin else None,
                    fetch_owner_vehicles=fetch_owner_vehicles,
                    gateway=gateway,
                    scheduler=sync_scheduler_for(settings) if args.apply else None,
                )
            )
        except SeedError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
