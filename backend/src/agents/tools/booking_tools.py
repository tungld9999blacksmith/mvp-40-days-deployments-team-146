from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# Danh sách xưởng dịch vụ VinFast chuẩn mẫu
MOCK_WORKSHOPS = [
    {
        "workshop_id": "ws-thanh-xuan-01",
        "name": "Xưởng Dịch vụ VinFast Thanh Xuân",
        "address": "Số 68 Lê Văn Lương, Phường Nhân Chính, Quận Thanh Xuân, Hà Nội",
        "region": "Thanh Xuân",
        "latitude": 21.0035,
        "longitude": 105.8042,
        "operating_hours": "08:00 - 18:00 (Thứ 2 - Chủ Nhật)",
        "phone": "1900 23 23 89",
    },
    {
        "workshop_id": "ws-cau-giay-02",
        "name": "Xưởng Dịch vụ VinFast Cầu Giấy",
        "address": "Số 122 Xuân Thủy, Phường Dịch Vọng Hậu, Quận Cầu Giấy, Hà Nội",
        "region": "Cầu Giấy",
        "latitude": 21.0368,
        "longitude": 105.7876,
        "operating_hours": "08:00 - 18:00 (Thứ 2 - Thứ 7)",
        "phone": "1900 23 23 89",
    },
    {
        "workshop_id": "ws-ha-dong-03",
        "name": "Xưởng Dịch vụ VinFast Hà Đông",
        "address": "TTTM Vincom Plaza, Số 104 Quang Trung, Quận Hà Đông, Hà Nội",
        "region": "Hà Đông",
        "latitude": 20.9712,
        "longitude": 105.7734,
        "operating_hours": "08:00 - 18:00 (Thứ 2 - Chủ Nhật)",
        "phone": "1900 23 23 89",
    },
    {
        "workshop_id": "ws-hai-ba-trung-04",
        "name": "Xưởng Dịch vụ VinFast Bà Triệu",
        "address": "Vincom Center Bà Triệu, 191 Bà Triệu, Quận Hai Bà Trưng, Hà Nội",
        "region": "Hai Bà Trưng",
        "latitude": 21.0118,
        "longitude": 105.8501,
        "operating_hours": "08:30 - 18:30 (Thứ 2 - Chủ Nhật)",
        "phone": "1900 23 23 89",
    },
]


