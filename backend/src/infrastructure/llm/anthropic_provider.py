from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import anthropic

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

DEFAULT_MAX_TOKENS = 16000


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "anthropic"

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
        system, turns = _split_system(messages)
        kwargs = self._build_kwargs(system, turns, config)

        try:
            response = await self._client.messages.create(**kwargs)
        except anthropic.AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMProviderUnavailableError(str(exc)) from exc
            raise LLMInvalidRequestError(str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderUnavailableError(str(exc)) from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        return LLMResponse(
            text=text,
            model=response.model,
            stop_reason=response.stop_reason,
            usage=LLMUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
            raw=response,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        config: GenerationConfig | None = None,
    ) -> AsyncIterator[str]:
        config = config or GenerationConfig()
        system, turns = _split_system(messages)
        kwargs = self._build_kwargs(system, turns, config)

        try:
            async with self._client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.AuthenticationError as exc:
            raise LLMAuthError(str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise LLMRateLimitError(str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMProviderUnavailableError(str(exc)) from exc
            raise LLMInvalidRequestError(str(exc)) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderUnavailableError(str(exc)) from exc

    def _build_kwargs(
        self,
        system: str | None,
        turns: list[ChatMessage],
        config: GenerationConfig,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": config.max_tokens or DEFAULT_MAX_TOKENS,
            "messages": [{"role": m.role, "content": m.content} for m in turns],
        }
        if system:
            kwargs["system"] = system
        if config.temperature is not None:
            kwargs["temperature"] = config.temperature
        if config.top_p is not None:
            kwargs["top_p"] = config.top_p
        if config.top_k is not None:
            kwargs["top_k"] = config.top_k
        if config.stop_sequences:
            kwargs["stop_sequences"] = config.stop_sequences
        kwargs.update(config.extra)
        return kwargs


def _split_system(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
    system_parts = [m.content for m in messages if m.role == "system"]
    turns = [m for m in messages if m.role != "system"]
    system = "\n".join(system_parts) if system_parts else None
    return system, turns
