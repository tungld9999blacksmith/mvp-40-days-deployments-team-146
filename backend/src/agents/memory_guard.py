"""Do not claim memory changes without a successful tool in the current turn."""

import json
import re

from langchain_core.messages import HumanMessage, ToolMessage

from src.modules.agent_memory.preferences import explicit_consent, normalized, validate_value
from src.modules.conversation.errors import InvalidRequest

_PREFERENCE_LABELS = {
    "preferred_service_window": "ngày/buổi bảo dưỡng",
    "preferred_workshop_id": "xưởng ưu tiên",
    "cost_display_preference": "định dạng chi phí",
}


def memory_change_request(content):
    return explicit_consent(content) or normalized(content).startswith(
        ("hay quen ", "quen ", "xoa so thich ", "dung nho ", "forget ", "please forget ")
    )


def preference_only_request(content):
    """An explicit request to only repeat a preference/choice, with no service action."""
    text = normalized(content)
    only = re.search(r"\bchi nhac\b.*\b(?:so thich|lua chon|dinh dang|ngay|buoi|muc tieu|uuid)\b", text)
    mixed = re.search(r"(?:^|[.;,]\s*|\b(?:va|roi|sau do|dong thoi)\s+)(?:hay\s+)?(?:tim|tra|dat|tao|du toan|kiem tra)\b", text)
    return bool(only and not mixed)


def memory_topic_request(content):
    return bool(re.search(r"\b(?:ghi nho|so thich|dinh dang chi phi|thich|uu tien)\b", normalized(content))) or bool(preference_recall_keys(content))


def preference_recall_keys(content):
    """Recognize preference recall; current choices and service requests stay with the graph."""
    if memory_change_request(content):
        return []
    text = normalized(content)
    if not re.search(r"\b(?:ghi nho|nho|so thich|uu tien|thich|preference|preferences|preferred|remember|remembered|saved|stored)\b", text):
        return []
    if re.search(r"\b(?:lan nay|lan truoc|lich su cuoc tro chuyen|bao nhieu|du toan|bao gia)\b", text):
        return []
    if re.search(r"(?:^|[.;,]\s*|\b(?:va|roi|sau do|dong thoi)\s+)(?:hay\s+)?(?:tim|tra|dat|tao|kiem tra)\b", text):
        return []
    recall = re.search(
        r"\b(?:(?:da|dang|con|co) ghi nho|ghi nho nao|da luu|da yeu cau ghi nho|"
        r"ban (?:con )?(?:co|biet|nho)|theo.{0,35}(?:ghi nho|so thich)|"
        r"toi thich.{0,40}(?:nao|gi)|toi.{0,20}uu tien.{0,30}(?:nao|gi))\b", text)
    english = re.search(r"\b(?:what|which|do you|have you)\b", text) and re.search(
        r"\b(?:remember|remembered|saved|stored|preference|preferred)\b", text)
    if not recall and not english:
        return []
    keys = []
    if re.search(r"\b(?:ngay|buoi|khung gio|gio bao duong|lich bao duong|day|period|service window|time window)\b", text):
        keys.append("preferred_service_window")
    if re.search(r"\b(?:xuong|workshop|uuid)\b", text):
        keys.append("preferred_workshop_id")
    if re.search(r"\b(?:chi phi|dinh dang gia|hien thi gia|cost|format)\b", text):
        keys.append("cost_display_preference")
    if not keys and re.search(r"\b(?:so thich|thong tin|uu tien|preferences)\b", text):
        keys = list(_PREFERENCE_LABELS)
    return keys


def current_preference_choice(response, messages):
    """Repeat an explicit one-time choice without executing a service or saving it."""
    if not messages or not isinstance(messages[-1], HumanMessage):
        return response
    content = str(messages[-1].content)
    text = normalized(content)
    if memory_change_request(content) or not preference_only_request(content) or "lan nay" not in text:
        return response
    if not re.search(r"\btoi\s+(?:(?:chi|muon)\s+)*(?:chon|thich|xem)\b", text):
        return response
    choice = content.split(".", 1)[0].strip()
    return response.model_copy(update={
        "content": f'Lựa chọn cho lần này bạn vừa nêu: “{choice}”. Chưa lưu thành sở thích dài hạn.',
        "response_metadata": {**response.response_metadata, "memory_current_choice_grounded": True},
    })


