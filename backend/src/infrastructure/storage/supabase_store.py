"""Supabase Storage implementation of `FileStorage` (the only file that imports the SDK)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, BinaryIO, TypeVar

from storage3.exceptions import StorageApiError
from storage3.types import CreateSignedUploadUrlOptions
from storage3.utils import StorageException

from .base import (
    FileStorage,
    SignedUpload,
    StorageConflictError,
    StorageError,
    StorageNotFoundError,
    StoragePermissionError,
    StoredObject,
    guess_content_type,
    normalize_key,
    normalize_prefix,
)

T = TypeVar("T")


def _translate(exc: Exception, key: str | None = None) -> StorageError:
    """Map SDK exceptions onto the provider-agnostic error hierarchy."""
    target = f" ({key})" if key else ""
    if isinstance(exc, StorageApiError):
        status = str(exc.status)
        code = str(exc.code or "").lower()
        message = str(exc.message or "")
        text = f"{message}{target}"
        if status == "404" or "not_found" in code or "not found" in message.lower():
            return StorageNotFoundError(text)
        if status == "409" or "duplicate" in code or "already exists" in message.lower():
            return StorageConflictError(text)
        if status in ("401", "403") or "unauthorized" in code:
            return StoragePermissionError(text)
        return StorageError(f"[{status}] {text}")
    return StorageError(f"{exc}{target}")


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class SupabaseFileStorage(FileStorage):
    """`FileStorage` over one Supabase Storage bucket.

    *client* is a `supabase.Client` (or anything exposing `.storage.from_(bucket)`).
    Use a server-side secret key: it bypasses Storage RLS policies.
    """

    def __init__(self, client: Any, bucket: str) -> None:
        super().__init__(bucket)
        self._client = client

    @property
    def backend_name(self) -> str:
        return "supabase"

    def _api(self) -> Any:
        return self._client.storage.from_(self._bucket)

    def _call(self, fn: Callable[[], T], key: str | None = None) -> T:
        try:
            return fn()
        except (StorageApiError, StorageException) as exc:
            raise _translate(exc, key) from exc

    # -- write ------------------------------------------------------------
    def upload(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str | None = None,
        overwrite: bool = False,
        cache_control_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StoredObject:
        key = normalize_key(key)
        content_type = content_type or guess_content_type(key)
        options: dict[str, Any] = {
            "content-type": content_type,
            "upsert": "true" if overwrite else "false",
        }
        if cache_control_seconds is not None:
            options["cache-control"] = str(cache_control_seconds)
        if metadata:
            options["metadata"] = metadata
        body = data if isinstance(data, bytes) else data.read()

        self._call(lambda: self._api().upload(key, body, options), key)
        return StoredObject(
            key=key,
            name=key.rsplit("/", 1)[-1],
            size=len(body),
            content_type=content_type,
            metadata=metadata or {},
        )

    def delete(self, keys: str | list[str]) -> list[str]:
        keys = [normalize_key(k) for k in ([keys] if isinstance(keys, str) else keys)]
        if not keys:
            return []
        removed = self._call(lambda: self._api().remove(keys))
        return [item.get("name", "") for item in removed or []]

    def move(self, src_key: str, dst_key: str) -> None:
        src, dst = normalize_key(src_key), normalize_key(dst_key)
        self._call(lambda: self._api().move(src, dst), src)

    def copy(self, src_key: str, dst_key: str) -> None:
        src, dst = normalize_key(src_key), normalize_key(dst_key)
        self._call(lambda: self._api().copy(src, dst), src)

    # -- read -------------------------------------------------------------
    def download(self, key: str) -> bytes:
        key = normalize_key(key)
        return self._call(lambda: self._api().download(key), key)

    def exists(self, key: str) -> bool:
        key = normalize_key(key)
        try:
            return bool(self._api().exists(key))
        except (StorageApiError, StorageException) as exc:
            err = _translate(exc, key)
            if isinstance(err, StorageNotFoundError):
                return False
            raise err from exc

    def info(self, key: str) -> StoredObject:
        key = normalize_key(key)
        raw = self._call(lambda: self._api().info(key), key)
        return StoredObject(
            key=key,
            name=key.rsplit("/", 1)[-1],
            size=raw.get("size"),
            content_type=raw.get("content_type"),
            etag=raw.get("etag"),
            created_at=_parse_dt(raw.get("created_at")),
            updated_at=_parse_dt(raw.get("last_modified") or raw.get("updated_at")),
            metadata=raw.get("metadata") or {},
        )

    def list(
        self,
        prefix: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
    ) -> list[StoredObject]:
        folder = normalize_prefix(prefix)
        options: dict[str, Any] = {"limit": limit, "offset": offset}
        if search:
            options["search"] = search
        items = self._call(lambda: self._api().list(folder, options), folder or None)
        return [self._to_object(folder, item) for item in items or []]

    @staticmethod
    def _to_object(folder: str, item: dict[str, Any]) -> StoredObject:
        name = item["name"]
        key = f"{folder}/{name}" if folder else name
        # Supabase returns virtual folders with no id and no metadata.
        if item.get("id") is None:
            return StoredObject(key=key, name=name, is_folder=True)
        meta = item.get("metadata") or {}
        return StoredObject(
            key=key,
            name=name,
            size=meta.get("size"),
            content_type=meta.get("mimetype"),
            etag=meta.get("eTag"),
            created_at=_parse_dt(item.get("created_at")),
            updated_at=_parse_dt(item.get("updated_at")),
            metadata=item.get("user_metadata") or {},
        )

    # -- URLs -------------------------------------------------------------
    def signed_url(self, key: str, expires_in: int, *, download: bool | str = False) -> str:
        key = normalize_key(key)
        options = {"download": download} if download else None
        res = self._call(lambda: self._api().create_signed_url(key, expires_in, options), key)
        url = res.get("signedURL") or res.get("signedUrl")
        if not url:
            raise StorageNotFoundError(f"No signed URL returned ({key})")
        return url

    def signed_urls(self, keys: list[str], expires_in: int) -> dict[str, str]:
        keys = [normalize_key(k) for k in keys]
        if not keys:
            return {}
        rows = self._call(lambda: self._api().create_signed_urls(keys, expires_in))
        return {row["path"]: row["signedURL"] for row in rows if row.get("signedURL") and not row.get("error")}

    def public_url(self, key: str) -> str:
        key = normalize_key(key)
        return self._api().get_public_url(key)

    def create_signed_upload(self, key: str, *, overwrite: bool = False) -> SignedUpload:
        key = normalize_key(key)
        options = CreateSignedUploadUrlOptions(upsert="true") if overwrite else None
        res = self._call(lambda: self._api().create_signed_upload_url(key, options), key)
        return SignedUpload(key=key, url=res["signed_url"], token=res["token"])
