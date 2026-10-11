"""Role configuration must reach real composition roots without external calls."""
import os
from types import SimpleNamespace

import pytest

from src.agents import graph
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.rewriter import QueryRewriter
from src.config import Settings
from src.infrastructure.llm import dependency


@pytest.fixture(autouse=True)
def clean_stage_cache(monkeypatch):
    # RAG imports load the local .env into os.environ; isolate configuration tests.
    for name in list(os.environ):
        if name.startswith(("LLM_", "OPENROUTER_", "GEMINI_", "GOOGLE_")) or name == "MODEL_NAME":
            monkeypatch.delenv(name)
    dependency._cached_provider.cache_clear()
    dependency._cached_stage_provider.cache_clear()
    yield
    dependency._cached_provider.cache_clear()
    dependency._cached_stage_provider.cache_clear()


def configured(**overrides):
    return Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="test-key", openrouter_model="shared-model",
                    openrouter_agent_model="agent-model", openrouter_rewrite_model="rewrite-model", openrouter_rag_model="rag-model",
                    openrouter_write_model="write-model", **overrides)


def test_role_models_are_loaded_from_env_file(tmp_path, monkeypatch):
    for name in ("LLM_PROVIDER", "OPENROUTER_MODEL", "OPENROUTER_AGENT_MODEL", "OPENROUTER_REWRITE_MODEL", "OPENROUTER_RAG_MODEL", "OPENROUTER_WRITE_MODEL"):
        monkeypatch.delenv(name, raising=False)
    env = tmp_path / "models.env"
    env.write_text("LLM_PROVIDER=openrouter\nOPENROUTER_MODEL=shared\nOPENROUTER_AGENT_MODEL=agent\nOPENROUTER_REWRITE_MODEL=rewrite\nOPENROUTER_RAG_MODEL=rag\nOPENROUTER_WRITE_MODEL=write\n", encoding="utf-8")
    settings = Settings(_env_file=env)
    assert [settings.openrouter_model_for_stage(role) for role in ("agent", "rewrite", "rag", "write")] == ["agent", "rewrite", "rag", "write"]


def test_process_environment_overrides_model_from_file(tmp_path, monkeypatch):
    env = tmp_path / "models.env"
    env.write_text("OPENROUTER_RAG_MODEL=file-model\n", encoding="utf-8")
    monkeypatch.setenv("OPENROUTER_RAG_MODEL", "process-model")
    assert Settings(_env_file=env).openrouter_model_for_stage("rag") == "process-model"


@pytest.mark.parametrize("role", ["agent", "rewrite", "rag", "write"])
def test_unset_or_blank_role_keeps_legacy_model(role):
    for value in (None, "", "  "):
        settings = Settings(_env_file=None, openrouter_model="legacy", **{"openrouter_" + role + "_model": value})
        assert settings.openrouter_model_for_stage(role) == "legacy"


def test_unknown_role_is_not_silently_treated_as_default():
    with pytest.raises(ValueError, match="Unknown LLM stage"):
        configured().openrouter_model_for_stage("unknown")


def test_default_agent_rewriter_and_generator_use_their_own_models(monkeypatch):
    settings = configured()
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    assert graph.get_agent_llm().model_name == "agent-model"
    assert QueryRewriter().llm_provider._model == "rewrite-model"
    assert GroundedAnswerGenerator().llm_provider._model == "rag-model"
    assert settings.openrouter_model == "shared-model"
    # The write provider is not constructed by any of those read/proposal paths.
    assert dependency._cached_stage_provider.cache_info().currsize == 2


def test_same_model_can_share_a_client_without_collapsing_distinct_models(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="test-key", openrouter_model="shared",
                        openrouter_agent_model="same", openrouter_rewrite_model="same", openrouter_rag_model="different")
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    assert dependency.get_llm_provider_for_stage("agent") is dependency.get_llm_provider_for_stage("rewrite")
    assert dependency.get_llm_provider_for_stage("rag") is not dependency.get_llm_provider_for_stage("agent")
    assert dependency.get_llm_provider()._model == "shared"


def test_non_openrouter_provider_preserves_existing_selection(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="gemini", openrouter_rag_model="ignored-openrouter-model")
    calls = []
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    def create(settings, provider):
        calls.append((settings, provider))
        return SimpleNamespace(provider_name=provider)
    monkeypatch.setattr(dependency, "create_llm_provider", create)
    assert dependency.get_llm_provider_for_stage("rag") is dependency.get_llm_provider()
    assert len(calls) == 1 and calls[0][1] == "gemini"


def test_explicit_injected_rag_providers_are_preserved():
    injected = object()
    assert QueryRewriter(injected).llm_provider is injected
    assert GroundedAnswerGenerator(injected).llm_provider is injected


def test_role_routing_reaches_agent_and_stage_provider_without_affecting_write(monkeypatch):
    settings = configured().model_copy(update={"openrouter_endpoint_order": "", "openrouter_agent_endpoint_order": "mistral/us, mistral/eu", "openrouter_rewrite_endpoint_order": "mistral/eu", "openrouter_rag_endpoint_order": "mistral/us"})
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    assert graph.get_agent_llm().extra_body["provider"]["order"] == ["mistral/us", "mistral/eu"]
    rewrite = QueryRewriter().llm_provider
    generation = GroundedAnswerGenerator().llm_provider
    assert rewrite._default_endpoint_order == ["mistral/eu"]
    assert generation._default_endpoint_order == ["mistral/us"]
    assert settings.openrouter_endpoints_for_stage("write") == ()


def test_identical_models_with_different_routes_do_not_share_cached_provider(monkeypatch):
    settings = configured().model_copy(update={"openrouter_agent_model": "same", "openrouter_rag_model": "same", "openrouter_agent_endpoint_order": "mistral/us", "openrouter_rag_endpoint_order": "mistral/eu"})
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    assert dependency.get_llm_provider_for_stage("agent") is not dependency.get_llm_provider_for_stage("rag")
