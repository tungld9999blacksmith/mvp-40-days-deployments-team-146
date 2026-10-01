from __future__ import annotations

import logging

from .schemas import CitationItem, RetrievalCandidate

logger = logging.getLogger(__name__)


class CitationBuilder:
    """Xây dựng ngữ cảnh trích dẫn có cấu trúc cho LLM và chuẩn hóa danh sách Citations."""

    def build(
        self,
        candidates: list[RetrievalCandidate],
    ) -> tuple[str, list[CitationItem]]:
        """Chuyển đổi danh sách Top-K candidates thành:

        1. Context dạng Markdown có đánh số [Tài liệu 1], [Tài liệu 2] cho System Prompt.
        2. Danh sách đối tượng CitationItem chuẩn hóa phục vụ response JSON.
        """
        if not candidates:
            return "Không có tài liệu tham khảo phù hợp.", []

        context_lines: list[str] = [
            "### DANH SÁCH TÀI LIỆU CHÍNH HÃNG ĐƯỢC CẤP PHÉP THAM KHẢO:\n"
        ]
        citation_items: list[CitationItem] = []

        for idx, cand in enumerate(candidates, start=1):
            meta = cand.metadata or {}
            doc_id = cand.doc_id or meta.get("doc_id", f"DOC_{idx:03d}")
            title = meta.get("title") or meta.get("source") or "Cẩm nang xe điện VinFast"
            section = meta.get("section_header") or meta.get("section") or ""
            source_url = meta.get("source_url") or meta.get("url") or None
            model = meta.get("model", "ALL")
            category = meta.get("category", "")
            score = cand.rerank_score or cand.rrf_score or cand.dense_score

            # Tạo CitationItem có cấu trúc
            citation_item = CitationItem(
                document_id=doc_id,
                title=title,
                section=section,
                source_url=source_url,
                chunk_id=cand.chunk_id,
                score=round(score, 4) if score is not None else None,
            )
            citation_items.append(citation_item)

            # Đóng gói ngữ cảnh chi tiết gửi vào prompt LLM
            doc_header = f"[Tài liệu {idx}] (ID: {doc_id} | Chunk: {cand.chunk_id})"
            meta_details: list[str] = [f"Tiêu đề: {title}"]
            if section:
                meta_details.append(f"Mục: {section}")
            if model and model != "ALL":
                meta_details.append(f"Dòng xe áp dụng: {model}")
            if category:
                meta_details.append(f"Hạng mục: {category}")

            context_lines.append(f"{doc_header}")
            context_lines.append(f"- Thông tin nguồn: {' | '.join(meta_details)}")
            context_lines.append(f"- Nội dung trích xuất:\n\"\"\"\n{cand.content.strip()}\n\"\"\"\n")
            context_lines.append("---\n")

        formatted_context = "\n".join(context_lines)
        return formatted_context, citation_items
