"""
Script di chuyển và nạp toàn bộ Knowledge Base sang Qdrant Cloud (hoặc Qdrant Local)
kết hợp Embedding API Google Gemini (models/gemini-embedding-001 - 3072 dims):

Chạy từ root project:
    python backend/scripts/migrate_to_qdrant.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    getattr(sys.stdout, "reconfigure")(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    getattr(sys.stderr, "reconfigure")(encoding="utf-8")

# Tìm đường dẫn Root của Repository
CURRENT_DIR = Path(__file__).resolve().parent
ROOT = CURRENT_DIR.parent.parent  # backend/scripts/ -> backend/ -> root

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "backend" / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("MigrateQdrant")

from src.agents.tools.RAG.ingestion import (
    DocumentChunk,
    GeminiEmbeddingProvider,
    QdrantVectorStore,
)
from src.config import get_settings


def migrate():
    settings = get_settings()

    print("=" * 75)
    print("  CHUYỂN ĐỔI KNOWLEDGE BASE SANG QDRANT CLOUD")
    print("=" * 75)

    qdrant_url = (settings.qdrant_url or os.getenv("QDRANT_URL", "")).strip()
    qdrant_api_key = (settings.qdrant_api_key or os.getenv("QDRANT_API_KEY", "")).strip()
    collection_name = settings.qdrant_collection_name or "ev_care_knowledge_base"

    if qdrant_url and qdrant_api_key:
        print(f"\n[CẤU HÌNH]: Qdrant Cloud Cluster tại {qdrant_url.split('?')[0]}")
    elif qdrant_url:
        print(f"\n[CẤU HÌNH]: Qdrant Server tại {qdrant_url}")
    else:
        print("\n[CẤU HÌNH]: Chưa có QDRANT_URL. Tự động lưu trữ tại ./data/qdrant_local")
        print("  (Để đồng bộ lên Qdrant Cloud, thêm QDRANT_URL và QDRANT_API_KEY vào .env)")

    print(f"  -> Collection Name: {collection_name}")

    # 1. Khởi tạo Gemini Embedding Provider (3072 dimensions)
    print("\n[1/3] Khởi tạo Embedding API (Google Gemini 3072-dims)...")
    try:
        embedding_provider = GeminiEmbeddingProvider()
        print(f"  -> Model: {embedding_provider.model} (3072 chiều vector)")
    except Exception as e:
        print(f"  -> Không thể khởi tạo GeminiEmbeddingProvider: {e}")
        raise e

    # 2. Khởi tạo Qdrant Store
    print("\n[2/3] Kết nối và kiểm tra Qdrant Collection...")
    qdrant_store = QdrantVectorStore(
        collection_name=collection_name,
        embedding_provider=embedding_provider,
    )
    print(f"  -> Đã sẵn sàng Collection '{collection_name}' với vector size {qdrant_store.vector_size}")

    # 3. Đọc dữ liệu nguồn từ ChromaDB hiện có (751 chunks đã sạch và có metadata)
    print("\n[3/3] Trích xuất 751 chunks từ ChromaDB và nạp sang Qdrant...")
    import chromadb  # type: ignore

    client = chromadb.PersistentClient(path=str(ROOT / "data" / "chroma"))
    collection = client.get_or_create_collection("vinfast_ev_knowledge")
    chroma_data = collection.get(include=["documents", "metadatas"])

    ids = chroma_data.get("ids") or []
    docs = chroma_data.get("documents") or []
    metas = chroma_data.get("metadatas") or []

    print(f"  -> Tìm thấy {len(ids)} chunks từ ChromaDB.")

    if not ids:
        print("  -> Không có chunk nào trong ChromaDB. Vui lòng chạy pipeline ingest trước.")
        return

    # Chuyển đổi thành DocumentChunk
    document_chunks: list[DocumentChunk] = []
    for idx, chunk_id in enumerate(ids):
        content = docs[idx] if idx < len(docs) else ""
        meta = metas[idx] if idx < len(metas) else {}

        document_chunks.append(
            DocumentChunk(
                chunk_id=str(chunk_id),
                doc_id=str(meta.get("doc_id", "unknown")),
                content=str(content),
                metadata=dict(meta) if isinstance(meta, dict) else {},
                chunk_index=idx,
                total_chunks=len(ids),
            )
        )

    # 4. Upsert lên Qdrant theo batch
    print("  -> Đang sinh vector embedding 3072-dim và upsert lên Qdrant...")
    t0 = time.time()
    total_upserted = qdrant_store.add_chunks(
        document_chunks,
        batch_size=48,
        sleep_between_batches=1.2,
    )
    duration = time.time() - t0

    print("\n" + "=" * 75)
    print(f"  NẠP THÀNH CÔNG {total_upserted} CHUNKS LÊN QDRANT!")
    print(f"  -> Thời gian thực hiện: {duration:.2f}s")
    print(f"  -> Tổng số points hiện có trong Qdrant: {qdrant_store.count():,} points")
    print("=" * 75)


if __name__ == "__main__":
    migrate()
