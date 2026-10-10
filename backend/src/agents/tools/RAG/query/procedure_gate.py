"""Conservative evidence checks for two procedures often confused with advice.

These checks do not certify general claim entailment or the source's freshness.
They only prevent generating missing app creation steps or rain intervention SOPs.
"""
from __future__ import annotations

import re
import unicodedata

from .schemas import CitationItem, QueryAnalysis, RAGResponse


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    return "".join(char for char in text if unicodedata.category(char) != "Mn").replace("đ", "d")


def mentions_rain(text: str) -> bool:
    # Accentless "mua" alone also means buy; do not intercept charger pricing.
    return "mưa" in text.casefold() or any(term in fold(text) for term in ("troi mua", "gap mua", "bi mua", "mua to", "sam set"))


def evidence_blocks(context: str, citations: list[CitationItem]) -> list[tuple[int, CitationItem, str]]:
    pattern = r'\[Tài liệu\s+(\d+)\]\s+\(ID:[^\n]*\)\n.*?- Nội dung trích xuất:\n"""\n(.*?)\n"""'
    blocks = []
    for match in re.finditer(pattern, context, flags=re.DOTALL):
        index = int(match.group(1))
        if 1 <= index <= len(citations):
            blocks.append((index, citations[index - 1], match.group(2)))
    return blocks


def procedure_evidence_gate(analysis: QueryAnalysis, context: str, citations: list[CitationItem]) -> RAGResponse | None:
    query = fold(analysis.original_query)
    blocks = evidence_blocks(context, citations)
    rescue = "cuu ho pin" in query and any(term in query for term in ("hoat dong", "quy trinh", "cac buoc", "nhu the nao", "cach goi"))
    specific_terms = ("gia", "chi phi", "bao nhieu", "mien phi", "dieu kien", "thoi gian", "hotline", "so dien thoai")
    if rescue and not any(term in query for term in specific_terms):
        for index, citation, body in blocks:
            if "quy trinh goi cuu ho pin" not in fold(citation.section):
                continue
            steps = re.findall(r"^\s*-\s*(Bước\s+([1-4]):[^\n]+)", body, flags=re.MULTILINE | re.IGNORECASE)
            # Quote one complete procedure from one chunk. Never join missing
            # steps across sources or invent operating conditions and prices.
            if [number for _, number in steps] != ["1", "2", "3", "4"] or any(len(text) > 300 for text, _ in steps):
                continue
            return RAGResponse(
                answer="Đoạn tài liệu truy xuất mô tả quy trình gọi cứu hộ pin như sau:\n"
                + "\n".join(f"- {text.strip()} [Tài liệu 1]." for text, _ in steps)
                + "\n\nĐây là các bước được ghi trong đoạn nguồn; chưa xác minh hiệu lực và điều kiện áp dụng cho trường hợp cụ thể. Vui lòng xác nhận với đơn vị hỗ trợ trước khi áp dụng.",
                citations=[citation], confidence="low", fallback_required=True,
                metadata={"reason": "battery_rescue_documented_steps_only", "evidence_gate": True,
                          "source_cited_doc_indexes": [index], "source_rule_verified": False},
            )
    app_steps = "dat lich" in query and ("ung dung" in query or re.search(r"\bapp\b", query)) and any(term in query for term in ("nhu the nao", "huong dan", "cach", "cac buoc"))
    if app_steps:
        for _, citation, body in blocks:
            text = fold(body)
            source = fold(citation.title + " " + citation.section + " " + body)
            if "theo doi" in fold(citation.section):
                continue
            if ("ung dung" in source or re.search(r"\bapp\b", source)) and re.search(r"chon (?:loai )?dich vu", text) and "chon thoi gian" in text:
                return None
        return RAGResponse(
            answer="Các đoạn tài liệu được cung cấp chưa đủ hướng dẫn từng bước tạo lịch hẹn mới trên ứng dụng VinFast. Hướng dẫn theo dõi lịch đã đặt không xác định các bước tạo lịch mới. Vui lòng liên hệ xưởng dịch vụ để được hướng dẫn phù hợp.",
            confidence="low", fallback_required=True,
            metadata={"reason": "app_booking_steps_missing", "evidence_gate": True, "source_cited_doc_indexes": []},
        )
    rain_charging = "sac" in query and mentions_rain(analysis.original_query)
    if not rain_charging:
        return None
    for _, citation, body in blocks:
        section = fold(citation.section)
        if mentions_rain(citation.section) and "sac" in section and re.search(r"buoc\s*1\b", fold(body)):
            return None  # An explicit weather/charging procedure is available.
    # Quote only the direct weather warning; never turn it into disconnection SOP.
    for index, citation, body in blocks:
        for sentence in re.split(r"(?<=[.!?])\s+|\n", body):
            text = fold(sentence)
            if "khong nen sac" in text and ("mua to" in text or "sam set" in text) and len(sentence) <= 450:
                return RAGResponse(
                    answer=sentence.strip() + " [Tài liệu 1]\n\nCác đoạn này chưa xác định quy trình xử lý xe đang sạc khi gặp mưa. Không thể suy ra thao tác ngắt sạc, rút cáp hoặc di chuyển xe từ cảnh báo này. Vui lòng liên hệ hỗ trợ kỹ thuật để được hướng dẫn theo tình huống.",
                    citations=[citation], confidence="low", fallback_required=True,
                    metadata={"reason": "rain_charging_procedure_missing", "evidence_gate": True, "source_cited_doc_indexes": [index]},
                )
    return RAGResponse(
        answer="Các đoạn tài liệu được cung cấp chưa xác định quy trình xử lý khi xe đang sạc gặp mưa. Vui lòng liên hệ hỗ trợ kỹ thuật; tôi chưa có căn cứ để hướng dẫn thao tác ngắt sạc, rút cáp hoặc di chuyển xe trong tình huống này.",
        confidence="low", fallback_required=True,
        metadata={"reason": "rain_charging_procedure_missing", "evidence_gate": True, "source_cited_doc_indexes": []},
    )
