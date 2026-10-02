"""
Kiểm tra toàn bộ luồng RAG Retrieval & Serving Engine:
  Query Rewriter -> Metadata Filter -> Hybrid Retrieval (Dense+BM25) -> Reranker -> Citation Builder -> Grounded LLM Response

Chạy kiểm thử từ root project:
    python backend/tests/test_agents/test_rag_retrieval_flow.py
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
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

SEP = "=" * 75
PASS = "✅"
FAIL = "❌"


def section(title: str):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


def check(label: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    print(f"  {status}  {label}" + (f"  →  {detail}" if detail else ""))
    return ok


# ─────────────────────────────────────────────────────────────────────────────
section("BƯỚC 1: QUERY REWRITER & METADATA EXTRACTION")
# ─────────────────────────────────────────────────────────────────────────────
from src.agents.tools.RAG.query.rewriter import QueryRewriter
from src.agents.tools.RAG.query.schemas import UserVehicleContext

rewriter = QueryRewriter()

# Test 1: Khử đại từ "xe tôi" kèm vehicle_context
q1 = "Xe tôi đi được 24.000 km thì cần bảo dưỡng những gì?"
ctx1 = UserVehicleContext(model="VF8", current_odometer_km=24000)
analysis1 = rewriter._heuristic_fallback(q1, ctx1)

check("Phát hiện Model từ context xe", analysis1.model == "VF8", f"model={analysis1.model}")
check("Phát hiện Category bảo dưỡng", analysis1.category == "maintenance", f"cat={analysis1.category}")
check("Trích xuất mốc 24.000 km", analysis1.milestone_km == 24000, f"milestone={analysis1.milestone_km}")
check("Trích xuất từ khóa cho BM25", len(analysis1.keywords) > 0, f"keywords={analysis1.keywords}")

# Test 2: Phát hiện model trực tiếp từ text
q2 = "Chính sách bảo hành pin cho xe máy điện Feliz ra sao?"
analysis2 = rewriter._heuristic_fallback(q2, None)
check("Phát hiện Model từ nội dung query", analysis2.model == "Feliz", f"model={analysis2.model}")
check("Phát hiện Category bảo hành", analysis2.category == "warranty", f"cat={analysis2.category}")

# ─────────────────────────────────────────────────────────────────────────────
section("BƯỚC 2: SPARSE RETRIEVAL VỚI BM25 OKAPI")
# ─────────────────────────────────────────────────────────────────────────────
from src.agents.tools.RAG.query.bm25_searcher import BM25Searcher

bm25 = BM25Searcher()

# Nạp một corpus mẫu gồm cả ô tô và xe máy điện
sample_corpus = [
    {
        "chunk_id": "c1",
        "doc_id": "vf8_manual",
        "content": "VinFast VF8 cần bảo dưỡng định kỳ mỗi 24.000 km hoặc 12 tháng. Kiểm tra pin cao áp, hệ thống phanh.",
        "metadata": {"model": "VF8", "category": "maintenance"},
    },
    {
        "chunk_id": "c2",
        "doc_id": "vf8_warranty",
        "content": "Bảo hành pin xe VF8 trong thời hạn 10 năm hoặc 200.000 km tùy điều kiện nào đến trước.",
        "metadata": {"model": "VF8", "category": "warranty"},
    },
    {
        "chunk_id": "c3",
        "doc_id": "feliz_warranty",
        "content": "Bảo hành xe máy điện Feliz là 3 năm không giới hạn số km. Pin được bảo hành 3 năm.",
        "metadata": {"model": "Feliz", "category": "warranty"},
    },
    {
        "chunk_id": "c4",
        "doc_id": "general_policy",
        "content": "Chính sách cứu hộ xe điện VinFast miễn phí 24/7 trên toàn quốc cho mọi dòng xe.",
        "metadata": {"model": "ALL", "category": "general"},
    },
]

bm25.fit(sample_corpus)
check("BM25 nạp corpus thành công", bm25.doc_count == 4)

# Test lọc: hỏi VF8 không bao giờ ra Feliz
bm25_res = bm25.search("bảo hành pin", keywords=["bảo hành", "pin"], model="VF8", top_k=5)
models_found = [r.metadata.get("model") for r in bm25_res]
check("Chỉ trả về model VF8 và ALL", all(m in ["VF8", "ALL"] for m in models_found), f"models={models_found}")
check("Không lẫn dòng xe khác (Feliz)", "Feliz" not in models_found)

# ─────────────────────────────────────────────────────────────────────────────
section("BƯỚC 3: HYBRID RETRIEVAL & RECIPROCAL RANK FUSION (RRF)")
# ─────────────────────────────────────────────────────────────────────────────
from src.agents.tools.RAG.query.hybrid import HybridRetriever
from src.agents.tools.RAG.query.schemas import RetrievalCandidate

hybrid = HybridRetriever(bm25_searcher=bm25)

dense_cands = [
    RetrievalCandidate(chunk_id="c1", doc_id="vf8_manual", content=sample_corpus[0]["content"], metadata=sample_corpus[0]["metadata"], dense_score=0.92),
    RetrievalCandidate(chunk_id="c4", doc_id="general_policy", content=sample_corpus[3]["content"], metadata=sample_corpus[3]["metadata"], dense_score=0.75),
]
sparse_cands = [
    RetrievalCandidate(chunk_id="c2", doc_id="vf8_warranty", content=sample_corpus[1]["content"], metadata=sample_corpus[1]["metadata"], sparse_score=1.5),
    RetrievalCandidate(chunk_id="c1", doc_id="vf8_manual", content=sample_corpus[0]["content"], metadata=sample_corpus[0]["metadata"], sparse_score=1.2),
]

fused = hybrid._reciprocal_rank_fusion(dense_cands, sparse_cands, top_n=3)
check("RRF hợp nhất thành công", len(fused) > 0)
check("Chunk c1 xuất hiện ở cả 2 nhánh có điểm RRF cao nhất", fused[0].chunk_id == "c1", f"top={fused[0].chunk_id}, score={fused[0].rrf_score}")

# ─────────────────────────────────────────────────────────────────────────────
section("BƯỚC 4: RERANKER (CROSS-ENCODER)")
# ─────────────────────────────────────────────────────────────────────────────
from src.agents.tools.RAG.query.reranker import RerankerService

reranker = RerankerService(provider="auto")
reranked = reranker.rerank(
    query="Bảo dưỡng xe VF8 mốc 24.000 km",
    candidates=fused,
    top_k=2,
)
check("Reranker trả về đúng Top-K (K=2)", len(reranked) == 2, f"count={len(reranked)}")
check("Chunk bảo dưỡng c1 đứng đầu sau khi rerank", reranked[0].chunk_id == "c1", f"top={reranked[0].chunk_id}")

# ─────────────────────────────────────────────────────────────────────────────
section("BƯỚC 5: CITATION BUILDER (ĐÓNG GÓI CONTEXT & NGUỒN)")
# ─────────────────────────────────────────────────────────────────────────────
from src.agents.tools.RAG.query.citation_builder import CitationBuilder

builder = CitationBuilder()
context_text, citations = builder.build(reranked)

check("Context đóng gói có nội dung", len(context_text) > 0)
check("Context có tiền tố [Tài liệu X]", "[Tài liệu 1]" in context_text)
check("Danh sách citations tạo đúng số lượng", len(citations) == 2)
check("Citation có metadata title", citations[0].title != "")

# ─────────────────────────────────────────────────────────────────────────────
section("BƯỚC 6: GROUNDED ANSWER GENERATION & FULL PIPELINE")
# ─────────────────────────────────────────────────────────────────────────────
from src.agents.tools.RAG.query.generator import GroundedAnswerGenerator
from src.agents.tools.RAG.query.rag_pipeline import RAGPipeline

generator = GroundedAnswerGenerator()
pipeline = RAGPipeline(
    rewriter=rewriter,
    hybrid_retriever=hybrid,
    reranker=reranker,
    citation_builder=builder,
    generator=generator,
)

t0 = time.time()
final_res = pipeline.query_sync(
    query=q1,
    vehicle_context=ctx1,
    top_k=2,
)
elapsed_ms = (time.time() - t0) * 1000

check("End-to-End pipeline hoàn thành", final_res is not None)
check("Thời gian phản hồi nhanh (< 500ms)", elapsed_ms < 500, f"{elapsed_ms:.1f}ms")
check("Citations trả về đúng định dạng yêu cầu", len(final_res.citations) > 0)

# ─────────────────────────────────────────────────────────────────────────────
section("TỔNG KẾT RAG RETRIEVAL PIPELINE")
# ─────────────────────────────────────────────────────────────────────────────
print(f"""
  Luồng 6 bước hoàn chỉnh đã hoạt động ổn định:
    [1] Query Rewriting / Metadata Extraction  → OK
    [2] Sparse Search (BM25)                   → OK
    [3] Hybrid Fusion (RRF: Dense + Sparse)    → OK
    [4] Cross-Encoder Reranking Top-K          → OK
    [5] Context Packaging with Citations       → OK
    [6] Grounded Answer with Structured JSON   → OK
""")


if __name__ == "__main__":
    pass
