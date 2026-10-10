"""Booking reads/proposals: bind explicit read IDs and render verified facts."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, time
from typing import Any
from uuid import UUID

from langchain_core.messages import ToolMessage

from .business_grounding import BUSINESS_TOOLS, business_answer

_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_TOOLS = BUSINESS_TOOLS | {"find_workshops", "get_available_slots", "propose_booking"}


def explicit_workshop_id(user: str) -> str | None:
    """Only the current user's single, directly named workshop can bind a read.

    No fuzzy matching, history IDs, tool documents, negated or conditional IDs.
    Proposal/write arguments are deliberately outside this repair.
    """
    imperative = unicodedata.normalize("NFC", user.casefold()).replace("hãy", "please")
    folded = unicodedata.normalize("NFD", imperative).replace("đ", "d")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    if re.search(r"\b(?:neu|gia su|vi du|tai lieu|hoac|hay|dung)\b|\bkhong\b.{0,40}\b(?:xuong|tra|xem|tim)\b|\bchua\b.{0,40}\b(?:tra|xem|tim)\b", folded) or any(mark in folded for mark in ('"', "'", "`")):
        return None
    ids = re.findall(r"(?<![0-9a-f-])" + _UUID + r"(?![0-9a-f-])", folded)
    direct = re.findall(r"\b(?:xuong|workshop)(?:\s+(?:id|ma))?\s*[:#]?\s*(" + _UUID + r")(?![0-9a-f-])", folded)
    if len(ids) != 1 or direct != ids:
        return None
    return str(UUID(ids[0]))


def _data(message: ToolMessage) -> dict:
    value = json.loads(message.content)
    if not isinstance(value, dict) or value.get("status") == "ERROR" or message.status == "error":
        raise ValueError("Failed booking tool")
    return value


def selected_named_workshop_id(user: str, current: list[Any]) -> str | None:
    """Bind a named choice only to the newest successful workshop lookup this turn."""
    def normalize(value: str) -> str:
        return " ".join(unicodedata.normalize("NFC", value).casefold().split())

    user = normalize(user)
    choice = re.match(r"^(?:tôi chọn xưởng|toi chon xuong)\s+(.+)$", user)
    if choice is None:
        return None
    lookup = next((m for m in reversed(current) if isinstance(m, ToolMessage) and m.name == "find_workshops"), None)
    if lookup is None:
        return None
    try:
        entries = _data(lookup).get("workshops")
        if not isinstance(entries, list):
            return None
        matches = []
        for entry in entries:
            name = entry.get("name") if isinstance(entry, dict) else None
            if not isinstance(name, str) or not name.strip():
                continue
            if re.match(re.escape(normalize(name)) + r"(?:\s*[,.;]|$)", choice.group(1)):
                matches.append(str(UUID(str(entry["workshop_id"]))))
        return matches[0] if len(matches) == 1 else None
    except (ValueError, TypeError, KeyError):
        return None


def _clock(value: Any) -> str:
    parsed = time.fromisoformat(str(value))
    if parsed.tzinfo or parsed.second or parsed.microsecond:
        raise ValueError("Invalid local slot")
    return parsed.strftime("%H:%M")


def _slots(data: dict, session: str | None = None) -> str:
    workshop = str(UUID(str(data["workshop_id"])))
    day = date.fromisoformat(data["date"]).strftime("%d/%m/%Y")
    slots = data["slots"]
    if not isinstance(slots, list):
        raise ValueError("Invalid slots")
    available, unavailable, seen = [], [], set()
    bounds = {"morning": (6, 12, "sáng (06:00–11:59)"), "afternoon": (12, 18, "chiều (12:00–17:59)"), "evening": (18, 24, "tối (18:00–23:59)")}.get(session)
    for slot in slots:
        if not isinstance(slot, dict) or not isinstance(slot.get("available"), bool):
            raise ValueError("Invalid availability")
        at = _clock(slot["time_slot"])
        remaining = slot.get("remaining")
        if type(remaining) is not int or remaining < 0 or at in seen or (slot["available"] and not remaining):
            raise ValueError("Invalid capacity or duplicate slot")
        seen.add(at)
        if bounds and not bounds[0] <= int(at[:2]) < bounds[1]:
            continue
        if slot["available"]:
            available.append(f"- {at}: còn {remaining} chỗ.")
        else:
            unavailable.append(at)
    scope = " trong buổi " + bounds[2] if bounds else ""
    lines = [f"Ngày {day}, xưởng {workshop} có {len(available)} khung giờ khả dụng{scope}."]
    lines.extend(available)
    if unavailable:
        lines.append("Khung giờ không khả dụng: " + ", ".join(unavailable) + ".")
    if not slots:
        lines.append("Không có khung giờ trong dữ liệu lịch ngày này.")
    if available:
        lines.append("Bạn hãy chọn rõ một khung giờ. Lịch chưa được đặt hoặc giữ chỗ.")
    return "\n".join(lines)


def _proposal(message: ToolMessage, data: dict) -> str:
    card = message.artifact
    if data.get("status") != "PROPOSED" or not isinstance(card, dict) or card.get("type") != "BOOKING_PROPOSAL":
        raise ValueError("No verified proposal card")
    if UUID(str(data["proposal_id"])) != UUID(str(card["proposalId"])):
        raise ValueError("Proposal/card mismatch")
    primary = card["primary"]
    UUID(str(primary["workshopId"]))
    name = primary["workshopName"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Missing workshop name")
    day = date.fromisoformat(primary["date"]).strftime("%d/%m/%Y")
    at = _clock(primary["timeSlot"])
    return (f"Đã tạo thẻ đề xuất tại {name}, ngày {day}, lúc {at}.\n"
            'Lịch chưa được đặt và chưa giữ chỗ. Bạn hãy bấm "Xác nhận đặt lịch" trên thẻ để hoàn tất.')


def booking_answer(messages: list[Any], *, session: str | None = None) -> str | None:
    """Current-turn only; render one day, including separately verified workshops."""
    results = [m for m in messages if isinstance(m, ToolMessage)]
    names = {m.name for m in results}
    if names - _TOOLS or not names & {"get_available_slots", "propose_booking"}:
        return None
    try:
        if "propose_booking" in names:
            latest = next(m for m in reversed(results) if m.name == "propose_booking")
            return _proposal(latest, _data(latest))
        slot_results = [_data(m) for m in results if m.name == "get_available_slots"]
        if len({r.get("date") for r in slot_results}) != 1:
            return None  # Different-day comparisons still need a separate renderer.
        # Repeated reads use the newest result per workshop; never merge capacity
        # or apply one workshop's availability to another.
        latest_slots = {}
        for result in slot_results:
            latest_slots[str(UUID(str(result["workshop_id"])))] = result
        sections = []
        business = business_answer([m for m in results if m.name in BUSINESS_TOOLS])
        if business:
            sections.append(business)
        workshops = next((m for m in reversed(results) if m.name == "find_workshops"), None)
        if workshops:
            entries = _data(workshops)["workshops"]
            if not isinstance(entries, list):
                raise ValueError("Invalid workshop list")
            labels = []
            for entry in entries:
                identity = str(UUID(str(entry["workshop_id"])))
                if not isinstance(entry.get("name"), str):
                    raise ValueError("Invalid workshop name")
                labels.append(f"- {entry['name']}: {identity}.")
            if labels:
                sections.append("Xưởng đã tìm được:\n" + "\n".join(labels))
        sections.extend(_slots(result, session) for result in latest_slots.values())
        return "\n\n".join(sections)
    except (ValueError, TypeError, KeyError, StopIteration):
        return "Chưa có dữ liệu lịch hoặc thẻ đề xuất hợp lệ để xác nhận. Lịch chưa được đặt hoặc giữ chỗ; vui lòng tra lại."
