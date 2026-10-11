"""Output guard: inspect and sanitize the model answer before the client sees it.

Checks (see testing-strategy spec #5):

1. PII redaction  -- never leak VIN / national id / phone / plate / email.
2. No-source-no-claim -- a technical/warranty claim must carry a citation.
3. Cost labelling -- any money figure must be marked as an estimate unless it
   comes from an approved quote.

`apply_output_guard` returns the sanitized text plus a report. The orchestrator
decides enforcement: PII is always redacted; the other two are surfaced as
flags (warn in MVP, hard-gate in CI per spec #11).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .patterns import PII_PATTERNS, PII_PLACEHOLDER

# Money figures: "1.200.000đ", "250 000 VND", "1,2 triệu", "150k".
_MONEY_RE = re.compile(
    r"\b\d[\d.,]*\s*(?:đ|vnđ|vnd|k|nghìn|ngàn|triệu)\b",
    re.IGNORECASE,
)

# Keywords that satisfy the estimate-labelling requirement.
_ESTIMATE_KEYWORDS = (
    "ước tính",
    "dự kiến",
    "tham khảo",
    "khoảng",
    "tạm tính",
)

# Lexical cues that a sentence makes a technical/warranty assertion that needs
# a source. Kept small and high-precision for MVP.
_TECHNICAL_CUES = (
    "bảo hành",
    "mốc",
    "định kỳ",
    "km",
    "pin",
    "phanh",
    "dung dịch",
    "cần thay",
    "quy định",
    "chính sách",
)

# Hedging cues that mean the model is *not* asserting (so no citation needed).
_HEDGE_CUES = (
    "chưa có dữ liệu",
    "không tìm thấy",
    "vui lòng liên hệ",
    "mình chưa chắc",
    "không rõ",
)


@dataclass
class OutputGuardReport:
    pii_redacted: dict[str, int] = field(default_factory=dict)
    missing_citation: bool = False
    unlabelled_cost: bool = False

    @property
    def is_clean(self) -> bool:
        return not (self.pii_redacted or self.missing_citation or self.unlabelled_cost)


def _redact_pii(text: str) -> tuple[str, dict[str, int]]:
    redacted: dict[str, int] = {}
    out = text
    for name, pattern in PII_PATTERNS.items():
        matches = pattern.findall(out)
        if matches:
            redacted[name] = len(matches)
            out = pattern.sub(PII_PLACEHOLDER[name], out)
    return out, redacted


def _makes_technical_claim(text: str) -> bool:
    low = text.casefold()
    if any(h in low for h in _HEDGE_CUES):
        return False
    return any(cue in low for cue in _TECHNICAL_CUES)


def _has_unlabelled_cost(text: str) -> bool:
    if not _MONEY_RE.search(text):
        return False
    low = text.casefold()
    return not any(k in low for k in _ESTIMATE_KEYWORDS)


def inspect_output(
    text: str,
    *,
    citations: list | None = None,
    cost_from_approved_quote: bool = False,
) -> OutputGuardReport:
    """Inspect (without mutating) the answer; redaction count is still reported."""
    _, redacted = _redact_pii(text)
    missing_citation = _makes_technical_claim(text) and not (citations or [])
    unlabelled_cost = (not cost_from_approved_quote) and _has_unlabelled_cost(text)
    return OutputGuardReport(
        pii_redacted=redacted,
        missing_citation=missing_citation,
        unlabelled_cost=unlabelled_cost,
    )


def apply_output_guard(
    text: str,
    *,
    citations: list | None = None,
    cost_from_approved_quote: bool = False,
) -> tuple[str, OutputGuardReport]:
    """Return (sanitized_text, report). PII is always redacted in the text."""
    safe_text, redacted = _redact_pii(text)
    missing_citation = _makes_technical_claim(text) and not (citations or [])
    unlabelled_cost = (not cost_from_approved_quote) and _has_unlabelled_cost(text)
    report = OutputGuardReport(
        pii_redacted=redacted,
        missing_citation=missing_citation,
        unlabelled_cost=unlabelled_cost,
    )
    return safe_text, report