def verified_preference_recall(response, messages, preferences):
    """Ground a pure recall answer in the server's current, authorized projection.

    Historical messages, summary, model claims and schema examples cannot supply
    a missing key. No preference values are added to checkpoint metadata.
    """
    if getattr(response, "tool_calls", None):
        return response
    start = next((i for i in range(len(messages)-1, -1, -1) if isinstance(messages[i], HumanMessage)), None)
    if start is None:
        return response
    keys = preference_recall_keys(str(messages[start].content))
    if not keys or any(isinstance(m, ToolMessage) for m in messages[start+1:]):
        return response  # Actual tool/combined business results keep their existing guards.
    available = {}
    for item in preferences or []:
        if not isinstance(item, dict) or item.get("key") not in keys or item.get("scope") not in {"account", "vehicle"}:
            continue
        key = item["key"]
        try:
            value = validate_value(key, item.get("value"))
        except InvalidRequest:
            continue
        previous = available.get(key)
        if previous is None or (item.get("scope") == "vehicle" and previous[0] != "vehicle"):
            available[key] = (item.get("scope"), value)
    days = {"monday": "thứ Hai", "tuesday": "thứ Ba", "wednesday": "thứ Tư", "thursday": "thứ Năm",
            "friday": "thứ Sáu", "saturday": "thứ Bảy", "sunday": "Chủ nhật"}
    periods = {"morning": "sáng", "afternoon": "chiều", "evening": "buổi tối"}
    lines = []
    for key in keys:
        if key not in available:
            lines.append(f"Chưa có sở thích {_PREFERENCE_LABELS[key]} khả dụng trong thông tin ghi nhớ hiện tại.")
            continue
        value = available[key][1]
        if key == "preferred_service_window":
            description = f"{periods[value['period']]} {days[value['day']]}"
        elif key == "preferred_workshop_id":
            description = f"UUID {value['workshop_id']}"
        else:
            description = "từng hạng mục" if value["format"] == "itemized" else "tổng tiền"
        lines.append(f"Sở thích {_PREFERENCE_LABELS[key]} đã ghi nhớ: {description}.")
    return response.model_copy(update={"content": "\n".join(lines),
        "response_metadata": {**response.response_metadata, "memory_recall_grounded": True}})


def guard_memory_calls(response, content):
    calls = list(getattr(response, "tool_calls", None) or [])
    retained = [c for c in calls if c["name"] != "remember_preference" or explicit_consent(content)]
    if preference_only_request(content):
        retained = [c for c in retained if c["name"] in {"remember_preference", "forget_preference"}]
    if retained == calls:
        return response
    answer = response.content
    if not retained:
        choice = content.split(".", 1)[0].strip()
        answer = f'Lựa chọn bạn vừa nêu: “{choice}”. Chưa lưu sở thích dài hạn từ lựa chọn này.'
    return response.model_copy(update={"tool_calls": retained, "content": answer,
        "response_metadata": {**response.response_metadata, "memory_request_calls_rejected": len(calls)-len(retained)}})


def memory_save_claim(content):
    for clause in re.split(r"[.!?;\n]", normalized(str(content).replace("*", ""))):
        if re.match(r"\s*(?:(?:toi|minh|he thong)\s+)?da\s+(?:ghi nho|luu so thich)\b", clause):
            return True
    return False


def verified_memory_response(response, messages):
    if getattr(response, "tool_calls", None):
        return response
    start = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), None)
    if start is None:
        return response
    if not memory_change_request(str(messages[start].content)):
        if memory_save_claim(response.content):
            return response.model_copy(update={"content":
                "Mình chưa lưu sở thích dài hạn từ lựa chọn này. Nếu muốn lưu, bạn hãy yêu cầu ghi nhớ rõ ràng."})
        return response
    expected = "remember_preference" if explicit_consent(str(messages[start].content)) else "forget_preference"
    result = None
    for message in messages[start + 1 :]:
        if isinstance(message, ToolMessage) and message.name == expected:
            try:
                result = json.loads(message.content) if isinstance(message.content, str) else message.content
            except (ValueError, TypeError):
                result = None
    if not isinstance(result, dict) or result.get("status") != "ok":
        return response.model_copy(
            update={
                "content": "Mình chưa lưu được sở thích này. Bạn có thể kiểm tra mục Ghi nhớ và yêu cầu lưu lại rõ ràng."
                if expected == "remember_preference"
                else "Mình chưa xác nhận được việc xóa sở thích. Bạn có thể xóa trong mục Ghi nhớ."
            }
        )
    return response.model_copy(
        update={
            "content": "Mình đã ghi nhớ sở thích bạn yêu cầu. Bạn có thể xem, sửa hoặc xóa trong mục Ghi nhớ."
            if expected == "remember_preference"
            else "Mình đã xóa sở thích bạn yêu cầu khỏi thông tin đã ghi nhớ."
        }
    )
