from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

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

_ROLE_MAP = {"user": "user", "assistant": "model"}


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "gemini"

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
        contents, gen_config = self._build_request(messages, config)

        max_retries = 3
        last_error = None
        response = None
        for attempt in range(max_retries):
            try:
                response = await self._client.aio.models.generate_content(
                    model=self._model, contents=contents, config=gen_config
                )
                break
            except genai_errors.ClientError as exc:
                last_error = _map_client_error(exc)
                if exc.code == 429 and attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise last_error
            except genai_errors.ServerError as exc:
                last_error = LLMProviderUnavailableError(exc.message)
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise last_error from exc
            except Exception as exc:
                if attempt < max_retries - 1 and (
                    "demand" in str(exc).lower() or "503" in str(exc) or "429" in str(exc)
                ):
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                raise exc

        if response is None:
            if last_error:
                raise last_error
            raise LLMProviderUnavailableError("Max retries exceeded without response")

        candidate = response.candidates[0] if response.candidates else None
        usage = response.usage_metadata
        return LLMResponse(
            text=response.text or "",
            model=self._model,
            stop_reason=candidate.finish_reason.value if candidate and candidate.finish_reason else None,
            usage=LLMUsage(
                input_tokens=(usage.prompt_token_count or 0) if usage else 0,
                output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            ),
            raw=response,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        config: GenerationConfig | None = None,
    ) -> AsyncIterator[str]:
        config = config or GenerationConfig()
        contents, gen_config = self._build_request(messages, config)

        try:
            stream = await self._client.aio.models.generate_content_stream(
                model=self._model, contents=contents, config=gen_config
            )
            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except genai_errors.ClientError as exc:
            raise _map_client_error(exc)
        except genai_errors.ServerError as exc:
            raise LLMProviderUnavailableError(exc.message) from exc

    def _build_request(
        self,
        messages: list[ChatMessage],
        config: GenerationConfig,
    ) -> tuple[list[genai_types.Content], genai_types.GenerateContentConfig]:
        system_parts = [m.content for m in messages if m.role == "system"]
        contents = [
            genai_types.Content(
                role=_ROLE_MAP.get(m.role, "user"),
                parts=[genai_types.Part(text=m.content)],
            )
            for m in messages
            if m.role != "system"
        ]

        config_kwargs = dict(config.extra)
        if system_parts:
            config_kwargs.setdefault("system_instruction", "\n".join(system_parts))
        if config.temperature is not None:
            config_kwargs.setdefault("temperature", config.temperature)
        if config.top_p is not None:
            config_kwargs.setdefault("top_p", config.top_p)
        if config.top_k is not None:
            config_kwargs.setdefault("top_k", config.top_k)
        if config.max_tokens is not None:
            config_kwargs.setdefault("max_output_tokens", config.max_tokens)
        if config.stop_sequences:
            config_kwargs.setdefault("stop_sequences", config.stop_sequences)

        return contents, genai_types.GenerateContentConfig(**config_kwargs)


def _map_client_error(exc: genai_errors.ClientError) -> Exception:
    if exc.code in (401, 403):
        return LLMAuthError(exc.message)
    if exc.code == 429:
        return LLMRateLimitError(exc.message)
    return LLMInvalidRequestError(exc.message)
