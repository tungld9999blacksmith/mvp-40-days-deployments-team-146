import logging
import re
from pathlib import Path
from typing import Any

import html2text
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .metadata import DocumentMetadata, RawDocument

logger = logging.getLogger(__name__)


class IngestionEngine:
    """Engine xử lý đọc và nạp các định dạng tài liệu gốc (PDF, HTML, MD, TXT)."""

    def __init__(self) -> None:
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.ignore_tables = False
        self.html_converter.body_width = 0

    def ingest_file(self, file_path: Path | str) -> RawDocument:
        """Đọc và nạp một file theo định dạng phần mở rộng."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Không tìm thấy file: {path}")

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self._ingest_pdf(path)
        elif suffix in [".html", ".htm"]:
            return self._ingest_html(path)
        elif suffix in [".md", ".markdown", ".txt"]:
            return self._ingest_text(path)
        else:
            raise ValueError(f"Định dạng file không hỗ trợ: {suffix}. Hỗ trợ: .pdf, .html, .md, .txt")

    def ingest_directory(self, dir_path: Path | str) -> list[RawDocument]:
        """Quét và nạp tất cả tài liệu hợp lệ trong thư mục."""
        path = Path(dir_path)
        if not path.exists() or not path.is_dir():
            logger.warning(f"Thư mục không tồn tại: {path}")
            return []

        documents: list[RawDocument] = []
        supported_extensions = {".pdf", ".html", ".htm", ".md", ".txt"}

        for file_path in sorted(path.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                try:
                    doc = self.ingest_file(file_path)
                    documents.append(doc)
                    logger.info(f"Ingested thành công: {file_path.name} ({len(doc.content)} ký tự)")
                except Exception as e:
                    logger.error(f"Lỗi khi ingest {file_path.name}: {e}")

        return documents

    def _ingest_pdf(self, path: Path) -> RawDocument:
        """Đọc nội dung file PDF qua pypdf, trích xuất text từng trang."""
        text_parts: list[str] = []
        meta_dict: dict[str, Any] = {}

        with open(path, "rb") as f:
            reader = PdfReader(f)
            total_pages = len(reader.pages)
            if reader.metadata:
                meta_dict = {
                    "author": str(reader.metadata.author or ""),
                    "creator": str(reader.metadata.creator or ""),
                    "title": str(reader.metadata.title or ""),
                }

            for page_idx, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"--- [Trang {page_idx}/{total_pages}] ---\n{page_text.strip()}")

        content = "\n\n".join(text_parts)
        doc_id = path.stem

        # Ưu tiên title từ tên file (đặt tên theo convention category_model)
        # Fallback: metadata PDF → extract từ text → tên file
        title_from_filename = self._title_from_filename(path.stem)
        title = (
            title_from_filename
            or meta_dict.get("title")
            or self._extract_title_from_text(content)
            or path.stem.replace("_", " ").title()
        )

        category, model, milestone_km = self._infer_metadata(title + "\n" + content[:1000], filename=path.name)

        metadata = DocumentMetadata(
            source=str(path.name),
            doc_id=doc_id,
            title=title,
            file_type="pdf",
            model=model,
            category=category,
            milestone_km=milestone_km,
            extra={
                "total_pages": total_pages,
                "file_path": str(path),
                **meta_dict,
            },
        )
        return RawDocument(doc_id=doc_id, content=content, metadata=metadata)

    def _ingest_html(self, path: Path) -> RawDocument:
        """Đọc file HTML, loại bỏ thẻ rác (script, style, nav, footer) và chuyển sang markdown."""
        html_content = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html_content, "html.parser")

        # Bỏ các thẻ không mang nội dung kiến thức
        for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg"]):
            tag.decompose()

        # Trích xuất title
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.h1:
            title = soup.h1.get_text().strip()

        # Chuyển đổi phần thân HTML thành Markdown có cấu trúc
        markdown_text = self.html_converter.handle(str(soup))
        if not title:
            title = self._extract_title_from_text(markdown_text) or path.stem.replace("_", " ").title()

        doc_id = path.stem
        category, model, milestone_km = self._infer_metadata(title + "\n" + markdown_text[:1000], filename=path.name)

        metadata = DocumentMetadata(
            source=str(path.name),
            doc_id=doc_id,
            title=title,
            file_type="html",
            model=model,
            category=category,
            milestone_km=milestone_km,
            extra={"file_path": str(path)},
        )
        return RawDocument(doc_id=doc_id, content=markdown_text, metadata=metadata)

    def _ingest_text(self, path: Path) -> RawDocument:
        """Đọc file Markdown hoặc TXT."""
        content = path.read_text(encoding="utf-8", errors="ignore")
        title = self._extract_title_from_text(content) or path.stem.replace("_", " ").title()
        doc_id = path.stem
        category, model, milestone_km = self._infer_metadata(title + "\n" + content[:1000], filename=path.name)

        file_type = "md" if path.suffix.lower() in [".md", ".markdown"] else "txt"
        source_url_match = re.search(r"https://(?:www\.)?(?:vinfastauto|shop\.vinfastauto)\.com/[^\s)>]+", content)
        metadata = DocumentMetadata(
            source=str(path.name),
            doc_id=doc_id,
            title=title,
            file_type=file_type,
            model=model,
            category=category,
            milestone_km=milestone_km,
            extra={
                "file_path": str(path),
                "source_url": source_url_match.group(0).rstrip(".,") if source_url_match else None,
            },
        )
        return RawDocument(doc_id=doc_id, content=content, metadata=metadata)

    def _title_from_filename(self, stem: str) -> str:
        """Sinh title có nghĩa từ tên file theo convention category_model.
        Ví dụ: warranty_maintenance_VF8 → Sổ bảo hành & bảo dưỡng VinFast VF8
        """
        lower = stem.lower()
        # Xác định model từ tên file
        model_map = {
            "vfe34": "VF e34",
            "vfmpv7": "VF MPV 7",
            "vf3": "VF3",
            "vf5": "VF5",
            "vf6": "VF6",
            "vf7": "VF7",
            "vf8": "VF8",
            "vf9": "VF9",
        }
        model_label = ""
        for key, label in model_map.items():
            if key in lower:
                model_label = label
                break

        if "warranty_maintenance" in lower and model_label:
            return f"Sổ bảo hành & nhật ký bảo dưỡng VinFast {model_label}"
        if "bao_hanh" in lower and model_label:
            return f"Chính sách bảo hành VinFast {model_label}"
        if "bao_duong" in lower and model_label:
            return f"Cẩm nang bảo dưỡng định kỳ VinFast {model_label}"
        if "bang_gia" in lower:
            return f"Bảng giá dịch vụ VinFast{' ' + model_label if model_label else ''}"
        return ""

    def _extract_title_from_text(self, text: str) -> str:
        """Trích xuất tiêu đề chính từ dòng đầu tiên có dạng # Title hoặc text đậm."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines[:5]:
            if line.startswith("#"):
                clean = re.sub(r"^#+\s*", "", line).strip()
                if clean:
                    return clean
            elif len(line) > 5 and len(line) < 120 and not line.startswith("---"):
                return line
        return ""

    def _infer_metadata(self, sample_text: str, filename: str = "") -> tuple[str, str, int | None]:
        """Phân tích tên file và nội dung để suy ra category, model xe và mốc km nếu có."""
        lower = sample_text.lower()
        file_lower = filename.lower()

        # 1. Infer category — ưu tiên tên file, rồi mới xét nội dung
        # Tên file dạng: warranty_maintenance_VFxx.pdf → cả warranty lẫn maintenance
        # Chọn category chính: nếu file có cả hai thì dùng "warranty" (bao trùm hơn)
        if "bang_gia" in file_lower or "pricing" in file_lower:
            category = "pricing"
        elif "warranty_policy" in file_lower:
            category = "warranty"
        elif "toi_uu_moc_bao_duong" in file_lower or "lich_bao_duong" in file_lower:
            category = "maintenance"
        elif "faq" in file_lower:
            # FAQ la tai lieu da chu de. Category se duoc gan lai theo tung
            # section trong DocumentChunker; khong suy dien tu 1.000 ky tu dau.
            category = "general"
        elif "quy_trinh" in file_lower or "hitl" in file_lower:
            category = "procedure"
        elif "battery" in file_lower or "an_toan_pin" in file_lower:
            category = "battery"
        elif "warranty_maintenance" in file_lower or "bao_hanh" in file_lower:
            # Sổ bảo hành VinFast chứa cả warranty + maintenance log → gán "warranty"
            # chunker sẽ override per-chunk khi section header có "bảo dưỡng"
            category = "warranty"
        elif "bao_duong" in file_lower or "cam_nang" in file_lower or "maintenance" in file_lower:
            category = "maintenance"
        # Fallback: xét nội dung
        elif "bảng giá" in lower or "giá dịch vụ" in lower:
            category = "pricing"
        elif "chính sách bảo hành" in lower or "sổ bảo hành" in lower:
            category = "warranty"
        elif "nhật ký bảo dưỡng" in lower or "bảo dưỡng định kỳ" in lower:
            category = "maintenance"
        elif "bảo dưỡng" in lower:
            category = "maintenance"
        elif "pin" in lower or "bms" in lower:
            category = "battery"
        elif "quy trình" in lower or "duyệt" in lower:
            category = "procedure"
        else:
            category = "general"

        # 2. Infer model — mở rộng thêm VFe34, VFMPV7, VF9
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

        # Ưu tiên tên file trước (chính xác nhất)
        model_from_file = ""
        for m, pattern in model_patterns.items():
            if re.search(pattern, file_lower):
                model_from_file = m
                break

        if "_all" in file_lower or file_lower.startswith("faq_"):
            model = "ALL"
        elif model_from_file:
            model = model_from_file
        else:
            # Tìm trong nội dung
            found_models = [m for m, pattern in model_patterns.items() if re.search(pattern, lower)]
            if len(found_models) > 1 or "tất cả" in lower or "toàn bộ" in lower or "all" in lower:
                model = "ALL"
            elif len(found_models) == 1:
                model = found_models[0]
            else:
                model = "ALL"

        # 3. Infer milestone km
        milestone_km: int | None = None
        km_match = re.search(r"(\d{1,3}(?:[.,]\d{3})*|\d+)\s*(?:km|cây số)", lower)
        if km_match:
            raw_num = km_match.group(1).replace(".", "").replace(",", "")
            if raw_num.isdigit():
                val = int(raw_num)
                if val in [10000, 15000, 20000, 30000, 40000, 50000, 60000, 80000, 100000, 120000]:
                    milestone_km = val

        return category, model, milestone_km
