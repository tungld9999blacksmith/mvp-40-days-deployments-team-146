from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from google.genai import errors as genai_errors

from src.infrastructure.llm.base import ChatMessage, LLMAuthError, LLMInvalidRequestError
from src.infrastructure.llm.gemini_provider import GeminiProvider


def _fake_response(text: str = "Hello!") -> SimpleNamespace:
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(value="STOP"))],
        usage_metadata=SimpleNamespace(prompt_token_count=6, candidates_token_count=2),
    )


@pytest.fixture
def provider() -> GeminiProvider:
    p = GeminiProvider(api_key="test-key", model="gemini-2.5-flash")
    p._client.aio.models.generate_content = AsyncMock(return_value=_fake_response())
    return p


@pytest.mark.asyncio
async def test_chat_maps_response_fields(provider: GeminiProvider):
    result = await provider.chat([ChatMessage(role="user", content="Hi")])

    assert result.text == "Hello!"
    assert result.stop_reason == "STOP"
    assert result.usage.input_tokens == 6
    assert result.usage.output_tokens == 2


@pytest.mark.asyncio
async def test_assistant_role_is_mapped_to_model(provider: GeminiProvider):
    await provider.chat(
        [
            ChatMessage(role="user", content="Hi"),
            ChatMessage(role="assistant", content="Hello, how can I help?"),
            ChatMessage(role="user", content="Tell me a joke"),
        ]
    )

    kwargs = provider._client.aio.models.generate_content.call_args.kwargs
    roles = [c.role for c in kwargs["contents"]]
    assert roles == ["user", "model", "user"]


@pytest.mark.asyncio
async def test_system_message_becomes_system_instruction(provider: GeminiProvider):
    await provider.chat(
        [
            ChatMessage(role="system", content="Be terse."),
            ChatMessage(role="user", content="Hi"),
        ]
    )

    kwargs = provider._client.aio.models.generate_content.call_args.kwargs
    assert kwargs["config"].system_instruction == "Be terse."


@pytest.mark.asyncio
async def test_auth_error_is_translated(provider: GeminiProvider):
    provider._client.aio.models.generate_content = AsyncMock(
        side_effect=genai_errors.ClientError(401, {"error": {"message": "bad key"}})
    )

    with pytest.raises(LLMAuthError):
        await provider.chat([ChatMessage(role="user", content="Hi")])


@pytest.mark.asyncio
async def test_bad_request_error_is_translated(provider: GeminiProvider):
    provider._client.aio.models.generate_content = AsyncMock(
        side_effect=genai_errors.ClientError(400, {"error": {"message": "bad request"}})
    )

    with pytest.raises(LLMInvalidRequestError):
        await provider.chat([ChatMessage(role="user", content="Hi")])
