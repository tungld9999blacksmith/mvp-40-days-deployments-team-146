"""Photos of extra items — private bucket, signed URLs only (bao-gia-hai-tang D16, RR2, OV5, OV6).

Upload flow: the workshop asks for a signed upload into
``booking-lines/{booking_id}/pending/{uuid}`` before the line exists; when it
sends the line, ``validate`` checks each key (this booking's prefix, uploaded in
the last 12 h, ≤ 5 MB, real JPEG/PNG/WebP bytes) and the service stores the key
on ``booking_line_photo``. Files are never moved. ``purge_pending`` removes
pending objects older than 24 h that no line references, re-checking the DB
right before each delete. Photos never enter the LLM context.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlmodel import Session, select

from src.common.core.maintenance.booking_line import BookingLinePhoto
from src.infrastructure.storage import FileStorage, SignedUpload, StorageError, StorageNotFoundError

from . import errors
from .domain import MAX_PHOTO_BYTES, MAX_PHOTOS, PHOTO_TYPES

logger = logging.getLogger(__name__)

ROOT = "booking-lines"
ATTACH_WINDOW = timedelta(hours=12)
PURGE_AFTER = timedelta(hours=24)
_PENDING_NAME = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class CheckedPhoto:
    key: str
    content_type: str
    size_bytes: int


def sniff_image_type(head: bytes) -> str | None:
    """Content type from the file signature, or None when it is not JPEG/PNG/WebP."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def pending_prefix(booking_id: UUID) -> str:
    return f"{ROOT}/{booking_id}/pending/"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LinePhotos:
    def __init__(
        self,
        storage: FileStorage,
        *,
        url_ttl_seconds: int = 600,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._storage = storage
        self._ttl = url_ttl_seconds
        self._clock = clock

    def sign_upload(self, booking_id: UUID, content_type: str) -> SignedUpload:
        if content_type not in PHOTO_TYPES:
            raise errors.PhotoInvalidError("Ảnh tối đa 5 MB, định dạng JPG/PNG/WebP.", reason="BAD_TYPE")
        try:
            return self._storage.create_signed_upload(pending_prefix(booking_id) + uuid4().hex)
        except StorageError as exc:
            logger.exception("booking_line.photo_sign_failed", extra={"booking_id": str(booking_id)})
            raise errors.ServiceUnavailableError() from exc

    def validate(self, booking_id: UUID, keys: list[str]) -> list[CheckedPhoto]:
        if len(keys) > MAX_PHOTOS:
            raise errors.PhotoInvalidError(f"At most {MAX_PHOTOS} photos per item.", reason="TOO_MANY")
        if len(set(keys)) != len(keys):
            raise errors.PhotoInvalidError("The same photo was sent twice.", reason="DUPLICATE")
        prefix = pending_prefix(booking_id)
        return [self._check(prefix, key) for key in keys]

    def _check(self, prefix: str, key: str) -> CheckedPhoto:
        if not key.startswith(prefix) or not _PENDING_NAME.match(key[len(prefix) :]):
            raise errors.PhotoInvalidError("The photo does not belong to this booking.", reason="WRONG_BOOKING")
        try:
            info = self._storage.info(key)
        except StorageNotFoundError as exc:
            raise errors.PhotoInvalidError("The photo was not uploaded.", reason="MISSING") from exc
        except StorageError as exc:
            raise errors.ServiceUnavailableError() from exc
        created = info.created_at or info.updated_at
        if created is None or self._clock() - created > ATTACH_WINDOW:
            raise errors.PhotoInvalidError("The photo upload expired, please upload it again.", reason="EXPIRED")
        if not info.size or info.size > MAX_PHOTO_BYTES:
            self._discard(key)
            raise errors.PhotoInvalidError("Ảnh tối đa 5 MB, định dạng JPG/PNG/WebP.", reason="TOO_LARGE")
        try:
            data = self._storage.download(key)
        except StorageError as exc:
            raise errors.ServiceUnavailableError() from exc
        content_type = sniff_image_type(data[:16])
        if content_type is None or len(data) > MAX_PHOTO_BYTES:
            self._discard(key)
            raise errors.PhotoInvalidError("Ảnh tối đa 5 MB, định dạng JPG/PNG/WebP.", reason="BAD_TYPE")
        return CheckedPhoto(key=key, content_type=content_type, size_bytes=len(data))

    def _discard(self, key: str) -> None:
        try:
            self._storage.delete(key)
        except StorageError:
            logger.warning("booking_line.photo_discard_failed", extra={"key": key})

    def urls(self, keys: list[str]) -> dict[str, str]:
        """One batch of short-lived signed URLs; an outage hides photos, never the lines."""
        if not keys:
            return {}
        try:
            return self._storage.signed_urls(keys, self._ttl)
        except StorageError:
            logger.warning("booking_line.photo_urls_failed", extra={"count": len(keys)})
            return {}

    def purge_pending(self, session: Session) -> int:
        """Delete pending uploads older than 24 h that no line references (OV5)."""
        cutoff = self._clock() - PURGE_AFTER
        removed = 0
        for obj in self._storage.iter_objects(ROOT, recursive=True):
            if "/pending/" not in obj.key:
                continue
            created = obj.created_at or obj.updated_at
            if created is None or created > cutoff:
                continue
            # Re-check right before deleting: a line may have attached it meanwhile.
            if session.exec(select(BookingLinePhoto.id).where(BookingLinePhoto.storage_key == obj.key)).first():
                continue
            self._discard(obj.key)
            removed += 1
        return removed
