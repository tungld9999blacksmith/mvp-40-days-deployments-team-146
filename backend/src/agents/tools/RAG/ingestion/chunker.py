import logging
import re
from typing import Any

from .config import rag_settings
from .metadata import CleanedDocument, DocumentChunk

logger = logging.getLogger(__name__)


class DocumentChunker:
    """Engine phân đoạn văn bản thông minh (Semantic & Section-aware Recursive Chunking)."""

    def __init__(
        self,
        chunk_size: int = rag_settings.chunk_size,
        chunk_overlap: int = rag_settings.chunk_overlap,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_document(self, doc: CleanedDocument) -> list[DocumentChunk]:
        """Phân đoạn CleanedDocument thành danh sách DocumentChunk có metadata phong phú."""
        text = doc.cleaned_content
        if not text.strip():
            return []

        # 1. Tách văn bản thành các section dựa theo Markdown heading (# , ## , ### )
        sections = self._split_by_markdown_headers(text)

        # 2. Xử lý từng section, nếu section dài quá chunk_size thì chia nhỏ tiếp
        raw_chunks: list[dict[str, Any]] = []

        for sec in sections:
            header = sec["header"]
            content = sec["content"]
            prefix = f"[{doc.metadata.title} > {header}]\n" if header else f"[{doc.metadata.title}]\n"

            if len(content) + len(prefix) <= self.chunk_size:
                raw_chunks.append({
                    "text": prefix + content,
                    "section_header": header,
                })
            else:
                sub_chunks = self._recursive_split(content, self.chunk_size - len(prefix), self.chunk_overlap)
                for sc in sub_chunks:
                    raw_chunks.append({
                        "text": prefix + sc,
                        "section_header": header,
                    })

        # 3. Đóng gói thành DocumentChunk với metadata
        total_chunks = len(raw_chunks)
        chunks: list[DocumentChunk] = []

        for idx, item in enumerate(raw_chunks):
            chunk_id = f"{doc.doc_id}_chk_{idx + 1:04d}"
            chunk_text = item["text"].strip()

            # Trích xuất metadata bổ sung từ nội dung chunk (vd: có nhắc tới mốc km hay model cụ thể)
            chunk_meta = self._enrich_chunk_metadata(doc, chunk_text, item["section_header"], idx, total_chunks)

            chunks.append(DocumentChunk(
                chunk_id=chunk_id,
                doc_id=doc.doc_id,
                content=chunk_text,
                metadata=chunk_meta,
                chunk_index=idx,
                total_chunks=total_chunks,
            ))

        logger.info(f"Tạo {len(chunks)} chunks cho tài liệu: {doc.doc_id}")
        return chunks

    def _split_by_markdown_headers(self, text: str) -> list[dict[str, str]]:
        """Phân tách văn bản theo các tiêu đề Markdown (#, ##, ###)
        và các heading dạng plain-text từ PDF (Roman numeral, ALL-CAPS ngắn)."""
        lines = text.split("\n")
        sections: list[dict[str, str]] = []
        current_header = ""
        current_lines: list[str] = []

        # Heading Markdown: # , ## , ###
        md_header = re.compile(r"^(#{1,3})\s+(.+)$")
        # Heading Roman numeral từ PDF: "I.", "II.", "III.", "IV.", "V." ... ở đầu dòng
        roman_header = re.compile(
            r"^(I{1,3}V?|IV|VI{0,3}|IX|XI{0,3}|XX?)[\.\)]\s+(.+)$"
        )
        # ALL-CAPS heading ngắn (< 80 ký tự, không phải số trang đơn lẻ)
        allcaps_header = re.compile(r"^([A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĐ\s]{8,79})$")

        def is_heading(line: str) -> tuple[bool, str]:
            s = line.strip()
            if not s:
                return False, ""
            m = md_header.match(s)
            if m:
                return True, m.group(2).strip()
            m = roman_header.match(s)
            if m:
                return True, s
            # ALL-CAPS: phải có ít nhất 2 từ, không phải chỉ số hoặc mã
            if allcaps_header.match(s) and len(s.split()) >= 2 and not re.match(r"^[\d\s]+$", s):
                return True, s
            return False, ""

        for line in lines:
            matched, header_text = is_heading(line)
            if matched:
                if current_lines:
                    content_str = "\n".join(current_lines).strip()
                    if content_str:
                        sections.append({
                            "header": current_header,
                            "content": content_str,
                        })
                current_header = header_text
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            content_str = "\n".join(current_lines).strip()
            if content_str:
                sections.append({
                    "header": current_header,
                    "content": content_str,
                })

        if not sections:
            sections = [{"header": "", "content": text}]

        return sections

    def _recursive_split(self, text: str, max_size: int, overlap: int) -> list[str]:
        """Chia đệ quy theo dấu ngắt đoạn, dòng, hoặc câu."""
        if len(text) <= max_size:
            return [text]

        separators = ["\n\n", "\n", ". ", "; ", " "]
        for sep in separators:
            parts = text.split(sep)
            if len(parts) > 1:
                return self._merge_parts(parts, sep, max_size, overlap)

        # Fallback cứng nếu không có khoảng trắng
        chunks = []
        start = 0
        while start < len(text):
            chunks.append(text[start : start + max_size])
            start += max_size - overlap
        return chunks

    def _merge_parts(self, parts: list[str], sep: str, max_size: int, overlap: int) -> list[str]:
        """Gộp các phần nhỏ lại với nhau tôn trọng max_size và overlap."""
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_len = 0

        for part in parts:
            part_len = len(part) + len(sep)
            if current_len + part_len > max_size and current_chunk:
                chunk_str = sep.join(current_chunk).strip()
                if chunk_str:
                    chunks.append(chunk_str)

                # Giữ lại một phần cuối cho overlap
                overlap_tokens: list[str] = []
                overlap_len = 0
                for prev in reversed(current_chunk):
                    if overlap_len + len(prev) <= overlap:
                        overlap_tokens.insert(0, prev)
                        overlap_len += len(prev) + len(sep)
                    else:
                        break

                current_chunk = overlap_tokens
                current_len = overlap_len

            current_chunk.append(part)
            current_len += part_len

        if current_chunk:
            final_str = sep.join(current_chunk).strip()
            if final_str:
                chunks.append(final_str)

        return chunks

    def _enrich_chunk_metadata(
        self,
        doc: CleanedDocument,
        chunk_text: str,
        section_header: str,
        chunk_idx: int,
        total_chunks: int,
    ) -> dict[str, Any]:
        """Sinh metadata cho chunk để hỗ trợ filter chính xác khi RAG retrieval."""
        meta: dict[str, Any] = {
            "source": doc.metadata.source,
            "doc_id": doc.doc_id,
            "title": doc.metadata.title,
            "file_type": doc.metadata.file_type,
            "section_header": section_header,
            "chunk_index": chunk_idx,
            "total_chunks": total_chunks,
            "category": doc.metadata.category,
            "model": doc.metadata.model,
            "milestone_km": doc.metadata.milestone_km or 0,
        }
        source_url = doc.metadata.extra.get("source_url")
        if source_url:
            meta["source_url"] = source_url

        # Bổ sung model nếu trong đoạn nhắc đến cụ thể một model duy nhất
        lower = chunk_text.lower()
        model_patterns = {
            "VFe34": r"\bvf\s*e\s*34\b",
            "VFMPV7": r"\bvf\s*mpv\s*7\b",
            "VF3": r"\bvf\s*3\b",
            "VF5": r"\bvf\s*5(?:\s*plus)?\b",
            "VF6": r"\bvf\s*6\b",
            "VF7": r"\bvf\s*7\b",
            "VF8": r"\bvf\s*8\b",
            "VF9": r"\bvf\s*9\b",
        }
        found_models = [m for m, pattern in model_patterns.items() if re.search(pattern, lower)]
        if len(found_models) == 1:
            meta["model"] = found_models[0]
        elif len(found_models) > 1 or doc.metadata.model == "ALL":
            meta["model"] = "ALL"
        else:
            meta["model"] = doc.metadata.model

        # Gán category theo section. FAQ là tài liệu đa chủ đề nên
        # không thể dùng category của phần mở đầu cho hàng trăm section.
        cat = doc.metadata.category
        header_lower = section_header.lower()

        # Các section rõ ràng là nhật ký bảo dưỡng → override sang maintenance
        maintenance_headers = [
            "nhật ký bảo dưỡng", "lịch bảo dưỡng", "bảo dưỡng định kỳ",
            "bảo dưỡng cấp", "hạng mục bảo dưỡng", "mốc bảo dưỡng",
        ]
        warranty_headers = [
            "chính sách bảo hành", "điều kiện bảo hành", "phạm vi bảo hành",
            "thời hạn bảo hành", "trường hợp không bảo hành", "quy trình bảo hành",
            "bảo hành",
        ]
        pricing_headers = [
            "bảng giá", "giá dịch vụ", "chi phí", "giá sạc",
            "phí sạc", "phí thuê pin", "thanh toán phí",
        ]
        procedure_headers = [
            "quy trình", "hitl", "đặt lịch", "các bước", "làm thế nào",
            "cách kiểm tra", "cách cài đặt", "hướng dẫn thêm",
            "chuyển quyền", "cập nhật phần mềm", "lịch sử dịch vụ",
        ]
        battery_headers = [
            "an toàn pin", "pin ô tô", "pin cao áp", "cứu hộ pin",
            "sạc pin", "trạm sạc", "bộ sạc", "súng sạc", "hốc sạc",
            "công suất sạc", "thời gian nạp pin", "quãng đường di chuyển 1 lần sạc",
        ]

        # Pricing catalogues may contain headings such as "bộ sạc", "pin cao áp"
        # or "quy trình nhận báo giá". Those phrases describe the priced item
        # or quote workflow, not a change of document intent. Keeping the
        # document-level category prevents category-filtered retrieval from
        # hiding official price chunks.
        if doc.metadata.category == "pricing":
            cat = "pricing"
        elif "mốc bảo dưỡng" in header_lower:
            cat = "maintenance"
        elif any(h in header_lower for h in pricing_headers):
            cat = "pricing"
        elif any(h in header_lower for h in warranty_headers):
            cat = "warranty"
        elif any(h in header_lower for h in battery_headers):
            cat = "battery"
        elif any(h in header_lower for h in maintenance_headers):
            cat = "maintenance"
        elif any(h in header_lower for h in procedure_headers):
            cat = "procedure"
        # Không có header đặc thù → giữ category tài liệu gốc (không override bằng nội dung chunk)
        meta["category"] = cat

        # Bổ sung mốc km nếu trong đoạn nhắc đến
        km_match = re.search(r"(\d{1,3}(?:[.,]\d{3})*|\d+)\s*(?:km|cây số)", lower)
        if km_match:
            raw_num = km_match.group(1).replace(".", "").replace(",", "")
            if raw_num.isdigit():
                val = int(raw_num)
                if val in [10000, 15000, 20000, 30000, 40000, 50000, 60000, 80000, 100000, 120000]:
                    meta["milestone_km"] = val

        return meta
