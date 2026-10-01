"""
File storage abstraction — one bucket-style interface over object stores.

Design decisions:
    - One `FileStorage` instance is bound to ONE bucket. Callers address
      objects by *key* ("folder/sub/file.pdf"), never by bucket, so swapping
      bucket or provider is a config change only.
    - Keys are normalized by `normalize_key` before every call: forward
      slashes only, no leading "/", no "." / ".." segments.
    - Callers depend on `FileStorage` + the error hierarchy below, never on a
      provider SDK or its exception types.

This file has NO dependency on any provider SDK — concrete stores do.
"""

from __future__ import annotations

import mimetypes
import re
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO

from pydantic import BaseModel, Field

DEFAULT_CONTENT_TYPE = "application/octet-stream"


# -- errors -----------------------------------------------------------------
class StorageError(Exception):
    """Base exception for file storage errors."""


class StorageNotFoundError(StorageError):
    """The object (or bucket) does not exist."""


class StorageConflictError(StorageError):
    """The object already exists and overwrite was not requested."""


class StoragePermissionError(StorageError):
    """The credentials are not allowed to perform the operation."""


# -- value objects ----------------------------------------------------------
class StoredObject(BaseModel):
    """Metadata of one object (or one virtual folder when `is_folder`)."""

    key: str
    name: str
    size: int | None = None
    content_type: str | None = None
    etag: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_folder: bool = False
    # Custom metadata attached at upload time (e.g. original file name).
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignedUpload(BaseModel):
    """Pre-signed upload target a client (e.g. the frontend) can PUT to directly."""

    key: str
    url: str
    token: str


# -- key helpers ------------------------------------------------------------
_UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9._\-/]+")


def normalize_key(key: str) -> str:
    """Return a canonical object key or raise `ValueError`.

    Converts backslashes (Windows paths) to "/", strips leading/trailing
    slashes and collapses empty segments. Rejects "." and ".." segments.
    """
    parts = [p for p in key.replace("\\", "/").split("/") if p]
    if any(p in (".", "..") for p in parts):
        raise ValueError(f"Invalid storage key (relative segment): {key!r}")
    normalized = "/".join(parts)
    if not normalized:
        raise ValueError("Storage key must not be empty")
    return normalized


def normalize_prefix(prefix: str | None) -> str:
    """Folder prefix without leading/trailing slash ("" = bucket root)."""
    if not prefix:
        return ""
    return normalize_key(prefix)


def join_key(*parts: str) -> str:
    return normalize_key("/".join(p for p in parts if p))


def safe_key_segment(name: str) -> str:
    """ASCII-safe version of one key segment (file or folder name).

    Many providers (Supabase included) reject non-ASCII keys, so Vietnamese
    names are transliterated: "Sổ tay bảo dưỡng VF8.pdf" -> "So-tay-bao-duong-VF8.pdf".
    """
    text = name.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = _UNSAFE_KEY_CHARS.sub("-", text.replace("/", "-"))
    text = re.sub(r"-*\.-*", ".", re.sub(r"-{2,}", "-", text)).strip("-.")
    if not text:
        raise ValueError(f"Cannot build a safe storage key from {name!r}")
    return text


def safe_key(key: str) -> str:
    """Apply `safe_key_segment` to every segment of *key*."""
    return "/".join(safe_key_segment(p) for p in normalize_key(key).split("/"))


def guess_content_type(name: str) -> str:
    content_type, _ = mimetypes.guess_type(name)
    return content_type or DEFAULT_CONTENT_TYPE


