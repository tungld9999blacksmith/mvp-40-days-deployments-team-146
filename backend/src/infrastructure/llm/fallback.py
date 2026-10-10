"""Retry transient failures on the configured fallback before any stream output."""

from .base import (
    ChatMessage,
    GenerationConfig,
    LLMProvider,
    LLMProviderUnavailableError,
    LLMRateLimitError,
    LLMResponse,
)

TRANSIENT_ERRORS = (LLMRateLimitError, LLMProviderUnavailableError)


class FallbackLLMProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    @property
    def provider_name(self) -> str:
        return self.primary.provider_name

    async def generate_text(self, prompt: str, config: GenerationConfig | None = None) -> LLMResponse:
        return await self.chat([ChatMessage(role="user", content=prompt)], config)

    async def chat(self, messages: list[ChatMessage], config: GenerationConfig | None = None) -> LLMResponse:
        try:
            return await self.primary.chat(messages, config)
        except TRANSIENT_ERRORS:
            return await self.fallback.chat(messages, config)

    async def chat_stream(self, messages: list[ChatMessage], config: GenerationConfig | None = None):
        emitted = False
        try:
            async for chunk in self.primary.chat_stream(messages, config):
                emitted = True
                yield chunk
        except TRANSIENT_ERRORS:
            if emitted:
                raise
            async for chunk in self.fallback.chat_stream(messages, config):
                yield chunk
