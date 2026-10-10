from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "src")]

from src.agents.tools.RAG.ingestion.metadata import DocumentChunk
from src.agents.tools.RAG.ingestion.qdrant_store import QdrantVectorStore


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))


class _FakeClient:
    def __init__(self, existing: dict[str, str]):
        self.existing = existing
        self.upserted: list = []

    def retrieve(self, collection_name, ids, with_payload, with_vectors):
        return [
            SimpleNamespace(id=point_id, payload={"embedding_model": self.existing[point_id]})
            for point_id in ids
            if point_id in self.existing
        ]

    def upsert(self, collection_name, points):
        self.upserted.extend(points)


class _FakeEmbedder:
    model = "fake-embedding"

    def __init__(self):
        self.embedded: list[str] = []

    def embed_documents(self, texts):
        self.embedded.extend(texts)
        return [[0.1, 0.2] for _ in texts]


class QdrantIncrementalIndexingTests(unittest.TestCase):
    def test_inherited_vectors_are_reembedded_and_real_vectors_skipped(self):
        chunks = [
            DocumentChunk(chunk_id=cid, doc_id="doc", content=cid, metadata={}, chunk_index=i, total_chunks=3)
            for i, cid in enumerate(["real_chk", "inherited_chk", "new_chk"])
        ]
        client = _FakeClient({
            _point_id("real_chk"): "text-embedding-004",
            _point_id("inherited_chk"): "inherited-from-related-official-source",
        })
        embedder = _FakeEmbedder()
        store = QdrantVectorStore.__new__(QdrantVectorStore)
        store._client = client
        store.collection_name = "test"
        store.embedding_provider = embedder

        store.add_chunks(chunks, sleep_between_batches=0)

        self.assertEqual(embedder.embedded, ["inherited_chk", "new_chk"])
        self.assertEqual(
            {point.id for point in client.upserted},
            {_point_id("inherited_chk"), _point_id("new_chk")},
        )
        self.assertTrue(all(point.payload["embedding_model"] == "fake-embedding" for point in client.upserted))


if __name__ == "__main__":
    unittest.main()