# -- interface --------------------------------------------------------------
class FileStorage(ABC):
    """Standardized interface every concrete file storage must implement.

    All methods are synchronous (provider SDKs are sync); call them from sync
    route handlers, Celery tasks or `run_in_threadpool` in async code.
    """

    def __init__(self, bucket: str) -> None:
        self._bucket = bucket

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """Stable identifier, e.g. "supabase"."""

    # -- write ------------------------------------------------------------
    @abstractmethod
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
        """Store *data* under *key*.

        Raises `StorageConflictError` when the key exists and `overwrite` is False.
        `content_type` defaults to a guess from the key's extension.
        """

    def upload_file(
        self,
        local_path: str | Path,
        key: str | None = None,
        *,
        content_type: str | None = None,
        overwrite: bool = False,
        cache_control_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StoredObject:
        """Upload a local file. *key* defaults to the ASCII-safe file name."""
        path = Path(local_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        target = key or safe_key_segment(path.name)
        with path.open("rb") as fh:
            return self.upload(
                target,
                fh,
                content_type=content_type or guess_content_type(path.name),
                overwrite=overwrite,
                cache_control_seconds=cache_control_seconds,
                metadata=metadata,
            )

    @abstractmethod
    def delete(self, keys: str | list[str]) -> list[str]:
        """Delete objects; returns the keys actually deleted (missing keys are skipped)."""

    def delete_prefix(self, prefix: str) -> list[str]:
        """Delete every object under *prefix* (a "folder"). Returns deleted keys."""
        keys = [obj.key for obj in self.iter_objects(prefix, recursive=True)]
        deleted: list[str] = []
        for start in range(0, len(keys), 100):
            deleted.extend(self.delete(keys[start : start + 100]))
        return deleted

    @abstractmethod
    def move(self, src_key: str, dst_key: str) -> None:
        """Move / rename an object inside the bucket."""

    @abstractmethod
    def copy(self, src_key: str, dst_key: str) -> None:
        """Copy an object inside the bucket."""

    # -- read -------------------------------------------------------------
    @abstractmethod
    def download(self, key: str) -> bytes:
        """Return the object's content. Raises `StorageNotFoundError`."""

    def download_to(self, key: str, local_path: str | Path) -> Path:
        """Download into *local_path* (a file, or an existing directory)."""
        target = Path(local_path)
        if target.is_dir():
            target = target / normalize_key(key).rsplit("/", 1)[-1]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.download(key))
        return target

    @abstractmethod
    def exists(self, key: str) -> bool:
        """True when an object is stored under *key*."""

    @abstractmethod
    def info(self, key: str) -> StoredObject:
        """Metadata of one object. Raises `StorageNotFoundError`."""

    @abstractmethod
    def list(
        self,
        prefix: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
        search: str | None = None,
    ) -> list[StoredObject]:
        """One page of the direct children of *prefix* (files and folders)."""

    def iter_objects(
        self,
        prefix: str | None = None,
        *,
        recursive: bool = False,
        page_size: int = 100,
    ) -> Iterator[StoredObject]:
        """Iterate all files under *prefix*, following pages (and sub-folders
        when *recursive*). Folders themselves are not yielded."""
        folders = [normalize_prefix(prefix)]
        while folders:
            folder = folders.pop()
            offset = 0
            while True:
                page = self.list(folder, limit=page_size, offset=offset)
                for obj in page:
                    if not obj.is_folder:
                        yield obj
                    elif recursive:
                        folders.append(obj.key)
                if len(page) < page_size:
                    break
                offset += page_size

    # -- URLs -------------------------------------------------------------
    @abstractmethod
    def signed_url(self, key: str, expires_in: int, *, download: bool | str = False) -> str:
        """Time-limited URL to read a private object.

        `download=True` forces a download; a string also sets the file name.
        """

    def signed_urls(self, keys: list[str], expires_in: int) -> dict[str, str]:
        """Signed URLs for many keys, as {key: url}."""
        return {key: self.signed_url(key, expires_in) for key in keys}

    @abstractmethod
    def public_url(self, key: str) -> str:
        """Permanent URL. Only works when the bucket is public."""

    @abstractmethod
    def create_signed_upload(self, key: str, *, overwrite: bool = False) -> SignedUpload:
        """Pre-signed upload target so a client can upload without backend credentials."""
