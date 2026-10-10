"""Resolve stage overrides without changing shared settings or API keys."""

import logging
from typing import Literal

from ...config import Settings

logger = logging.getLogger(__name__)

LLMStage = Literal["orchestrator", "agent", "rewrite", "rag", "booking", "write"]

_MODEL_FIELDS = {
    "openrouter": "openrouter_model",
    "openai": "model_name",
    "gemini": "gemini_model",
    "anthropic": "anthropic_model",
    "grok": "grok_model",
    "deepseek": "deepseek_model",
}
_API_KEY_FIELDS = {provider: f"{provider}_api_key" for provider in _MODEL_FIELDS}


def model_for_provider(provider: str) -> str:
    if provider not in _MODEL_FIELDS:
        raise ValueError(f"Unsupported LLM provider: {provider!r}")
    return _MODEL_FIELDS[provider]


def settings_for_stage(settings: Settings, stage: LLMStage) -> Settings:
    if stage not in ("orchestrator", "agent", "rewrite", "rag", "booking", "write"):
        raise ValueError(f"Unknown LLM stage: {stage!r}")
    canonical = {"agent": "orchestrator", "write": "booking"}.get(stage, stage)
    provider = getattr(settings, f"llm_{canonical}_provider") or settings.llm_provider
    model = getattr(settings, f"llm_{canonical}_model")
    # Explicit cross-provider stage settings win. Existing OPENROUTER_*_MODEL
    # configuration remains usable when those new settings are left blank.
    if not model and provider == "openrouter":
        legacy = "agent" if canonical == "orchestrator" else stage
        if legacy in ("agent", "rewrite", "rag", "write"):
            model = settings.openrouter_model_for_stage(legacy)
    updates = {"llm_provider": provider}
    if model:
        updates[model_for_provider(provider)] = model
    return settings.model_copy(update=updates)


def fallback_provider(settings: Settings) -> str:
    """Return the usable fallback for stage-resolved settings, or "" when none applies.

    A fallback without its API key is disabled instead of breaking the primary provider.
    """
    name = settings.llm_fallback_provider
    if not name or name == settings.llm_provider:
        return ""
    if not getattr(settings, _API_KEY_FIELDS[name]).strip():
        logger.warning("LLM_FALLBACK_PROVIDER=%s has no API key; fallback disabled", name)
        return ""
    return name
