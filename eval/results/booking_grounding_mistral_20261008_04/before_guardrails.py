"""Deterministic prerequisites for the current read/proposal tool contract."""
from __future__ import annotations

import ast
import json
import re
import unicodedata
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.modules.notification.domain import MAX_LEAD_DAYS, MIN_LEAD_DAYS

from .contracts import validate_arguments
from .reminder_intent import explicit_reminder_patch
from .tools.resolve_date import resolve_date


def payload(message: Any) -> dict[str, Any]:
    content = getattr(message, "content", message)
    if isinstance(content, dict):
        return content
    for parser in (json.loads, ast.literal_eval):
        try:
            value = parser(str(content))
            if isinstance(value, dict):
                return value
        except (ValueError, SyntaxError, TypeError):
            pass
    return {}


def latest_result(messages: list[Any], name: str) -> dict[str, Any] | None:
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == name:
            value = payload(message)
            if str(value.get("status", "")).upper() == "ERROR" or getattr(message, "status", "") == "error":
                return None
            return value
    return None


def reminder_change_claim(answer: str) -> bool:
    """Recognize asserted new settings changes, not descriptions of existing state."""
    folded = unicodedata.normalize("NFD", answer.casefold()).replace("đ", "d")
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    verbs = r"(?:cap nhat|luu|thay doi|bat|tat|kich hoat)"
    for clause in re.split(r"[.!?;\n]|\bnhung\b|\btuy nhien\b", folded):
        clause = re.sub(r"[*_`]+", "", clause).strip(" -:>")
        if re.match(r"(?:neu|khi|chua|khong)\b", clause):
            continue
        if re.search(r"^(?:(?:toi|minh|he thong)\s+)?da\s+" + verbs + r"\b", clause):
            return True
        if re.search(r"^(?:toi|minh)\s+" + verbs + r"\b.*\b(?:roi|xong|thanh cong)\b", clause):
            return True
        if re.search(r"^cai dat\b.*\bda\s+(?:duoc\s+)?(?:cap nhat|thay doi)\b", clause):
            return True
    return False


def reminder_update_answer(messages: list[Any], answer: str = "", *, reminder_context: bool = False) -> str | None:
    """Ground saved settings in this turn; a read cannot prove a new update."""
    tools = [message for message in messages if isinstance(message, ToolMessage)]
    names = {message.name for message in tools}
    reminder_tools = {"get_reminder_settings", "update_reminder_settings", "get_reminder_context"}
    result = latest_result(messages, "update_reminder_settings")
    saved = bool(result and str(result.get("status", "")).lower() == "ok")
    no_save = "Chưa có kết quả lưu cài đặt nhắc bảo dưỡng thành công trong lượt này."
    if saved:
        if names - {"get_reminder_settings", "update_reminder_settings"}:
            return None  # Preserve a combined request with a verified update.
    else:
        if not reminder_change_claim(answer) or not (names & reminder_tools or reminder_context):
            return None
        result = latest_result(messages, "get_reminder_settings")
        if not result or str(result.get("status", "")).lower() != "ok":
            return no_save
    data = result.get("data", {})
    if not isinstance(data, dict):
        return None if saved else no_save
    enabled, lead = data.get("remindersEnabled"), data.get("reminderLeadDays")
    channels = data.get("channels")
    email = next((channel for channel in channels if isinstance(channel, dict) and channel.get("channel") == "EMAIL"), None) if isinstance(channels, list) else None
    if not isinstance(enabled, bool) or type(lead) is not int or not email or not isinstance(email.get("enabled"), bool):
        return None if saved else no_save
    email_state = "Tắt"
    if email["enabled"]:
        email_state = "Đã bật trong cài đặt"
        if not enabled:
            email_state += "; chưa hoạt động vì nhắc bảo dưỡng đang tắt"
        elif not email.get("available") or not data.get("emailVerified") or data.get("emailSuppressed"):
            email_state += "; chưa đủ điều kiện gửi"
        elif data.get("emailTransport") == "off":
            email_state += "; dịch vụ gửi hiện đang tắt"
        elif data.get("emailTransport") == "mock":
            email_state += "; thư được mô phỏng trong ứng dụng"
    prefix = "Đã lưu cài đặt nhắc bảo dưỡng." if saved else "Chưa lưu thay đổi cài đặt nhắc bảo dưỡng trong lượt này. Cài đặt hiện tại:"
    footer = "Thao tác này chỉ cập nhật cài đặt, không gửi email." if saved else "Đọc cài đặt không thay đổi cấu hình và không gửi email."
    return (f"{prefix}\n"
            f"- Nhắc bảo dưỡng: {'Bật' if enabled else 'Tắt'}.\n"
            f"- Nhắc trước: {lead} ngày.\n"
            f"- Email: {email_state}.\n"
            f"{footer}")


