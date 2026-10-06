"""Index curated raw extracts by reusing vectors of equivalent source chunks.

Use this only when embedding quota is unavailable. Every curated chunk below is
an extract/restructure of an already embedded VinFast FAQ chunk. A normal full
re-index remains the preferred path once embedding quota is available.
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


CHUNK_SOURCE_MARKERS = {
    "pricing_tram_sac_ALL_chk_0003": "3,858 VNĐ/kWh",
    "pricing_tram_sac_ALL_chk_0004": "áp dụng từ 01/11/2025",
    "pricing_tram_sac_ALL_chk_0005": "2.000 đồng/phút",
    "pricing_tram_sac_ALL_chk_0006": "không áp dụng cho các dòng xe máy điện",
    "pricing_tram_sac_ALL_chk_0007": "giá 10,8 triệu đồng",
    "battery_sac_VF7_chk_0002": "Công suất sạc Pin tối đa trên VinFast VF 7",
    "battery_sac_VF7_chk_0003": "VF 7 Eco: 25 phút",
    "quy_trinh_ung_dung_ALL_chk_0002": "Cách tìm kiếm trạm sạc qua Ứng dụng VinFast",
    "quy_trinh_ung_dung_ALL_chk_0003": "Cách tìm kiếm trạm sạc qua Ứng dụng VinFast",
    "quy_trinh_ung_dung_ALL_chk_0004": "Cách tìm kiếm trạm sạc qua Ứng dụng VinFast",
    "quy_trinh_ung_dung_ALL_chk_0005": "Vào mục Lịch sử sạc",
    "quy_trinh_ung_dung_ALL_chk_0006": "Bấm Đặt dịch vụ",
    "quy_trinh_ung_dung_ALL_chk_0008": "Vào Dịch vụ, chọn Đặt dịch vụ",
}

CURATED_FILES = (
    "pricing_tram_sac_ALL.md",
    "battery_sac_VF7.md",
    "quy_trinh_ung_dung_ALL.md",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", required=True)
    args = parser.parse_args()

    kwargs = {"url": os.environ["QDRANT_URL"]}
    if os.getenv("QDRANT_API_KEY"):
        kwargs["api_key"] = os.environ["QDRANT_API_KEY"]
    client = QdrantClient(**kwargs, timeout=120)

    source_points = []
    offset = None
    while True:
        batch, offset = client.scroll(
            collection_name=args.collection,
            scroll_filter={
                "must": [
                    {"key": "document_id", "match": {"value": "faq_baoduong_baohanh_ALL"}}
                ]
            },
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        source_points.extend(batch)
        if offset is None:
            break

    engine = IngestionEngine()
    cleaner = TextCleaner()
    chunker = DocumentChunker()
    curated_chunks = []
    for filename in CURATED_FILES:
        document = engine.ingest_file(ROOT / "data/knowledge/raw" / filename)
        curated_chunks.extend(chunker.chunk_document(cleaner.clean(document)))

    points = []
    for chunk in curated_chunks:
        marker = CHUNK_SOURCE_MARKERS.get(chunk.chunk_id)
        if marker is None:
            continue
        source = next(
            (
                point
                for point in source_points
                if marker.casefold()
                in str((point.payload or {}).get("content", "")).casefold()
            ),
            None,
        )
        if source is None or source.vector is None:
            raise RuntimeError(f"No equivalent source vector for {chunk.chunk_id}: {marker!r}")

        metadata = dict(chunk.metadata)
        metadata["derived_from"] = "faq_baoduong_baohanh_ALL"
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
                    "category": metadata.get("category", "general"),
                    "milestone_km": metadata.get("milestone_km"),
                    "embedding_model": "inherited-from-equivalent-official-faq",
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
    print(f"Indexed {len(points)} curated raw chunks into {args.collection}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
