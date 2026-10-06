"""Local retrieval of actual repository documents, with inspectable excerpts."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCUMENTS = {
    "vf6-booklet": (
        "knowledge/demo/warranty_maintenance_VF6_excerpt.md",
        "Sổ bảo hành VF6 — trích đoạn kho tài liệu",
        "VF6",
    ),
    "warranty-policy": (
        "knowledge/demo/warranty_policy_excerpt.md",
        "Warranty Policy — trích đoạn kho tài liệu",
        "ALL",
    ),
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold()).replace("đ", "d")
    return "".join(c for c in text if not unicodedata.combining(c))


class DemoKnowledge:
    def __init__(self):
        self.chunks = []
        for doc_id, (path, title, model) in DOCUMENTS.items():
            content = (ROOT / path).read_text(encoding="utf-8")
            for chunk in re.split(r"\n(?=## )", content):
                if chunk.startswith("## "):
                    self.chunks.append((doc_id, title, model, chunk.strip()))

    def search(self, query: str, model: str = "VF6") -> dict:
        # The curated corpus only supports warranty; other questions must not be
        # made to look grounded merely because they mention a car or its battery.
        normalized = normalize(query)
        topics = ("bao hanh", "warranty", "maintenance exclusion", "bao duong co duoc mien phi")
        if not any(term in normalized for term in topics):
            return {
                "status": "empty",
                "code": "NO_EVIDENCE",
                "data": {"citations": []},
                "hint": "Kho demo chưa có nguồn cho câu hỏi này; không khẳng định số liệu kỹ thuật.",
            }
        terms = set(re.findall(r"\w+", normalized)) - {"xe", "cua", "toi", "vf6", "co", "khong", "la"}
        scored = []
        for doc_id, title, target_model, text in self.chunks:
            if target_model not in (model.upper(), "ALL"):
                continue
            words = set(re.findall(r"\w+", normalize(text)))
            score = len(terms & words)
            if score:
                scored.append((score, doc_id, title, text))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return {
                "status": "empty",
                "code": "NO_EVIDENCE",
                "data": {"citations": []},
                "hint": "Không có nguồn phù hợp.",
            }
        citations = [
            {
                "title": title,
                "version": "snapshot-repository",
                "documentType": "warranty_policy",
                "pageNumber": None,
                "snippet": text[:1400],
                "documentId": doc_id,
                "sourceUrl": f"/api/v1/demo/documents/{doc_id}",
            }
            for _, doc_id, title, text in scored[:2]
        ]
        return {
            "status": "ok",
            "data": {"citations": citations, "evidence": "\n\n".join(c["snippet"] for c in citations)},
            "hint": "Chỉ khẳng định điều được chứng minh bởi trích đoạn; dữ liệu kho demo có thể khác chính sách hiện hành.",
        }
