"""
Provider adapter for any OpenAI Chat Completions-compatible API.

Backs OpenAI itself, and — via `base_url` — Grok (xAI), DeepSeek and OpenRouter,
which expose an OpenAI-compatible `/chat/completions` endpoint.

Note: the Chat Completions API has no `top_k` parameter. `GenerationConfig.
top_k` is ignored here; pass it via `config.extra` only if a specific
OpenAI-compatible backend documents a non-standard extension for it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import openai

from .base import (
    ChatMessage,
    GenerationConfig,
    LLMAuthError,
    LLMInvalidRequestError,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponse,
    LLMUsage,
)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        provider_name: str = "openai",
        base_url: str | None = None,
        default_max_tokens: int | None = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._provider_name = provider_name
        self._default_max_tokens = default_max_tokens

    @property
    def provider_name(self) -> str:
        return self._provider_name

    async def generate_text(
        self,
        prompt: str,
        config: GenerationConfig | None = None,
    ) -> LLMResponse:
        return await self.chat([ChatMessage(role="user", content=prompt)], config)

    async def chat(
        self,
        messages: list[ChatMessage],
        config: GenerationConfig | None = None,
    ) -> LLMResponse:
        config = config or GenerationConfig()
        kwargs = self._build_kwargs(messages, config)

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMProviderUnavailableError(str(exc)) from exc
            raise LLMInvalidRequestError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise LLMProviderUnavailableError(str(exc)) from exc

        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            text=choice.message.content or "",
            model=response.model,
            stop_reason=choice.finish_reason,
            usage=LLMUsage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
            raw=response,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        config: GenerationConfig | None = None,
    ) -> AsyncIterator[str]:
        config = config or GenerationConfig()
        kwargs = self._build_kwargs(messages, config)
        kwargs["stream"] = True

        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yield delta
        except openai.AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMProviderUnavailableError(str(exc)) from exc
            raise LLMInvalidRequestError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise LLMProviderUnavailableError(str(exc)) from exc

    def _build_kwargs(
        self,
        messages: list[ChatMessage],
        config: GenerationConfig,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        if config.top_p is not None:
            kwargs["top_p"] = config.top_p
        if config.max_tokens is not None:
            kwargs["max_tokens"] = config.max_tokens
        elif self._default_max_tokens is not None:
            kwargs["max_tokens"] = self._default_max_tokens
        if config.stop_sequences:
            kwargs["stop"] = config.stop_sequences
        kwargs.update(config.extra)
        return kwargs
