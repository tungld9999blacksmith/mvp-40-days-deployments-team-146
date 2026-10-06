from __future__ import annotations

import logging
import math
import re
from typing import Any

from ..ingestion.metadata import canonicalize_vehicle_model
from .schemas import RetrievalCandidate

logger = logging.getLogger(__name__)


# Các thuật ngữ song ngữ xuất hiện trong policy chính hãng. Mở
# rộng query thay vì dịch/chỉnh sửa tài liệu raw, nhờ đó BM25 có
# thể tìm nguồn tiếng Anh từ câu hỏi tiếng Việt.
DOMAIN_QUERY_EXPANSIONS: dict[str, str] = {
    "bảo hành": "warranty",
    "pin cao áp": "high voltage battery",
    "ắc quy 12v": "12v battery",
    "không giới hạn": "unlimited mileage",
    "hệ thống treo": "suspension components",
    "phụ tùng thay thế": "replacement parts",
    "phụ tùng": "parts",
    "xưởng dịch vụ": "authorized service center",
    "không thuộc": "not covered",
    "không được bảo hành": "not covered warranty exclusions",
    "ngập nước": "flooded conditions floods",
    "thương mại": "commercial use",
    "năm": "years",
}


def default_tokenizer(text: str) -> list[str]:
    """Tách từ đơn giản cho tiếng Việt và các mã kỹ thuật xe điện."""
    text = text.lower()
    # Tách các từ, giữ lại các mã xe như vf8, e34, mốc km như 15000km, 24000
    tokens = re.findall(r"\b[\w\d_]+\b", text)
    return [t for t in tokens if len(t) > 1]


class BM25Searcher:
    """Công cụ tìm kiếm từ khóa chính xác Sparse Retrieval sử dụng thuật toán BM25Okapi."""

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        tokenizer: Any = None,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.tokenizer = tokenizer or default_tokenizer

        self.corpus_chunks: list[dict[str, Any]] = []
        self.tokenized_corpus: list[list[str]] = []
        self.doc_lengths: list[int] = []
        self.avg_doc_length: float = 0.0
        self.doc_count: int = 0
        self.idf: dict[str, float] = {}

    def fit(self, chunks: list[dict[str, Any]]) -> None:
        """Nạp dữ liệu corpus (danh sách chunk với id, content, metadata)."""
        self.corpus_chunks = chunks
        self.doc_count = len(chunks)
        if self.doc_count == 0:
            return

        self.tokenized_corpus = [self.tokenizer(c.get("content", "")) for c in self.corpus_chunks]
        self.doc_lengths = [len(doc) for doc in self.tokenized_corpus]
        total_len = sum(self.doc_lengths)
        self.avg_doc_length = (total_len / self.doc_count) if self.doc_count > 0 else 0.0

        # Tính toán IDF
        df: dict[str, int] = {}
        for doc in self.tokenized_corpus:
            unique_terms = set(doc)
            for term in unique_terms:
                df[term] = df.get(term, 0) + 1

        self.idf = {}
        for term, freq in df.items():
            # Công thức BM25 IDF chuẩn: ln((N - n + 0.5) / (n + 0.5) + 1)
            self.idf[term] = math.log((self.doc_count - freq + 0.5) / (freq + 0.5) + 1.0)

        logger.info(f"BM25Searcher đã index {self.doc_count} chunks với {len(self.idf)} từ khóa.")

    def search(
        self,
        query: str,
        keywords: list[str] | None = None,
        top_k: int = 20,
        model: str | None = None,
        category: str | None = None,
    ) -> list[RetrievalCandidate]:
        """Tìm kiếm các chunk phù hợp nhất bằng BM25, có hỗ trợ metadata filtering."""
        if not self.corpus_chunks:
            return []

        # Kết hợp query text và danh sách keywords bổ sung
        search_text = query
        if keywords:
            search_text += " " + " ".join(keywords)
        folded_query = query.casefold()
        requested_model = canonicalize_vehicle_model(model)
        expansions = [
            english
            for vietnamese, english in DOMAIN_QUERY_EXPANSIONS.items()
            if vietnamese in folded_query
        ]
        if expansions:
            search_text += " " + " ".join(expansions)

        query_tokens = self.tokenizer(search_text)
        if not query_tokens:
            return []

        scores: list[tuple[int, float]] = []

        for idx, doc_tokens in enumerate(self.tokenized_corpus):
            # 1. Kiểm tra Metadata Filter trước
            chunk_data = self.corpus_chunks[idx]
            meta = chunk_data.get("metadata", {})

            # Lọc theo Model
            if requested_model and requested_model != "ALL":
                doc_model = canonicalize_vehicle_model(meta.get("model", "ALL"))
                if doc_model not in [requested_model, "ALL"]:
                    continue

            # Lọc theo Category
            if category and category != "all" and category != "general":
                doc_cat = meta.get("category", "")
                if doc_cat and doc_cat != category:
                    continue

            # 2. Tính điểm BM25
            doc_len = self.doc_lengths[idx]
            score = 0.0

            # Đếm term frequency trong doc
            term_freqs: dict[str, int] = {}
            for t in doc_tokens:
                term_freqs[t] = term_freqs.get(t, 0) + 1

            for q_term in query_tokens:
                if q_term not in term_freqs:
                    continue
                tf = term_freqs[q_term]
                idf_val = self.idf.get(q_term, 0.0)

                # BM25 formula
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (
                    1.0 - self.b + self.b * (doc_len / self.avg_doc_length if self.avg_doc_length > 0 else 1.0)
                )
                score += idf_val * (numerator / denominator)

            if score > 0:
                scores.append((idx, score))

        # Sắp xếp giảm dần theo điểm BM25
        scores.sort(key=lambda x: x[1], reverse=True)

        results: list[RetrievalCandidate] = []
        for idx, score in scores[:top_k]:
            raw_chunk = self.corpus_chunks[idx]
            meta = raw_chunk.get("metadata", {})
            results.append(
                RetrievalCandidate(
                    chunk_id=raw_chunk.get("chunk_id", f"chunk_{idx}"),
                    doc_id=raw_chunk.get("doc_id", meta.get("doc_id", "")),
                    content=raw_chunk.get("content", ""),
                    metadata=meta,
                    sparse_score=round(score, 4),
                )
            )

        return results