@tool
def find_workshops(
    area_or_address: str,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Tìm kiếm danh sách xưởng dịch vụ xe điện VinFast gần nhất theo quận, huyện, tỉnh thành hoặc địa chỉ.

    (Công cụ Đọc - CQRS Read Tool)

    Args:
        area_or_address: Tên khu vực, quận huyện, hoặc địa chỉ cần tìm (ví dụ: 'Thanh Xuân', 'Cầu Giấy', 'Hà Đông')
        limit: Số lượng xưởng tối đa muốn lấy (mặc định: 3)

    Returns:
        Danh sách xưởng phù hợp kèm khoảng cách ước tính và giờ hoạt động.
    """
    clean_area = area_or_address.strip().lower()

    # Thử truy vấn qua DB nếu có kết nối
    try:
        from sqlmodel import Session, select

        try:
            from common.core.workshop import Workshop, WorkshopStatus
        except ImportError:
            from src.common.core.workshop import Workshop, WorkshopStatus

        try:
            from infrastructure.supabase.db import engine
        except ImportError:
            from src.infrastructure.supabase.db import engine

        with Session(engine) as session:
            workshops = session.exec(select(Workshop).where(Workshop.status == WorkshopStatus.ACTIVE)).all()
            if workshops:
                matched = [
                    w
                    for w in workshops
                    if clean_area in (w.region or "").lower()
                    or clean_area in (w.address or "").lower()
                    or clean_area in (w.name or "").lower()
                ] or workshops
                return [
                    {
                        "workshop_id": str(w.id),
                        "name": w.name,
                        "address": w.address,
                        "region": w.region,
                        "distance_km": 1.2 if clean_area in (w.region or "").lower() else 3.5,
                    }
                    for w in matched[:limit]
                ]
    except Exception as e:
        logger.debug("Database workshop query skipped (%s), using standard workshop directory.", e)

    # Fallback sử dụng bộ dữ liệu chuẩn mẫu
    scored = []
    for w in MOCK_WORKSHOPS:
        match_score = 0
        dist = 3.5
        if clean_area in w["region"].lower() or clean_area in w["address"].lower():
            match_score = 2
            dist = 1.2
        elif any(part in w["address"].lower() for part in clean_area.split()):
            match_score = 1
            dist = 2.8

        scored.append((match_score, dist, w))

    # Sắp xếp theo độ khớp và khoảng cách
    scored.sort(key=lambda x: (-x[0], x[1]))

    results = []
    for _, dist, w in scored[:limit]:
        item = dict(w)
        item["distance_km"] = dist
        results.append(item)

    return results


@tool
def get_available_slots(
    workshop_id: str,
    target_date: str,
) -> dict[str, Any]:
    """Tra cứu các khung giờ (slot) còn chỗ để bảo dưỡng tại xưởng dịch vụ vào một ngày cụ thể.

    (Công cụ Đọc - CQRS Read Tool)

    Args:
        workshop_id: ID hoặc mã xưởng dịch vụ (ví dụ: 'ws-thanh-xuan-01')
        target_date: Ngày cần đặt lịch (ví dụ: 'Thứ Bảy', '2026-10-03', 'cuối tuần này')

    Returns:
        Danh sách các khung giờ sáng/chiều còn nhận xe kèm số lượng chỗ còn trống.
    """
    # Tìm tên xưởng
    ws_name = "Xưởng Dịch vụ VinFast Thanh Xuân"
    for w in MOCK_WORKSHOPS:
        if w["workshop_id"] == workshop_id or workshop_id in w["name"]:
            ws_name = w["name"]
            break

    return {
        "workshop_id": workshop_id,
        "workshop_name": ws_name,
        "target_date": target_date,
        "available_slots": [
            {"time": "08:30", "period": "morning", "status": "FULL", "remaining_capacity": 0},
            {"time": "10:00", "period": "morning", "status": "AVAILABLE", "remaining_capacity": 2},
            {"time": "14:00", "period": "afternoon", "status": "AVAILABLE", "remaining_capacity": 3},
            {"time": "15:30", "period": "afternoon", "status": "AVAILABLE", "remaining_capacity": 2},
            {"time": "16:30", "period": "afternoon", "status": "AVAILABLE", "remaining_capacity": 1},
        ],
        "suggested_afternoon_slots": ["14:00", "15:30", "16:30"],
        "note": "Khung giờ chiều thứ Bảy còn 3 lựa chọn thuận tiện (14:00, 15:30, 16:30).",
    }


@tool
def create_booking_draft(
    workshop_id: str,
    slot_time: str,
    service_items: list[str],
    vehicle_id: str | None = None,
) -> dict[str, Any]:
    """Tạo bản nháp giữ chỗ lịch hẹn (HOLD trong 10 phút) sau khi chủ xe đã ĐỒNG Ý và CHỌN khung giờ.

    ⚠️ QUY TẮC AN TOÀN (CQRS Write Tool):
    CHỈ ĐƯỢC GỌI KHI CHỦ XE ĐÃ CHỌN RÕ KHUNG GIỜ VÀ XÁC NHẬN MUỐN ĐẶT LỊCH.
    KHÔNG ĐƯỢC TỰ Ý GỌI KHI CHỈ ĐANG TƯ VẤN HOẶC ĐỀ XUẤT GIỜ.

    Args:
        workshop_id: Mã xưởng dịch vụ
        slot_time: Giờ hẹn cụ thể mà khách hàng đã chọn (ví dụ: '14:00 Thứ Bảy 03/10')
        service_items: Danh sách các hạng mục bảo dưỡng cần thực hiện
        vehicle_id: Mã định danh xe (tùy chọn)

    Returns:
        Mã bản nháp lịch hẹn (draft_id, booking_code), thời gian giữ chỗ (HOLD 10 phút).
    """
    draft_id = str(uuid4())
    booking_code = "EVC-" + secrets.token_hex(4).upper()
    now = datetime.now()
    hold_expires = now + timedelta(minutes=10)

    # Tìm tên xưởng
    ws_name = "Xưởng Dịch vụ VinFast"
    for w in MOCK_WORKSHOPS:
        if w["workshop_id"] == workshop_id or workshop_id in w["name"]:
            ws_name = w["name"]
            break

    return {
        "status": "HOLD",
        "draft_id": draft_id,
        "booking_code": booking_code,
        "workshop_id": workshop_id,
        "workshop_name": ws_name,
        "slot_time": slot_time,
        "service_items": service_items,
        "hold_expires_at": hold_expires.strftime("%H:%M:%S ngày %d/%m/%Y"),
        "hold_duration_minutes": 10,
        "message": (
            f"Đã tạm giữ chỗ thành công cho xe của bạn vào khung giờ {slot_time} tại {ws_name}. "
            f"Mã phiếu hẹn tạm thời: {booking_code}. Chỗ này được giữ trong 10 phút. "
            "Bạn có xác nhận hoàn tất đặt lịch này không?"
        ),
    }
