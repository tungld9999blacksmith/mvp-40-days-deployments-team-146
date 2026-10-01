from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from qdrant_client import QdrantClient, models

from src.config import Settings
from src.infrastructure.vectorstore import VectorError, VectorRecord
from src.infrastructure.vectorstore.factory import create_vector_store
from src.infrastructure.vectorstore.qdrant_store import QdrantVectorStore


@pytest.fixture
def client():
    value = QdrantClient(":memory:")
    try:
        yield value
    finally:
        value.close()


@pytest.fixture
def embedding():
    return SimpleNamespace(
        dimensions=3,
        identity="test:fixed",
        embed_documents=lambda texts: [[1.0, 0.0, 0.0] for _ in texts],
        embed_query=lambda text: [1.0, 0.0, 0.0],
        aembed_query=AsyncMock(return_value=[1.0, 0.0, 0.0]),
    )


def test_chat_upsert_filter_roundtrip_and_delete(client, embedding):
    store = QdrantVectorStore(embedding, client)
    store.add(
        "conversation_messages",
        [
            VectorRecord(id="message-a", content="first", metadata={"conversationId": "a"}),
            VectorRecord(id="message-b", content="second", metadata={"conversationId": "b"}),
        ],
    )
    hits = store.similarity_search("conversation_messages", "query", where={"conversationId": "a"})
    assert [h.id for h in hits] == ["message-a"]
    assert hits[0].embedding_model == "test:fixed"
    assert hits[0].score == pytest.approx(1)
    store.add(
        "conversation_messages", [VectorRecord(id="message-a", content="updated", metadata={"conversationId": "a"})]
    )
    assert store.count("conversation_messages") == 2
    store.delete("conversation_messages", ["message-a"])
    assert store.count("conversation_messages") == 1
    assert store.similarity_search("conversation_messages", "query", where={"conversationId": "a"}) == []
    store.delete_collection("conversation_messages")
    assert store.count("conversation_messages") == 0


@pytest.mark.asyncio
async def test_reads_existing_rag_payload_with_citations(client, embedding):
    client.create_collection("knowledge", vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
    client.upsert(
        "knowledge",
        points=[
            models.PointStruct(
                id=QdrantVectorStore._point_id("chunk-original"),
                vector=[1.0, 0.0, 0.0],
                payload={
                    "chunk_id": "chunk-original",
                    "document_id": "doc-1",
                    "content": "Battery warranty",
                    "page": 7,
                    "metadata": {"source": "manual.pdf"},
                    "embedding_model": "test:fixed",
                },
            )
        ],
    )
    store = QdrantVectorStore(embedding, client, knowledge_collection="knowledge")
    hits = await store.asimilarity_search("*", "battery")
    assert hits[0].id == "chunk-original"
    assert hits[0].metadata == {"source": "manual.pdf", "document_id": "doc-1", "page_number": 7}
    assert store.similarity_search("doc-2", "battery") == []
    assert store.count("doc-1") == 1
    assert store.count("*") == 1


def test_knowledge_deletion_is_scoped(client, embedding):
    store = QdrantVectorStore(embedding, client, knowledge_collection="knowledge")
    for doc in ["a", "b"]:
        store.add(doc, [VectorRecord(id=f"chunk-{doc}", content=doc)])
    store.delete("a", ["chunk-b"])
    assert store.count("b") == 1
    with pytest.raises(ValueError):
        store.delete_collection("*")
    store.delete_collection("a")
    assert store.count("*") == 1
    assert store.count("b") == 1


def test_dimension_mismatch_preserves_existing_collection(client, embedding):
    client.create_collection("legacy", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
    client.upsert("legacy", [models.PointStruct(id=1, vector=[1.0, 0.0])])
    store = QdrantVectorStore(embedding, client)
    with pytest.raises(VectorError, match="dimensions"):
        store.add("legacy", [VectorRecord(id="new", content="new")])
    assert client.count("legacy").count == 1
    assert client.get_collection("legacy").config.params.vectors.size == 2


def test_missing_collection_read_does_not_create_it(client, embedding):
    store = QdrantVectorStore(embedding, client)
    assert store.similarity_search("missing", "query") == []
    assert not client.collection_exists("missing")


def test_default_factory_routes_to_qdrant(monkeypatch, client, embedding):
    from src.infrastructure.qdrant import dependency

    monkeypatch.setattr(dependency, "get_qdrant_service", lambda *args: SimpleNamespace(client=client))
    settings = Settings(_env_file=None)
    assert settings.vector_store == "qdrant"
    assert create_vector_store(settings, embedding).backend_name == "qdrant"
    with pytest.raises(ValueError, match="Unknown vector store"):
        create_vector_store(settings, embedding, backend="unknown")


def test_knowledge_dependency_uses_configured_qdrant(monkeypatch, client, embedding):
    from src.infrastructure.qdrant import dependency as qdrant_dependency
    from src.infrastructure.vectorstore import dependency

    settings = Settings(_env_file=None, vector_store="qdrant", qdrant_collection_name="knowledge")
    monkeypatch.setattr(dependency, "get_settings", lambda: settings)
    monkeypatch.setattr(dependency, "get_embedding_engine_by_name", lambda provider: embedding)
    monkeypatch.setattr(qdrant_dependency, "get_qdrant_service", lambda *args: SimpleNamespace(client=client))
    dependency._cached_knowledge_store.cache_clear()
    try:
        store = dependency.get_knowledge_vector_store()
        store.add("doc-1", [VectorRecord(id="chunk-1", content="knowledge")])
        assert client.count("knowledge").count == 1
        assert store.similarity_search("*", "query")[0].id == "chunk-1"
    finally:
        dependency._cached_knowledge_store.cache_clear()


def test_rag_ingester_rejects_incompatible_existing_collection(monkeypatch, client):
    from src.agents.tools.RAG.ingestion.qdrant_store import QdrantVectorStore as RagStore
    from src.infrastructure.qdrant import dependency

    client.create_collection("knowledge", vectors_config=models.VectorParams(size=3, distance=models.Distance.COSINE))
    monkeypatch.setattr(dependency, "get_qdrant_service", lambda *args: SimpleNamespace(client=client))
    with pytest.raises(ValueError, match="3072"):
        RagStore(collection_name="knowledge", embedding_provider=SimpleNamespace(model="gemini-embedding-001"))
    assert client.get_collection("knowledge").config.params.vectors.size == 3


@pytest.mark.asyncio
async def test_health_reports_qdrant(monkeypatch):
    from src.modules.health import service

    probe = Mock()
    monkeypatch.setattr(service, "get_qdrant_service", lambda: SimpleNamespace(client=probe))
    monkeypatch.setattr(service, "_ping_redis", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_ping_database", lambda: "dialect=postgresql")
    result = await service.check_dependencies()
    assert result.status == "ok"
    assert set(result.checks) == {"qdrant", "redis", "database"}
    probe.get_collections.assert_called_once()
