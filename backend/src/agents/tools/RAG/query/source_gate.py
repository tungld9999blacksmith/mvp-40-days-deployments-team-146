"""Narrow observed evidence failures; does not certify general claim entailment."""
from __future__ import annotations

import re

from .procedure_gate import evidence_blocks, fold
from .schemas import CitationItem, QueryAnalysis, RAGResponse


def scope_conflicts(context: str, citations: list[CitationItem]) -> list[int]:
    model = r"vf\s*(?:e\s*34|mpv\s*7|[3-9])\b"
    conflicts = []
    for index, citation, body in evidence_blocks(context, citations):
        declared = {re.sub(r"\s+", "", m) for m in re.findall(model, fold(citation.title))}
        text = fold(re.sub(r"^\[[^\n]*\]\s*$", "", body, flags=re.MULTILINE))
        claims = re.findall(r"doi voi\s+(?:xe\s+)?(" + model + r")", text)
        if not claims:
            claims = re.findall(r"(?:dong xe|xe)\s+(?:vinfast\s+)?(" + model + r")", text)
        policy = {re.sub(r"\s+", "", m) for m in claims}
        if len(declared) == 1 and policy and not policy & declared:
            conflicts.append(index)
    return conflicts


def scope_fallback(conflicts: list[int], original_answer: str | None = None) -> RAGResponse:
    return RAGResponse(
        answer="Tiêu đề và nội dung nguồn đang chỉ đến các dòng xe khác nhau; chưa xác minh được phạm vi áp dụng. Cần đối chiếu đúng tài liệu và phiên bản trước khi kết luận chính sách cho xe của bạn.",
        confidence="low", fallback_required=True,
        metadata={"reason": "source_model_scope_conflict", "evidence_gate": True, "conflicting_source_indexes": conflicts,
                  "source_cited_doc_indexes": [], "original_generation_answer": original_answer},
    )


def source_evidence_gate(analysis: QueryAnalysis, context: str, citations: list[CitationItem]) -> RAGResponse | None:
    blocks = evidence_blocks(context, citations)
    query = fold(analysis.original_query)
    conflicts = scope_conflicts(context, citations)
    if blocks and len(conflicts) == len(blocks):
        return scope_fallback(conflicts)
    usable = [(i, c, body) for i, c, body in blocks if i not in conflicts]
    capability = re.search(r"\b(?:ai|hitl)\b|human[ -]in[ -]the[ -]loop", query)
    if capability and not any(re.search(r"\b(?:ai|hitl)\b|human[ -]in[ -]the[ -]loop", fold(body)) for _, _, body in usable):
        return RAGResponse(
            answer="Các đoạn tài liệu được cung cấp chưa xác định chức năng của AI hoặc quy trình mang tên HITL. Cần thông tin về chức năng của hệ thống đang sử dụng để trả lời phần này.",
            confidence="low", fallback_required=True,
            metadata={"reason": "system_capability_evidence_missing", "evidence_gate": True, "source_cited_doc_indexes": []},
        )
    # Only the flattened two-cell row: do not override a complete period matrix.
    if "dau phanh" in query and any(term in query for term in ("tung ky", "ky dau", "xen ke", "moc")):
        selected_model = re.sub(r"\s+", "", fold(analysis.model or ""))
        applicable = [(i, c, body) for i, c, body in blocks if i not in conflicts and (selected_model in {"", "all"} or selected_model in re.sub(r"\s+", "", fold(c.title + " " + c.section)))]
        explicit_first = any("dau phanh" in fold(line) and re.search(r"\b(?:ky|lan)\s+(?:dau|1)\b", fold(line)) for _, _, body in applicable for line in body.splitlines())
        rows = [(index, citation, line) for index, citation, body in applicable for line in body.splitlines()
                if line.strip().startswith("|") and "dau phanh" in fold(line)]
        if not explicit_first and rows and all(len([c for c in line.split("|") if c.strip()]) == 2 and "kiem tra, thay moi xen ke" in fold(line) for _, _, line in rows):
            index, citation, _ = rows[0]
            return RAGResponse(
                answer="Bảng nêu dầu phanh được kiểm tra và thay mới xen kẽ [Tài liệu 1]. Các đoạn được cung cấp chưa ánh xạ thao tác vào từng kỳ, nên chưa xác định kỳ đầu là kiểm tra hay thay mới và chưa thể liệt kê lịch từng mốc.",
                citations=[citation], confidence="low", fallback_required=True,
                metadata={"reason": "alternating_period_mapping_missing", "evidence_gate": True, "source_cited_doc_indexes": [index]},
            )
    cancel_when = re.search(r"\b(?:huy|doi lich)\b", query) and any(t in query for t in ("khi nao", "thoi diem", "bao lau", "truoc", "gio"))
    if cancel_when:
        sentences = [(i, c, sentence) for i, c, body in usable for sentence in re.split(r"(?<=[.!?])\s+", " ".join(body.split()))
                     if re.search(r"\b(?:huy|doi lich)\b", fold(sentence))]
        # Real cancellation hour limits must go through normal generation/review.
        if any(re.search(r"\b(?:\d+|bon|hai|ba|mot)\s*(?:gio|tieng|ngay)\b", fold(s)) for _, _, s in sentences):
            return None
        for index, citation, sentence in sentences:
            if "truoc khi lich hen dien ra" in fold(sentence) and len(sentence) < 450:
                return RAGResponse(
                    answer=sentence.strip() + " [Tài liệu 1]\n\nĐoạn này chưa nêu hạn hủy/đổi theo số giờ. Không dùng mốc xác nhận báo giá để suy ra hạn hủy/đổi lịch.",
                    citations=[citation], confidence="medium", fallback_required=False,
                    metadata={"reason": "cancellation_deadline_separate_from_quote", "evidence_gate": True, "source_cited_doc_indexes": [index]},
                )
    return None
