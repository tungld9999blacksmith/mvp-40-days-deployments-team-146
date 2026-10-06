"""Provider selection must not depend on unrelated API keys being present."""

import pytest
from langchain_openai import ChatOpenAI

from src.agents import graph
from src.config import Settings


def test_agent_openrouter_uses_selected_provider_and_supports_tool_binding(monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_provider="openrouter",
        openrouter_api_key="test-openrouter-key",
        openrouter_model="google/gemini-3.5-flash-lite",
        openrouter_base_url="https://openrouter.ai/api/v1",
        gemini_api_key="test-gemini-key",
        openai_api_key="test-openai-key",
        chat_run_timeout_seconds=15,
    )
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    llm = graph.get_agent_llm()
    assert isinstance(llm, ChatOpenAI)
    assert llm.openai_api_base == settings.openrouter_base_url
    assert llm.openai_api_key.get_secret_value() == settings.openrouter_api_key
    assert llm.model_name == settings.openrouter_model
    assert llm.request_timeout == 15
    assert llm.max_tokens == settings.openrouter_max_tokens
    bound = llm.bind_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "get_current_km",
                    "description": "Read the current odometer",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
    )
    assert bound.kwargs["tools"][0]["function"]["name"] == "get_current_km"


def test_agent_openrouter_missing_key_does_not_select_gemini(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="", gemini_api_key="test-key")
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        graph.get_agent_llm()
