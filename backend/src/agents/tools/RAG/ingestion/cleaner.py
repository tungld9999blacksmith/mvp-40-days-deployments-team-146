import html
import logging
import re
import unicodedata

from .metadata import CleanedDocument, RawDocument

logger = logging.getLogger(__name__)


class TextCleaner:
    """Engine làm sạch văn bản thô từ PDF/HTML trước khi thực hiện chunking."""

    def __init__(self) -> None:
        pass

    def clean(self, raw_doc: RawDocument) -> CleanedDocument:
        """Làm sạch toàn bộ văn bản và trả về CleanedDocument."""
        text = raw_doc.content

        # 1. Decode HTML entities (e.g. &nbsp; -> space, &amp; -> &)
        text = html.unescape(text)

        # 2. Unicode normalization (NFC: canonical composition chuẩn tiếng Việt)
        text = unicodedata.normalize("NFC", text)

        # 3. Thay thế các khoảng trắng lạ (\xa0, \u200b, \t) thành space thông thường
        text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 4. Loại bỏ các dòng nhiễu thường gặp trong PDF (vd: Trang 1/15, Confidential, ...)
        text = self._remove_header_footer_noise(text)

        # 5. Chuẩn hóa Markdown links và images thừa (giữ lại anchor text)
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)  # bỏ image markdown
        text = re.sub(r"\[(.*?)\]\((?:javascript:.*?|#.*?)\)", r"\1", text)  # bỏ JS link

        # 6. Chuẩn hóa định dạng bảng (Markdown tables)
        text = self._normalize_tables(text)

        # 7. Xóa các khoảng trắng thừa ở cuối dòng và gộp dòng trống liên tiếp
        lines = [line.strip() for line in text.split("\n")]
        cleaned_lines: list[str] = []
        consecutive_empty = 0

        for line in lines:
            if not line:
                consecutive_empty += 1
                if consecutive_empty <= 1:
                    cleaned_lines.append("")
            else:
                consecutive_empty = 0
                # Gộp nhiều space liên tiếp trong dòng thành 1 space, trừ khi là thụt đầu dòng markdown
                line = re.sub(r"[ \t]{2,}", " ", line)
                cleaned_lines.append(line)

        cleaned_content = "\n".join(cleaned_lines).strip()

        char_count = len(cleaned_content)
        word_count = len(cleaned_content.split())

        logger.debug(f"Cleaned {raw_doc.doc_id}: {len(raw_doc.content)} -> {char_count} chars")

        return CleanedDocument(
            doc_id=raw_doc.doc_id,
            cleaned_content=cleaned_content,
            metadata=raw_doc.metadata,
            char_count=char_count,
            word_count=word_count,
        )

    def _remove_header_footer_noise(self, text: str) -> str:
        """Loại bỏ các dòng lặp trang PDF như 'Trang X / Y', 'Page X of Y', header thương hiệu rác."""
        patterns = [
            r"(?i)^---\s*\[Trang\s+\d+/\d+\]\s*---\s*$",
            r"(?i)^trang\s+\d+\s*(?:/\s*\d+)?\s*$",
            r"(?i)^page\s+\d+\s*(?:of\s*\d+)?\s*$",
            r"(?i)^\s*copyright\s*©.*?(?:all\s*rights\s*reserved)?\s*$",
        ]
        lines = text.split("\n")
        filtered_lines = []
        for line in lines:
            stripped = line.strip()
            if any(re.match(pat, stripped) for pat in patterns):
                continue
            filtered_lines.append(line)
        return "\n".join(filtered_lines)

    def _normalize_tables(self, text: str) -> str:
        """Đảm bảo phân cách cột bảng Markdown không bị xộc xệch."""
        lines = text.split("\n")
        formatted = []
        for line in lines:
            if "|" in line:
                # Chuẩn hóa khoảng cách xung quanh ký tự |
                cells = [c.strip() for c in line.split("|")]
                if len(cells) >= 3:
                    formatted.append("| " + " | ".join(cells[1:-1]) + " |")
                    continue
            formatted.append(line)
        return "\n".join(formatted)
