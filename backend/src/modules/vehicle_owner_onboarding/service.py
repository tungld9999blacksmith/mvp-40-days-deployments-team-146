"""Onboarding module — application service (use-case orchestration).

Coordinates the domain tables, the manufacturer gateway (port) and the
transaction boundaries for the registration & onboarding flow (US-001..US-004).

Rules:
    - Raise domain exceptions (errors.py); never return HTTP responses.
    - The manufacturer is the source of truth for vehicle & ownership data.
    - Enum values are lowercase in the DB; UPPER_SNAKE_CASE at the API edge.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from ev_contracts import (
    OwnershipVerifyRequest,
    OwnershipVerifyResponse,
    normalize_national_id,
    normalize_plate,
    normalize_vin,
)
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import OnboardingStatus, UserStatus, VehicleUser
from src.common.core.vehicle import OemSyncTrigger
from src.modules.oem_integration.ports import SyncScheduler

from . import errors, schemas
from .domain import (
    ConsentType,
    LocationSource,
    UserConsent,
    UserLocation,
    UserVehicle,
    VehicleLinkStatus,
    VehicleVerificationAttempt,
    VehicleVerificationStatus,
    VehicleWarranty,
    VerificationAttemptStatus,
    VerificationFailureReason,
    WarrantyComponent,
    WarrantyStatus,
    compute_expires_at,
    compute_next_step,
    normalize_phone,
)

logger = logging.getLogger(__name__)

# Every account created here is a vehicle owner (role split is phase 4, D-05).
_DEFAULT_ROLES = ["VEHICLE_USER"]
_VIN_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


def _now() -> datetime:
    return datetime.now(UTC)


def _mask_national_id(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 5:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 5) + value[-2:]


class OnboardingService:
    def __init__(
        self,
        session: Session,
        gateway,
        *,
        retention_days: int,
        max_failed_attempts: int,
        policy_version: str,
        sync_scheduler: SyncScheduler | None = None,
    ) -> None:
        self._db = session
        self._oem = gateway
        self._retention_days = retention_days
        self._max_failed_attempts = max_failed_attempts
        self._policy_version = policy_version
        self._sync_scheduler = sync_scheduler

    # ==================================================================
    # Lookups (used by the auth dependency)
    # ==================================================================
    def find_user_by_firebase_uid(self, firebase_uid: str) -> VehicleUser | None:
        stmt = select(VehicleUser).where(VehicleUser.firebase_uid == firebase_uid)
        return self._db.exec(stmt).first()

    # ==================================================================
    # API-001 — sign-in / account sync
    # ==================================================================
    async def sign_in(self, claims: dict) -> tuple[schemas.SignInData, bool]:
        provider = (claims.get("firebase") or {}).get("sign_in_provider")
        if provider and provider != "google.com":
            raise errors.OnboardingError(
                "Only Google sign-in is supported.",
                code="UNSUPPORTED_SIGN_IN_PROVIDER",
            )

        uid = claims.get("uid")
        email = (claims.get("email") or "").strip().lower() or None
        email_verified = bool(claims.get("email_verified"))
        if not email or not email_verified:
            raise errors.OnboardingError("A verified Google email is required.", code="EMAIL_NOT_VERIFIED")

        user = self.find_user_by_firebase_uid(uid)

        # Purge an expired, unfinished onboarding so the user can start fresh.
        if user is not None and self._is_expired(user):
            self._db.delete(user)
            self._db.commit()
            user = None

        is_new_user = user is None
        if user is None:
            # Guard: the same email must not belong to another Firebase UID.
            existing_email = self._db.exec(select(VehicleUser).where(VehicleUser.email == email)).first()
            if existing_email is not None:
                raise errors.EmailAlreadyLinkedError()

            user = VehicleUser(
                firebase_uid=uid,
                email=email,
                email_verified=email_verified,
                auth_provider=provider or "google.com",
                display_name=claims.get("name"),
                avatar_url=claims.get("picture"),
                status=UserStatus.ACTIVE,
                onboarding_status=OnboardingStatus.ONBOARDING_IN_PROGRESS,
                last_login_at=_now(),
            )
            self._db.add(user)
            self._db.commit()
            self._db.refresh(user)
            logger.info("Created new vehicle_user id=%s", user.user_id)
        else:
            if user.status != UserStatus.ACTIVE:
                raise errors.AccountLockedError(suspended=user.status == UserStatus.SUSPENDED)
            user.last_login_at = _now()
            user.display_name = claims.get("name") or user.display_name
            user.avatar_url = claims.get("picture") or user.avatar_url
            user.email_verified = email_verified
            self._db.add(user)
            self._db.commit()
            self._db.refresh(user)

        return (
            schemas.SignInData(
                is_new_user=is_new_user,
                user=self._user_summary(user),
                onboarding=self._onboarding_state(user),
            ),
            is_new_user,
        )

    # ==================================================================
    # API-002 — read onboarding state
    # ==================================================================
    def get_onboarding(self, user: VehicleUser) -> schemas.OnboardingData:
        location = self._get_primary_location(user.user_id)
        vehicle = self._get_active_vehicle(user.user_id)
        warranties = self._get_warranties(vehicle.id) if vehicle else []
        latest = self._get_latest_attempt(user.user_id)
        consents = self._current_consents(user.user_id)

        return schemas.OnboardingData(
            onboarding=self._onboarding_state(user),
            profile=self._profile_out(user),
            location=self._location_out(location) if location else None,
            vehicle=self._vehicle_out(vehicle) if vehicle else None,
            warranties=[self._warranty_out(w) for w in warranties],
            latest_verification=self._latest_verification_out(latest) if latest else None,
            remaining_attempts=self._remaining_attempts(user.user_id),
            consents=consents,
        )

    # ==================================================================
    # API-003 — save profile + location + consent
    # ==================================================================
    def update_profile(self, user: VehicleUser, req: schemas.ProfileUpdateRequest) -> schemas.ProfileUpdateData:
        self._assert_editable(user)

        if not req.personal_data_consent.granted:
            raise errors.ConsentRequiredError("You must agree to personal data processing to continue.")

        try:
            phone = normalize_phone(req.phone_number)
        except ValueError as exc:
            raise errors.InvalidProfileError(str(exc), field="phoneNumber") from exc

        national_id = normalize_national_id(req.national_id)
        if len(national_id) != 12:
            raise errors.InvalidProfileError("National id (CCCD) must have 12 digits.", field="nationalId")

        self._validate_location(req.location)

        # Uniqueness (D-03 phone unique; national id unique per Q-E06 proposal).
        self._assert_phone_available(phone, user.user_id)
        self._assert_national_id_available(national_id, user.user_id)

        user.full_name = req.full_name.strip()
        user.phone = phone
        user.national_id = national_id
        user.date_of_birth = req.date_of_birth
        if user.profile_completed_at is None:
            user.profile_completed_at = _now()
        self._db.add(user)

        location = self._upsert_primary_location(user.user_id, req.location)
        self._record_consent_if_changed(
            user.user_id,
            ConsentType.PERSONAL_DATA_PROCESSING,
            req.personal_data_consent,
        )

        self._db.commit()
        self._db.refresh(user)
        self._db.refresh(location)

        return schemas.ProfileUpdateData(
            onboarding=self._onboarding_state(user),
            profile=self._profile_out(user),
            location=self._location_out(location),
        )

    # ==================================================================
    # API-004 — vehicle models (proxy the manufacturer)
    # ==================================================================
    async def list_vehicle_models(self) -> schemas.VehicleModelsData:
        from .ports import OemTimeoutError

        try:
            raw = await self._oem.list_models()
        except OemTimeoutError as exc:
            raise errors.OemUnavailableError() from exc

        items = [
            schemas.VehicleModelOut(
                model_id=m["model_id"],
                model_name=m["model_name"],
                trim=m.get("trim"),
                production_year=m.get("production_year"),
            )
            for m in raw
        ]
        items.sort(key=lambda i: (i.model_name, i.trim or ""))
        return schemas.VehicleModelsData(items=items)

    # ==================================================================
    # API-005 — submit vehicle verification
    # ==================================================================
    async def submit_verification(
        self,
        user: VehicleUser,
        req: schemas.VehicleVerificationRequest,
        *,
        idempotency_key: str,
        trace_id: str | None = None,
    ) -> tuple[schemas.VerificationData, int]:
        from .ports import OemTimeoutError

        # --- format validation (needed to compute the idempotency hash) --
        vin = normalize_vin(req.vin)
        if len(vin) != 17 or any(ch not in _VIN_ALLOWED for ch in vin):
            raise errors.InvalidProfileError("VIN must be 17 alphanumeric characters.", field="vin")
        plate = normalize_plate(req.license_plate)
        request_hash = self._request_hash(vin, plate, req.model_id)

        # --- idempotency: replay a previous submission unchanged ----------
        existing = self._find_attempt(user.user_id, idempotency_key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise errors.IdempotencyKeyReuseError()
            vehicle = self._db.get(UserVehicle, existing.user_vehicle_id)
            self._db.refresh(user)
            return self._build_verification_result(user, vehicle, existing)

        # --- guards -------------------------------------------------------
        if user.profile_completed_at is None:
            raise errors.OnboardingStateError("Complete your profile first.", code="PROFILE_INCOMPLETE")
        self._assert_can_verify(user)

        if not req.oem_data_sharing_consent.granted:
            raise errors.ConsentRequiredError("You must agree to share vehicle data with the manufacturer.")

        # --- retry limit (D-04 / BR-006) ---------------------------------
        if self._remaining_attempts(user.user_id) <= 0:
            raise errors.VerificationAttemptsExceededError(self._seconds_until_attempt_window_frees(user.user_id))

        # --- BR-002: VIN already linked to another active account --------
        if self._vin_linked_to_other(vin, user.user_id):
            raise errors.VehicleAlreadyLinkedError()

        # --- TX1: record the request as pending --------------------------
        vehicle = self._upsert_draft_vehicle(user.user_id, vin, plate, req)
        attempt = VehicleVerificationAttempt(
            user_id=user.user_id,
            user_vehicle_id=vehicle.id,
            vin=vin,
            license_plate=plate,
            declared_model_id=req.model_id,
            status=VerificationAttemptStatus.PENDING,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            trace_id=trace_id,
            requested_at=_now(),
        )
        self._db.add(attempt)
        self._record_consent_if_changed(user.user_id, ConsentType.OEM_DATA_SHARING, req.oem_data_sharing_consent)
        user.onboarding_status = OnboardingStatus.PENDING_VEHICLE_VERIFICATION
        self._db.add(user)
        self._db.commit()
        self._db.refresh(vehicle)
        self._db.refresh(attempt)
        self._db.refresh(user)

        # --- call the manufacturer ---------------------------------------
        started = _now()
        oem_request = OwnershipVerifyRequest(
            vin=vin,
            license_plate=plate,
            model_id=req.model_id,
            email=user.email or "",
            national_id=user.national_id or "",
        )
        try:
            result = await self._oem.verify_ownership(oem_request)
        except OemTimeoutError:
            # EF-002: keep PENDING; a background worker will retry.
            logger.warning("OEM timeout for attempt=%s; left pending", attempt.id)
            data, _ = self._build_verification_result(user, vehicle, attempt)
            return data, 202

        latency_ms = int((_now() - started).total_seconds() * 1000)
        attempt.oem_http_status = 200
        attempt.latency_ms = latency_ms
        attempt.responded_at = _now()

        # --- TX2: persist the outcome ------------------------------------
        if result.verified:
            self._apply_verified(user, vehicle, attempt, result)
        else:
            self._apply_failed(user, vehicle, attempt, self._map_reason(result))

        self._db.commit()
        self._db.refresh(user)
        self._db.refresh(vehicle)
        self._db.refresh(attempt)
        if result.verified:
            self._schedule_initial_sync(vehicle)

        data, _ = self._build_verification_result(user, vehicle, attempt)
        return data, 200

    # ==================================================================
    # Verification outcome helpers
    # ==================================================================
    def _schedule_initial_sync(self, vehicle: UserVehicle) -> None:
        """Pull odometer + service history right after verification (FEAT-VEH-001 BR-011)."""
        if self._sync_scheduler is None:
            return
        try:
            self._sync_scheduler.schedule(vehicle.id, OemSyncTrigger.INITIAL)
        except Exception:  # noqa: BLE001 — API-VEH-003 re-enqueues a lost initial sync
            logger.exception("could not enqueue initial OEM sync for %s", vehicle.id)

    def _apply_verified(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        attempt: VehicleVerificationAttempt,
        result: OwnershipVerifyResponse,
    ) -> None:
        spec = result.vehicle
        assert spec is not None
        vehicle.verification_status = VehicleVerificationStatus.VERIFIED
        vehicle.verification_failure_reason = None
        vehicle.external_vehicle_id = spec.external_vehicle_id
        vehicle.external_owner_id = spec.external_owner_id
        vehicle.external_model_id = spec.external_model_id
        vehicle.model_name = spec.model_name
        vehicle.trim = spec.trim
        vehicle.color = spec.color
        vehicle.manufacture_date = spec.manufacture_date
        vehicle.production_year = spec.production_year
        vehicle.battery_capacity_kwh = spec.battery_capacity_kwh
        vehicle.motor_power_kw = spec.motor_power_kw
        vehicle.verified_at = _now()
        vehicle.oem_synced_at = _now()
        self._db.add(vehicle)

        # Replace-all warranties for this vehicle.
        for old in self._get_warranties(vehicle.id):
            self._db.delete(old)
        for w in result.warranties:
            self._db.add(
                VehicleWarranty(
                    user_vehicle_id=vehicle.id,
                    external_warranty_id=w.external_warranty_id,
                    external_policy_id=w.external_policy_id,
                    component=WarrantyComponent(w.component),
                    start_date=w.start_date,
                    end_date=w.end_date,
                    km_limit=w.km_limit,
                    duration_months=w.duration_months,
                    terms_description=w.terms_description,
                    oem_status=WarrantyStatus(w.status),
                )
            )

        attempt.status = VerificationAttemptStatus.SUCCESS
        attempt.failure_reason = None
        self._db.add(attempt)

        user.onboarding_status = OnboardingStatus.ACTIVE
        user.onboarding_completed_at = _now()
        user.external_owner_id = spec.external_owner_id
        self._db.add(user)

    def _apply_failed(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        attempt: VehicleVerificationAttempt,
        reason: VerificationFailureReason,
    ) -> None:
        vehicle.verification_status = VehicleVerificationStatus.FAILED
        vehicle.verification_failure_reason = reason
        self._db.add(vehicle)

        attempt.status = VerificationAttemptStatus.FAILED
        attempt.failure_reason = reason
        self._db.add(attempt)

        user.onboarding_status = OnboardingStatus.VERIFICATION_FAILED
        self._db.add(user)

    @staticmethod
    def _map_reason(result: OwnershipVerifyResponse) -> VerificationFailureReason:
        if result.failure_reason is None:
            return VerificationFailureReason.VIN_NOT_FOUND
        # ev_contracts reasons use UPPER names matching our enum names.
        return VerificationFailureReason[result.failure_reason.name]

    # ==================================================================
    # Persistence helpers
    # ==================================================================
    def _get_primary_location(self, user_id: int) -> UserLocation | None:
        stmt = select(UserLocation).where(
            UserLocation.user_id == user_id,
            UserLocation.is_primary == True,  # noqa: E712
        )
        return self._db.exec(stmt).first()

    def _get_active_vehicle(self, user_id: int) -> UserVehicle | None:
        """Return the vehicle currently in focus for onboarding.

        Prefers a verified+active vehicle; otherwise the pending/failed draft.
        """
        stmt = (
            select(UserVehicle)
            .where(
                UserVehicle.user_id == user_id,
                UserVehicle.link_status == VehicleLinkStatus.ACTIVE,
            )
            .order_by(UserVehicle.created_at.desc())  # type: ignore[union-attr]
        )
        vehicles = list(self._db.exec(stmt).all())
        for v in vehicles:
            if v.verification_status == VehicleVerificationStatus.VERIFIED:
                return v
        return vehicles[0] if vehicles else None

    def _get_warranties(self, user_vehicle_id) -> list[VehicleWarranty]:
        stmt = select(VehicleWarranty).where(VehicleWarranty.user_vehicle_id == user_vehicle_id)
        return list(self._db.exec(stmt).all())

    def _get_latest_attempt(self, user_id: int) -> VehicleVerificationAttempt | None:
        stmt = (
            select(VehicleVerificationAttempt)
            .where(VehicleVerificationAttempt.user_id == user_id)
            .order_by(VehicleVerificationAttempt.requested_at.desc())  # type: ignore[union-attr]
        )
        return self._db.exec(stmt).first()

    def _find_attempt(self, user_id: int, idempotency_key: str) -> VehicleVerificationAttempt | None:
        stmt = select(VehicleVerificationAttempt).where(
            VehicleVerificationAttempt.user_id == user_id,
            VehicleVerificationAttempt.idempotency_key == idempotency_key,
        )
        return self._db.exec(stmt).first()

    def _vin_linked_to_other(self, vin: str, user_id: int) -> bool:
        stmt = select(UserVehicle).where(
            UserVehicle.vin == vin,
            UserVehicle.verification_status == VehicleVerificationStatus.VERIFIED,
            UserVehicle.link_status == VehicleLinkStatus.ACTIVE,
            UserVehicle.user_id != user_id,
        )
        return self._db.exec(stmt).first() is not None

    def _upsert_draft_vehicle(
        self, user_id: int, vin: str, plate: str, req: schemas.VehicleVerificationRequest
    ) -> UserVehicle:
        stmt = select(UserVehicle).where(
            UserVehicle.user_id == user_id,
            UserVehicle.link_status == VehicleLinkStatus.ACTIVE,
            UserVehicle.verification_status != VehicleVerificationStatus.VERIFIED,
        )
        draft = self._db.exec(stmt).first()
        if draft is None:
            draft = UserVehicle(user_id=user_id)
        draft.vin = vin
        draft.license_plate = plate
        draft.declared_model_id = req.model_id
        draft.declared_manufacture_year = req.manufacture_year
        draft.verification_status = VehicleVerificationStatus.PENDING
        draft.verification_failure_reason = None
        draft.link_status = VehicleLinkStatus.ACTIVE
        self._db.add(draft)
        self._db.flush()  # assign PK before creating the attempt
        return draft

    def _upsert_primary_location(self, user_id: int, loc: schemas.LocationIn) -> UserLocation:
        existing = self._get_primary_location(user_id)
        if existing is None:
            existing = UserLocation(user_id=user_id, address_line=loc.address_line, province=loc.province)
        existing.address_line = loc.address_line
        existing.ward = loc.ward
        existing.district = loc.district
        existing.province = loc.province
        existing.latitude = loc.latitude
        existing.longitude = loc.longitude
        existing.source = LocationSource(loc.source.lower())
        existing.place_id = loc.place_id
        existing.is_primary = True
        self._db.add(existing)
        self._db.flush()
        return existing

    def _record_consent_if_changed(self, user_id: int, consent_type: ConsentType, consent: schemas.ConsentIn) -> None:
        current = self._current_consent(user_id, consent_type)
        if current is not None and current.granted == consent.granted:
            return
        self._db.add(
            UserConsent(
                user_id=user_id,
                consent_type=consent_type,
                policy_version=consent.policy_version,
                granted=consent.granted,
            )
        )

    def _current_consent(self, user_id: int, consent_type: ConsentType) -> UserConsent | None:
        stmt = (
            select(UserConsent)
            .where(
                UserConsent.user_id == user_id,
                UserConsent.consent_type == consent_type,
            )
            .order_by(UserConsent.created_at.desc())  # type: ignore[union-attr]
        )
        return self._db.exec(stmt).first()

    def _current_consents(self, user_id: int) -> dict:
        out: dict = {}
        for key, ctype in (
            ("personalDataProcessing", ConsentType.PERSONAL_DATA_PROCESSING),
            ("oemDataSharing", ConsentType.OEM_DATA_SHARING),
        ):
            c = self._current_consent(user_id, ctype)
            out[key] = schemas.ConsentStateOut(granted=c.granted, policy_version=c.policy_version) if c else None
        return out

    # ==================================================================
    # Validation / guards
    # ==================================================================
    def _is_expired(self, user: VehicleUser) -> bool:
        if user.onboarding_status == OnboardingStatus.ACTIVE:
            return False
        created = user.created_at
        if created is None:
            return False
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return created < _now() - timedelta(days=self._retention_days)

    def _assert_editable(self, user: VehicleUser) -> None:
        status = user.onboarding_status
        if status == OnboardingStatus.ACTIVE:
            raise errors.OnboardingStateError("Onboarding already completed.", code="ONBOARDING_ALREADY_COMPLETED")
        if status == OnboardingStatus.PENDING_VEHICLE_VERIFICATION:
            raise errors.OnboardingStateError("Vehicle verification is in progress.", code="VERIFICATION_IN_PROGRESS")

    def _assert_can_verify(self, user: VehicleUser) -> None:
        status = user.onboarding_status
        if status == OnboardingStatus.ACTIVE:
            raise errors.OnboardingStateError("Onboarding already completed.", code="ONBOARDING_ALREADY_COMPLETED")
        if status == OnboardingStatus.PENDING_VEHICLE_VERIFICATION:
            raise errors.OnboardingStateError("Vehicle verification is in progress.", code="VERIFICATION_IN_PROGRESS")

    @staticmethod
    def _validate_location(loc: schemas.LocationIn) -> None:
        try:
            source = LocationSource(loc.source.lower())
        except ValueError as exc:
            raise errors.InvalidProfileError("Invalid location source.", field="location.source") from exc
        has_lat = loc.latitude is not None
        has_lng = loc.longitude is not None
        if has_lat != has_lng:
            raise errors.InvalidProfileError("Latitude and longitude must be provided together.", field="location")
        if source in (LocationSource.MAP_PICK, LocationSource.GPS) and not has_lat:
            raise errors.InvalidProfileError("Coordinates are required for map/GPS locations.", field="location")

    def _assert_phone_available(self, phone: str, user_id: int) -> None:
        stmt = select(VehicleUser).where(VehicleUser.phone == phone, VehicleUser.user_id != user_id)
        if self._db.exec(stmt).first() is not None:
            raise errors.PhoneAlreadyInUseError()

    def _assert_national_id_available(self, national_id: str, user_id: int) -> None:
        stmt = select(VehicleUser).where(VehicleUser.national_id == national_id, VehicleUser.user_id != user_id)
        if self._db.exec(stmt).first() is not None:
            raise errors.OnboardingError(
                "This national id is already used by another account.",
                code="NATIONAL_ID_ALREADY_IN_USE",
            )

    def _remaining_attempts(self, user_id: int) -> int:
        used = self._count_recent_failures(user_id)
        return max(0, self._max_failed_attempts - used)

    def _count_recent_failures(self, user_id: int) -> int:
        window_start = _now() - timedelta(hours=24)
        stmt = select(VehicleVerificationAttempt).where(
            VehicleVerificationAttempt.user_id == user_id,
            VehicleVerificationAttempt.status == VerificationAttemptStatus.FAILED,
            VehicleVerificationAttempt.failure_reason != VerificationFailureReason.OEM_UNAVAILABLE,
            VehicleVerificationAttempt.requested_at >= window_start,
        )
        return len(list(self._db.exec(stmt).all()))

    def _seconds_until_attempt_window_frees(self, user_id: int) -> int:
        window_start = _now() - timedelta(hours=24)
        stmt = (
            select(VehicleVerificationAttempt)
            .where(
                VehicleVerificationAttempt.user_id == user_id,
                VehicleVerificationAttempt.status == VerificationAttemptStatus.FAILED,
                VehicleVerificationAttempt.requested_at >= window_start,
            )
            .order_by(VehicleVerificationAttempt.requested_at.asc())  # type: ignore[union-attr]
        )
        oldest = self._db.exec(stmt).first()
        if oldest is None:
            return 0
        requested = oldest.requested_at
        if requested.tzinfo is None:
            requested = requested.replace(tzinfo=UTC)
        free_at = requested + timedelta(hours=24)
        return max(0, int((free_at - _now()).total_seconds()))

    @staticmethod
    def _request_hash(vin: str, plate: str, model_id: str) -> str:
        canonical = json.dumps({"vin": vin, "plate": plate, "model_id": model_id}, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()

    # ==================================================================
    # Serialization
    # ==================================================================
    def _onboarding_state(self, user: VehicleUser) -> schemas.OnboardingStateOut:
        profile_completed = user.profile_completed_at is not None
        next_step = compute_next_step(user.onboarding_status, profile_completed)
        expires_at = compute_expires_at(user.created_at, user.onboarding_status, self._retention_days)
        return schemas.OnboardingStateOut(
            status=user.onboarding_status.name,
            next_step=next_step.value,
            profile_completed=profile_completed,
            profile_completed_at=user.profile_completed_at,
            completed_at=user.onboarding_completed_at,
            expires_at=expires_at,
        )

    @staticmethod
    def _user_summary(user: VehicleUser) -> schemas.UserSummaryOut:
        return schemas.UserSummaryOut(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            full_name=user.full_name,
            account_status=user.status.name,
            roles=list(_DEFAULT_ROLES),
        )

    @staticmethod
    def _profile_out(user: VehicleUser) -> schemas.ProfileOut:
        return schemas.ProfileOut(
            email=user.email,
            display_name=user.display_name,
            full_name=user.full_name,
            phone_number=user.phone,
            national_id_masked=_mask_national_id(user.national_id),
            date_of_birth=user.date_of_birth,
        )

    @staticmethod
    def _location_out(loc: UserLocation) -> schemas.LocationOut:
        return schemas.LocationOut(
            location_type=loc.location_type.name,
            address_line=loc.address_line,
            ward=loc.ward,
            district=loc.district,
            province=loc.province,
            latitude=loc.latitude,
            longitude=loc.longitude,
            source=loc.source.name,
        )

    @staticmethod
    def _vehicle_out(vehicle: UserVehicle) -> schemas.VehicleOut:
        spec = None
        if vehicle.verification_status == VehicleVerificationStatus.VERIFIED:
            spec = schemas.VehicleSpecOut(
                model_id=vehicle.external_model_id,
                model_name=vehicle.model_name,
                trim=vehicle.trim,
                color=vehicle.color,
                manufacture_date=vehicle.manufacture_date,
                production_year=vehicle.production_year,
                battery_capacity_kwh=vehicle.battery_capacity_kwh,
                motor_power_kw=vehicle.motor_power_kw,
            )
        return schemas.VehicleOut(
            vehicle_id=vehicle.id,
            vin=vehicle.vin,
            license_plate=vehicle.license_plate,
            declared_model_id=vehicle.declared_model_id,
            verification_status=vehicle.verification_status.name,
            verification_failure_reason=(
                vehicle.verification_failure_reason.name if vehicle.verification_failure_reason else None
            ),
            verified_at=vehicle.verified_at,
            spec=spec,
        )

    @staticmethod
    def _warranty_out(w: VehicleWarranty) -> schemas.WarrantyOut:
        # Recompute effective status from end_date rather than the synced value.
        today = _now().date()
        effective = "ACTIVE" if w.end_date >= today else "EXPIRED"
        return schemas.WarrantyOut(
            component=w.component.name,
            start_date=w.start_date,
            end_date=w.end_date,
            km_limit=w.km_limit,
            duration_months=w.duration_months,
            status=effective,
            terms_description=w.terms_description,
        )

    @staticmethod
    def _latest_verification_out(
        attempt: VehicleVerificationAttempt,
    ) -> schemas.LatestVerificationOut:
        return schemas.LatestVerificationOut(
            attempt_id=attempt.id,
            status=attempt.status.name,
            failure_reason=(attempt.failure_reason.name if attempt.failure_reason else None),
            requested_at=attempt.requested_at,
            responded_at=attempt.responded_at,
        )

    _FAILURE_MESSAGES = {
        VerificationFailureReason.VIN_NOT_FOUND: "VIN not found in the manufacturer system. Please check the VIN.",
        VerificationFailureReason.PLATE_MISMATCH: "The license plate does not match this VIN. Please check again.",
        VerificationFailureReason.MODEL_MISMATCH: "The selected model does not match the manufacturer record.",
        VerificationFailureReason.OWNER_EMAIL_MISMATCH: "Your Google email does not match the vehicle owner on record.",
        VerificationFailureReason.NATIONAL_ID_MISMATCH: "Your national id does not match the vehicle owner on record.",
        VerificationFailureReason.OEM_UNAVAILABLE: "The manufacturer system is temporarily unavailable. Please try again.",
    }

    def _build_verification_result(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        attempt: VehicleVerificationAttempt,
    ) -> tuple[schemas.VerificationData, int]:
        status = attempt.status
        if status == VerificationAttemptStatus.SUCCESS:
            message = "Vehicle verified successfully."
            http_status = 200
        elif status == VerificationAttemptStatus.FAILED:
            reason = attempt.failure_reason or VerificationFailureReason.VIN_NOT_FOUND
            message = self._FAILURE_MESSAGES.get(reason, "Verification failed.")
            http_status = 200
        else:  # PENDING
            message = "The manufacturer system is taking longer than expected."
            http_status = 202

        warranties = (
            self._get_warranties(vehicle.id)
            if vehicle.verification_status == VehicleVerificationStatus.VERIFIED
            else []
        )
        result = schemas.VerificationResultOut(
            attempt_id=attempt.id,
            status=attempt.status.name,
            failure_reason=(attempt.failure_reason.name if attempt.failure_reason else None),
            message=message,
            remaining_attempts=self._remaining_attempts(user.user_id),
        )
        data = schemas.VerificationData(
            onboarding=self._onboarding_state(user),
            verification=result,
            vehicle=self._vehicle_out(vehicle),
            warranties=[self._warranty_out(w) for w in warranties],
        )
        return data, http_status
