"""Follow-up — pure rules: send time, feedback classification, ticket priority (us-041).

No DB, no LLM: the LLM classifier (AI-007) is optional and plugs in through
``ports.FeedbackClassifier``; these rules are the always-available fallback.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

TZ_VN = ZoneInfo("Asia/Ho_Chi_Minh")
ISSUE_SUMMARY_MAX = 500
LOW_CONFIDENCE = Decimal("0.70")


class FeedbackIntent(StrEnum):
    SATISFIED = "SATISFIED"
    ISSUE_REPORTED = "ISSUE_REPORTED"
    COMPLAINT_SERVICE = "COMPLAINT_SERVICE"
    UNCLEAR = "UNCLEAR"


class ClassifiedBy(StrEnum):
    RULES = "RULES"
    LLM = "LLM"
    LLM_FALLBACK = "LLM_FALLBACK"


@dataclass(frozen=True)
class Classification:
    intent: FeedbackIntent
    has_issue: bool
    safety: bool
    classified_by: ClassifiedBy
    confidence: Decimal | None = None
    summary: str | None = None


# us-041 API §4.3 keyword groups, case-insensitive, on word boundaries.
SAFETY_KEYWORDS = ("phanh", "pin", "khói", "cháy", "mùi khét", "mất lái", "đèn đỏ", "rò rỉ", "cảnh báo")
TECHNICAL_KEYWORDS = ("lỗi", "kêu", "tiếng lạ", "rung", "đèn báo", "không chạy", "sai")
SERVICE_KEYWORDS = ("lâu", "chờ", "đắt", "tính tiền", "thái độ", "bẩn", "không sạch")


def fold(text: str) -> str:
    """Lower-case and strip Vietnamese diacritics (``đ`` → ``d``)."""
    text = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _has_any(comment: str, keywords: tuple[str, ...]) -> bool:
    """Match with diacritics when the owner typed them ("chạy" is not "cháy");
    fall back to diacritic-free matching for text typed without them."""
    text = unicodedata.normalize("NFC", comment.lower())
    if fold(text) == text:  # typed without diacritics
        keywords = tuple(fold(k) for k in keywords)
    return any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", text) for k in keywords)


def classify_by_rules(rating: int, comment: str | None, *, by: ClassifiedBy) -> Classification:
    """BR-906 / BR-908 keyword + rating fallback."""
    text = comment or ""
    if _has_any(text, SAFETY_KEYWORDS):
        return Classification(FeedbackIntent.ISSUE_REPORTED, True, True, by)
    if _has_any(text, TECHNICAL_KEYWORDS):
        return Classification(FeedbackIntent.ISSUE_REPORTED, True, False, by)
    if _has_any(text, SERVICE_KEYWORDS):
        return Classification(FeedbackIntent.COMPLAINT_SERVICE, True, False, by)
    has_issue = rating <= 2 or (rating == 3 and bool(comment))
    intent = FeedbackIntent.UNCLEAR if has_issue else FeedbackIntent.SATISFIED
    return Classification(intent, has_issue, False, by)


def apply_policy(result: Classification, rating: int) -> Classification:
    """BR-906 on top of an LLM answer: ≤ 2 stars or low confidence ⇒ an issue."""
    low = result.confidence is not None and result.confidence < LOW_CONFIDENCE
    if (rating <= 2 or low) and not result.has_issue:
        return Classification(
            result.intent, True, result.safety, result.classified_by, result.confidence, result.summary
        )
    return result


def issue_summary(result: Classification, rating: int, comment: str | None) -> str:
    """AI summary when present, else the owner's own words, else a neutral line."""
    if result.summary:
        return result.summary[:ISSUE_SUMMARY_MAX]
    if comment:
        return comment[:ISSUE_SUMMARY_MAX]
    return f"Khách chấm {rating}/5, không để lại nhận xét."


def quiet_hours_adjust(t: datetime, *, quiet_start: int, quiet_end: int) -> datetime:
    """BR-ENT-503 — never send between ``quiet_start``:00 and ``quiet_end``:00 (VN time)."""
    local = t.astimezone(TZ_VN)
    if local.time() >= time(quiet_start):
        return datetime.combine(local.date() + timedelta(days=1), time(quiet_end), tzinfo=TZ_VN)
    if local.time() < time(quiet_end):
        return datetime.combine(local.date(), time(quiet_end), tzinfo=TZ_VN)
    return t
