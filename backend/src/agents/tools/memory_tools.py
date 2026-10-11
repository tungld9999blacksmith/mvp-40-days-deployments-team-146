"""Explicit remember/forget tools; identity and consent come from committed chat."""

from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.config import get_settings
from src.modules.agent_memory.preferences import (
    CostPreference,
    MemoryKey,
    PreferenceService,
    Window,
    WorkshopPreference,
)
from src.modules.conversation.errors import ConversationError

from . import _services


def build_memory_tools(services=None):
    provider = services if services is not None else _services

    @tool
    def remember_preference(
        key: MemoryKey, value: Window | WorkshopPreference | CostPreference,
        config: RunnableConfig, scope: Literal["account", "vehicle"] = "account"
    ) -> dict:
        """Lưu sở thích CHỈ khi tin nhắn hiện tại bắt đầu bằng yêu cầu ghi nhớ rõ ràng.

        preferred_service_window: {day: monday..sunday, period: morning|afternoon|evening}.
        Sáng = morning, chiều = afternoon, buổi tối = evening; period chỉ nhận ba giá trị này.
        preferred_workshop_id: {workshop_id: UUID xưởng đã xác minh}.
        cost_display_preference: {format: itemized|total}.
        Không lưu một lựa chọn tạm thời; giá trị phải khớp lời chủ xe. Không đặt lịch.
        """
        with provider.open_session() as db:
            try:
                who = _services.caller(db, config)
                if not who.conversation_id or not who.source_message_id:
                    raise _services.MissingCallerError()
                row = PreferenceService(db, get_settings()).remember(
                    who.user.user_id, who.user_vehicle_id, who.conversation_id, who.source_message_id,
                    key, value.model_dump(mode="json"), scope
                )
                return {"status": "ok", "memory_id": str(row.id), "key": row.memory_key, "value": row.value_json}
            except (ConversationError, _services.MissingCallerError) as exc:
                return {"status": "ERROR", "code": exc.code, "message": exc.message}

    @tool
    def forget_preference(key: MemoryKey, config: RunnableConfig) -> dict:
        """Quên sở thích khi chủ xe yêu cầu rõ ràng ở tin nhắn hiện tại. Không đổi lịch đã đặt."""
        with provider.open_session() as db:
            try:
                who = _services.caller(db, config)
                if not who.conversation_id or not who.source_message_id:
                    raise _services.MissingCallerError()
                PreferenceService(db, get_settings()).forget_from_chat(
                    who.user.user_id, who.user_vehicle_id, who.conversation_id, who.source_message_id, key
                )
                return {"status": "ok", "key": key}
            except (ConversationError, _services.MissingCallerError) as exc:
                return {"status": "ERROR", "code": exc.code, "message": exc.message}

    return [remember_preference, forget_preference]
