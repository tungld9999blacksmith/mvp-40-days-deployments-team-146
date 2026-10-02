from __future__ import annotations

import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any

from .schemas import RetrievalCandidate

logger = logging.getLogger(__name__)


class BaseReranker(ABC):
    """Giao diện trừu tượng cho các bộ Reranker."""

    @abstractmethod
    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        top_k: int = 4,
    ) -> list[RetrievalCandidate]:
        """Sắp xếp lại danh sách candidate và trả về top_k kết quả tốt nhất."""
        pass


class FlashRankReranker(BaseReranker):
    """Reranker sử dụng FlashRank (Cross-Encoder chạy local bằng ONNX trên CPU siêu nhẹ)."""

    def __init__(self, model_name: str = "ms-marco-TinyBERT-L-2-v2") -> None:
        self.model_name = model_name
        self._ranker: Any = None
        self._load_ranker()

    def _load_ranker(self) -> None:
        try:
            from flashrank import Ranker  # type: ignore

            self._ranker = Ranker(model_name=self.model_name)
            logger.info(f"Đã nạp FlashRank model: {self.model_name}")
        except Exception as e:
            logger.warning(f"Không thể khởi tạo FlashRank: {e}")
            self._ranker = None

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        top_k: int = 4,
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []
        if self._ranker is None:
            raise RuntimeError("FlashRank chưa được cài đặt hoặc không thể nạp mô hình.")

        from flashrank import RerankRequest  # type: ignore

        passages = [{"id": c.chunk_id, "text": c.content, "meta": c.metadata} for c in candidates]

        rerank_req = RerankRequest(query=query, passages=passages)
        results = self._ranker.rerank(rerank_req)

        candidate_map = {c.chunk_id: c for c in candidates}
        reranked_list: list[RetrievalCandidate] = []

        for item in results[:top_k]:
            cid = item["id"]
            if cid in candidate_map:
                cand = candidate_map[cid]
                cand.rerank_score = round(float(item.get("score", 0.0)), 4)
                reranked_list.append(cand)

        return reranked_list


class CohereReranker(BaseReranker):
    """Reranker sử dụng Cohere Rerank API (v3.5)."""

    def __init__(self, api_key: str | None = None, model: str = "rerank-v3.5") -> None:
        self.api_key = api_key or os.getenv("COHERE_API_KEY", "")
        self.model = model
        self._client: Any = None
        if self.api_key:
            try:
                import cohere  # type: ignore

                self._client = cohere.ClientV2(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Không thể khởi tạo Cohere client: {e}")

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        top_k: int = 4,
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []
        if self._client is None:
            raise RuntimeError("Cohere API key chưa được cấu hình hoặc thư viện cohere chưa được cài đặt.")

        docs = [c.content for c in candidates]
        response = self._client.rerank(
            model=self.model,
            query=query,
            documents=docs,
            top_n=top_k,
        )

        reranked_list: list[RetrievalCandidate] = []
        for res in response.results:
            cand = candidates[res.index]
            cand.rerank_score = round(float(res.relevance_score), 4)
            reranked_list.append(cand)

        return reranked_list


class HeuristicReranker(BaseReranker):
    """Bộ xếp hạng dự phòng tính điểm đối chiếu trực tiếp giữa Query và Content.

    Kết hợp mật độ từ khóa, độ bao phủ cụm từ và điểm RRF ban đầu.
    """

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        top_k: int = 4,
    ) -> list[RetrievalCandidate]:
        if not candidates:
            return []

        query_terms = [t.lower() for t in re.findall(r"\b[\w\d]+\b", query) if len(t) > 1]
        if not query_terms:
            return candidates[:top_k]

        scored: list[tuple[RetrievalCandidate, float]] = []

        for cand in candidates:
            content_lower = cand.content.lower()
            matched_terms = sum(1 for t in query_terms if t in content_lower)
            coverage_ratio = matched_terms / len(query_terms)

            # Khớp nguyên cụm từ hoặc số km
            phrase_bonus = 0.2 if query.lower() in content_lower else 0.0

            # Mốc km nếu có
            km_bonus = 0.0
            km_match = re.search(r"\b\d+(?:\.000|000)\s*km\b", query.lower())
            if km_match and km_match.group(0) in content_lower:
                km_bonus = 0.3

            # Điểm kết hợp: 50% Coverage + 30% RRF Score + Bonuses
            rrf_contrib = (cand.rrf_score or 0.0) * 10.0
            final_score = (coverage_ratio * 0.5) + (rrf_contrib * 0.3) + phrase_bonus + km_bonus

            cand.rerank_score = round(final_score, 4)
            scored.append((cand, final_score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:top_k]]


class RerankerService:
    """Service điều phối bộ Reranker, tự động chọn provider tốt nhất có sẵn."""

    def __init__(self, provider: str = "auto") -> None:
        self.provider = provider
        self._reranker: BaseReranker = self._resolve_reranker()

    def _resolve_reranker(self) -> BaseReranker:
        # 1. Thử dùng Cohere nếu có API key
        if self.provider in ["auto", "cohere"]:
            cohere_key = os.getenv("COHERE_API_KEY")
            if cohere_key:
                try:
                    reranker = CohereReranker(api_key=cohere_key)
                    if reranker._client is not None:
                        logger.info("Sử dụng Cohere Reranker v3.5")
                        return reranker
                except Exception:
                    pass

        # 2. Thử dùng FlashRank nếu thư viện có sẵn
        if self.provider in ["auto", "flashrank"]:
            try:
                reranker = FlashRankReranker()
                if reranker._ranker is not None:
                    logger.info("Sử dụng FlashRank Reranker (local ONNX)")
                    return reranker
            except Exception:
                pass

        # 3. Fallback sang Heuristic Reranker
        logger.info("Sử dụng Heuristic Reranker (không tốn chi phí, độ trễ 0ms)")
        return HeuristicReranker()

    def rerank(
        self,
        query: str,
        candidates: list[RetrievalCandidate],
        top_k: int = 4,
    ) -> list[RetrievalCandidate]:
        """Thực thi Reranking Top-K."""
        return self._reranker.rerank(query=query, candidates=candidates, top_k=top_k)
