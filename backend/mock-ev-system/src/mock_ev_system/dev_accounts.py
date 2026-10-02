"""Dev accounts — create owner + vehicles for real Gmail accounts at startup.

Set ``MOCK_DEV_OWNER_EMAILS`` to a comma separated list of emails; each entry may
carry a fixed national id (CCCD) after a colon::

    MOCK_DEV_OWNER_EMAILS=you@gmail.com,teammate@gmail.com:079200009999
    MOCK_DEV_OWNER_VEHICLES=2

For every email that has no owner yet, the mock creates one owner with
``MOCK_DEV_OWNER_VEHICLES`` vehicles, each with usage, warranties (from the model's
policies) and service history (from the model's maintenance schedule).

Everything is derived from the email, so the same email always gets the same data,
whatever the run date, the order of the emails or the other rows in the database:

- ids come from a hash of the email (``OWN-DEV-<key>``, ``VEH-DEV-<key>-<n>``, ...);
- every field draws from its own RNG seeded by ``email | field | index``, so one
  field (or vehicle) never shifts the values of another;
- dates, ODO, battery SoH and warranty status are computed against a fixed reference
  date (``MOCK_DEV_REFERENCE_DATE``, ISO format, default ``2026-09-01``), not today.

The vehicle models, warranty policies and maintenance schedules come from the base
data (dump or seed), so the output only changes when that data changes. A VIN /
plate / CCCD that clashes with an existing row is redrawn deterministically.
Emails that already exist are left untouched, so it is safe to run on every startup
and after ``/admin/reset``.
"""

import hashlib
import logging
import os
import random
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta

from sqlmodel import Session, select

from .models import (
    DataSource,
    MaintenanceSchedule,
    Owner,
    ServiceCenter,
    ServiceHistory,
    Vehicle,
    VehicleModel,
    VehicleUsage,
    Warranty,
    WarrantyPolicy,
    WarrantyStatus,
)

# uvicorn configures this logger, so the created VIN / plate / CCCD show up in `docker logs`.
logger = logging.getLogger("uvicorn.error")

EMAILS_ENV = "MOCK_DEV_OWNER_EMAILS"
VEHICLES_ENV = "MOCK_DEV_OWNER_VEHICLES"
REFERENCE_DATE_ENV = "MOCK_DEV_REFERENCE_DATE"
DEFAULT_VEHICLES = 2
DEFAULT_REFERENCE_DATE = date(2026, 9, 1)

COLORS = ["Trắng", "Đen", "Xám", "Đỏ", "Xanh dương"]
PLATE_SERIES = "ABCDEFGHK"
KM_PER_YEAR = 15_000


