from __future__ import annotations

from ...config import Settings
from .base import LLMProvider


def create_llm_provider(settings: Settings, provider: str | None = None) -> LLMProvider:
    """Build the LLMProvider for *provider* (or `settings.llm_provider` if omitted)."""
    name = provider or settings.llm_provider

    # Tự động fallback sang Gemini nếu OpenAI chưa có key nhưng Gemini có key
    if name == "openai" and not settings.openai_api_key and settings.gemini_api_key:
        name = "gemini"

    if name == "openrouter":
        from .openai_compatible_provider import OpenAICompatibleProvider

        if not settings.openrouter_api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        return OpenAICompatibleProvider(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            provider_name="openrouter",
            base_url=settings.openrouter_base_url,
            default_max_tokens=settings.openrouter_max_tokens,
        )
    if name == "openai":
        from .openai_compatible_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            api_key=settings.openai_api_key,
            model=settings.model_name,
            provider_name="openai",
        )
    if name == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    if name == "gemini":
        from .gemini_provider import GeminiProvider

        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        )
    if name == "grok":
        from .openai_compatible_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            api_key=settings.grok_api_key,
            model=settings.grok_model,
            provider_name="grok",
            base_url=settings.grok_base_url,
        )
    if name == "deepseek":
        from .openai_compatible_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            provider_name="deepseek",
            base_url=settings.deepseek_base_url,
        )

    raise ValueError(f"Unknown LLM provider: {name!r}")
