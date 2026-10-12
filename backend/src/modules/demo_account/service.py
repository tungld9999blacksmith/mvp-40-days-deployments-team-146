"""Demo account module — application service.

``open_session`` (API ``POST /auth/demo-session``) makes sure the shared account exists
and returns a Firebase custom token for it. ``reset_if_due`` (hourly Celery job, or
``scripts/demo_account_reset.py``) wipes everything the visitors created and seeds the
account again once ``DEMO_RESET_INTERVAL_HOURS`` have passed since the last reset.

Seeding takes the same path as onboarding: each VIN goes through the manufacturer's
ownership check, then ``apply_verified_vehicle`` and an OEM sync, so ODO, warranties
and service history come from mock-ev-system (``demo_account.py`` there).

Wiping deletes the account row and lets ``ON DELETE CASCADE`` remove the rest;
only ``booking`` / ``booking_request`` lack the cascade and go first (with them their
lines, status events, progress, follow-ups and deliveries, on the workshop side too).
Chat threads go through the agent-memory cleanup outbox (checkpoints, vectors).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from ev_contracts import OwnershipVerifyRequest, OwnershipVerifyResponse, normalize_plate
from sqlalchemy import delete, or_, text
from sqlmodel import Session, select

from src.common.core.conversation import ChatMessage, Conversation
from src.common.core.conversation.memory import MemoryCleanup
from src.common.core.identity.vehicle_user import OnboardingStatus, UserStatus, VehicleUser
from src.common.core.maintenance import Booking, BookingRequest
from src.modules.vehicle_owner_onboarding.domain import (
    ConsentType,
    LocationSource,
    UserConsent,
    UserLocation,
    UserVehicle,
    VehicleLinkStatus,
)
from src.modules.vehicle_owner_onboarding.ports import OemTimeoutError, OemVehicleGateway
from src.modules.vehicle_owner_onboarding.service import apply_verified_vehicle

from .domain import STATE_ID, DemoAccountState
from .errors import DemoAccountUnavailableError
from .identity import DEMO_NATIONAL_ID, DEMO_UID
from .ports import DemoIdentityProvider, DemoOwnerAdmin

logger = logging.getLogger(__name__)

DISPLAY_NAME = "Tài khoản dùng thử"
FULL_NAME = "Khách Dùng Thử"
# Any constant: serializes seeding and resets across API processes and workers.
_ADVISORY_LOCK_KEY = 7_146_001


@dataclass(frozen=True)
class DemoVehicle:
    vin: str
    license_plate: str
    model_id: str


# Mirrors mock-ev-system demo_account.VEHICLES (VF3, VF8, VF Wild).
VEHICLES: tuple[DemoVehicle, ...] = (
    DemoVehicle("DEMOVF3EC00000001", "30K-999.01", "MDL-09"),
    DemoVehicle("DEMOVF8EC00000002", "30K-999.02", "MDL-05"),
    DemoVehicle("DEMOVFWLD00000003", "30K-999.03", "MDL-08"),
)

VehicleSyncer = Callable[[Session, UUID], Awaitable[object]]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def demo_resets_at(session: Session, interval_hours: int) -> datetime | None:
    """When the shared account is reset next (shown in the app banner); None before the first seed."""
    state = session.get(DemoAccountState, STATE_ID)
    if state is None:
        return None
    return _as_utc(state.last_reset_at) + timedelta(hours=interval_hours)


class DemoAccountService:
    def __init__(
        self,
        session: Session,
        *,
        email: str,
        reset_interval_hours: int,
        gateway: OemVehicleGateway,
        identity: DemoIdentityProvider | None = None,
        owner_admin: DemoOwnerAdmin | None = None,
        syncer: VehicleSyncer | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._db = session
        self._email = email.strip().lower()
        self._interval = timedelta(hours=reset_interval_hours)
        self._gateway = gateway
        self._identity = identity
        self._owner_admin = owner_admin
        self._syncer = syncer
        self._clock = clock

    # ------------------------------------------------------------------ API
    async def open_session(self) -> str:
        """Seed the account when needed, then mint a custom token for it."""
        if self._identity is None:
            raise RuntimeError("DemoAccountService was built without an identity provider.")
        await self.ensure_ready()
        try:
            self._identity.ensure_user(DEMO_UID, email=self._email, display_name=DISPLAY_NAME)
            return self._identity.mint_token(DEMO_UID)
        except Exception as exc:  # noqa: BLE001 — Firebase down / misconfigured
            logger.exception("demo account: Firebase user or token failed")
            raise DemoAccountUnavailableError() from exc

    async def ensure_ready(self) -> VehicleUser:
        """The demo account, seeded on first use (idempotent, safe under concurrent calls)."""
        user = self.find_user()
        if user is not None:
            return user
        responses = await self._verify_vehicles()
        self._lock()
        user = self.find_user()
        if user is None:
            user = self._seed(responses)
            self._save_state()
            self._db.commit()
            await self._sync(user)
        else:
            self._db.rollback()
        return user

    async def reset_if_due(self, *, force: bool = False) -> bool:
        """Wipe and re-seed the account when the interval has passed (or ``force``). True when reset."""
        if not force and not self.is_due():
            return False
        if self._owner_admin is not None:
            await self._owner_admin.reset_demo_owner()
        responses = await self._verify_vehicles()
        self._lock()
        if not force and not self.is_due():
            self._db.rollback()  # another worker reset it meanwhile
            return False
        old = self.find_user()
        if old is not None:
            self._purge(old)
        user = self._seed(responses)
        self._save_state()
        self._db.commit()
        logger.info("demo account reset: user_id=%s", user.user_id)
        await self._sync(user)
        return True

    def is_due(self) -> bool:
        state = self._db.get(DemoAccountState, STATE_ID)
        return state is None or self._clock() - _as_utc(state.last_reset_at) >= self._interval

    def find_user(self) -> VehicleUser | None:
        return self._db.exec(select(VehicleUser).where(VehicleUser.firebase_uid == DEMO_UID)).first()

    # ------------------------------------------------------------- helpers
    def _lock(self) -> None:
        """Transaction-scoped advisory lock (PostgreSQL); a no-op on the SQLite test engine."""
        if self._db.get_bind().dialect.name == "postgresql":
            self._db.exec(text("SELECT pg_advisory_xact_lock(:key)").bindparams(key=_ADVISORY_LOCK_KEY))

    async def _verify_vehicles(self) -> list[tuple[DemoVehicle, OwnershipVerifyResponse]]:
        """Ownership check of the three VINs, before any write: a failure leaves the account untouched."""
        results = []
        for spec in VEHICLES:
            request = OwnershipVerifyRequest(
                vin=spec.vin,
                license_plate=spec.license_plate,
                model_id=spec.model_id,
                email=self._email,
                national_id=DEMO_NATIONAL_ID,
            )
            try:
                response = await self._gateway.verify_ownership(request)
            except OemTimeoutError as exc:
                raise DemoAccountUnavailableError("The manufacturer system is unavailable.") from exc
            if not response.verified or response.vehicle is None:
                reason = response.failure_reason.value if response.failure_reason else "not verified"
                logger.error("demo account: manufacturer rejected %s (%s)", spec.vin, reason)
                raise DemoAccountUnavailableError(f"Demo vehicle {spec.vin} failed the ownership check: {reason}.")
            results.append((spec, response))
        return results

    def _seed(self, responses: list[tuple[DemoVehicle, OwnershipVerifyResponse]]) -> VehicleUser:
        now = self._clock()
        user = VehicleUser(
            firebase_uid=DEMO_UID,
            email=self._email,
            email_verified=True,
            auth_provider="custom",
            display_name=DISPLAY_NAME,
            full_name=FULL_NAME,
            national_id=DEMO_NATIONAL_ID,
            external_owner_id=responses[0][1].vehicle.external_owner_id,
            status=UserStatus.ACTIVE,
            onboarding_status=OnboardingStatus.ACTIVE,
            profile_completed_at=now,
            onboarding_completed_at=now,
            is_demo=True,
        )
        self._db.add(user)
        self._db.flush()
        self._db.add(
            UserLocation(
                user_id=user.user_id,
                address_line="Số 1 Đại Cồ Việt",
                district="Hai Bà Trưng",
                province="Hà Nội",
                latitude=Decimal("21.006700"),
                longitude=Decimal("105.843100"),
                source=LocationSource.MANUAL,
            )
        )
        for consent_type in (ConsentType.PERSONAL_DATA_PROCESSING, ConsentType.OEM_DATA_SHARING):
            self._db.add(
                UserConsent(user_id=user.user_id, consent_type=consent_type, policy_version="demo", granted=True)
            )
        for spec, response in responses:
            vehicle = UserVehicle(
                user_id=user.user_id,
                vin=spec.vin,
                license_plate=normalize_plate(spec.license_plate),
                declared_model_id=spec.model_id,
                link_status=VehicleLinkStatus.ACTIVE,
            )
            self._db.add(vehicle)
            self._db.flush()  # assign the PK before the warranties reference it
            apply_verified_vehicle(self._db, vehicle, response)
        self._db.flush()
        return user

    def _purge(self, user: VehicleUser) -> None:
        user_id = user.user_id
        vehicle_ids = select(UserVehicle.id).where(UserVehicle.user_id == user_id)
        booking_ids = list(
            self._db.exec(
                select(Booking.id).where(or_(Booking.user_id == user_id, Booking.user_vehicle_id.in_(vehicle_ids)))
            ).all()
        )
        # Chat threads: queue their checkpoints / vectors for the agent-memory cleanup job.
        for conversation_id in self._db.exec(select(Conversation.id).where(Conversation.user_id == user_id)).all():
            message_ids = self._db.exec(select(ChatMessage.id).where(ChatMessage.conversation_id == conversation_id))
            if self._db.get(MemoryCleanup, conversation_id) is None:
                self._db.add(MemoryCleanup(conversation_id=conversation_id, vector_ids=[str(i) for i in message_ids]))
        self._db.flush()
        self._db.exec(
            delete(BookingRequest).where(
                or_(BookingRequest.user_id == user_id, BookingRequest.booking_id.in_(booking_ids))
            )
        )
        self._db.exec(delete(Booking).where(Booking.id.in_(booking_ids)))
        self._db.exec(delete(VehicleUser).where(VehicleUser.user_id == user_id))
        self._db.expunge(user)
        self._db.flush()

    def _save_state(self) -> None:
        state = self._db.get(DemoAccountState, STATE_ID) or DemoAccountState(id=STATE_ID, last_reset_at=self._clock())
        state.last_reset_at = self._clock()
        self._db.add(state)

    async def _sync(self, user: VehicleUser) -> None:
        """Pull ODO + service history now so the due status shows at once (best effort)."""
        if self._syncer is None:
            return
        ids = self._db.exec(select(UserVehicle.id).where(UserVehicle.user_id == user.user_id)).all()
        for vehicle_id in ids:
            try:
                await self._syncer(self._db, vehicle_id)
            except Exception:  # noqa: BLE001 — the self-heal of API-VEH-003 syncs it later
                logger.exception("demo account: OEM sync of %s failed", vehicle_id)
