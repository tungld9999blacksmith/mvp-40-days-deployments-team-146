"""Narrow follow-up policy based on user intent, verified reads and API contracts."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from langchain_core.messages import HumanMessage, ToolMessage

from .booking_grounding import explicit_workshop_id
from .tools.resolve_date import ResolvedDate, resolve_date


def folded(value: str) -> str:
    value = unicodedata.normalize("NFC", value.casefold()).replace("hãy", "please")
    value = unicodedata.normalize("NFD", value).replace("đ", "d")
    return "".join(c for c in value if not unicodedata.combining(c))


def data(message: Any) -> dict | None:
    if not isinstance(message, ToolMessage) or message.status == "error":
        return None
    try:
        result = json.loads(message.content)
    except (TypeError, ValueError):
        return None
    return result if isinstance(result, dict) and str(result.get("status", "")).upper() != "ERROR" else None


def latest_read(messages: list[Any], name: str) -> dict | None:
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == name:
            return data(message)  # A newer failure invalidates an older success.
    return None


def uncertain_request(user: str) -> bool:
    text = folded(user)
    return bool(re.search(r"\b(?:neu|gia su|vi du|tai lieu|hoac|hay)\b|[\"`']", text))


def explicit_date(user: str, now: datetime) -> ResolvedDate | None:
    if uncertain_request(user):
        return None
    text = folded(user)
    if re.search(r"\b(?:khong phai|chu khong|tuan sau|tuan toi)\b", text):
        return None
    # Multiple explicit dates are choices, not permission to choose the first.
    if len(re.findall(r"\b(?:20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}/\d{1,2}(?:/20\d{2})?)\b", user)) > 1:
        return None
    if re.search(r"\bhom qua\b", text):
        return ResolvedDate(target_date=now.date() - timedelta(days=1), raw_text=user)
    # Preserve the existing resolver for formatting and relative dates.
    translated = text.replace("ngay mai", "ngày mai").replace("hom nay", "hôm nay").replace("ngay kia", "ngày kia")
    translated = translated.replace("thu bay", "thứ bảy").replace("chu nhat", "chủ nhật")
    translated = re.sub(r"\bchieu\b", "chiều", translated)
    translated = re.sub(r"\bsang\b", "sáng", translated)
    result = resolve_date(user, now=now) or resolve_date(translated, now=now)
    return result if result and not result.is_ambiguous else None


def previous_slots(messages: list[Any]) -> dict | None:
    """Newest historical result only; never read a slot from model prose/RAG."""
    result = latest_read(messages, "get_available_slots")
    if not result or not isinstance(result.get("slots"), list):
        return None
    try:
        UUID(str(result["workshop_id"]))
        datetime.fromisoformat(result["date"])
    except (ValueError, TypeError, KeyError):
        return None
    return result


def inherited_read_selection(history: list[Any], now: datetime) -> ResolvedDate | None:
    """Carry a user's verified day across a workshop switch, not model-selected dates."""
    slots = previous_slots(history)
    if not slots:
        return None
    users = [i for i, m in enumerate(history) if isinstance(m, HumanMessage)]
    for offset in reversed(users):
        text = str(history[offset].content)
        if re.search(r"\b(?:khong dat|dung dat|ngay khac)\b", folded(text)):
            return None
        resolved = explicit_date(text, now)
        if resolved:
            day = resolved.target_date.isoformat()
            return resolved if day == slots["date"] else None
    return None


def inherited_read_date(history: list[Any], now: datetime) -> str | None:
    selection = inherited_read_selection(history, now)
    return selection.target_date.isoformat() if selection else None


def mentions_day(user: str) -> bool:
    return bool(re.search(r"\b(?:ngay|hom|mai|mot|thu|chu nhat|tuan)\b|\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}\b|\b\d{1,2}/\d{1,2}\b", folded(user)))


def slot_request(user: str) -> bool:
    text = folded(user)
    return not uncertain_request(user) and not re.search(r"\b(?:khong|dung|chua)\s+(?:tim|tra|xem|kiem tra)\b", text) and bool(
        re.search(r"\b(?:tim|tra|xem|kiem tra)\b.*\b(?:lich|gio trong|khung gio|slot)\b", text)
    )


def reference_price_request(user: str) -> bool:
    text = folded(user)
    return not uncertain_request(user) and not re.search(r"\b(?:khong|dung|chua)\s+(?:tra|xem|hoi)\b", text) and bool(
        "gia tham khao" in text and re.search(r"\b(?:hoi lai|tra|xem|du toan|bao nhieu)\b", text)
    ) and explicit_workshop_id(user) is None


def verified_price_workshop(messages: list[Any]) -> str | None:
    estimate = latest_read(messages, "estimate_service_cost")
    if not estimate or estimate.get("status") != "READY" or not isinstance(estimate.get("workshop"), dict):
        return None
    try:
        return str(UUID(str(estimate["workshop"]["workshop_id"])))
    except (ValueError, TypeError, KeyError):
        return None


