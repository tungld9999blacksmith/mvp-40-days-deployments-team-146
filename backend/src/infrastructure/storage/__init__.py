"""File storage — one bucket-style interface over object stores.

- ``FileStorage``            — abstract port (upload / download / list / delete / URLs)
- ``StoredObject`` / ``SignedUpload`` — I/O value objects
- ``StorageError`` + subclasses — provider-agnostic errors
- ``SupabaseFileStorage``    — Supabase Storage backend
- ``create_file_storage`` / ``get_file_storage`` — factory + DI
"""

from .base import (
    FileStorage,
    SignedUpload,
    StorageConflictError,
    StorageError,
    StorageNotFoundError,
    StoragePermissionError,
    StoredObject,
    guess_content_type,
    join_key,
    normalize_key,
    safe_key,
    safe_key_segment,
)
from .dependency import get_file_storage, get_file_storage_for_bucket
from .factory import create_file_storage

__all__ = [
    "FileStorage",
    "SignedUpload",
    "StorageConflictError",
    "StorageError",
    "StorageNotFoundError",
    "StoragePermissionError",
    "StoredObject",
    "create_file_storage",
    "get_file_storage",
    "get_file_storage_for_bucket",
    "guess_content_type",
    "join_key",
    "normalize_key",
    "safe_key",
    "safe_key_segment",
]
