"""
metrics.py — Các hàm tính chỉ số đánh giá hệ thống RAG.

Chỉ số được tính:
    - Retrieval Score      : cosine similarity giữa query và chunk trả về
    - Hit Rate @K          : tỷ lệ câu có ít nhất 1 chunk từ relevant_doc_ids trong Top-K
    - Keyword Match Ratio  : tỷ lệ expected_keywords xuất hiện trong kết quả
    - MRR (Mean Reciprocal Rank) : thứ hạng trung bình của chunk đúng đầu tiên
    - Latency              : thời gian phản hồi mỗi câu truy vấn (ms)
    - Pass Rate            : tỷ lệ câu đạt ngưỡng score + keyword đồng thời
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class QueryResult:
    """Kết quả retrieval cho một câu query."""

    id: str
    query: str
    model: str | None
    category: str
    # Retrieval output
    retrieved_doc_ids: list[str] = field(default_factory=list)
    top_score: float = 0.0
    scores: list[float] = field(default_factory=list)
    retrieved_texts: list[str] = field(default_factory=list)
    # Ground truth
    relevant_doc_ids: list[str] = field(default_factory=list)
    expected_keywords: list[str] = field(default_factory=list)
    min_score: float = 0.50
    expected_answer: str = ""
    # Generated-answer output. Để trống trong retrieval-only evaluation;
    # không được dùng expected_answer thay cho output thực của RAG.
    actual_answer: str = ""
    cited_doc_ids: list[str] = field(default_factory=list)
    # LLM generation metadata (chỉ có khi chạy --full-rag / --evaluate-answers)
    generation_metadata: dict = field(default_factory=dict)
    # Query analysis từ rewriter (model, category, keywords, milestone_km...)
    analysis: dict = field(default_factory=dict)
    # Timing
    latency_ms: float = 0.0
    # Error
    error: str | None = None


@dataclass
class EvalMetrics:
    """Tổng hợp các chỉ số đánh giá toàn bộ golden set."""

    total: int = 0
    # Hit Rate
    hit_at_1: float = 0.0  # Có chunk đúng ở vị trí #1
    hit_at_3: float = 0.0  # Có chunk đúng trong Top-3
    hit_at_5: float = 0.0  # Có chunk đúng trong Top-5
    # Score
    avg_top_score: float = 0.0
    avg_score_pass_rate: float = 0.0  # % câu có top_score >= min_score
    # Keyword
    avg_keyword_ratio: float = 0.0
    keyword_pass_rate: float = 0.0  # % câu có keyword_ratio >= 0.5
    # MRR
    mrr: float = 0.0
    # Pass (score AND keyword)
    pass_rate: float = 0.0
    # Latency
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    # Per-category
    category_stats: dict[str, dict] = field(default_factory=dict)
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_relevancy: float | None = None
    citation_correctness: float | None = None


# ---------------------------------------------------------------------------
# Hàm tính từng chỉ số
# ---------------------------------------------------------------------------


def normalize_doc_id(value: str) -> str:
    """Chuẩn hóa ID file/chunk để so khớp chính xác, không dùng substring."""
    name = Path(value).stem.casefold().strip()
    return re.sub(r"_chk_\d+$", "", name)


def is_relevant_doc(doc_id: str, relevant_doc_ids: list[str]) -> bool:
    normalized = normalize_doc_id(doc_id)
    return normalized in {normalize_doc_id(item) for item in relevant_doc_ids}


def compute_hit_at_k(result: QueryResult, k: int) -> bool:
    """True nếu có ít nhất 1 chunk từ relevant_doc_ids trong Top-K."""
    if not result.relevant_doc_ids:
        return result.top_score >= result.min_score
    top_k = result.retrieved_doc_ids[:k]
    return any(is_relevant_doc(doc_id, result.relevant_doc_ids) for doc_id in top_k)


def compute_reciprocal_rank(result: QueryResult) -> float:
    """Reciprocal rank của chunk đúng đầu tiên trong danh sách kết quả."""
    if not result.relevant_doc_ids:
        return 1.0 if result.top_score >= result.min_score else 0.0
    for rank, doc_id in enumerate(result.retrieved_doc_ids, start=1):
        if is_relevant_doc(doc_id, result.relevant_doc_ids):
            return 1.0 / rank
    return 0.0


def compute_keyword_ratio(result: QueryResult) -> float:
    """Tỷ lệ expected_keywords xuất hiện trong kết quả trả về."""
    if not result.expected_keywords:
        return 1.0
    combined = " ".join(result.retrieved_texts).lower()
    hits = sum(1 for kw in result.expected_keywords if kw.lower() in combined)
    return hits / len(result.expected_keywords)


def compute_context_precision(result: QueryResult) -> float:
    """Tỷ lệ tài liệu retrieve duy nhất thuộc tập relevant_doc_ids."""
    retrieved = {normalize_doc_id(item) for item in result.retrieved_doc_ids if item}
    if not retrieved:
        return 0.0
    relevant = {normalize_doc_id(item) for item in result.relevant_doc_ids if item}
    if not relevant:
        return 1.0
    return len(retrieved & relevant) / len(retrieved)


def compute_context_recall(result: QueryResult) -> float:
    """Tỷ lệ relevant documents đã xuất hiện trong retrieval."""
    relevant = {normalize_doc_id(item) for item in result.relevant_doc_ids if item}
    if not relevant:
        return 1.0
    retrieved = {normalize_doc_id(item) for item in result.retrieved_doc_ids if item}
    return len(relevant & retrieved) / len(relevant)


_VI_STOPWORDS = {
    "có",
    "không",
    "là",
    "gì",
    "bao",
    "nhiêu",
    "như",
    "thế",
    "nào",
    "cho",
    "của",
    "và",
    "với",
    "tôi",
    "xe",
    "được",
    "cần",
    "thì",
}


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r"\b[\w\d]+\b", text.casefold()) if len(token) >= 2 and token not in _VI_STOPWORDS
    }


def compute_answer_relevancy(result: QueryResult) -> float | None:
    """Query-token coverage trên câu trả lời RAG thực; không chấm ground truth."""
    if not result.actual_answer.strip():
        return None
    query_tokens = _meaningful_tokens(result.query)
    if not query_tokens:
        return 1.0
    answer_tokens = _meaningful_tokens(result.actual_answer)
    return len(query_tokens & answer_tokens) / len(query_tokens)


def compute_citation_correctness(result: QueryResult) -> float | None:
    """Tỷ lệ nguồn được answer thật sự cite nằm trong relevant_doc_ids."""
    if not result.actual_answer.strip():
        return None
    cited = {normalize_doc_id(item) for item in result.cited_doc_ids if item}
    if not cited:
        return 0.0
    relevant = {normalize_doc_id(item) for item in result.relevant_doc_ids if item}
    if not relevant:
        return 1.0
    return len(cited & relevant) / len(cited)


def is_pass(result: QueryResult) -> bool:
    """Pass khi retrieval đúng nguồn, đủ bằng chứng và đạt score."""
    return result.top_score >= result.min_score and compute_keyword_ratio(result) >= 0.5 and compute_hit_at_k(result, 5)


def compute_metrics(results: list[QueryResult]) -> EvalMetrics:
    """Tính toàn bộ chỉ số từ danh sách QueryResult."""
    if not results:
        return EvalMetrics()

    n = len(results)
    m = EvalMetrics(total=n)

    scores = [r.top_score for r in results]
    latencies = [r.latency_ms for r in results]
    kw_ratios = [compute_keyword_ratio(r) for r in results]
    rr_scores = [compute_reciprocal_rank(r) for r in results]
    hit1s = [compute_hit_at_k(r, 1) for r in results]
    hit3s = [compute_hit_at_k(r, 3) for r in results]
    hit5s = [compute_hit_at_k(r, 5) for r in results]
    passes = [is_pass(r) for r in results]
    score_passes = [r.top_score >= r.min_score for r in results]
    context_precisions = [compute_context_precision(r) for r in results]
    context_recalls = [compute_context_recall(r) for r in results]
    answer_relevancies = [score for r in results if (score := compute_answer_relevancy(r)) is not None]
    citation_correctness = [score for r in results if (score := compute_citation_correctness(r)) is not None]

    m.hit_at_1 = sum(hit1s) / n
    m.hit_at_3 = sum(hit3s) / n
    m.hit_at_5 = sum(hit5s) / n
    m.avg_top_score = sum(scores) / n
    m.avg_score_pass_rate = sum(score_passes) / n
    m.avg_keyword_ratio = sum(kw_ratios) / n
    m.keyword_pass_rate = sum(kw >= 0.5 for kw in kw_ratios) / n
    m.mrr = sum(rr_scores) / n
    m.pass_rate = sum(passes) / n
    m.avg_latency_ms = sum(latencies) / n
    m.context_precision = sum(context_precisions) / n
    m.context_recall = sum(context_recalls) / n
    m.answer_relevancy = sum(answer_relevancies) / len(answer_relevancies) if answer_relevancies else None
    m.citation_correctness = sum(citation_correctness) / len(citation_correctness) if citation_correctness else None

    # P95 latency
    sorted_lat = sorted(latencies)
    p95_idx = int(0.95 * n)
    m.p95_latency_ms = sorted_lat[min(p95_idx, n - 1)]

    # Per-category stats
    categories: dict[str, list[QueryResult]] = {}
    for r in results:
        categories.setdefault(r.category, []).append(r)

    for cat, cat_results in categories.items():
        cn = len(cat_results)
        cat_passes = [is_pass(r) for r in cat_results]
        cat_scores = [r.top_score for r in cat_results]
        m.category_stats[cat] = {
            "total": cn,
            "pass": sum(cat_passes),
            "pass_rate": sum(cat_passes) / cn,
            "avg_score": sum(cat_scores) / cn,
            "hit_at_3": sum(compute_hit_at_k(r, 3) for r in cat_results) / cn,
        }

    return m


def format_metrics_report(m: EvalMetrics) -> str:
    """Định dạng báo cáo metrics dạng text có thể in ra terminal hoặc ghi file."""
    separator = "=" * 65
    lines = [
        separator,
        "  RAG EVALUATION METRICS REPORT",
        separator,
        f"  Total queries    : {m.total}",
        "",
        "  RETRIEVAL QUALITY",
        f"  Hit Rate @1      : {m.hit_at_1:.1%}",
        f"  Hit Rate @3      : {m.hit_at_3:.1%}",
        f"  Hit Rate @5      : {m.hit_at_5:.1%}",
        f"  MRR              : {m.mrr:.4f}",
        f"  Avg Top Score    : {m.avg_top_score:.4f}",
        f"  Score Pass Rate  : {m.avg_score_pass_rate:.1%}",
        "",
        "  ANSWER-READINESS (RETRIEVAL PROXY)",
        f"  Source correctness: {m.hit_at_3:.1%}",
        f"  Evidence coverage : {m.avg_keyword_ratio:.1%}",
        f"  Context precision : {m.context_precision:.1%}",
        f"  Context recall    : {m.context_recall:.1%}",
        f"  Coverage Pass Rate: {m.keyword_pass_rate:.1%}",
        f"  Grounded Pass Rate: {m.pass_rate:.1%}",
        f"  Answer relevancy  : {m.answer_relevancy:.1%}"
        if m.answer_relevancy is not None
        else "  Answer relevancy  : N/A (retrieval-only run)",
        f"  Citation correctness: {m.citation_correctness:.1%}"
        if m.citation_correctness is not None
        else "  Citation correctness: N/A (retrieval-only run)",
        "",
        "  LATENCY",
        f"  Avg Latency      : {m.avg_latency_ms:.1f}ms",
        f"  P95 Latency      : {m.p95_latency_ms:.1f}ms",
        "",
        "  PER-CATEGORY BREAKDOWN",
        f"  {'Category':<14} {'Pass/Total':<12} {'Pass%':>6}  {'AvgScore':>9}  {'Hit@3':>6}",
        f"  {'-' * 14} {'-' * 12} {'-' * 6}  {'-' * 9}  {'-' * 6}",
    ]
    for cat, s in sorted(m.category_stats.items()):
        grade = "✅" if s["pass_rate"] >= 0.70 else ("⚠️ " if s["pass_rate"] >= 0.50 else "❌")
        lines.append(
            f"  {cat:<14} {s['pass']}/{s['total']:<11} "
            f"{s['pass_rate']:>6.1%}  {s['avg_score']:>9.4f}  "
            f"{s['hit_at_3']:>6.1%}  {grade}"
        )
    lines.append("")
    # Overall verdict
    if m.pass_rate >= 0.80:
        lines.append("  ✅  Đánh giá: RAG hoạt động TỐT")
    elif m.pass_rate >= 0.60:
        lines.append("  ⚠️   Đánh giá: RAG TRUNG BÌNH — cần bổ sung tài liệu")
    else:
        lines.append("  ❌  Đánh giá: RAG CẦN CẢI THIỆN — thiếu tài liệu hoặc embedding yếu")
    lines.append(separator)
    return "\n".join(lines)
