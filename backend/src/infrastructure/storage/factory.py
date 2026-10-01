from __future__ import annotations

from ...config import Settings
from .base import FileStorage, StorageError


def create_file_storage(
    settings: Settings,
    backend: str | None = None,
    bucket: str | None = None,
) -> FileStorage:
    """Build the FileStorage for *backend* (or `settings.file_storage`) bound to
    *bucket* (or the backend's default bucket from settings)."""
    name = backend or settings.file_storage

    if name == "supabase":
        if not settings.supabase_url or not settings.supabase_key:
            raise StorageError("SUPABASE_URL and SUPABASE_KEY must be set to use Supabase Storage")
        from supabase import create_client

        from .supabase_store import SupabaseFileStorage

        client = create_client(settings.supabase_url, settings.supabase_key)
        return SupabaseFileStorage(client, bucket or settings.supabase_storage_bucket)

    raise ValueError(f"Unknown file storage backend: {name!r}")