def guarded_calls(response: Any, messages: list[Any], tools: list[Any]) -> Any:
    calls = list(getattr(response, "tool_calls", None) or [])
    registry = {tool.name: tool for tool in tools}
    # Legacy injected tools have a different contract and are exercised separately.
    modern = "get_due_maintenance" in registry and not registry["get_due_maintenance"].args
    if not modern:
        return response
    user_turns = [i for i, message in enumerate(messages) if isinstance(message, HumanMessage)]
    last_user = str(messages[user_turns[-1]].content).strip().casefold() if user_turns else ""
    lead_request = re.search(r"(?:nhắc|nhac)\s+trước\s+(-?\d+)\s*ngày|nhac\s+truoc\s+(-?\d+)\s*ngay", last_user)
    if lead_request:
        lead = int(next(value for value in lead_request.groups() if value is not None))
        if not MIN_LEAD_DAYS <= lead <= MAX_LEAD_DAYS:
            return response.model_copy(update={"content": f"Thời gian nhắc trước chỉ hợp lệ từ {MIN_LEAD_DAYS} đến {MAX_LEAD_DAYS} ngày. Chưa có cài đặt nào được thay đổi.", "tool_calls": [], "response_metadata": {**response.response_metadata, "rejected_tool_calls": calls, "invalid_reminder_lead_days": lead}})
    if last_user in {"ok", "đồng ý", "xác nhận", "tôi xác nhận", "có"} and len(user_turns) > 1:
        previous_turn = messages[user_turns[-2] + 1:user_turns[-1]]
        proposal = any(isinstance(getattr(message, "artifact", None), dict) and message.artifact.get("type") == "BOOKING_PROPOSAL" for message in previous_turn)
        if proposal or latest_result(previous_turn, "get_available_slots") is not None:
            answer = ('Lịch chưa được đặt. Bạn hãy bấm "Xác nhận đặt lịch" trên thẻ đề xuất để hoàn tất.' if proposal else
                      "Bạn hãy chọn rõ khung giờ muốn đặt trong danh sách đã tra. Tôi chưa tạo thẻ đề xuất hoặc đặt lịch từ câu xác nhận này.")
            return response.model_copy(update={"content": answer, "tool_calls": [], "response_metadata": {**response.response_metadata, "rejected_acknowledgement_response": str(response.content), "rejected_tool_calls": calls}})
    if not calls:
        if unconfirmed_booking_claim(str(response.content)):
            return AIMessage(content='Tôi chưa có kết quả xác nhận đặt lịch. Nếu đã có thẻ đề xuất, bạn hãy bấm "Xác nhận đặt lịch" và chờ hệ thống trả kết quả.', response_metadata={**response.response_metadata, "rejected_success_claim": str(response.content)})
        current_turn = messages[user_turns[-1] + 1:] if user_turns else messages
        read = latest_result(current_turn, "get_reminder_settings")
        data = read.get("data", {}) if read else {}
        verified_read = (
            read and str(read.get("status", "")).lower() == "ok" and isinstance(data, dict)
            and isinstance(data.get("remindersEnabled"), bool) and type(data.get("reminderLeadDays")) is int
            and isinstance(data.get("channels"), list)
            and any(isinstance(channel, dict) and channel.get("channel") == "EMAIL" and isinstance(channel.get("enabled"), bool) for channel in data["channels"])
        )
        patch = explicit_reminder_patch(last_user)
        attempted_update = any(isinstance(message, ToolMessage) and message.name == "update_reminder_settings" for message in current_turn)
        if patch and verified_read and not attempted_update and "update_reminder_settings" in registry:
            repaired = response.model_copy(update={
                "content": "",
                "tool_calls": [{"name": "update_reminder_settings", "args": patch, "id": f"reminder-request-{uuid4().hex}", "type": "tool_call"}],
                "response_metadata": {**response.response_metadata, "reminder_update_inserted_from_explicit_request": True, "original_reminder_answer_before_update": str(response.content)},
            })
            return guarded_calls(repaired, messages, tools)  # Reuse schema/authorization guards.
        reminder_context = bool(re.search(r"(?:email|nhắc|nhac|thông báo|thong bao)", last_user))
        reminder_answer = reminder_update_answer(current_turn, str(response.content), reminder_context=reminder_context)
        if reminder_answer:
            saved = latest_result(current_turn, "update_reminder_settings")
            rejected = reminder_change_claim(str(response.content)) and not (saved and str(saved.get("status", "")).lower() == "ok")
            return response.model_copy(update={"content": reminder_answer, "response_metadata": {**response.response_metadata, "reminder_answer_grounded_in_saved_settings": True, "unconfirmed_reminder_change_rejected": rejected, "original_reminder_answer": str(response.content)}})
        from .business_grounding import business_answer

        grounded = business_answer(current_turn)
        if grounded:
            return response.model_copy(update={"content": grounded, "response_metadata": {
                **response.response_metadata, "business_answer_grounded_in_tool_results": True,
                "original_business_answer": str(response.content),
            }})
        return response
    original = [{**call, "args": dict(call.get("args", {}))} for call in calls]
    from . import prompts
    date_hint = resolve_date(last_user, now=prompts.now_vn())
    normalized = []
    # Repair only equivalent representations backed by an unambiguous user date.
    # Keep the original request in metadata for raw argument scoring/review.
    for call in calls:
        args = dict(call.get("args", {}))
        if call["name"] in {"get_available_slots", "propose_booking"}:
            field = "target_date" if call["name"] == "get_available_slots" else "booking_date"
            ambiguous_text = bool(re.search(r"(?:hoặc|hay|không phải|chứ không|tuần sau|tuần tới)|\d{4}-\d{2}-\d{2}.*\d{4}-\d{2}-\d{2}", last_user))
            if date_hint and not date_hint.is_ambiguous and not ambiguous_text and args.get(field) != date_hint.target_date.isoformat():
                args[field] = date_hint.target_date.isoformat()
                normalized.append(field)
        if call["name"] == "propose_booking" and re.fullmatch(r"\d{2}:\d{2}:00", str(args.get("time_slot", ""))):
            args["time_slot"] = args["time_slot"][:5]
            normalized.append("time_slot")
        call["args"] = args
    response = response.model_copy(update={"tool_calls": calls, "response_metadata": {**response.response_metadata, "requested_tool_calls": original, "normalized_fields": normalized}})
    for call in calls:
        tool = registry.get(call["name"])
        errors = validate_arguments(tool, call.get("args", {})) if tool else ["Unknown tool"]
        if errors:
            return AIMessage(
                content="Thông tin gọi công cụ chưa hợp lệ. Chưa có thay đổi nào được thực hiện; vui lòng kiểm tra lại xưởng, ngày và giờ.",
                response_metadata={**response.response_metadata, "rejected_tool_calls": original, "argument_errors": errors},
            )
    names = {call["name"] for call in calls}
    if "update_reminder_settings" in names:
        requested = bool(re.search(r"(?:bật|tắt|bat|tat|đổi|doi|đặt|dat|nhắc trước|nhac truoc)", last_user)) and bool(re.search(r"(?:email|nhắc|nhac|thông báo|thong bao)", last_user))
        explanation_only = bool(re.search(r"(?:chỉ hỏi|chưa yêu cầu|chưa thay|không thay|đừng thay|tài liệu|có thể|có được)", last_user))
        if not requested or explanation_only:
            return AIMessage(content="Tôi chưa thay đổi cài đặt nhắc lịch. Bạn hãy nêu rõ cài đặt muốn bật, tắt hoặc đổi.", response_metadata={**response.response_metadata, "rejected_tool_calls": original})
    for call in calls:
        if call["name"] != "propose_booking":
            continue
        if last_user in {"ok", "đồng ý", "xác nhận", "tôi xác nhận", "có"} and any(isinstance(getattr(m, "artifact", None), dict) and m.artifact.get("type") == "BOOKING_PROPOSAL" for m in messages):
            return AIMessage(content='Lịch chưa được đặt. Bạn hãy bấm "Xác nhận đặt lịch" trên thẻ đề xuất để hoàn tất.', response_metadata=response.response_metadata)
        time_match = re.search(r"\b(\d{1,2})(?:[:h](\d{2})|h)\b", last_user)
        selection = f"{int(time_match.group(1)):02}:{int(time_match.group(2) or 0):02}" if time_match else None
        requested = bool(re.search(r"(?:đặt|dat|tạo|tao|chọn|chon|đề xuất|de xuat)", last_user))
        negated = bool(re.search(r"(?:chưa|không|đừng).{0,18}(?:đặt|tạo|giữ|đề xuất)", last_user))
        if selection != call.get("args", {}).get("time_slot") or not requested or negated:
            return AIMessage(content="Bạn hãy chọn rõ xưởng, ngày và giờ muốn đặt trước khi tôi tạo thẻ đề xuất. Chưa có lịch hẹn hoặc chỗ nào được đặt.", response_metadata={**response.response_metadata, "rejected_tool_calls": original})
    maintenance = latest_result(messages, "get_due_maintenance")
    booking_intent = "get_available_slots" in names and bool(re.search(r"\b(?:đặt|dat|booking)\b", last_user))
    if (names & {"estimate_service_cost", "propose_booking"} or booking_intent) and maintenance is None:
        replacement = [{"name": "get_due_maintenance", "args": {}, "id": f"prerequisite-{uuid4().hex}", "type": "tool_call"}]
        replacement.extend(call for call in calls if call["name"] not in {"get_due_maintenance", "estimate_service_cost", "propose_booking"})
        return response.model_copy(update={"tool_calls": replacement})
    for call in calls:
        if call["name"] != "propose_booking":
            continue
        args = call.get("args", {})
        # A proposal must use an exact slot from a successful availability response,
        # not a matching time from another day/workshop.
        matched = False
        for message in reversed(messages):
            if not isinstance(message, ToolMessage) or message.name != "get_available_slots":
                continue
            result = payload(message)
            if (str(result.get("workshop_id")) != str(args.get("workshop_id"))
                    or result.get("date") != args.get("booking_date")):
                continue
            matched = any(
                slot.get("available") is True
                and str(slot.get("time_slot", ""))[:5] == args.get("time_slot")
                for slot in result.get("slots", [])
            )
            break  # Newest result for this exact workshop/day is authoritative.
        if not matched:
            if date_hint and not date_hint.is_ambiguous and date_hint.target_time and date_hint.target_date.isoformat() == args.get("booking_date") and date_hint.target_time.strftime("%H:%M") == args.get("time_slot") and str(args.get("workshop_id", "")) in last_user:
                replacement = [{"name": "get_available_slots", "args": {"workshop_id": args["workshop_id"], "target_date": args["booking_date"]}, "id": f"availability-{uuid4().hex}", "type": "tool_call"}]
                return response.model_copy(update={"tool_calls": replacement})
            return AIMessage(content="Tôi cần kiểm tra lại đúng xưởng, ngày và giờ còn trống trước khi tạo thẻ đề xuất. Chưa có lịch hẹn hoặc chỗ nào được đặt.", response_metadata=response.response_metadata)
        if last_user in {"ok", "đồng ý", "xác nhận", "tôi xác nhận", "có"} and any(
            isinstance(getattr(m, "artifact", None), dict)
            and m.artifact.get("type") == "BOOKING_PROPOSAL" for m in messages
        ):
            return AIMessage(content='Lịch chưa được đặt. Bạn hãy bấm "Xác nhận đặt lịch" trên thẻ đề xuất để hoàn tất.')
    return response


