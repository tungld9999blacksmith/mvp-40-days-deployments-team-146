"""Shared regex patterns for PII detection/redaction and injection heuristics.

Patterns target the Vietnamese EV-ownership domain (VIN, CCCD/national id,
phone, license plate, email). They are intentionally conservative: they aim
for high precision on this domain so the output guard does not over-redact
ordinary numbers such as odometer values or prices.
"""

from __future__ import annotations

import re

# --- PII -------------------------------------------------------------------

# VIN: 17 chars, A-H/J-N/P-Z and digits (no I, O, Q). Word-bounded.
VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")

# National id (CCCD): exactly 12 digits, not part of a longer number.
CCCD_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")

# Vietnamese phone: 0xxxxxxxxx (10 digits) or +84xxxxxxxxx.
PHONE_RE = re.compile(r"(?<![\w])(?:\+84|0)\d{9}(?![\d])")

# License plate: 2-digit province + 1 letter + optional dash + 4-5 digits,
# allowing a dot group e.g. 30A-766.78 or 30G-97834.
PLATE_RE = re.compile(r"\b\d{2}[A-Z]{1,2}-?\d{3}[.\d]{1,3}\b")

EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "vin": VIN_RE,
    "national_id": CCCD_RE,
    "phone": PHONE_RE,
    "plate": PLATE_RE,
    "email": EMAIL_RE,
}

# Redaction placeholders shown to the end user (Vietnamese, user-facing).
PII_PLACEHOLDER = {
    "vin": "[VIN đã ẩn]",
    "national_id": "[CCCD đã ẩn]",
    "phone": "[SĐT đã ẩn]",
    "plate": "[biển số đã ẩn]",
    "email": "[email đã ẩn]",
}

# --- Prompt-injection heuristics ------------------------------------------
# Lowercased substring/regex cues. These only *flag*; the policy layer decides.
INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"bỏ qua (mọi |các |những )?(hướng dẫn|chỉ dẫn|quy tắc|chỉ thị)",
        r"ignore (all |the |previous )?(instructions?|rules?|prompt)",
        r"(quên|disregard|forget) (mọi |all |the )?(hướng dẫn|instructions?|rules?)",
        r"system prompt",
        r"you are (now |)?(a |an |)?(dan|developer mode|không có luật|unrestricted)",
        r"đóng vai .*(không có|bỏ) (luật|quy tắc|giới hạn)",
        r"reveal|tiết lộ .*(prompt|system|hướng dẫn hệ thống)",
        r"act as (a |an |)?(jailbroken|unfiltered)",
    )
)

# Cues that the user is asking the agent to assert a *fixed* cost/number
# (which must stay labelled as an estimate).
COST_CERTAINTY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"giá (chắc chắn|cố định|chính xác|đúng là)",
        r"cam kết giá",
        r"guarantee.{0,10}price",
    )
)
