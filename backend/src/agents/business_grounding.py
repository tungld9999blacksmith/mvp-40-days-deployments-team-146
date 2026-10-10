"""Render business facts from current-turn tool results, without another LLM call."""

from __future__ import annotations

import json
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.messages import ToolMessage

BUSINESS_TOOLS = frozenset({"get_due_maintenance", "estimate_service_cost"})


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError("Missing numeric field")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid numeric field") from exc
    if not result.is_finite():
        raise ValueError("Non-finite numeric field")
    return result


def _format(value: Decimal) -> str:
    return format(value, ",f").rstrip("0").rstrip(".") if value.as_tuple().exponent < 0 else format(value, ",f")


def _date(value: Any) -> str:
    return date.fromisoformat(str(value)).strftime("%d/%m/%Y")


def _maintenance(data: dict[str, Any]) -> str:
    status = data.get("due_status")
    if status == "UNKNOWN":
        return "Chưa đủ dữ liệu để xác định hạn bảo dưỡng; không thể kết luận xe đã đến hạn hoặc quá hạn."
    labels = {"NORMAL": "Xe chưa đến hạn bảo dưỡng", "DUE_SOON": "Xe sắp đến hạn bảo dưỡng", "OVERDUE": "Xe đã quá hạn bảo dưỡng"}
    if status not in labels:
        raise ValueError("Invalid maintenance status")
    reasons = {"KM": "theo số km", "TIME": "theo thời gian", "BOTH": "theo cả số km và thời gian"}
    reason = data.get("due_reason")
    if reason not in {None, *reasons} or (status != "NORMAL" and reason is None):
        raise ValueError("Invalid maintenance reason")
    lines = [labels[status] + (f" {reasons[reason]}." if reason else ".")]
    for field, unit in (("remaining_km", "km"), ("remaining_days", "ngày")):
        value = data.get(field)
        if value is None:
            continue
        number = _number(value)
        if number < 0:
            lines.append(f"- Theo {unit}: quá hạn {_format(-number)} {unit}.")
        elif number > 0:
            lines.append(f"- Theo {unit}: còn {_format(number)} {unit} đến hạn.")
        else:
            lines.append(f"- Theo {unit}: đã đến hạn (còn 0 {unit}).")
    milestone = data.get("next_milestone")
    if not isinstance(milestone, dict):
        raise ValueError("Missing milestone")
    km, months = milestone.get("odo_milestone_km"), milestone.get("month_milestone")
    milestones = []
    if km is not None:
        milestones.append(f"{_format(_number(km))} km")
    if months is not None:
        milestones.append(f"{_format(_number(months))} tháng")
    if milestones:
        lines.append("- Mốc bảo dưỡng: " + " / ".join(milestones) + ".")
    if milestone.get("due_date"):
        lines.append(f"- Hạn theo thời gian: {_date(milestone['due_date'])}.")
    odometer = data.get("odometer")
    if isinstance(odometer, dict) and odometer.get("odo_km") is not None:
        lines.append(f"- ODO ghi nhận: {_format(_number(odometer['odo_km']))} km."
                     + (" Dữ liệu ODO đã cũ; cần cập nhật." if odometer.get("is_stale") is True else ""))
    service = data.get("last_service")
    if isinstance(service, dict) and service.get("date"):
        if service.get("type") == "PURCHASE_DATE":
            lines.append(f"- Ngày mua xe dùng làm mốc tính: {_date(service['date'])}; đây không phải bản ghi lần bảo dưỡng gần nhất.")
        elif service.get("type") in {"OEM_SERVICE_RECORD", "EV_CARE_SERVICE_RECORD"}:
            lines.append(f"- Lần bảo dưỡng ghi nhận gần nhất: {_date(service['date'])}.")
    items = milestone.get("items", [])
    if not isinstance(items, list):
        raise ValueError("Invalid maintenance items")
    if items:
        lines.append("Hạng mục tại mốc này:")
    for item in items:
        if not isinstance(item, dict) or not item.get("item_name"):
            raise ValueError("Invalid maintenance item")
        # A rule flag alone does not establish the vehicle's current warranty.
        flag = item.get("is_covered_by_warranty")
        suffix = " (quy tắc có bảo hành; cần dự toán để xác định phần được tính miễn phí)" if flag is True else ""
        lines.append(f"- {item['item_name']}{suffix}.")
    return "\n".join(lines)


def price_comparison_request(question: str) -> bool:
    text = unicodedata.normalize("NFD", question.casefold()).replace("đ", "d")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return "gia xuong" in text and "gia tham khao" in text


