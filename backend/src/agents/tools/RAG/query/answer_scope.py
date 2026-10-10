"""Recognize a narrow evidence limitation, never certify its truth or completeness."""
from __future__ import annotations

import re

from .procedure_gate import fold


def is_evidence_limitation(answer: str) -> bool:
    text = fold(answer.strip())
    # Only one scoped sentence. Technical numbers, extra claims and broad denials
    # must not escape citation review by setting fallback_required=true.
    if not re.fullmatch(r"cac doan tai lieu (?:duoc cung cap|truy xuat) chua xac dinh[^.!?\n]*\.?", text):
        return False
    text = re.sub(r"\bvf\s*(?:e\s*34|mpv\s*7|[3-9])\b", "", text)
    return not re.search(r"\d|%|\[|\b(?:nhung|tuy nhien|dam bao|chac chan|khong can|khong co)\b", text)
