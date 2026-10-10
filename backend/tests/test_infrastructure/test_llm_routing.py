from unittest.mock import AsyncMock

import pytest

from src.config import Settings
from src.infrastructure.llm import dependency
from src.infrastructure.llm.base import LLMAuthError, LLMProviderUnavailableError, LLMRateLimitError, LLMResponse
from src.infrastructure.llm.fallback import FallbackLLMProvider
from src.infrastructure.llm.routing import settings_for_stage


@pytest.fixture
def settings():
    return Settings(
        _env_file=None,
        llm_provider="openrouter",
        openrouter_api_key="test-key",
        gemini_api_key="test-google-key",
        llm_fallback_provider="gemini",
        llm_orchestrator_provider="openrouter",
        llm_rewrite_provider="openrouter",
        llm_rag_provider="openrouter",
        llm_booking_provider="openrouter",
        llm_orchestrator_model="mistralai/mistral-small-2603",
        llm_rewrite_model="mistralai/mistral-small-2603",
        llm_rag_model="google/gemma-4-26b-a4b-it",
        llm_booking_model="openai/gpt-4o",
    )


@pytest.mark.parametrize(
    "stage,model",
    [
        ("orchestrator", "mistralai/mistral-small-2603"),
        ("rewrite", "mistralai/mistral-small-2603"),
        ("rag", "google/gemma-4-26b-a4b-it"),
        ("booking", "openai/gpt-4o"),
    ],
)
def test_stage_selects_distinct_model_and_preserves_fallback(settings, stage, model):
    resolved = settings_for_stage(settings, stage)
    assert resolved.openrouter_model == model
    assert resolved.gemini_model == "gemini-3.5-flash-lite"
    assert settings.openrouter_model == "google/gemini-3.5-flash-lite"


def test_explicit_provider_override(settings):
    settings.llm_rewrite_provider = "gemini"
    settings.llm_rewrite_model = "custom-gemini"
    resolved = settings_for_stage(settings, "rewrite")
    assert resolved.llm_provider == "gemini"
    assert resolved.gemini_model == "custom-gemini"


def test_default_stage_inherits_without_override():
    settings = Settings(_env_file=None, llm_rag_provider="", llm_rag_model="")
    assert settings_for_stage(settings, "rag").model_name == settings.model_name


def test_unknown_stage_is_rejected(settings):
    with pytest.raises(ValueError, match="Unknown LLM stage"):
        settings_for_stage(settings, "typo")


def test_cached_providers_do_not_share_model_between_stages(settings, monkeypatch):
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    dependency.get_llm_provider_for_stage.cache_clear()
    try:
        rewrite = dependency.get_llm_provider_for_stage("rewrite")
        rag = dependency.get_llm_provider_for_stage("rag")
        booking = dependency.get_llm_provider_for_stage("booking")
        assert rewrite.primary._model == settings.llm_rewrite_model
        assert rag.primary._model == settings.llm_rag_model
        assert booking.primary._model == settings.llm_booking_model
        assert rag.fallback._model == settings.gemini_model
        assert rewrite is dependency.get_llm_provider_for_stage("rewrite")
    finally:
        dependency.get_llm_provider_for_stage.cache_clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [LLMRateLimitError, LLMProviderUnavailableError])
async def test_transient_error_uses_fallback(error):
    primary, fallback = AsyncMock(), AsyncMock()
    primary.chat.side_effect = error("temporary")
    fallback.chat.return_value = LLMResponse(text="fallback", model="gemini-3.5-flash-lite")
    result = await FallbackLLMProvider(primary, fallback).chat([])
    assert result.model == "gemini-3.5-flash-lite"
    fallback.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_error_is_not_hidden_by_fallback():
    primary, fallback = AsyncMock(), AsyncMock()
    primary.chat.side_effect = LLMAuthError("invalid key")
    with pytest.raises(LLMAuthError):
        await FallbackLLMProvider(primary, fallback).chat([])
    fallback.chat.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("partial", [False, True])
async def test_stream_fallback_only_before_first_chunk(partial):
    async def primary_stream(*args):
        if partial:
            yield "partial"
        raise LLMRateLimitError("temporary")

    async def fallback_stream(*args):
        yield "fallback"

    primary, fallback = AsyncMock(), AsyncMock()
    primary.chat_stream = primary_stream
    fallback.chat_stream = fallback_stream
    provider = FallbackLLMProvider(primary, fallback)
    if partial:
        with pytest.raises(LLMRateLimitError):
            _ = [chunk async for chunk in provider.chat_stream([])]
    else:
        assert [chunk async for chunk in provider.chat_stream([])] == ["fallback"]


def test_inherited_provider_stage_model_does_not_raise():
    settings = Settings(_env_file=None, llm_provider="anthropic", llm_rag_provider="", llm_rag_model="custom-claude")
    assert settings_for_stage(settings, "rag").anthropic_model == "custom-claude"


def test_missing_fallback_key_keeps_primary(settings, monkeypatch):
    settings.gemini_api_key = ""
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    dependency.get_llm_provider_for_stage.cache_clear()
    try:
        provider = dependency.get_llm_provider_for_stage("rag")
        assert not isinstance(provider, FallbackLLMProvider)
        assert provider._model == settings.llm_rag_model
    finally:
        dependency.get_llm_provider_for_stage.cache_clear()
