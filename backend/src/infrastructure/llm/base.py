"""
LLM provider abstraction — standardizes generation calls across OpenAI,
Anthropic (Claude), Gemini, Grok, and DeepSeek behind a single interface.

Rules:
    - This file has NO dependency on any provider SDK.
    - Concrete adapters (anthropic_provider.py, etc.) implement `LLMProvider`
      and are the only files allowed to import a provider SDK.
    - Callers depend on `LLMProvider` + the error hierarchy below, never on
      a concrete provider class or a provider's own exception types.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant"]


class ChatMessage(BaseModel):
    role: Role
    content: str


class GenerationConfig(BaseModel):
    """
    Common generation parameters. Fields left as None are omitted from the
    provider request instead of being sent as a provider-specific default.

    `extra` carries provider-specific parameters (e.g. Claude's `thinking`,
    Gemini's `safety_settings`) that don't belong in the common interface.
    """

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=1)
    max_tokens: int | None = Field(default=None, ge=1)
    stop_sequences: list[str] | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class LLMUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(BaseModel):
    text: str
    model: str
    stop_reason: str | None = None
    usage: LLMUsage = Field(default_factory=LLMUsage)
    raw: Any = None

    model_config = {"arbitrary_types_allowed": True}


# ---------------------------------------------------------------------------
# Errors — providers must translate their SDK's exceptions into these.
# ---------------------------------------------------------------------------
class LLMProviderError(Exception):
    """Base exception for all LLM provider errors."""


class LLMAuthError(LLMProviderError):
    """Invalid or missing API key/credentials."""


class LLMRateLimitError(LLMProviderError):
    """Provider rate limit was hit."""


class LLMInvalidRequestError(LLMProviderError):
    """Request was rejected by the provider (bad params, invalid model, ...)."""


class LLMProviderUnavailableError(LLMProviderError):
    """Network error or provider-side outage (5xx, timeout, connection error)."""


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class LLMProvider(ABC):
    """Standardized interface every concrete LLM adapter must implement."""

    @property
    @abstractmethod
    def provider_name(self) -> str: ...

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
    ) -> LLMResponse:
        """Single-turn text generation from a plain prompt."""
        ...

    @abstractmethod
    async def chat(
        self,
        messages: list[ChatMessage],
        config: GenerationConfig | None = None,
    ) -> LLMResponse:
        """
        Multi-turn chat completion.

        A `system` role message, if present, is extracted and passed using
        the provider's native system-prompt mechanism rather than being
        sent as a regular message.
        """
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        config: GenerationConfig | None = None,
    ) -> AsyncIterator[str]:
        """Multi-turn chat completion, yielding text chunks as they arrive."""
        yield ""
