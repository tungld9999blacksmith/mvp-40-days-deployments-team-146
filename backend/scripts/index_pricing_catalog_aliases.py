"""Index official pricing extracts when the embedding quota is unavailable.

The payload text and metadata always come from the new official raw documents.
Only the dense vector is inherited from a related, already embedded VinFast
document. BM25 therefore searches the exact new pricing text. Run a normal
full re-index later to replace these temporary related-source vectors.
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


TARGETS = {
    "pricing_thiet_bi_sac_ALL_chk_0002": (
        "pricing_tram_sac_ALL",
        "Bộ sạc treo tường AC 7,4 kW",
    ),
    "pricing_phu_kien_VF5_chk_0002": (
        "warranty_maintenance_VF5",
        "VF 5",
    ),
    "pricing_phu_kien_VF8_chk_0002": (
        "warranty_maintenance_VF8",
        "VF 8",
    ),
    "pricing_bao_gia_dich_vu_ALL_chk_0002": (
        "dich_vu_bao_duong_ALL",
        "báo giá",
    ),
    "pricing_bao_gia_dich_vu_ALL_chk_0003": (
        "quy_trinh_ung_dung_ALL",
        "bảng báo giá",
    ),
}

RAW_FILES = (
    "pricing_thiet_bi_sac_ALL.md",
    "pricing_phu_kien_VF5.md",
    "pricing_phu_kien_VF8.md",
    "pricing_bao_gia_dich_vu_ALL.md",
)


def _find_source(client: QdrantClient, collection: str, doc_id: str, marker: str):
    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter={
            "must": [{"key": "document_id", "match": {"value": doc_id}}]
        },
        limit=100,
        with_payload=True,
        with_vectors=True,
    )
    return next(
        (
            point
            for point in points
            if marker.casefold() in str((point.payload or {}).get("content", "")).casefold()
        ),
        None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    args = parser.parse_args()

    client_kwargs = {"url": os.environ["QDRANT_URL"]}
    if os.getenv("QDRANT_API_KEY"):
        client_kwargs["api_key"] = os.environ["QDRANT_API_KEY"]
    client = QdrantClient(**client_kwargs, timeout=120)

    engine = IngestionEngine()
    cleaner = TextCleaner()
    chunker = DocumentChunker()
    chunks = {}
    for filename in RAW_FILES:
        document = engine.ingest_file(ROOT / "data/knowledge/raw" / filename)
        for chunk in chunker.chunk_document(cleaner.clean(document)):
            chunks[chunk.chunk_id] = chunk

    points = []
    for chunk_id, (source_doc_id, marker) in TARGETS.items():
        chunk = chunks.get(chunk_id)
        if chunk is None:
            raise RuntimeError(f"Missing generated chunk: {chunk_id}")
        source = _find_source(client, args.collection, source_doc_id, marker)
        if source is None or source.vector is None:
            raise RuntimeError(
                f"No related source vector for {chunk_id}: {source_doc_id}/{marker!r}"
            )

        metadata = dict(chunk.metadata)
        metadata["vector_inherited_from"] = str(source.id)
        metadata["vector_source_document_id"] = source_doc_id
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
                    "category": metadata.get("category", "pricing"),
                    "milestone_km": metadata.get("milestone_km"),
                    "embedding_model": "inherited-from-related-official-source",
                    "metadata": metadata,
                },
            )
        )

    for start in range(0, len(points), 4):
        client.upsert(
            collection_name=args.collection,
            points=points[start : start + 4],
            wait=True,
        )
    print(f"Indexed {len(points)} official pricing chunks into {args.collection}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
