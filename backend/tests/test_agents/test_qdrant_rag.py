"""
Kiểm tra End-to-End RAG Pipeline với Qdrant Cloud + Gemini LLM:

Chạy từ root project:
    python backend/tests/test_agents/test_qdrant_rag.py
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
ROOT = CURRENT_DIR.parent.parent.parent  # backend/tests/test_agents -> backend/tests -> backend -> root

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

from src.agents.tools.RAG.ingestion import QdrantVectorStore
from src.agents.tools.RAG.query import (
    HybridRetriever,
    QueryRewriter,
    RAGPipeline,
    RerankerService,
    UserVehicleContext,
)
from src.infrastructure.llm.dependency import get_llm_provider


def run_test():
    print("=" * 75)
    print("  KIỂM THỬ TOÀN DIỆN RAG PIPELINE VỚI QDRANT CLOUD + GEMINI LLM")
    print("=" * 75)

    # 1. Khởi tạo Qdrant Vector Store
    print("\n[1/4] Kết nối Qdrant Vector Store...")
    qdrant_store = QdrantVectorStore()
    stats = qdrant_store.get_stats()
    print(f"  -> Collection: {stats['collection_name']}")
    print(f"  -> Cluster / Target: {stats['qdrant_url']}")
    print(f"  -> Vector size: {stats['vector_size']} chiều")
    print(f"  -> Tổng số vector hiện có: {stats['total_vectors']:,} chunks")

    # 2. Khởi tạo HybridRetriever với Qdrant và đồng bộ sang BM25
    print("\n[2/4] Đồng bộ dữ liệu từ Qdrant sang BM25 Sparse Search...")
    hybrid = HybridRetriever(vector_store=qdrant_store)
    synced_count = hybrid.sync_bm25_from_vector_store()
    print(f"  -> Đã nạp {synced_count} chunks vào BM25 Searcher.")

    # 3. Khởi tạo LLM Provider và RAG Pipeline
    print("\n[3/4] Khởi tạo LLM Provider & RAG Pipeline...")
    llm = get_llm_provider()
    model_name = getattr(llm, "_model", getattr(llm, "model", "default"))
    print(f"  -> LLM Provider: {llm.provider_name} (Model: {model_name})")

    pipeline = RAGPipeline(
        rewriter=QueryRewriter(llm_provider=llm),
        hybrid_retriever=hybrid,
        reranker=RerankerService(provider="auto"),
    )

    # 4. Thực thi câu hỏi thực tế
    question = "Lịch bảo dưỡng định kỳ xe VF e34 như thế nào?"
    user_car = UserVehicleContext(model="VFe34")

    print(f"\n[4/4] Thực thi truy vấn RAG:")
    print(f'  -> Câu hỏi: "{question}"')
    print(f"  -> Ngữ cảnh xe: VinFast {user_car.model}")

    t0 = time.time()
    response = pipeline.query_sync(
        query=question,
        vehicle_context=user_car,
        top_k=3,
    )
    total_time = (time.time() - t0) * 1000

    print("\n" + "=" * 75)
    print("  KẾT QUẢ PHẢN HỒI TỪ RAG PIPELINE (GROUNDED ANSWER)")
    print("=" * 75)
    print(f"\n[CÂU TRẢ LỜI CỦA AI]:\n{response.answer}\n")
    print(f"- Mức độ tin cậy: {response.confidence.upper()}")
    print(f"- Cần hỗ trợ trực tiếp từ KTV (Fallback): {response.fallback_required}")
    print(f"- Tổng thời gian xử lý: {total_time:.1f}ms")

    print(f"\n[DANH SÁCH TRÍCH DẪN NGUỒN CHÍNH HÃNG ({len(response.citations)} tài liệu)]:")
    for idx, c in enumerate(response.citations, 1):
        print(f"  [{idx}] File/Tài liệu: {c.title}")
        if c.section:
            print(f"      Mục: {c.section}")
        print(f"      ID: {c.document_id} | Chunk ID: {c.chunk_id} | Score: {c.score}")

    print("\n" + "=" * 75)
    print("  HOÀN TẤT THỬ NGHIỆM THÀNH CÔNG VỚI QDRANT!")
    print("=" * 75)


if __name__ == "__main__":
    run_test()
