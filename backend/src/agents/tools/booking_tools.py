"""Booking tools of the customer agent (AI-004): two reads and one proposal.

The reads call ``BookingService``, the same service as the booking endpoints
(BR-011). No tool creates, cancels or moves a booking (us-061 BR-1514):
``propose_booking`` only makes a proposal card; the owner books by pressing
"Xác nhận đặt lịch" on it (API-QB-02).
"""

from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from src.modules.booking import errors as booking_errors
from src.modules.quick_booking import errors as quick_errors

from . import _services

if TYPE_CHECKING:
    from .dependency import AgentToolServices

# Bounds of the ``limit`` query of API-BK-01.
_MAX_WORKSHOPS = 10

_NEXT_STEP = (
    'Chủ xe bấm "Xác nhận đặt lịch" trên thẻ để đặt. Lịch CHƯA được tạo; không có tool nào tạo lịch thay chủ xe.'
)


def _parse_workshop(workshop_id: str) -> UUID:
    try:
        return UUID(workshop_id)
    except ValueError as exc:
        raise booking_errors.WorkshopNotFoundError() from exc


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise booking_errors.BookingError("Date must be YYYY-MM-DD (e.g. 2026-10-10).", code="INVALID_DATE") from exc


def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise booking_errors.BookingError("Time slot must be HH:MM (e.g. 14:00).", code="INVALID_TIME") from exc


def _slot_full(exc: booking_errors.SlotFullError) -> dict[str, Any]:
    out = _services.tool_error(exc)
    out["alternatives"] = [a.model_dump(mode="json") for a in exc.alternatives]
    return out


def build_booking_tools(services: AgentToolServices | None = None) -> list[BaseTool]:
    """Create tools bound to these service factories."""
    provider = services if services is not None else _services

    @tool
    async def find_workshops(
        config: RunnableConfig,
        area_or_address: str | None = None,
        limit: int = 3,
    ) -> dict[str, Any]:
        """Tìm xưởng dịch vụ đang hoạt động gần chủ xe (API-BK-01, UC-401).

        (Công cụ Đọc)

        Args:
            area_or_address: Khu vực / tỉnh thành chủ xe nêu (ví dụ: 'Hà Nội'). Bỏ trống để
                tìm quanh vị trí chính trong hồ sơ hoặc xưởng ưu tiên của chủ xe.
            limit: Số xưởng tối đa (1-10).

        Returns:
            anchor (cách xếp hạng), workshops: workshop_id (UUID, dùng cho các tool sau), name,
            address, region, distance_km (có thể null), is_preferred.
        """
        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                data = await provider.booking_service(session).find_nearby(
                    who.user,
                    anchor_source=None,
                    lat=None,
                    lng=None,
                    query=(area_or_address or "").strip() or None,
                    province=None,
                    user_vehicle_id=who.user_vehicle_id,
                    d=None,
                    time_slot=None,
                    limit=min(max(limit, 1), _MAX_WORKSHOPS),
                )
                return data.model_dump(mode="json")
            except (_services.MissingCallerError, booking_errors.BookingError) as exc:
                return _services.tool_error(exc)

    @tool
    async def get_available_slots(
        config: RunnableConfig,
        workshop_id: str,
        target_date: str,
    ) -> dict[str, Any]:
        """Các khung giờ trong ngày của một xưởng và chỗ còn trống (API-BK-02, UC-402).

        (Công cụ Đọc)

        Args:
            workshop_id: workshop_id (UUID) lấy từ find_workshops.
            target_date: Ngày cần xem, dạng YYYY-MM-DD. Quy đổi 'thứ Bảy này', 'mai'... theo
                ngày hôm nay trong ngữ cảnh.

        Returns:
            workshop_id, date, slots: time_slot, available, remaining (chỗ còn trống).
            Không có slot nào nghĩa là xưởng nghỉ ngày đó.
        """
        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                data = await provider.booking_service(session).check_availability(
                    who.user,
                    _parse_workshop(workshop_id),
                    _parse_date(target_date),
                    None,
                    with_alternatives=False,
                )
                return data.model_dump(mode="json")
            except (_services.MissingCallerError, booking_errors.BookingError) as exc:
                return _services.tool_error(exc)

    @tool(response_format="content_and_artifact")
    async def propose_booking(
        config: RunnableConfig,
        workshop_id: str,
        booking_date: str,
        time_slot: str,
        odo_milestone: int | None = None,
    ) -> tuple[dict[str, Any], dict | None]:
        """Tạo ĐỀ XUẤT đặt lịch cho xe đang chọn: hiện thẻ có nút "Xác nhận đặt lịch" (us-061 TOOL-QB-01).

        Tool này KHÔNG tạo lịch hẹn và KHÔNG giữ chỗ. Lịch chỉ được tạo khi chủ xe bấm nút
        "Xác nhận đặt lịch" trên thẻ. Gọi khi chủ xe đã chọn xưởng, ngày và giờ cụ thể.
        Chủ xe gõ "đồng ý" / "xác nhận" thì nhắc họ bấm nút trên thẻ, không gọi lại tool.

        Args:
            workshop_id: workshop_id (UUID) lấy từ find_workshops.
            booking_date: Ngày hẹn, dạng YYYY-MM-DD.
            time_slot: Giờ bắt đầu khung giờ, dạng HH:MM, phải là một slot available của get_available_slots.
            odo_milestone: Mốc km bảo dưỡng (next_milestone.odo_milestone_km), nếu đã biết.

        Returns:
            status PROPOSED, proposal_id, summary, next_step. Lỗi SLOT_FULL kèm alternatives;
            SLOT_TOO_SOON khi khung giờ bắt đầu quá sớm.
        """
        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                if who.conversation_id is None:
                    raise _services.MissingCallerError()
                proposal, card = await provider.quick_booking_service(session).propose_from_agent(
                    who.user.user_id,
                    who.user_vehicle_id,
                    who.conversation_id,
                    _parse_workshop(workshop_id),
                    _parse_date(booking_date),
                    _parse_time(time_slot),
                    odo_milestone,
                )
            except booking_errors.SlotFullError as exc:
                return _slot_full(exc), None
            except (_services.MissingCallerError, booking_errors.BookingError, quick_errors.QuickBookingError) as exc:
                return _services.tool_error(exc), None
            primary = card["primary"]
            summary = f"Đề xuất {primary['workshopName']} lúc {primary['timeSlot']} ngày {primary['date']}."
            return {
                "status": "PROPOSED",
                "proposal_id": str(proposal.id),
                "summary": summary,
                "next_step": _NEXT_STEP,
            }, card

    return [find_workshops, get_available_slots, propose_booking]


find_workshops, get_available_slots, propose_booking = build_booking_tools()