def guarded_booking_turn(messages: list[Any]) -> bool:
    """Used before streaming so a replaced model answer cannot leak first."""
    users = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if not users:
        return False
    text = folded(str(messages[users[-1]].content))
    if invalid_booking_time(str(messages[users[-1]].content)):
        return True
    if re.search(r"\b(?:lich|de xuat|xac nhan|slot|gia tham khao)\b", text):
        return True
    return previous_slots(messages[:users[-1]]) is not None and bool(re.search(r"\b(?:gio|chon|hom qua|ngay khac|xuong)\b", text))


def invalid_booking_time(user: str) -> str | None:
    """Explain a single invalid selected hour without executing any model call."""
    text = folded(user)
    if uncertain_request(user) or not re.search(r"\b(?:chon|dat|de xuat|tao the)\b", text):
        return None
    if re.search(r"\b(?:khong|dung|chua)\b.{0,18}\b(?:chon|dat|de xuat|tao)\b", text):
        return None
    matches = list(re.finditer(r"\b(\d{1,2})(?:[:h](\d{2})|h)\b", text))
    if len(matches) != 1:
        return None
    hour, minute = int(matches[0][1]), int(matches[0][2] or 0)
    if hour < 24 and minute < 60:
        return None
    return (f"Giờ {hour:02d}:{minute:02d} không hợp lệ; giờ phải từ 00 đến 23 và phút từ 00 đến 59. "
            "Bạn hãy chọn lại giờ hợp lệ để tôi kiểm tra lịch. Chưa tạo thẻ, đặt lịch hoặc giữ chỗ.")


def proposal_creation_request(user: str) -> bool:
    """Creating a proposal is distinct from confirming a booking or asking about it."""
    if uncertain_request(user):
        return False
    text = folded(user)
    if re.search(r"\b(?:khong|dung|chua)\b.{0,18}\b(?:tao|lap|gui)\b.{0,18}\b(?:the|proposal)\b", text):
        return False
    return bool(re.search(r"\b(?:tao|lap|gui)\b.{0,18}\b(?:the(?: de xuat)?|proposal)\b", text))


def followup_answer(user: str, history: list[Any], current: list[Any], now: datetime) -> str | None:
    """Small contract explanations; mixed requests remain with the normal graph."""
    if uncertain_request(user):
        return None
    invalid_time = invalid_booking_time(user)
    if invalid_time:
        return invalid_time
    text = folded(user)
    slots = previous_slots(history)
    if re.search(r"\b(?:huy lich|huy booking|doi lich hen)\b", text):
        return "Agent hiện chưa có công cụ hủy hoặc thay đổi lịch hẹn đã tạo. Bạn hãy thực hiện thao tác này trong phần quản lý lịch hẹn; tôi chưa hủy hoặc đổi lịch nào."
    if proposal_creation_request(user) or re.search(r"\b(?:va|dong thoi)\b", text):
        return None
    if re.search(r"\bxac nhan\b.*\b(?:hai|2) lan\b", text):
        return ('Xác nhận lại cùng một thẻ không tạo lịch trùng: backend trả lại kết quả đã ghi cho proposal đó. '
                'Bạn hãy xem trạng thái lịch hẹn được hệ thống trả về; tôi không hủy hay đổi lịch qua chat.')
    if re.search(r"\b(?:the de xuat|the.*de xuat)\b", text) and re.search(r"\b(?:giu cho|da dat|dat lich)\b", text):
        return ('Thẻ đề xuất chưa đặt lịch và chưa giữ chỗ. Chủ xe cần bấm "Xác nhận đặt lịch" trên thẻ. '
                'Sau đó backend kiểm tra lại chỗ trống và trả trạng thái: xưởng AUTO có thể xác nhận ngay; xưởng MANUAL cần chờ xưởng xác nhận. Hãy xem trạng thái thực tế trong kết quả.')
    if slots and re.search(r"\bngay khac\b", text) and explicit_date(user, now) is None:
        return "Bạn muốn chuyển sang ngày nào? Tôi cần ngày cụ thể để tra lại lịch; chưa giữ chỗ hay tạo thẻ cho ngày khác."
    resolved = explicit_date(user, now)
    if slots and resolved and resolved.target_date < now.date() and re.search(r"\b(?:chon|dat|de xuat)\b", text):
        return "Không thể đặt lịch cho ngày đã qua. Bạn hãy chọn ngày và giờ trong tương lai để tôi kiểm tra lại; chưa có lịch hẹn hoặc chỗ nào được đặt."
    if current:
        return None  # Slot/proposal/business renderers own actual tool responses.
    if slots and (re.search(r"\bchua chon gio\b", text) or text.strip(" .!") in {"dat lich do", "chon gio nao"}):
        times = []
        selection = inherited_read_selection(history, now)
        bounds = {"morning": (6, 12), "afternoon": (12, 18), "evening": (18, 24)}.get(selection.session if selection else None)
        for slot in slots["slots"]:
            if not isinstance(slot, dict) or slot.get("available") is not True or type(slot.get("remaining")) is not int or slot["remaining"] <= 0:
                continue
            value = str(slot.get("time_slot", ""))
            if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d(?::00)?", value):
                if bounds is None or bounds[0] <= int(value[:2]) < bounds[1]:
                    times.append(value[:5])
        if not times:
            return "Danh sách đã tra không có khung giờ khả dụng để chọn. Bạn muốn tra ngày hoặc xưởng khác?"
        examples = ", ".join(times[:3])
        day = datetime.fromisoformat(slots["date"]).strftime("%d/%m/%Y")
        return f'Bạn hãy chọn rõ một giờ trong danh sách ngày {day}, ví dụ {examples}. Tôi chưa tạo thẻ hoặc đặt lịch; sau khi có thẻ, bạn cần bấm "Xác nhận đặt lịch".'
    return None