def parse_dev_owners(raw: str) -> list[tuple[str, str | None]]:
    """``"a@x.com, b@x.com:079200009999"`` → ``[("a@x.com", None), ("b@x.com", "079200009999")]``."""
    result: list[tuple[str, str | None]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        email, _, national_id = entry.partition(":")
        email = email.strip().lower()
        national_id = re.sub(r"\D", "", national_id)
        if "@" not in email:
            logger.warning("%s: skipping invalid email %r", EMAILS_ENV, entry)
            continue
        if national_id and len(national_id) != 12:
            logger.warning("%s: national id for %s must have 12 digits, generating one", EMAILS_ENV, email)
            national_id = ""
        result.append((email, national_id or None))
    return result


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    for day in (d.day, 30, 29, 28):
        try:
            return date(d.year + y, m + 1, day)
        except ValueError:
            continue
    raise ValueError(d)


def _rng(email: str, *parts: object) -> random.Random:
    """RNG seeded by the email plus a field name / index, independent of every other draw."""
    seed = "|".join([email, *map(str, parts)])
    return random.Random(int(hashlib.sha256(seed.encode()).hexdigest(), 16))


def _email_key(email: str) -> str:
    """Short stable id fragment for an email, e.g. ``1A2B3C4D``."""
    return hashlib.sha256(email.encode()).hexdigest()[:8].upper()


def _unique(email: str, field: str, make: Callable[[random.Random], str], taken: set[str]) -> str:
    """First value of ``make`` not in ``taken``; each retry uses its own seeded RNG."""
    for attempt in range(1000):
        value = make(_rng(email, field, attempt))
        if value not in taken:
            taken.add(value)
            return value
    raise RuntimeError(f"could not generate a unique {field} for {email}")


def _reference_date() -> date:
    raw = os.getenv(REFERENCE_DATE_ENV, "").strip()
    if not raw:
        return DEFAULT_REFERENCE_DATE
    try:
        return date.fromisoformat(raw)
    except ValueError:
        logger.warning("%s=%r is not an ISO date, using %s", REFERENCE_DATE_ENV, raw, DEFAULT_REFERENCE_DATE)
        return DEFAULT_REFERENCE_DATE


def ensure_dev_owners(session: Session) -> None:
    """Create the owners listed in ``MOCK_DEV_OWNER_EMAILS`` that do not exist yet."""
    entries = parse_dev_owners(os.getenv(EMAILS_ENV, ""))
    if not entries:
        return
    try:
        vehicles_per_owner = max(1, int(os.getenv(VEHICLES_ENV, DEFAULT_VEHICLES)))
    except ValueError:
        vehicles_per_owner = DEFAULT_VEHICLES

    owners = session.exec(select(Owner)).all()
    vehicles = session.exec(select(Vehicle)).all()
    models = sorted(session.exec(select(VehicleModel)).all(), key=lambda m: m.model_id)
    centers = sorted(session.exec(select(ServiceCenter)).all(), key=lambda c: c.center_id)
    if not models or not centers:
        logger.warning("%s: no vehicle models / service centers loaded, skipping", EMAILS_ENV)
        return
    policies = sorted(session.exec(select(WarrantyPolicy)).all(), key=lambda p: p.policy_id)
    schedules = session.exec(select(MaintenanceSchedule)).all()

    owner_ids = {o.owner_id for o in owners}
    emails = {o.email.lower() for o in owners}
    national_ids = {o.national_id for o in owners}
    vins = {v.vin for v in vehicles}
    plates = {v.license_plate for v in vehicles}
    ref = _reference_date()

    for email, fixed_national_id in entries:
        if email in emails:
            logger.info("%s: owner %s already exists, skipping", EMAILS_ENV, email)
            continue
        key = _email_key(email)
        owner_id = f"OWN-DEV-{key}"
        if owner_id in owner_ids:
            logger.warning("%s: owner id %s already used, skipping %s", EMAILS_ENV, owner_id, email)
            continue
        emails.add(email)
        owner_ids.add(owner_id)

        if fixed_national_id and fixed_national_id in national_ids:
            logger.warning(
                "%s: national id %s already used, generating one for %s", EMAILS_ENV, fixed_national_id, email
            )
            fixed_national_id = None
        if fixed_national_id:
            national_id = fixed_national_id
            national_ids.add(national_id)
        else:
            national_id = _unique(email, "national_id", lambda r: f"0792{r.randint(0, 99_999_999):08d}", national_ids)

        local = email.split("@")[0]
        owner = Owner(
            owner_id=owner_id,
            full_name=f"Dev {local}",
            phone=f"09{_rng(email, 'phone').randint(0, 99_999_999):08d}",
            email=email,
            national_id=national_id,
        )
        session.add(owner)

        model_offset = _rng(email, "model").randrange(len(models))
        created: list[str] = []
        for i in range(vehicles_per_owner):
            n = i + 1
            vrnd = _rng(email, "vehicle", n)
            model = models[(model_offset + i) % len(models)]
            mfg = min(
                date(model.production_year, 1, 1) + timedelta(days=vrnd.randint(0, 364)),
                ref - timedelta(days=60),
            )
            stem = f"DEV{model.model_name}{model.trim}".upper().replace(" ", "")[:10]
            digits = 17 - len(stem)
            vin = _unique(email, f"vin{n}", lambda r: f"{stem}{r.randint(0, 10**digits - 1):0{digits}d}", vins)
            plate = _unique(
                email, f"plate{n}", lambda r: f"30{r.choice(PLATE_SERIES)}-{r.randint(10_000, 99_999)}", plates
            )
            vehicle = Vehicle(
                vehicle_id=f"VEH-DEV-{key}-{n}",
                vin=vin,
                model_id=model.model_id,
                current_owner_id=owner.owner_id,
                color=vrnd.choice(COLORS),
                manufacture_date=mfg,
                license_plate=plate,
            )
            session.add(vehicle)

            age_years = max((ref - mfg).days / 365, 0.1)
            current_km = int(age_years * KM_PER_YEAR)
            session.add(
                VehicleUsage(
                    vehicle_id=vehicle.vehicle_id,
                    current_km=current_km,
                    battery_soh=round(max(85.0, 100 - age_years * 1.5), 1),
                    data_source=DataSource.telematics,
                    last_updated_at=datetime.combine(ref, datetime.min.time()).replace(hour=8),
                )
            )

            for policy in (p for p in policies if p.model_id == model.model_id):
                end = _add_months(mfg, policy.duration_months)
                session.add(
                    Warranty(
                        warranty_id=f"WRT-DEV-{key}-{n}-{policy.policy_id}",
                        vehicle_id=vehicle.vehicle_id,
                        policy_id=policy.policy_id,
                        start_date=mfg,
                        end_date=end,
                        km_limit=policy.km_limit,
                        status=WarrantyStatus.active if end > ref else WarrantyStatus.expired,
                    )
                )

            days_owned = max((ref - mfg).days, 1)
            for s in sorted((s for s in schedules if s.model_id == model.model_id), key=lambda s: s.milestone_km):
                if s.milestone_km > current_km:
                    break
                srnd = _rng(email, "service", n, s.milestone_km)
                km = min(s.milestone_km + srnd.randint(-500, 800), current_km)
                served = mfg + timedelta(days=int(days_owned * km / max(current_km, 1)))
                session.add(
                    ServiceHistory(
                        order_id=f"SH-DEV-{key}-{n}-{s.milestone_km}",
                        vehicle_id=vehicle.vehicle_id,
                        service_center_id=srnd.choice(centers).center_id,
                        service_date=min(served, ref),
                        km_at_service=km,
                        items_done=s.description,
                        is_periodic=True,
                        total_cost=srnd.choice([0, 350_000, 900_000, 1_900_000]),
                    )
                )
            created.append(f"{vehicle.vehicle_id} VIN={vin} plate={plate} model={model.model_id}")

        logger.info(
            "%s: created owner %s (%s, CCCD=%s) with vehicles: %s",
            EMAILS_ENV,
            owner.owner_id,
            email,
            national_id,
            "; ".join(created),
        )
    session.commit()