def unconfirmed_booking_claim(answer: str) -> bool:
    patterns = [r"(?:đã|vừa)\s+(?:đặt\s+lịch|(?:tạm\s+)?giữ\s+chỗ|tạo\s+(?:booking|lịch\s+hẹn))", r"(?:lịch\s+hẹn|chỗ)\s+(?:đã\s+)?được\s+(?:đặt|giữ)", r"EVC-[A-Z0-9]{4,}"]
    for sentence in re.split(r"[.!?;\n]|\bnhưng\b|\btuy nhiên\b", answer, flags=re.I):
        if re.search(r"\b(?:chưa|không|sẽ|nếu|khi)\b", sentence, re.I):
            continue
        if any(re.search(pattern, sentence, re.I) for pattern in patterns):
            return True
    return False


def tool_failure(messages: list[Any]) -> str | None:
    """Terminate this turn on a tool error; never let a model invent a replacement."""
    current = []
    for message in reversed(messages):
        if not isinstance(message, ToolMessage):
            break
        current.append(message)
    for message in current:
        value = payload(message)
        if str(value.get("status", "")).upper() != "ERROR" and getattr(message, "status", "") != "error":
            continue
        if message.name == "estimate_service_cost":
            return "Hệ thống chưa tra được dự toán chi phí. Tôi chưa có giá đã xác minh để báo cho bạn; vui lòng thử lại sau."
        if message.name == "propose_booking":
            if value.get("error_code") == "SLOT_FULL":
                return "Khung giờ vừa hết chỗ. Chưa có lịch hẹn nào được tạo; bạn hãy chọn một khung giờ khác."
            return "Chưa tạo được thẻ đề xuất; chưa có lịch hẹn hoặc chỗ nào được đặt. Vui lòng kiểm tra lại thông tin và thử lại."
        return "Hệ thống chưa tra được thông tin đã xác minh. Chưa có kết quả thành công cho yêu cầu này; vui lòng thử lại sau."
    return None