def missing_read_plan(user: str, messages: list[Any], current: list[Any], now: datetime) -> tuple[list[dict], str] | None:
    """Finish an explicit, single-day read request when the model supplies no tools."""
    if reference_price_request(user):
        if any(isinstance(m, ToolMessage) and m.name == "estimate_service_cost" for m in current):
            return None
        due = latest_read(messages, "get_due_maintenance")
        if due is None:
            if any(isinstance(m, ToolMessage) and m.name == "get_due_maintenance" for m in current):
                return None
            return [{"name": "get_due_maintenance", "args": {}}], "reference_price_prerequisite"
        next_due = due.get("next_milestone")
        milestone = next_due.get("odo_milestone_km") if isinstance(next_due, dict) else None
        if type(milestone) is int and milestone > 0:
            args = {"odo_milestone": milestone}
            workshop = verified_price_workshop(messages)
            if workshop:
                args["workshop_id"] = workshop
            return [{"name": "estimate_service_cost", "args": args}], "reference_price_estimate"
        return None
    resolved = explicit_date(user, now)
    if resolved is None and not mentions_day(user) and explicit_workshop_id(user) and slot_request(user):
        day = inherited_read_date(messages, now)
        if day:
            resolved = ResolvedDate(target_date=datetime.fromisoformat(day).date(), raw_text=user)
    if not slot_request(user) or not resolved or resolved.target_date < now.date():
        return None
    if any(isinstance(m, ToolMessage) and m.name == "get_available_slots" for m in current):
        return None
    if re.search(r"\b(?:hai|ba|2|3|nhieu|so sanh)\b.*\bxuong\b", folded(user)):
        return None  # Multi-choice reads need the model's explicit plan.
    if "bao duong" in folded(user) and latest_read(messages, "get_due_maintenance") is None:
        if any(isinstance(m, ToolMessage) and m.name == "get_due_maintenance" for m in current):
            return None
        return [{"name": "get_due_maintenance", "args": {}}], "booking_read_prerequisite"
    identity = explicit_workshop_id(user)
    if identity is None:
        found = latest_read(current, "find_workshops")
        if found is None:
            if any(isinstance(m, ToolMessage) and m.name == "find_workshops" for m in current):
                return None
            area = re.search(r"\bgần\s+([^,.;!?]+)", user, re.I)
            query = area.group(1).strip() if area else None
            if query and folded(query) in {"toi", "nha toi", "day"}:
                query = None
            args = {"limit": 1}
            if query:
                args["area_or_address"] = query
            return [{"name": "find_workshops", "args": args}], "booking_workshop_read"
        entries = found.get("workshops", [])
        if not isinstance(entries, list) or len(entries) != 1:
            return None  # Do not turn multiple returned workshops into a choice.
        try:
            identity = str(UUID(str(entries[0]["workshop_id"])))
        except (ValueError, TypeError, KeyError):
            return None
    return [{"name": "get_available_slots", "args": {"workshop_id": identity, "target_date": resolved.target_date.isoformat()}}], "booking_slot_read"


def empty_rag_answer(current: list[Any]) -> str | None:
    results = [m for m in current if isinstance(m, ToolMessage)]
    if not results or any(m.name not in {"search_ev_knowledge", "get_maintenance_schedule_rag", "get_warranty_policy_rag"} for m in results):
        return None
    artifacts = [m.artifact for m in results]
    if all(isinstance(a, dict) and a.get("type") == "RAG_EVIDENCE" and a.get("fallback_required") is True and not a.get("citations") for a in artifacts):
        return "Chưa có tài liệu phù hợp để xác minh thông tin này. Bạn hãy bổ sung dòng xe hoặc hạng mục cần hỏi; tôi chưa có nguồn để đưa ra kết luận hay thông tin liên hệ."
    return None