def _estimate(data: dict[str, Any], *, compare_prices: bool = False) -> str:
    if data.get("status") == "NO_RULE":
        return "Chưa có quy tắc để lập dự toán cho mốc này; chưa có giá được xác minh."
    if data.get("status") != "READY" or data.get("currency") != "VND":
        raise ValueError("Invalid estimate status/currency")
    warranty = data.get("warranty_status")
    warranty_labels = {"ACTIVE": "Bảo hành xe: còn hiệu lực theo dữ liệu tool.",
                       "EXPIRED": "Bảo hành xe: đã hết hiệu lực theo dữ liệu tool.",
                       "UNKNOWN": "Bảo hành xe: chưa xác định. Công cụ dự toán áp dụng quy tắc bảo hành cho hạng mục khi trạng thái chưa xác định; cần xưởng xác nhận quyền lợi thực tế."}
    if warranty not in warranty_labels:
        raise ValueError("Invalid warranty state")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Missing estimate items")
    lines = [warranty_labels[warranty]]
    total = Decimal(0)
    reference = False
    workshop_price = False
    for item in items:
        if not isinstance(item, dict) or not item.get("item_name") or not isinstance(item.get("covered"), bool):
            raise ValueError("Invalid estimate item")
        price = _number(item.get("price"))
        if price < 0:
            raise ValueError("Negative price")
        if item["covered"]:
            if price != 0 or warranty == "EXPIRED":
                raise ValueError("Contradictory warranty price")
            label = "công cụ tính 0 theo quy tắc bảo hành"
        else:
            source = item.get("price_source")
            if source not in {"WORKSHOP_PRICE", "REFERENCE_PRICE"}:
                raise ValueError("Missing price source")
            reference |= source == "REFERENCE_PRICE"
            workshop_price |= source == "WORKSHOP_PRICE"
            label = "giá tham khảo" if source == "REFERENCE_PRICE" else "giá của xưởng"
            total += price
        lines.append(f"- {item['item_name']}: {_format(price)} VND ({label}).")
    if total != _number(data.get("chargeable_total")) or data.get("has_reference_price") is not reference:
        raise ValueError("Inconsistent estimate total/source")
    if compare_prices:
        lines += [
            "Phân biệt nguồn giá: giá xưởng là giá do xưởng cung cấp cho hạng mục; "
            "giá tham khảo là giá từ quy tắc dịch vụ được dùng khi chưa có giá của xưởng cho hạng mục đó. "
            "Giá tham khảo chưa phải báo giá được xưởng xác nhận.",
        ]
        if reference:
            lines.append("Dự toán này có hạng mục dùng giá tham khảo; xưởng cần xác nhận giá thực tế.")
        elif workshop_price:
            lines.append("Các hạng mục có phí trong dự toán này dùng giá của xưởng; chưa có giá tham khảo riêng để so sánh số tiền.")
        else:
            lines.append("Các hạng mục trong dự toán này đều được công cụ tính 0 theo quy tắc bảo hành; không có dòng giá xưởng hoặc giá tham khảo để so sánh số tiền.")
    lines.append(f"Tổng chi phí ước tính: {_format(total)} VND."
                 + (" Có giá tham khảo; xưởng có thể báo giá khác." if reference else ""))
    lines.append("Dữ liệu dự toán chưa xác định giá đã bao gồm VAT hay chưa; cần xưởng xác nhận.")
    return "\n".join(lines)


def business_answer(messages: list[Any], *, question: str = "") -> str | None:
    """Only replace terminal answers for pure business reads in this turn.

    Never reuse a successful result after a newer failure, or combine unknown
    tool contracts with this renderer (booking/RAG/reminders keep their flow).
    """
    results = [message for message in messages if isinstance(message, ToolMessage)]
    names = {message.name for message in results}
    if not names or names - BUSINESS_TOOLS:
        return None
    sections = []
    for name, renderer in (("get_due_maintenance", _maintenance), ("estimate_service_cost", _estimate)):
        latest = next((message for message in reversed(results) if message.name == name), None)
        if latest is None:
            continue
        try:
            data = json.loads(latest.content)
            if not isinstance(data, dict) or latest.status == "error" or data.get("status") == "ERROR":
                raise ValueError("Tool failed")
            sections.append(
                _estimate(data, compare_prices=price_comparison_request(question))
                if name == "estimate_service_cost" else renderer(data)
            )
        except (ValueError, TypeError, KeyError):
            noun = "hạn bảo dưỡng" if name == "get_due_maintenance" else "dự toán chi phí"
            sections.append(f"Chưa có dữ liệu {noun} hợp lệ để xác nhận; cần kiểm tra lại kết quả công cụ.")
    return "\n\n".join(sections)
