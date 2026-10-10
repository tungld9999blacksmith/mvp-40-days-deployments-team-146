"""Quote tools of the customer agent (AI-005): draft a quote and read its status.

Both call ``QuoteService``, the service of the quote endpoints (us-049). No tool
sends a quote to the workshop: the owner submits it with the card's "Gửi xưởng
duyệt" button (BR-1103), so the agent never makes that side effect. A draft is
invisible to the workshop until then (BR-1110).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from src.modules.quote import errors as quote_errors
from src.modules.quote import schemas as quote_schemas
from src.modules.quote.cards import quote_card

from . import _services

if TYPE_CHECKING:
    from .dependency import AgentToolServices

# Recent quotes listed by get_quote_status besides the newest one.
_MAX_OTHER_QUOTES = 4

_NEXT_STEP = {
    "DRAFT": (
        'Báo giá là NHÁP, xưởng CHƯA thấy. Chủ xe bấm "Gửi xưởng duyệt" trên thẻ để gửi; '
        "không có tool nào gửi thay chủ xe."
    ),
    "PENDING_APPROVAL": "Báo giá đã gửi và đang chờ xưởng duyệt; không cần gửi lại.",
}


def _parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise quote_errors.InvalidRequestError(f"{field} must be a UUID returned by a tool.") from exc


def _brief(quote: quote_schemas.QuoteOut | quote_schemas.QuoteSummaryOut) -> dict[str, Any]:
    """What the model may say about a quote; every number comes from ``quote`` / ``quote_item``."""
    data = quote.model_dump(
        mode="json",
        include={
            "quote_id",
            "display_status",
            "price_label",
            "odo_milestone",
            "estimated_total",
            "approved_total",
            "submitted_at",
            "reviewed_at",
            "expires_at",
            "reviewer_note",
            "can_attach_to_booking",
        },
    )
    data["workshop_name"] = quote.workshop.name
    data["workshop_id"] = str(quote.workshop.workshop_id)
    if isinstance(quote, quote_schemas.QuoteOut):
        data["items"] = [
            {
                "item_name": i.item_name,
                "covered": i.covered,
                "estimated_price": float(i.estimated_price),
                "approved_price": float(i.approved_price) if i.approved_price is not None else None,
                "reviewer_note": i.reviewer_note,
            }
            for i in quote.items
        ]
    return data


def build_quote_tools(services: AgentToolServices | None = None) -> list[BaseTool]:
    """Create tools bound to these service factories."""
    provider = services if services is not None else _services

    @tool(response_format="content_and_artifact")
    def create_draft_quote(
        config: RunnableConfig,
        workshop_id: str,
        odo_milestone: int,
    ) -> tuple[dict[str, Any], dict | None]:
        """Lập BÁO GIÁ NHÁP cho xe đang chọn tại một xưởng và hiện thẻ báo giá (TOOL-501).

        Dòng và giá do hệ thống tính từ dự toán của xưởng, không truyền giá. Tool KHÔNG gửi báo
        giá cho xưởng: chủ xe tự bấm "Gửi xưởng duyệt" trên thẻ. Gọi khi chủ xe muốn xưởng báo
        giá, sau estimate_service_cost. Nếu xe đã có báo giá nháp hoặc đang chờ duyệt cho đúng
        xưởng và mốc này, tool trả lại báo giá đó (reused = true) thay vì lập mới.

        Args:
            workshop_id: workshop.workshop_id từ estimate_service_cost (hoặc từ find_workshops).
            odo_milestone: milestone.odo_milestone từ estimate_service_cost.

        Returns:
            status (DRAFT / PENDING_APPROVAL), reused, quote (tổng, nhãn giá, hạng mục), next_step.
            Lỗi: NO_MAINTENANCE_RULE, MILESTONE_NOT_FOUND (kèm details.validMilestones),
            WORKSHOP_INACTIVE.
        """
        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                payload = quote_schemas.CreateQuoteRequest(
                    user_vehicle_id=who.user_vehicle_id,
                    workshop_id=_parse_uuid(workshop_id, "workshop_id"),
                    odo_milestone=odo_milestone,
                )
                quote, reused = provider.quote_service(session).draft_from_chat(
                    who.user, payload, source_message_id=who.source_message_id
                )
            except ValidationError:
                return _services.tool_error(
                    quote_errors.InvalidRequestError("odo_milestone must be a positive milestone.")
                ), None
            except (_services.MissingCallerError, quote_errors.QuoteError) as exc:
                return _services.tool_error(exc), None
        status = quote.display_status
        return {
            "status": status,
            "reused": reused,
            "quote": _brief(quote),
            "next_step": _NEXT_STEP.get(status, ""),
        }, quote_card(quote)

    @tool
    def get_quote_status(config: RunnableConfig, quote_id: str | None = None) -> dict[str, Any]:
        """Trạng thái báo giá của xe đang chọn: xưởng đã duyệt / sửa giá / từ chối chưa (TOOL-503).

        (Công cụ Đọc)

        Args:
            quote_id: quote_id cụ thể (từ create_draft_quote hoặc lần gọi trước). Bỏ trống để xem
                báo giá mới nhất của xe cùng vài báo giá gần đây.

        Returns:
            latest: display_status (DRAFT, PENDING_APPROVAL, APPROVED, MODIFIED = xưởng đã sửa giá,
            EXPIRED, REJECTED), tổng ước tính / đã duyệt, hạn hiệu lực expires_at, reviewer_note
            (lý do từ chối hoặc ghi chú), items; others: các báo giá khác. latest = null khi xe
            chưa có báo giá nào.
        """
        with provider.open_session() as session:
            try:
                who = _services.caller(session, config)
                quotes = provider.quote_service(session)
                if quote_id:
                    return {"latest": _brief(quotes.get_for_owner(who.user, _parse_uuid(quote_id, "quote_id")))}
                listed = quotes.list_for_owner(
                    who.user,
                    user_vehicle_id=who.user_vehicle_id,
                    statuses=None,
                    unseen_result=False,
                    limit=_MAX_OTHER_QUOTES + 1,
                    cursor=None,
                ).items
                if not listed:
                    return {"latest": None, "others": []}
                # Reading the result here tells the owner, so it is marked seen (BR-1109).
                latest = quotes.get_for_owner(who.user, listed[0].quote_id)
                return {"latest": _brief(latest), "others": [_brief(q) for q in listed[1:]]}
            except (_services.MissingCallerError, quote_errors.QuoteError) as exc:
                return _services.tool_error(exc)

    return [create_draft_quote, get_quote_status]


create_draft_quote, get_quote_status = build_quote_tools()
