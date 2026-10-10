"""Provider selection must not depend on unrelated API keys being present."""

import pytest
from langchain_openai import ChatOpenAI

from src.agents import graph
from src.config import Settings


@pytest.fixture(autouse=True)
def isolate_stage_overrides(monkeypatch):
    monkeypatch.delenv("LLM_ORCHESTRATOR_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_ORCHESTRATOR_MODEL", raising=False)


def test_agent_openrouter_uses_selected_provider_and_supports_tool_binding(monkeypatch):
    settings = Settings(
        _env_file=None,
        llm_provider="openrouter",
        openrouter_api_key="test-openrouter-key",
        openrouter_model="google/gemini-3.5-flash-lite",
        openrouter_agent_model=None,
        openrouter_base_url="https://openrouter.ai/api/v1",
        gemini_api_key="test-gemini-key",
        openai_api_key="test-openai-key",
        llm_call_timeout_seconds=15,
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


def test_agent_uses_orchestrator_override_without_changing_rag_default(monkeypatch):
    settings = Settings(
        _env_file=None, llm_provider="openrouter", openrouter_api_key="test-key",
        llm_orchestrator_provider="openrouter", llm_orchestrator_model="mistralai/mistral-small-2603",
        openrouter_model="google/gemma-4-26b-a4b-it",
    )
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    assert graph.get_agent_llm().model_name == "mistralai/mistral-small-2603"
    assert settings.openrouter_model == "google/gemma-4-26b-a4b-it"


def test_agent_openai_selection_is_not_overridden_by_gemini_key(monkeypatch):
    settings = Settings(
        _env_file=None, llm_provider="openai", openai_api_key="test-openai-key",
        gemini_api_key="test-google-key", model_name="gpt-4o",
    )
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    assert isinstance(graph.get_agent_llm(), ChatOpenAI)
    assert graph.get_agent_llm().model_name == "gpt-4o"


def _fallback_settings(**overrides):
    values = dict(
        _env_file=None, llm_provider="openrouter", openrouter_api_key="test-key", gemini_api_key="test-google-key",
        llm_fallback_provider="gemini", llm_booking_check_enabled=False, llm_call_timeout_seconds=10,
    )
    return Settings(**{**values, **overrides})


def test_graph_builds_when_fallback_key_is_missing(monkeypatch):
    from langgraph.checkpoint.memory import MemorySaver

    monkeypatch.setattr(graph, "get_settings", lambda: _fallback_settings(gemini_api_key=""))
    assert graph.build_graph(tools=[], checkpointer=MemorySaver()) is not None
    # Without a usable fallback the primary keeps its own retry.
    assert graph.get_agent_llm().max_retries == 1


def test_primary_leaves_turn_budget_for_fallback(monkeypatch):
    settings = _fallback_settings()
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    primary = graph.get_agent_llm()
    assert primary.max_retries == 0
    assert primary.request_timeout == settings.llm_call_timeout_seconds < settings.chat_run_timeout_seconds
    assert graph.get_agent_llm(fallback=True).max_retries == 1
