from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.infrastructure.embedding.factory import create_embedding_engine
from src.infrastructure.embedding.openai_provider import OpenAIEmbeddingEngine


def _settings(**overrides) -> Settings:
    # Pass every relevant field: the developer's .env is already in os.environ.
    fields = {
        "embedding_provider": "openrouter",
        "embedding_dimensions": 3072,
        "embedding_openrouter_model": "google/gemini-embedding-001",
        "openrouter_api_key": "or-test-key",
        "openrouter_base_url": "https://openrouter.ai/api/v1",
        "openai_api_key": "sk-openai-test",
        "embedding_openai_model": "text-embedding-3-small",
    }
    fields.update(overrides)
    return Settings(_env_file=None, **fields)


def test_openrouter_engine_uses_openrouter_key_url_and_model():
    engine = create_embedding_engine(_settings())

    assert isinstance(engine, OpenAIEmbeddingEngine)
    assert engine.provider_name == "openrouter"
    assert engine.identity == "openrouter:google/gemini-embedding-001"
    assert engine.dimensions == 3072
    assert engine._sync.api_key == "or-test-key"
    assert str(engine._sync.base_url).rstrip("/") == "https://openrouter.ai/api/v1"


def test_openrouter_engine_requests_configured_dimensions():
    engine = create_embedding_engine(_settings(embedding_dimensions=4))
    create = MagicMock(return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3, 0.4])]))
    engine._sync = SimpleNamespace(embeddings=SimpleNamespace(create=create))

    assert engine.embed_query("lịch bảo dưỡng VF8") == [0.1, 0.2, 0.3, 0.4]
    create.assert_called_once_with(model="google/gemini-embedding-001", input=["lịch bảo dưỡng VF8"], dimensions=4)


def test_openai_engine_keeps_openai_identity():
    engine = create_embedding_engine(_settings(embedding_provider="openai"))

    assert engine.identity == "openai:text-embedding-3-small"
    assert engine._sync.api_key == "sk-openai-test"


def test_unknown_embedding_provider_is_rejected():
    with pytest.raises(ValidationError):
        _settings(embedding_provider="anthropic")
