from __future__ import annotations

from functools import lru_cache

from ...config import get_settings
from .base import EmbeddingEngine
from .factory import create_embedding_engine


@lru_cache
def _cached_engine(name: str) -> EmbeddingEngine:
    return create_embedding_engine(get_settings(), provider=name)


def get_embedding_engine() -> EmbeddingEngine:
    """Default engine dependency — reads `settings.embedding_provider`."""
    return _cached_engine(get_settings().embedding_provider)


def get_embedding_engine_by_name(name: str) -> EmbeddingEngine:
    """Explicit engine selection, e.g. for a route that lets callers pick one."""
    return _cached_engine(name)
