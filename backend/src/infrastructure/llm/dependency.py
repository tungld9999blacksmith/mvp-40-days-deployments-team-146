from __future__ import annotations

from functools import lru_cache

from ...config import get_settings
from .base import LLMProvider
from .factory import create_llm_provider
from .fallback import FallbackLLMProvider
from .routing import LLMStage, fallback_provider, model_for_provider, settings_for_stage


@lru_cache
def _cached_provider(name: str) -> LLMProvider:
    return create_llm_provider(get_settings(), provider=name)


def get_llm_provider() -> LLMProvider:
    """Default provider dependency — reads `settings.llm_provider`."""
    return _cached_provider(get_settings().llm_provider)


def get_llm_provider_by_name(name: str) -> LLMProvider:
    """Explicit provider selection, e.g. for a route that lets callers pick one."""
    return _cached_provider(name)


@lru_cache
def _cached_stage_provider(name: str, model: str, endpoints: tuple[str, ...]) -> LLMProvider:
    settings = get_settings().model_copy(update={
        "llm_provider": name,
        model_for_provider(name): model,
        "openrouter_endpoint_order": ",".join(endpoints),
    })
    return create_llm_provider(settings, provider=name)


@lru_cache
def _cached_fallback_provider(primary: LLMProvider, fallback: LLMProvider) -> LLMProvider:
    return FallbackLLMProvider(primary, fallback)


def get_llm_provider_for_stage(stage: LLMStage) -> LLMProvider:
    """Resolve both stage conventions; cache clients by model and endpoint routing."""
    original = get_settings()
    settings = settings_for_stage(original, stage)
    provider = settings.llm_provider
    model = getattr(settings, model_for_provider(provider))
    route = {"orchestrator": "agent", "booking": "write"}.get(stage, stage)
    endpoints = settings.openrouter_endpoints_for_stage(route) if provider == "openrouter" else ()
    if provider != "openrouter" and model == getattr(original, model_for_provider(provider)):
        primary = _cached_provider(provider)
    else:
        primary = _cached_stage_provider(provider, model, endpoints)
    if fallback := fallback_provider(settings):
        backup = _cached_stage_provider(fallback, getattr(settings, model_for_provider(fallback)), ())
        return _cached_fallback_provider(primary, backup)
    return primary


def _clear_stage_caches() -> None:
    _cached_stage_provider.cache_clear()
    _cached_fallback_provider.cache_clear()
    _cached_provider.cache_clear()


# Preserve develop's cache invalidation API without caching unresolved stage names.
get_llm_provider_for_stage.cache_clear = _clear_stage_caches
