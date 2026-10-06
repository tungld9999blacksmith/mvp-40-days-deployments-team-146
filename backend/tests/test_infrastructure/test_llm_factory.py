import pytest

from src.config import Settings
from src.infrastructure.llm.anthropic_provider import AnthropicProvider
from src.infrastructure.llm.factory import create_llm_provider
from src.infrastructure.llm.gemini_provider import GeminiProvider
from src.infrastructure.llm.openai_compatible_provider import OpenAICompatibleProvider


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        openai_api_key="test-openai-key",
        anthropic_api_key="test-anthropic-key",
        gemini_api_key="test-gemini-key",
        grok_api_key="test-grok-key",
        deepseek_api_key="test-deepseek-key",
        openrouter_api_key="test-openrouter-key",
    )


@pytest.mark.parametrize(
    "provider_name,expected_type,expected_provider_name",
    [
        ("openai", OpenAICompatibleProvider, "openai"),
        ("anthropic", AnthropicProvider, "anthropic"),
        ("gemini", GeminiProvider, "gemini"),
        ("grok", OpenAICompatibleProvider, "grok"),
        ("deepseek", OpenAICompatibleProvider, "deepseek"),
        ("openrouter", OpenAICompatibleProvider, "openrouter"),
    ],
)
def test_create_llm_provider_dispatches_by_name(
    settings: Settings, provider_name, expected_type, expected_provider_name
):
    provider = create_llm_provider(settings, provider=provider_name)
    assert isinstance(provider, expected_type)
    assert provider.provider_name == expected_provider_name


def test_create_llm_provider_defaults_to_settings_llm_provider(settings: Settings):
    settings.llm_provider = "anthropic"
    provider = create_llm_provider(settings)
    assert isinstance(provider, AnthropicProvider)


def test_create_llm_provider_rejects_unknown_name(settings: Settings):
    with pytest.raises(ValueError):
        create_llm_provider(settings, provider="not-a-real-provider")


def test_openrouter_uses_its_key_model_and_endpoint_with_gemini_key_present(settings: Settings):
    settings.llm_provider = "openrouter"
    settings.openrouter_model = "google/gemini-3.5-flash-lite"
    provider = create_llm_provider(settings)
    assert provider.provider_name == "openrouter"
    assert provider._client.api_key == "test-openrouter-key"
    assert str(provider._client.base_url) == "https://openrouter.ai/api/v1/"
    assert provider._model == settings.openrouter_model


def test_openrouter_missing_key_does_not_fall_back_to_gemini(settings: Settings):
    settings.openrouter_api_key = ""
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        create_llm_provider(settings, provider="openrouter")
