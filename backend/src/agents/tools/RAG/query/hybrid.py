from __future__ import annotations

import logging
import re
from typing import Any

from ..ingestion.metadata import canonicalize_vehicle_model
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
        enable_dense: bool = True,
    ) -> None:
        self.vector_store = vector_store
        self.bm25_searcher = bm25_searcher or BM25Searcher()
        self.rrf_k = rrf_k
        self.enable_dense = enable_dense
        self._dense_disabled = False
        self._is_bm25_initialized = False

    def expand_neighbors(
        self,
        candidates: list[RetrievalCandidate],
        window: int = 1,
    ) -> list[RetrievalCandidate]:
        """Gộp chunk liền kề cùng section vào chunk gốc.

        Neighbor chỉ là phần mở rộng bằng chứng, không phải một kết quả tìm
        kiếm độc lập. Cách này giữ đủ bảng/Q&A bị cắt nhưng không làm tăng mẫu
        số Context Precision hoặc tạo thêm citation không liên quan.
        """
        if window <= 0 or not candidates or not self.bm25_searcher.corpus_chunks:
            return candidates

        corpus = {
            str(item.get("chunk_id", "")): item
            for item in self.bm25_searcher.corpus_chunks
        }
        expanded: list[RetrievalCandidate] = []
        for candidate in candidates:
            prefix, marker, number = candidate.chunk_id.rpartition("_chk_")
            if not marker or not number.isdigit():
                expanded.append(candidate)
                continue
            index = int(number)
            width = len(number)
            parts: list[tuple[int, str, str]] = [(index, candidate.chunk_id, candidate.content)]
            anchor_section = str(candidate.metadata.get("section_header", "")).strip().casefold()
            for offset in range(-window, window + 1):
                if offset == 0 or index + offset < 1:
                    continue
                neighbor_id = f"{prefix}_chk_{index + offset:0{width}d}"
                raw = corpus.get(neighbor_id)
                if not raw:
                    continue
                metadata = raw.get("metadata", {})
                neighbor_section = str(metadata.get("section_header", "")).strip().casefold()
                # Không kéo section khác vào context: đây từng là nguồn chính
                # làm giảm precision và citation correctness.
                if anchor_section and neighbor_section != anchor_section:
                    continue
                parts.append((index + offset, neighbor_id, raw.get("content", "")))

            parts.sort(key=lambda item: item[0])
            merged = candidate.model_copy(deep=True)
            merged.content = "\n\n".join(text for _, _, text in parts if text.strip())
            merged.metadata["expanded_chunk_ids"] = [chunk_id for _, chunk_id, _ in parts]
            expanded.append(merged)
        return expanded

    def select_context(
        self,
        candidates: list[RetrievalCandidate],
        analysis: QueryAnalysis,
        top_k: int = 4,
    ) -> list[RetrievalCandidate]:
        """Chọn context cuối có liên quan, đúng model/category và đa dạng nguồn.

        Reranker có thể trả nhiều chunk gần giống nhau từ cùng một tài liệu.
        Chọn tối đa một anchor mỗi tài liệu giúp Context Recall theo nguồn,
        còn ``expand_neighbors`` đảm nhiệm việc bổ sung phần văn bản liền kề.
        """
        if top_k <= 0 or not candidates:
            return []

        query_terms = {
            token
            for token in re.findall(r"\b[\w\d]+\b", analysis.original_query.casefold())
            if len(token) >= 2
        }
        query_numbers = set(re.findall(r"\d+(?:[.,]\d+)*", analysis.original_query.casefold()))

        rescored: list[tuple[float, RetrievalCandidate]] = []
        requested_model = canonicalize_vehicle_model(analysis.model)
        for position, candidate in enumerate(candidates):
            meta = candidate.metadata or {}
            doc_model = canonicalize_vehicle_model(str(meta.get("model", "ALL"))) or "ALL"
            if requested_model and requested_model != "ALL" and doc_model not in {requested_model, "ALL"}:
                continue

            content = candidate.content.casefold()
            matched = sum(1 for term in query_terms if term in content)
            lexical = matched / max(len(query_terms), 1)
            number_match = 1.0 if query_numbers and all(number in content for number in query_numbers) else 0.0
            category_match = 1.0 if analysis.category and meta.get("category") == analysis.category else 0.0
            model_match = 1.0 if requested_model and doc_model == requested_model else 0.0
            base = candidate.rerank_score
            if base is None:
                base = candidate.dense_score or candidate.rrf_score or 0.0
            score = (
                float(base)
                + lexical * 0.25
                + number_match * 0.15
                + category_match * 0.12
                + model_match * 0.08
                - position * 0.001
            )
            rescored.append((score, candidate))

        rescored.sort(key=lambda item: item[0], reverse=True)
        if not rescored:
            return []

        # Loại candidate yếu rõ rệt so với kết quả tốt nhất. Ngưỡng tương đối
        # tránh đưa context rác vào prompt nhưng vẫn hoạt động với các loại
        # score khác nhau (cosine, cross-encoder, heuristic).
        best_score = rescored[0][0]
        minimum = best_score * 0.55 if best_score > 0 else best_score
        effective_top_k = top_k
        if analysis.category == "pricing":
            # Một câu hỏi giá cụ thể chỉ cần bảng giá chính và tối đa một nguồn
            # đối chiếu. Với câu hỏi về quy trình báo giá, giữ tối đa ba nguồn.
            exact_price_query = any(
                phrase in analysis.original_query.casefold()
                for phrase in ("giá bao nhiêu", "có mất tiền", "chi phí bao nhiêu")
            )
            effective_top_k = min(top_k, 1 if exact_price_query else 3)

        selected: list[RetrievalCandidate] = []
        doc_counts: dict[str, int] = {}
        max_per_document = 2 if analysis.category == "battery" else 1
        for score, candidate in rescored:
            if score < minimum:
                continue
            doc_key = candidate.doc_id or candidate.chunk_id
            if doc_counts.get(doc_key, 0) >= max_per_document:
                continue
            selected.append(candidate)
            doc_counts[doc_key] = doc_counts.get(doc_key, 0) + 1
            if len(selected) >= effective_top_k:
                break

        return selected

    def _ensure_vector_store(self) -> Any:
        if self.vector_store is None:
            import os

            from src.config import get_settings

            cfg = get_settings()
            has_qdrant = bool(cfg.qdrant_url or os.getenv("QDRANT_URL"))

            if has_qdrant:
                from src.agents.tools.RAG.ingestion import QdrantVectorStore
                self.vector_store = QdrantVectorStore()
            else:
                from src.agents.tools.RAG.ingestion import QdrantVectorStore
                self.vector_store = QdrantVectorStore()

        return self.vector_store

    def sync_bm25_from_vector_store(self) -> int:
        """Đồng bộ toàn bộ văn bản từ Vector Store (Qdrant hoặc ChromaDB) vào BM25Searcher để lập chỉ mục từ khóa."""
        vs = self._ensure_vector_store()
        try:
            chunks: list[dict[str, Any]] = []

            # Trường hợp 1: Qdrant Vector Store
            if hasattr(vs, "get_all_chunks"):
                chunks = vs.get_all_chunks()
            # Trường hợp 2: ChromaDB
            elif hasattr(vs, "_collection"):
                collection_data = vs._collection.get(include=["documents", "metadatas"])
                ids = collection_data.get("ids") or []
                docs = collection_data.get("documents") or []
                metas = collection_data.get("metadatas") or []

                for idx, chunk_id in enumerate(ids):
                    meta = metas[idx] if idx < len(metas) else {}
                    content = docs[idx] if idx < len(docs) else ""
                    chunks.append(
                        {
                            "chunk_id": chunk_id,
                            "doc_id": meta.get("doc_id", ""),
                            "content": content,
                            "metadata": meta,
                        }
                    )

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
        top_candidates: int = 30,
        dense_limit: int = 35,
        sparse_limit: int = 35,
    ) -> list[RetrievalCandidate]:
        """Thực hiện Hybrid Retrieval gồm:

        1. Lọc Metadata nghiêm ngặt (theo model & category)
        2. Chạy song song Dense Search (Chroma) + Sparse Search (BM25)
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

        # --- NHÁNH 1: DENSE SEARCH (QDRANT) ---
        # Dense retrieval không hard-filter category. Category là nhãn đơn
        # nhưng nhiều section FAQ có nhiều ý định; hard filter từng làm
        # mất tài liệu đúng. Model vẫn được giữ để tránh lẫn dòng xe.
        dense_results = []
        if self.enable_dense and not self._dense_disabled:
            dense_results = self._dense_search(
                vs=vs,
                query=query_text,
                model=target_model,
                category=None,
                limit=dense_limit,
            )

        # --- NHÁNH 2: SPARSE SEARCH (BM25 KEYWORDS) ---
        sparse_results = self.bm25_searcher.search(
            query=query_text,
            keywords=analysis.keywords,
            top_k=sparse_limit,
            model=target_model,
            category=target_category,
        )

        # Sparse search mở rộng category; kết quả trùng với nhánh
        # category-filtered được RRF ưu tiên.
        if target_category and target_category != "general":
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
        """Gọi truy vấn semantic vector từ Qdrant."""
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
                        dense_score=getattr(r, "score", None) if getattr(r, "score", None) is not None else getattr(r, "dense_score", None),
                    )
                )
            return candidates
        except Exception as e:
            message = str(e).casefold()
            if "resource_exhausted" in message or "quota" in message or "429" in message:
                # Circuit breaker: sau lỗi quota, dùng BM25 cho các query còn
                # lại thay vì chờ retry embedding lặp lại ở mỗi request.
                self._dense_disabled = True
                logger.warning("Tạm tắt dense retrieval do hết quota embedding; chuyển sang BM25 fallback.")
            else:
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
