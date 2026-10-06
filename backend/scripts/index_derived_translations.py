"""Index traceable translations by inheriting vectors from equivalent source chunks.

This is a quota-safe fallback for a translated document whose meaning is already
represented by an embedded source document. BM25 indexes the translated payload;
dense search continues to use the vector of the cited source claim. Re-embedding
the translated chunks normally on the next full rebuild is still preferred.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.models import PointStruct

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "src")]
load_dotenv(ROOT / ".env")

from src.agents.tools.RAG.ingestion import DocumentChunker, IngestionEngine, TextCleaner  # noqa: E402


SOURCE_MARKERS = {
    "Chính sách bảo hành VinFast hiện hành - bản chuẩn hóa tiếng Việt": "# Warranty Policy",
    "Thời hạn bảo hành xe mới": "Fadil, Lux A 2.0",
    "Bảo hành pin cao áp theo xe mới": "High-voltage battery supplied with a new vehicle",
    "Bảo hành ắc quy 12V": "#### 12V battery",
    "Bảo hành các bộ phận hệ thống treo": "#### Suspension Components",
    "Bảo hành phụ tùng thay thế chính hãng": "Parts, excluding the 12V battery",
    "Bảo hành pin cao áp mua thay thế": "A battery purchased by the customer",
    "Xe sử dụng cho mục đích thương mại": "Commercial use applies to business customers",
    "Các trường hợp loại trừ bảo hành liên quan ngập nước và tai nạn": "flooded conditions",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    args = parser.parse_args()

    kwargs = {"url": os.environ["QDRANT_URL"]}
    if os.getenv("QDRANT_API_KEY"):
        kwargs["api_key"] = os.environ["QDRANT_API_KEY"]
    client = QdrantClient(**kwargs)

    source_points = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=args.collection,
            scroll_filter={"must": [{"key": "document_id", "match": {"value": "warranty_policy_ALL"}}]},
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        source_points.extend(batch)
        if offset is None:
            break

    document = IngestionEngine().ingest_file(ROOT / "knowledge/derived/warranty_policy_vi.md")
    chunks = DocumentChunker().chunk_document(TextCleaner().clean(document))
    points = []
    for chunk in chunks:
        header = chunk.metadata.get("section_header", "")
        marker = SOURCE_MARKERS[header]
        source = next(
            (point for point in source_points if marker.casefold() in str((point.payload or {}).get("content", "")).casefold()),
            None,
        )
        if source is None or source.vector is None:
            raise RuntimeError(f"No embedded source chunk found for {header!r} / {marker!r}")
        metadata = dict(chunk.metadata)
        metadata["derived_from"] = "warranty_policy_ALL"
        metadata["vector_inherited_from"] = str(source.id)
        points.append(
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id)),
                vector=source.vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.doc_id,
                    "content": chunk.content,
                    "source": metadata.get("source", ""),
                    "model": metadata.get("model", "ALL"),
                    "category": metadata.get("category", "warranty"),
                    "milestone_km": metadata.get("milestone_km"),
                    "embedding_model": "inherited-from-equivalent-source-translation",
                    "metadata": metadata,
                },
            )
        )

    client.upsert(collection_name=args.collection, points=points, wait=True)
    print(f"Indexed {len(points)} translated chunks into {args.collection}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
