from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ResolvedDate:
    """Kết quả phân giải ngày giờ tự nhiên cho Agent EV Care.

    - target_date: Ngày cụ thể đã giải quyết (theo múi giờ địa phương Việt Nam)
    - target_time: Giờ hẹn cụ thể nếu người dùng nêu rõ (ví dụ: 14:00, 15:30), ngược lại là None
    - session: Buổi trong ngày ("morning", "afternoon", "evening") nếu người dùng chỉ nói buổi
    - is_ambiguous: True nếu ngày/giờ mơ hồ, cần hỏi lại người dùng
    - raw_text: Chuỗi văn bản gốc
    """

    target_date: date
    target_time: time | None = None
    session: Literal["morning", "afternoon", "evening"] | None = None
    is_ambiguous: bool = False
    raw_text: str = ""


# Bản đồ ánh xạ thứ trong tuần tiếng Việt -> weekday index (0=Thứ 2, ..., 6=Chủ Nhật)
WEEKDAY_MAP: dict[str, int] = {
    "thứ hai": 0,
    "thứ 2": 0,
    "t2": 0,
    "thứ ba": 1,
    "thứ 3": 1,
    "t3": 1,
    "thứ tư": 2,
    "thứ 4": 2,
    "t4": 2,
    "thứ năm": 3,
    "thứ 5": 3,
    "t5": 3,
    "thứ sáu": 4,
    "thứ 6": 4,
    "t6": 4,
    "thứ bảy": 5,
    "thứ 7": 5,
    "thứ bẩy": 5,
    "t7": 5,
    "chủ nhật": 6,
    "chu nhat": 6,
    "cn": 6,
}


def resolve_date(
    text: str,
    now: datetime | None = None,
    tz_name: str = "Asia/Ho_Chi_Minh",
) -> ResolvedDate | None:
    """Module thuần phân giải văn bản ngày/giờ tự nhiên tiếng Việt sang ResolvedDate.

    Tuân thủ quy tắc kiến trúc Stage 2:
    - Không gán một giờ cố định khi khách chỉ nói buổi ("chiều" -> session="afternoon", target_time=None).
    - Thứ trong tuần tính là ngày gần nhất từ hôm nay; nếu hôm nay là thứ đó nhưng đã hết giờ làm việc (>= 17:00),
      sẽ đề xuất tuần kế tiếp (+7 ngày).
    - Hỗ trợ định dạng ISO YYYY-MM-DD, DD/MM/YYYY, DD/MM, tương đối (hôm nay, mai, mốt...).
    """
    if not text or not text.strip():
        return None

    clean_text = text.strip().lower()

    # Xác định mốc thời gian hiện tại theo timezone địa phương
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Ho_Chi_Minh")

    current_dt = now.astimezone(tz) if now else datetime.now(tz)
    today = current_dt.date()
    current_time = current_dt.time()

    resolved_target_date: date | None = None
    session: Literal["morning", "afternoon", "evening"] | None = None
    target_time: time | None = None
    is_ambiguous: bool = False

    # 1. Trích xuất giờ cụ thể nếu có (ví dụ: 14h, 14:30, 14h30, 09:00, 9h)
    time_match = re.search(r"\b(\d{1,2})(?:[:h](\d{2})|h)\b", clean_text)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            target_time = time(hour, minute)

    # 2. Trích xuất buổi trong ngày
    if "sáng" in clean_text:
        session = "morning"
    elif "chiều" in clean_text:
        session = "afternoon"
    elif "tối" in clean_text:
        session = "evening"

    # 3. Phân giải ngày dạng ISO: YYYY-MM-DD
    iso_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", clean_text)
    if iso_match:
        try:
            y, m, d = int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))
            resolved_target_date = date(y, m, d)
        except ValueError:
            is_ambiguous = True

    # 4. Phân giải ngày dạng DD/MM/YYYY hoặc DD/MM
    if not resolved_target_date:
        vn_date_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", clean_text)
        if vn_date_match:
            try:
                d = int(vn_date_match.group(1))
                m = int(vn_date_match.group(2))
                y = int(vn_date_match.group(3) or today.year)
                resolved_target_date = date(y, m, d)
                if resolved_target_date < today and not vn_date_match.group(3):
                    # Nếu ngày đã qua trong năm nay và người dùng không nêu rõ năm, chuyển sang năm sau
                    resolved_target_date = date(y + 1, m, d)
            except ValueError:
                is_ambiguous = True

    # 5. Phân giải từ khóa tương đối: hôm nay, ngày mai, ngày kia
    if not resolved_target_date:
        if "hôm nay" in clean_text:
            resolved_target_date = today
        elif "ngày mai" in clean_text or "mai" in clean_text.split():
            resolved_target_date = today + timedelta(days=1)
        elif "ngày kia" in clean_text or "mốt" in clean_text:
            resolved_target_date = today + timedelta(days=2)

    # 6. Phân giải thứ trong tuần: "thứ bảy", "thứ 7", "chủ nhật"...
    if not resolved_target_date:
        for wk_text, target_weekday in WEEKDAY_MAP.items():
            if wk_text in clean_text:
                days_ahead = (target_weekday - today.weekday()) % 7
                if days_ahead == 0:
                    # Hôm nay chính là thứ được yêu cầu
                    # Nếu đã quá 17:00 (hết giờ làm việc thông thường) hoặc buổi chiều đã qua, sang tuần kế tiếp
                    if current_time >= time(17, 0) or (session == "afternoon" and current_time >= time(16, 30)):
                        days_ahead = 7
                resolved_target_date = today + timedelta(days=days_ahead)
                break

    # Nếu không nhận diện được ngày nào
    if not resolved_target_date:
        return None

    return ResolvedDate(
        target_date=resolved_target_date,
        target_time=target_time,
        session=session,
        is_ambiguous=is_ambiguous,
        raw_text=text,
    )
