from __future__ import annotations

import logging
from typing import Any

from .bm25_searcher import BM25Searcher
from .schemas import QueryAnalysis, RetrievalCandidate

logger = logging.getLogger(__name__)


class HybridRetriever:
    """Bộ truy xuất phức hợp (Hybrid Retrieval) kết hợp Dense (Vector) + Sparse (BM25) qua RRF."""

    def __init__(
        self,
        vector_store: Any = None,
        bm25_searcher: BM25Searcher | None = None,
        rrf_k: int = 60,
    ) -> None:
        self.vector_store = vector_store
        self.bm25_searcher = bm25_searcher or BM25Searcher()
        self.rrf_k = rrf_k
        self._is_bm25_initialized = False

    def _ensure_vector_store(self) -> Any:
        if self.vector_store is None:
            from src.agents.tools.RAG.ingestion import QdrantVectorStore

            self.vector_store = QdrantVectorStore()

        return self.vector_store

    def sync_bm25_from_vector_store(self) -> int:
        """Đồng bộ văn bản từ Qdrant vào BM25Searcher để lập chỉ mục từ khóa."""
        vs = self._ensure_vector_store()
        try:
            chunks = vs.get_all_chunks()

            if chunks:
                self.bm25_searcher.fit(chunks)
                self._is_bm25_initialized = True
                logger.info(f"Đã nạp thành công {len(chunks)} chunks từ Vector Store vào BM25 Searcher.")
                return len(chunks)
            else:
                logger.warning("Vector Store rỗng, chưa có chunk nào để nạp BM25.")
                return 0
        except Exception as e:
            logger.warning(f"Không thể đồng bộ BM25 từ Vector Store: {e}")
            return 0

    def retrieve(
        self,
        analysis: QueryAnalysis,
        top_candidates: int = 20,
        dense_limit: int = 25,
        sparse_limit: int = 25,
    ) -> list[RetrievalCandidate]:
        """Thực hiện Hybrid Retrieval gồm:

        1. Lọc Metadata nghiêm ngặt (theo model & category)
        2. Chạy song song Dense Search (Qdrant) + Sparse Search (BM25)
        3. Cơ chế Soft Fallback nếu bộ lọc trả về ít kết quả
        4. Hợp nhất thứ hạng bằng Reciprocal Rank Fusion (RRF).
        """
        vs = self._ensure_vector_store()

        # Đồng bộ BM25 nếu chưa nạp corpus
        if not self._is_bm25_initialized and self.bm25_searcher.doc_count == 0:
            self.sync_bm25_from_vector_store()

        query_text = analysis.rewritten_query or analysis.original_query
        target_model = analysis.model
        target_category = analysis.category

        # --- NHÁNH 1: DENSE SEARCH (VECTOR QDRANT) ---
        dense_results = self._dense_search(
            vs=vs,
            query=query_text,
            model=target_model,
            category=target_category,
            limit=dense_limit,
        )

        # Soft Fallback cho Dense: Nếu kết quả ít và có lọc category, thử mở rộng bỏ category
        if len(dense_results) < 2 and target_category and target_category != "general":
            fallback_dense = self._dense_search(
                vs=vs,
                query=query_text,
                model=target_model,
                category=None,
                limit=dense_limit,
            )
            # Thêm các kết quả fallback không bị trùng
            existing_ids = {r.chunk_id for r in dense_results}
            for r in fallback_dense:
                if r.chunk_id not in existing_ids:
                    dense_results.append(r)

        # --- NHÁNH 2: SPARSE SEARCH (BM25 KEYWORDS) ---
        sparse_results = self.bm25_searcher.search(
            query=query_text,
            keywords=analysis.keywords,
            top_k=sparse_limit,
            model=target_model,
            category=target_category,
        )

        # Soft Fallback cho Sparse nếu ít kết quả
        if len(sparse_results) < 2 and target_category and target_category != "general":
            fallback_sparse = self.bm25_searcher.search(
                query=query_text,
                keywords=analysis.keywords,
                top_k=sparse_limit,
                model=target_model,
                category=None,
            )
            existing_sparse_ids = {r.chunk_id for r in sparse_results}
            for r in fallback_sparse:
                if r.chunk_id not in existing_sparse_ids:
                    sparse_results.append(r)

        # --- NHÁNH 3: RECIPROCAL RANK FUSION (RRF) ---
        fused_candidates = self._reciprocal_rank_fusion(
            dense_results=dense_results,
            sparse_results=sparse_results,
            top_n=top_candidates,
        )

        return fused_candidates

    def _dense_search(
        self,
        vs: Any,
        query: str,
        model: str | None,
        category: str | None,
        limit: int,
    ) -> list[RetrievalCandidate]:
        """Gọi truy vấn semantic vector từ QdrantVectorStore."""
        try:
            raw_results = vs.search(
                query=query,
                n_results=limit,
                model=model,
                category=category,
            )
            candidates: list[RetrievalCandidate] = []
            for r in raw_results:
                meta = r.metadata or {}
                candidates.append(
                    RetrievalCandidate(
                        chunk_id=r.chunk_id,
                        doc_id=meta.get("doc_id", ""),
                        content=r.content,
                        metadata=meta,
                        dense_score=getattr(r, "score", None)
                        if getattr(r, "score", None) is not None
                        else getattr(r, "dense_score", None),
                    )
                )
            return candidates
        except Exception as e:
            logger.error(f"Lỗi khi Dense Search Qdrant: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        dense_results: list[RetrievalCandidate],
        sparse_results: list[RetrievalCandidate],
        top_n: int = 20,
    ) -> list[RetrievalCandidate]:
        """Thuật toán Reciprocal Rank Fusion (RRF) kết hợp bảng xếp hạng Dense và Sparse:

        RRF_Score(d) = 1/(k + rank_dense) + 1/(k + rank_sparse)
        """
        scores: dict[str, float] = {}
        candidate_map: dict[str, RetrievalCandidate] = {}

        # 1. Đóng góp từ Dense Ranking
        for rank, item in enumerate(dense_results):
            cid = item.chunk_id
            rrf_point = 1.0 / (self.rrf_k + rank + 1)
            scores[cid] = scores.get(cid, 0.0) + rrf_point

            if cid not in candidate_map:
                candidate_map[cid] = item
            else:
                candidate_map[cid].dense_score = item.dense_score

        # 2. Đóng góp từ Sparse Ranking
        for rank, item in enumerate(sparse_results):
            cid = item.chunk_id
            rrf_point = 1.0 / (self.rrf_k + rank + 1)
            scores[cid] = scores.get(cid, 0.0) + rrf_point

            if cid not in candidate_map:
                candidate_map[cid] = item
            else:
                candidate_map[cid].sparse_score = item.sparse_score

        # 3. Gán điểm RRF và sắp xếp giảm dần
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        final_list: list[RetrievalCandidate] = []

        for cid in sorted_ids[:top_n]:
            cand = candidate_map[cid]
            cand.rrf_score = round(scores[cid], 5)
            final_list.append(cand)

        return final_list
