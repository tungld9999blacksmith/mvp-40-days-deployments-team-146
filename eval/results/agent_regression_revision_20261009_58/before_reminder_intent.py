"""Recognize a small set of explicit reminder-setting commands, never source text.

This is intentionally not general NLU. Unknown clauses, ambiguity and questions
return None so the model must clarify instead of the runtime inventing a write.
"""
from __future__ import annotations

import re
import unicodedata

from src.modules.notification.domain import MAX_LEAD_DAYS, MIN_LEAD_DAYS


def explicit_reminder_patch(user: str) -> dict | None:
    text = unicodedata.normalize("NFD", user.casefold()).replace("đ", "d")
    text = "".join(c for c in text if not unicodedata.combining(c)).strip().rstrip(".")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(?:toi muon|hay|vui long) ", "", text)
    text = re.sub(r" (?:cho toi|giup toi)$", "", text)
    clauses = re.split(r"\s+va\s+", text)
    patch = {}
    for clause in clauses:
        toggle = re.fullmatch(r"(bat|tat)(?: lai)? (.+)", clause)
        lead = re.fullmatch(r"(?:(?:doi|dat) )?(?:thoi gian )?(?:nhac )?truoc (-?\d+) ngay", clause)
        if toggle:
            enabled, subject = toggle.group(1) == "bat", toggle.group(2)
            if subject in {"email", "email nhac", "email nhac bao duong", "nhac qua email", "nhac bao duong qua email"}:
                changes = {"email_enabled": enabled}
                if enabled:
                    changes["reminders_enabled"] = True
            elif subject in {"nhac", "nhac bao duong", "moi nhac", "moi nhac bao duong", "tat ca nhac bao duong"}:
                changes = {"reminders_enabled": enabled}
            else:
                return None
        elif lead:
            value = int(lead.group(1))
            if not MIN_LEAD_DAYS <= value <= MAX_LEAD_DAYS:
                return None
            changes = {"reminder_lead_days": value}
        else:
            return None
        if any(key in patch and patch[key] != value for key, value in changes.items()):
            return None
        patch.update(changes)
    return patch or None
