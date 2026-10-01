from __future__ import annotations

from functools import lru_cache

from ...config import get_settings
from .base import FileStorage
from .factory import create_file_storage


@lru_cache
def _cached_storage(backend: str, bucket: str | None) -> FileStorage:
    return create_file_storage(get_settings(), backend=backend, bucket=bucket)


def get_file_storage() -> FileStorage:
    """Default storage dependency — `settings.file_storage` + its default bucket."""
    return _cached_storage(get_settings().file_storage, None)


def get_file_storage_for_bucket(bucket: str) -> FileStorage:
    """Same backend, explicit bucket (e.g. a separate attachments bucket)."""
    return _cached_storage(get_settings().file_storage, bucket)
