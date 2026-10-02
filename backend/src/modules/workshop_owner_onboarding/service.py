"""Workshop-owner onboarding — application service (FEAT-AUTH-003, API-201..204).

Coordinates the domain tables, the manufacturer gateway and the retry
scheduler (ports), and owns the transaction boundaries.

Rules:
    - Raise domain exceptions (errors.py); never return HTTP responses.
    - The manufacturer decides who manages which service center (W-01): the
      owner never picks a center, the OEM returns it for (Gmail, CCCD).
    - One owner ↔ one workshop; a workshop has at most one owner (BR-202).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from ev_contracts import ManagerVerifyRequest, ManagerVerifyResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import UserStatus
from src.common.core.identity.workshop_owner import WorkshopOwner, WorkshopOwnerOnboardingStatus
from src.common.core.workshop.workshop import (
    ServiceCenterType,
    Workshop,
    WorkshopOperatingHour,
    WorkshopStatus,
)
from src.common.request_context import RequestContext

from . import errors, schemas
from .domain import (
    AttemptStatus,
    ConsentType,
    OperatingHoursError,
    OperatingHourValue,
    WorkshopOwnerConsent,
    WorkshopRegistration,
    WorkshopVerificationAttempt,
    WorkshopVerificationFailureReason,
    WorkshopVerificationStatus,
    compute_expires_at,
    compute_next_step,
    mask_national_id,
    normalize_hotline,
    normalize_mobile,
    normalize_national_id,
    validate_operating_hours,
)
from .ports import (
    NullSignInAuditor,
    OemServiceCenterGateway,
    OemTimeoutError,
    SignInAuditor,
    VerificationRetryScheduler,
)

logger = logging.getLogger(__name__)

_ROLES = ["WORKSHOP_OWNER"]
_OS = WorkshopOwnerOnboardingStatus
_REASON = WorkshopVerificationFailureReason


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; treat them as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _to_decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _to_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


class WorkshopOnboardingService:
    def __init__(
        self,
        session: Session,
        gateway: OemServiceCenterGateway,
        scheduler: VerificationRetryScheduler,
        *,
        retention_days: int,
        max_failed_attempts: int,
        retry_delays_seconds: Sequence[int],
        policy_versions: Sequence[str],
        auditor: SignInAuditor | None = None,
    ) -> None:
        self._db = session
        self._auditor = auditor or NullSignInAuditor()
        self._oem = gateway
        self._scheduler = scheduler
        self._retention_days = retention_days
        self._max_failed_attempts = max_failed_attempts
        self._retry_delays = list(retry_delays_seconds)
        self._policy_versions = set(policy_versions)

    # ==================================================================
    # Lookups
    # ==================================================================
    def find_owner_by_firebase_uid(self, firebase_uid: str | None) -> WorkshopOwner | None:
        if not firebase_uid:
            return None
        stmt = select(WorkshopOwner).where(WorkshopOwner.firebase_uid == firebase_uid)
        return self._db.exec(stmt).first()

    # ==================================================================
    # API-201 — sign-in / account sync
    # ==================================================================
    def sign_in(self, claims: dict, context: RequestContext | None = None) -> tuple[schemas.SignInData, bool]:
        """Find/create the account and audit the sign-in (FEAT-AUTH-004 BR-305)."""
        provider = (claims.get("firebase") or {}).get("sign_in_provider")
        if provider and provider != "google.com":
            raise errors.WorkshopOnboardingError(
                "Chỉ hỗ trợ đăng nhập bằng Google.", code="UNSUPPORTED_SIGN_IN_PROVIDER"
            )
        uid = claims.get("uid")
        email = (claims.get("email") or "").strip().lower()
        email_verified = bool(claims.get("email_verified"))
        if not email or not email_verified:
            raise errors.WorkshopOnboardingError("Cần email Google đã được xác minh.", code="EMAIL_NOT_VERIFIED")

        audit_ctx = RequestContext(
            ip_address=context.ip_address if context else None,
            user_agent=context.user_agent if context else None,
            trace_id=context.trace_id if context else None,
            auth_provider=provider or "google.com",
        )
        owner = self.find_owner_by_firebase_uid(uid)
        if owner is not None and self._is_expired(owner):
            # BR-208: purge the unfinished onboarding and start over.
            logger.info("purging expired workshop onboarding owner=%s", owner.id)
            self._db.delete(owner)
            self._db.commit()
            owner = None

        is_new = owner is None
        if owner is None:
            taken = self._db.exec(select(WorkshopOwner).where(WorkshopOwner.email == email)).first()
            if taken is not None:
                raise errors.WorkshopOnboardingError(
                    "Email này đã được liên kết với một tài khoản chủ xưởng khác.",
                    code="EMAIL_ALREADY_LINKED",
                )
            owner = WorkshopOwner(
                firebase_uid=uid,
                email=email,
                email_verified=email_verified,
                auth_provider=provider or "google.com",
                display_name=claims.get("name"),
                avatar_url=claims.get("picture"),
                status=UserStatus.ACTIVE,
                onboarding_status=_OS.ONBOARDING_IN_PROGRESS,
                last_login_at=_now(),
            )
            self._db.add(owner)
            self._auditor.record_login(owner.id, audit_ctx)
            try:
                self._db.commit()
            except IntegrityError:
                # A concurrent sign-in created the row first — reuse it.
                self._db.rollback()
                owner = self.find_owner_by_firebase_uid(uid)
                if owner is None:
                    raise
                is_new = False
            else:
                self._db.refresh(owner)
                logger.info("created workshop_owner id=%s", owner.id)

        if not is_new:
            if owner.status != UserStatus.ACTIVE:
                suspended = owner.status == UserStatus.SUSPENDED
                self._auditor.record_login_denied(
                    owner.id, "account_suspended" if suspended else "account_inactive", audit_ctx
                )
                self._db.commit()
                raise errors.AccountLockedError(suspended=suspended)
            self._auditor.record_login(owner.id, audit_ctx)
            owner.last_login_at = _now()
            owner.display_name = claims.get("name") or owner.display_name
            owner.avatar_url = claims.get("picture") or owner.avatar_url
            owner.email_verified = email_verified
            self._db.add(owner)
            self._db.commit()
            self._db.refresh(owner)

        workshop = self._owned_workshop(owner.id)
        return (
            schemas.SignInData(
                is_new_owner=is_new,
                owner=self._owner_summary(owner),
                onboarding=self._state(owner),
                workshop=self._workshop_out(workshop) if workshop else None,
            ),
            is_new,
        )

    # ==================================================================
    # API-202 — read onboarding state
    # ==================================================================
    def get_onboarding(self, owner: WorkshopOwner) -> schemas.OnboardingData:
        registration = self._draft_registration(owner.id)
        latest = self._latest_attempt(owner.id)
        workshop = self._owned_workshop(owner.id)
        return schemas.OnboardingData(
            onboarding=self._state(owner),
            profile=self._profile_out(owner),
            registration=self._registration_out(registration) if registration else None,
            latest_attempt=self._latest_attempt_out(owner.id, latest) if latest else None,
            consents=self._current_consents(owner.id),
            workshop=self._workshop_out(workshop) if workshop else None,
        )

    # ==================================================================
    # API-203 — save profile (full name, phone, CCCD) + consent
    # ==================================================================
    def update_profile(
        self, owner: WorkshopOwner, req: schemas.WorkshopProfileUpdateRequest
    ) -> schemas.ProfileUpdateData:
        # Lock the account row so a concurrent API-204 cannot switch it to
        # PENDING while the profile is being rewritten; re-check after lock.
        owner = self._lock_owner(owner)
        self._assert_onboarding_open(owner)
        self._assert_consent(req.personal_data_consent, "xử lý dữ liệu cá nhân")

        full_name = " ".join(req.full_name.split())
        if len(full_name) < 2:
            raise errors.InvalidFieldError("Họ tên không hợp lệ.", field="fullName")
        try:
            phone = normalize_mobile(req.phone_number)
        except ValueError as exc:
            raise errors.InvalidFieldError("Số điện thoại không hợp lệ.", field="phoneNumber") from exc
        try:
            national_id = normalize_national_id(req.national_id)
        except ValueError as exc:
            raise errors.InvalidFieldError("Số CCCD phải gồm 12 chữ số.", field="nationalId") from exc

        if self._taken_by_other(WorkshopOwner.phone, phone, owner.id):
            raise errors.WorkshopOnboardingError(
                "Số điện thoại đã được sử dụng bởi tài khoản chủ xưởng khác.",
                code="PHONE_ALREADY_IN_USE",
                field="phoneNumber",
            )
        if self._taken_by_other(WorkshopOwner.national_id, national_id, owner.id):
            raise errors.WorkshopOnboardingError(
                "Số CCCD đã được sử dụng bởi tài khoản chủ xưởng khác.",
                code="NATIONAL_ID_ALREADY_IN_USE",
                field="nationalId",
            )

        owner.full_name = full_name
        owner.phone = phone
        owner.national_id = national_id
        if owner.profile_completed_at is None:
            owner.profile_completed_at = _now()
        self._db.add(owner)
        self._record_consent_if_changed(owner.id, ConsentType.PERSONAL_DATA_PROCESSING, req.personal_data_consent)
        self._db.commit()
        self._db.refresh(owner)
        return schemas.ProfileUpdateData(onboarding=self._state(owner), profile=self._profile_out(owner))

    # ==================================================================
    # API-204 — submit verification
    # ==================================================================
    async def submit_verification(
        self,
        owner: WorkshopOwner,
        req: schemas.WorkshopVerificationRequest,
        *,
        idempotency_key: str,
        trace_id: str | None = None,
    ) -> tuple[schemas.VerificationData, int]:
        payload = self._normalize_verification(req)
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

        # --- idempotency: replay the stored outcome, never call the OEM again
        existing = self._db.exec(
            select(WorkshopVerificationAttempt).where(
                WorkshopVerificationAttempt.owner_id == owner.id,
                WorkshopVerificationAttempt.idempotency_key == idempotency_key,
            )
        ).first()
        if existing is not None:
            if existing.request_hash != request_hash:
                raise errors.IdempotencyKeyReuseError()
            self._db.refresh(owner)
            return self._result(owner, existing)

        # --- guards (after locking the account row: no double submit) -------
        owner = self._lock_owner(owner)
        if owner.profile_completed_at is None:
            raise errors.OnboardingStateError("Vui lòng hoàn tất thông tin cá nhân trước.", code="PROFILE_INCOMPLETE")
        self._assert_onboarding_open(owner)
        self._assert_consent(req.oem_data_sharing_consent, "chia sẻ Gmail và CCCD cho hãng")
        if self._failed_last_24h(owner.id) >= self._max_failed_attempts:
            raise errors.VerificationAttemptsExceededError(
                self._seconds_until_window_frees(owner.id), self._max_failed_attempts
            )

        # --- TX1: record the request as pending before calling the OEM -----
        registration = self._upsert_draft(owner.id, payload)
        attempt = WorkshopVerificationAttempt(
            owner_id=owner.id,
            registration_id=registration.id,
            status=AttemptStatus.PENDING,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            trace_id=trace_id,
            requested_at=_now(),
        )
        self._db.add(attempt)
        self._record_consent_if_changed(owner.id, ConsentType.OEM_DATA_SHARING, req.oem_data_sharing_consent)
        owner.onboarding_status = _OS.PENDING_WORKSHOP_VERIFICATION
        self._db.add(owner)
        self._db.commit()
        for row in (owner, registration, attempt):
            self._db.refresh(row)

        await self._run_oem_check(owner, registration, attempt)
        return self._result(owner, attempt)

    # ==================================================================
    # Background retry (called by the Celery task)
    # ==================================================================
    async def retry_verification(self, attempt_id: UUID) -> None:
        """Re-run the OEM call for a pending attempt (EF-202).

        No-op when the attempt already has a final status (the request or an
        earlier retry resolved it).
        """
        attempt = self._db.get(WorkshopVerificationAttempt, attempt_id)
        if attempt is None or attempt.status != AttemptStatus.PENDING:
            return
        owner = self._db.get(WorkshopOwner, attempt.owner_id)
        registration = self._db.get(WorkshopRegistration, attempt.registration_id)
        if owner is None or registration is None:
            return
        attempt.retry_count += 1
        await self._run_oem_check(owner, registration, attempt)

    def stale_pending_attempt_ids(self, *, grace_seconds: int = 300) -> list[UUID]:
        """Pending attempts whose scheduled retry is overdue (lost task)."""
        cutoff = _now() - timedelta(seconds=grace_seconds)
        stmt = select(WorkshopVerificationAttempt).where(
            WorkshopVerificationAttempt.status == AttemptStatus.PENDING,
        )
        return [
            a.id for a in self._db.exec(stmt).all() if a.next_retry_at is not None and _aware(a.next_retry_at) < cutoff
        ]

    def purge_expired_onboarding(self) -> int:
        """BR-208 / W-03: delete unfinished onboardings older than retention,
        and verification logs older than retention. Returns owners deleted."""
        cutoff = _now() - timedelta(days=self._retention_days)
        owners = self._db.exec(
            select(WorkshopOwner).where(
                WorkshopOwner.onboarding_status.in_(  # type: ignore[union-attr]
                    [_OS.ONBOARDING_IN_PROGRESS, _OS.VERIFICATION_FAILED]
                )
            )
        ).all()
        deleted = 0
        for owner in owners:
            if _aware(owner.created_at) and _aware(owner.created_at) < cutoff:
                self._db.delete(owner)
                deleted += 1
        for attempt in self._db.exec(select(WorkshopVerificationAttempt)).all():
            if attempt.status != AttemptStatus.PENDING and _aware(attempt.requested_at) < cutoff:
                self._db.delete(attempt)
        self._db.commit()
        return deleted

    # ==================================================================
    # OEM call + outcome (TX2)
    # ==================================================================
    async def _run_oem_check(
        self,
        owner: WorkshopOwner,
        registration: WorkshopRegistration,
        attempt: WorkshopVerificationAttempt,
    ) -> None:
        started = _now()
        try:
            result = await self._oem.verify_manager(
                ManagerVerifyRequest(
                    manager_email=owner.email,
                    manager_national_id=owner.national_id or "",
                )
            )
        except OemTimeoutError:
            self._handle_oem_timeout(owner, registration, attempt)
            return

        attempt.oem_http_status = 200
        attempt.latency_ms = int((_now() - started).total_seconds() * 1000)
        attempt.responded_at = _now()

        if not result.verified or result.service_center is None:
            reason = (
                _REASON[result.failure_reason.name] if result.failure_reason is not None else _REASON.MANAGER_NOT_FOUND
            )
            self._apply_failed(owner, registration, attempt, reason)
            self._db.commit()
            return

        attempt.external_center_id = result.service_center.center_id
        registration.external_center_id = result.service_center.center_id
        workshop = self._claim_workshop(owner, registration, result)
        if workshop is None:
            self._apply_failed(owner, registration, attempt, _REASON.ALREADY_CLAIMED)
        else:
            self._apply_verified(owner, registration, attempt, workshop)
        self._db.commit()
        for row in (owner, registration, attempt):
            self._db.refresh(row)

    def _handle_oem_timeout(
        self,
        owner: WorkshopOwner,
        registration: WorkshopRegistration,
        attempt: WorkshopVerificationAttempt,
    ) -> None:
        if attempt.retry_count >= len(self._retry_delays):
            logger.warning("OEM still unavailable after %s retries attempt=%s", attempt.retry_count, attempt.id)
            attempt.responded_at = _now()
            attempt.next_retry_at = None
            self._apply_failed(owner, registration, attempt, _REASON.OEM_UNAVAILABLE)
            self._db.commit()
            return

        delay = self._retry_delays[attempt.retry_count]
        attempt.next_retry_at = _now() + timedelta(seconds=delay)
        self._db.add(attempt)
        self._db.commit()
        self._db.refresh(attempt)
        logger.warning("OEM timeout attempt=%s; retry #%s in %ss", attempt.id, attempt.retry_count + 1, delay)
        try:
            self._scheduler.schedule(attempt.id, delay_seconds=delay)
        except Exception:  # noqa: BLE001 — the reconciler picks it up later
            logger.exception("could not schedule retry for attempt=%s", attempt.id)

    def _claim_workshop(
        self,
        owner: WorkshopOwner,
        registration: WorkshopRegistration,
        result: ManagerVerifyResponse,
    ) -> Workshop | None:
        """Create or claim the workshop for this owner; ``None`` if another
        active owner already manages it (BR-202)."""
        center = result.service_center
        assert center is not None
        workshop = self._db.exec(
            select(Workshop).where(Workshop.external_center_id == center.center_id).with_for_update()
        ).first()
        if workshop is not None and workshop.owner_id not in (None, owner.id):
            return None
        if workshop is None:
            workshop = Workshop(
                external_center_id=center.center_id,
                name=center.name,
                region=center.region,
                type=ServiceCenterType(center.type),
                address=registration.address,
                total_technicians=registration.total_technicians,
            )

        # W-10: name/region/type are (re)synced from the OEM at onboarding only.
        workshop.name = center.name
        workshop.region = center.region
        workshop.type = ServiceCenterType(center.type)
        workshop.address = registration.address
        workshop.total_technicians = registration.total_technicians
        workshop.emergency_slots_reserved = registration.emergency_slots_reserved
        workshop.hotline = registration.hotline
        workshop.latitude = registration.latitude
        workshop.longitude = registration.longitude
        workshop.owner_id = owner.id
        workshop.status = WorkshopStatus.ACTIVE
        workshop.onboarded_at = _now()
        workshop.oem_synced_at = _now()

        savepoint = self._db.begin_nested()
        try:
            self._db.add(workshop)
            self._db.flush()
        except IntegrityError:
            # Lost a race: another owner inserted/claimed the same center.
            savepoint.rollback()
            return None

        for old in self._db.exec(
            select(WorkshopOperatingHour).where(WorkshopOperatingHour.workshop_id == workshop.id)
        ).all():
            self._db.delete(old)
        self._db.flush()
        for item in registration.operating_hours:
            self._db.add(
                WorkshopOperatingHour(
                    workshop_id=workshop.id,
                    day_of_week=item["dayOfWeek"],
                    is_closed=item["isClosed"],
                    open_time=time.fromisoformat(item["openTime"]) if item["openTime"] else None,
                    close_time=time.fromisoformat(item["closeTime"]) if item["closeTime"] else None,
                )
            )
        return workshop

    def _apply_verified(
        self,
        owner: WorkshopOwner,
        registration: WorkshopRegistration,
        attempt: WorkshopVerificationAttempt,
        workshop: Workshop,
    ) -> None:
        registration.verification_status = WorkshopVerificationStatus.VERIFIED
        registration.verification_failure_reason = None
        registration.workshop_id = workshop.id
        registration.verified_at = _now()
        attempt.status = AttemptStatus.SUCCESS
        attempt.failure_reason = None
        attempt.next_retry_at = None
        owner.onboarding_status = _OS.ACTIVE
        owner.onboarding_completed_at = _now()
        self._db.add_all([registration, attempt, owner])

    def _apply_failed(
        self,
        owner: WorkshopOwner,
        registration: WorkshopRegistration,
        attempt: WorkshopVerificationAttempt,
        reason: WorkshopVerificationFailureReason,
    ) -> None:
        registration.verification_status = WorkshopVerificationStatus.FAILED
        registration.verification_failure_reason = reason.value
        attempt.status = AttemptStatus.FAILED
        attempt.failure_reason = reason.value
        attempt.next_retry_at = None
        owner.onboarding_status = _OS.VERIFICATION_FAILED
        self._db.add_all([registration, attempt, owner])

    def _result(
        self, owner: WorkshopOwner, attempt: WorkshopVerificationAttempt
    ) -> tuple[schemas.VerificationData, int]:
        if attempt.failure_reason == _REASON.ALREADY_CLAIMED.value:
            raise errors.WorkshopAlreadyClaimedError(attempt.id)
        workshop = self._owned_workshop(owner.id) if attempt.status == AttemptStatus.SUCCESS else None
        data = schemas.VerificationData(
            onboarding=self._state(owner),
            verification=schemas.VerificationResultOut(
                attempt_id=attempt.id,
                status=self._verification_status_name(attempt.status),
                failure_reason=attempt.failure_reason.upper() if attempt.failure_reason else None,
                failed_attempts_last24h=self._failed_last_24h(owner.id),
                max_failed_attempts=self._max_failed_attempts,
            ),
            workshop=self._workshop_out(workshop) if workshop else None,
        )
        return data, 202 if attempt.status == AttemptStatus.PENDING else 200

    @staticmethod
    def _verification_status_name(status: AttemptStatus) -> str:
        return {
            AttemptStatus.PENDING: "PENDING",
            AttemptStatus.SUCCESS: "VERIFIED",
            AttemptStatus.FAILED: "FAILED",
        }[status]

    # ==================================================================
    # Validation / guards
    # ==================================================================
    def _normalize_verification(self, req: schemas.WorkshopVerificationRequest) -> dict:
        """Validate API-204 input and return the canonical payload (also hashed)."""
        address = " ".join(req.address.split())
        if len(address) < 5:
            raise errors.InvalidFieldError("Địa chỉ không hợp lệ.", field="address")
        if (req.latitude is None) != (req.longitude is None):
            raise errors.InvalidFieldError("Vĩ độ và kinh độ phải đi cùng nhau.", field="latitude")
        try:
            hotline = normalize_hotline(req.hotline)
        except ValueError as exc:
            raise errors.InvalidFieldError("Số hotline không hợp lệ.", field="hotline") from exc
        if req.emergency_slots_reserved > req.total_technicians:
            raise errors.InvalidFieldError(
                "Số slot dự phòng không được vượt số kỹ thuật viên.", field="emergencySlotsReserved"
            )
        try:
            hours: list[OperatingHourValue] = validate_operating_hours(req.operating_hours)
        except OperatingHoursError as exc:
            raise errors.InvalidFieldError(str(exc), field=exc.field) from exc
        return {
            "address": address,
            "latitude": req.latitude,
            "longitude": req.longitude,
            "hotline": hotline,
            "totalTechnicians": req.total_technicians,
            "emergencySlotsReserved": req.emergency_slots_reserved,
            "operatingHours": [h.to_json() for h in hours],
        }

    def _lock_owner(self, owner: WorkshopOwner) -> WorkshopOwner:
        """Re-read the owner row ``FOR UPDATE`` (no-op lock on SQLite)."""
        return self._db.exec(
            select(WorkshopOwner)
            .where(WorkshopOwner.id == owner.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).one()

    def _assert_onboarding_open(self, owner: WorkshopOwner) -> None:
        if owner.onboarding_status == _OS.ACTIVE:
            raise errors.OnboardingStateError("Bạn đã hoàn tất onboarding.", code="ONBOARDING_ALREADY_COMPLETED")
        if owner.onboarding_status == _OS.PENDING_WORKSHOP_VERIFICATION:
            raise errors.OnboardingStateError("Hệ thống đang xác thực với hãng.", code="VERIFICATION_IN_PROGRESS")

    def _assert_consent(self, consent: schemas.ConsentIn, purpose: str) -> None:
        if not consent.granted or consent.policy_version not in self._policy_versions:
            raise errors.ConsentRequiredError(f"Bạn cần đồng ý điều khoản {purpose} để tiếp tục.")

    def _taken_by_other(self, column, value: str, owner_id: UUID) -> bool:
        stmt = select(WorkshopOwner).where(column == value, WorkshopOwner.id != owner_id)
        return self._db.exec(stmt).first() is not None

    def _is_expired(self, owner: WorkshopOwner) -> bool:
        if owner.onboarding_status not in (_OS.ONBOARDING_IN_PROGRESS, _OS.VERIFICATION_FAILED):
            return False
        created = _aware(owner.created_at)
        return created is not None and created < _now() - timedelta(days=self._retention_days)

    def _failed_attempts_window(self, owner_id: UUID) -> list[WorkshopVerificationAttempt]:
        window_start = _now() - timedelta(hours=24)
        stmt = select(WorkshopVerificationAttempt).where(
            WorkshopVerificationAttempt.owner_id == owner_id,
            WorkshopVerificationAttempt.status == AttemptStatus.FAILED,
        )
        return [
            a
            for a in self._db.exec(stmt).all()
            if a.failure_reason != _REASON.OEM_UNAVAILABLE.value and _aware(a.requested_at) >= window_start
        ]

    def _failed_last_24h(self, owner_id: UUID) -> int:
        return len(self._failed_attempts_window(owner_id))

    def _seconds_until_window_frees(self, owner_id: UUID) -> int:
        attempts = self._failed_attempts_window(owner_id)
        if not attempts:
            return 0
        oldest = min(_aware(a.requested_at) for a in attempts)
        return max(0, int((oldest + timedelta(hours=24) - _now()).total_seconds()))

    # ==================================================================
    # Persistence helpers
    # ==================================================================
    def _upsert_draft(self, owner_id: UUID, payload: dict) -> WorkshopRegistration:
        draft = self._draft_registration(owner_id)
        if draft is None:
            draft = WorkshopRegistration(
                owner_id=owner_id,
                address=payload["address"],
                hotline=payload["hotline"],
                total_technicians=payload["totalTechnicians"],
            )
        draft.address = payload["address"]
        draft.latitude = _to_decimal(payload["latitude"])
        draft.longitude = _to_decimal(payload["longitude"])
        draft.hotline = payload["hotline"]
        draft.total_technicians = payload["totalTechnicians"]
        draft.emergency_slots_reserved = payload["emergencySlotsReserved"]
        draft.operating_hours = payload["operatingHours"]
        draft.verification_status = WorkshopVerificationStatus.PENDING
        draft.verification_failure_reason = None
        draft.external_center_id = None
        self._db.add(draft)
        self._db.flush()
        return draft

    def _draft_registration(self, owner_id: UUID) -> WorkshopRegistration | None:
        stmt = select(WorkshopRegistration).where(
            WorkshopRegistration.owner_id == owner_id,
            WorkshopRegistration.verification_status != WorkshopVerificationStatus.VERIFIED,
        )
        return self._db.exec(stmt).first()

    def _latest_attempt(self, owner_id: UUID) -> WorkshopVerificationAttempt | None:
        stmt = (
            select(WorkshopVerificationAttempt)
            .where(WorkshopVerificationAttempt.owner_id == owner_id)
            .order_by(WorkshopVerificationAttempt.requested_at.desc())  # type: ignore[union-attr]
        )
        return self._db.exec(stmt).first()

    def _owned_workshop(self, owner_id: UUID) -> Workshop | None:
        return self._db.exec(select(Workshop).where(Workshop.owner_id == owner_id)).first()

    def _record_consent_if_changed(self, owner_id: UUID, consent_type: ConsentType, consent: schemas.ConsentIn) -> None:
        current = self._current_consent(owner_id, consent_type)
        if current is not None and current.granted == consent.granted:
            return
        self._db.add(
            WorkshopOwnerConsent(
                owner_id=owner_id,
                consent_type=consent_type,
                policy_version=consent.policy_version,
                granted=consent.granted,
                created_at=_now(),
            )
        )

    def _current_consent(self, owner_id: UUID, consent_type: ConsentType) -> WorkshopOwnerConsent | None:
        stmt = (
            select(WorkshopOwnerConsent)
            .where(
                WorkshopOwnerConsent.owner_id == owner_id,
                WorkshopOwnerConsent.consent_type == consent_type,
            )
            .order_by(WorkshopOwnerConsent.created_at.desc())  # type: ignore[union-attr]
        )
        return self._db.exec(stmt).first()

    def _current_consents(self, owner_id: UUID) -> dict[str, schemas.ConsentStateOut | None]:
        out: dict[str, schemas.ConsentStateOut | None] = {}
        for key, ctype in (
            ("personalDataProcessing", ConsentType.PERSONAL_DATA_PROCESSING),
            ("oemDataSharing", ConsentType.OEM_DATA_SHARING),
        ):
            c = self._current_consent(owner_id, ctype)
            out[key] = schemas.ConsentStateOut(granted=c.granted, policy_version=c.policy_version) if c else None
        return out

    # ==================================================================
    # Serialization
    # ==================================================================
    def _state(self, owner: WorkshopOwner) -> schemas.WorkshopOnboardingStateOut:
        profile_completed = owner.profile_completed_at is not None
        return schemas.WorkshopOnboardingStateOut(
            status=owner.onboarding_status.name,
            next_step=compute_next_step(owner.onboarding_status, profile_completed).value,
            profile_completed=profile_completed,
            profile_completed_at=owner.profile_completed_at,
            completed_at=owner.onboarding_completed_at,
            expires_at=compute_expires_at(_aware(owner.created_at), owner.onboarding_status, self._retention_days),
        )

    @staticmethod
    def _owner_summary(owner: WorkshopOwner) -> schemas.OwnerSummaryOut:
        return schemas.OwnerSummaryOut(
            owner_id=owner.id,
            email=owner.email,
            display_name=owner.display_name,
            avatar_url=owner.avatar_url,
            full_name=owner.full_name,
            account_status=owner.status.name,
            roles=list(_ROLES),
        )

    @staticmethod
    def _profile_out(owner: WorkshopOwner) -> schemas.OwnerProfileOut:
        return schemas.OwnerProfileOut(
            email=owner.email,
            full_name=owner.full_name,
            phone_number=owner.phone,
            national_id_masked=mask_national_id(owner.national_id),
        )

    @staticmethod
    def _registration_out(reg: WorkshopRegistration) -> schemas.RegistrationOut:
        return schemas.RegistrationOut(
            registration_id=reg.id,
            address=reg.address,
            latitude=_to_float(reg.latitude),
            longitude=_to_float(reg.longitude),
            hotline=reg.hotline,
            total_technicians=reg.total_technicians,
            emergency_slots_reserved=reg.emergency_slots_reserved,
            operating_hours=[schemas.OperatingHourOut.model_validate(h) for h in reg.operating_hours],
            verification_status=reg.verification_status.name,
            failure_reason=reg.verification_failure_reason.upper() if reg.verification_failure_reason else None,
        )

    def _latest_attempt_out(self, owner_id: UUID, attempt: WorkshopVerificationAttempt) -> schemas.LatestAttemptOut:
        return schemas.LatestAttemptOut(
            attempt_id=attempt.id,
            status=self._verification_status_name(attempt.status),
            failure_reason=attempt.failure_reason.upper() if attempt.failure_reason else None,
            retry_count=attempt.retry_count,
            requested_at=attempt.requested_at,
            responded_at=attempt.responded_at,
            failed_attempts_last24h=self._failed_last_24h(owner_id),
            max_failed_attempts=self._max_failed_attempts,
        )

    def _workshop_out(self, workshop: Workshop) -> schemas.WorkshopSummaryOut:
        hours = self._db.exec(
            select(WorkshopOperatingHour)
            .where(WorkshopOperatingHour.workshop_id == workshop.id)
            .order_by(WorkshopOperatingHour.day_of_week)  # type: ignore[arg-type]
        ).all()
        return schemas.WorkshopSummaryOut(
            workshop_id=workshop.id,
            center_id=workshop.external_center_id,
            name=workshop.name,
            region=workshop.region,
            type=workshop.type.name,
            status=workshop.status.name,
            address=workshop.address,
            latitude=_to_float(workshop.latitude),
            longitude=_to_float(workshop.longitude),
            hotline=workshop.hotline,
            total_technicians=workshop.total_technicians,
            emergency_slots_reserved=workshop.emergency_slots_reserved,
            operating_hours=[
                schemas.OperatingHourOut(
                    day_of_week=h.day_of_week,
                    is_closed=h.is_closed,
                    open_time=h.open_time.strftime("%H:%M") if h.open_time else None,
                    close_time=h.close_time.strftime("%H:%M") if h.close_time else None,
                )
                for h in hours
            ],
            onboarded_at=workshop.onboarded_at,
        )
