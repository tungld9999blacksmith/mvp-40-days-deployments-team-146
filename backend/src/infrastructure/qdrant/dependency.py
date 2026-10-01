from __future__ import annotations

from functools import lru_cache

from .qdrant_service import QdrantService


def get_qdrant_service(
    url: str | None = None,
    api_key: str | None = None,
    prefer_grpc: bool | None = None,
) -> QdrantService:
    """Dependency cung cấp singleton instance của QdrantService."""
    from ...config import get_settings

    settings = get_settings()
    return _cached_service(
        url=settings.qdrant_url if url is None else url,
        api_key=settings.qdrant_api_key if api_key is None else api_key,
        prefer_grpc=settings.qdrant_prefer_grpc if prefer_grpc is None else prefer_grpc,
    )


@lru_cache
def _cached_service(url: str, api_key: str, prefer_grpc: bool) -> QdrantService:
    return QdrantService(url=url, api_key=api_key, prefer_grpc=prefer_grpc)
