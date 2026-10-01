from __future__ import annotations

from functools import lru_cache

from ...config import get_settings
from .base import LLMProvider
from .factory import create_llm_provider


@lru_cache
def _cached_provider(name: str) -> LLMProvider:
    return create_llm_provider(get_settings(), provider=name)


def get_llm_provider() -> LLMProvider:
    """Default provider dependency — reads `settings.llm_provider`."""
    return _cached_provider(get_settings().llm_provider)


def get_llm_provider_by_name(name: str) -> LLMProvider:
    """Explicit provider selection, e.g. for a route that lets callers pick one."""
    return _cached_provider(name)
