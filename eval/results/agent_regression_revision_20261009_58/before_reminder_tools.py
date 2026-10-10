"""Maintenance-reminder tools; identity comes exclusively from trusted config."""

from typing import TYPE_CHECKING
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import StrictBool, StrictInt

from src.modules.notification.errors import NotificationError
from src.modules.notification.schemas import ChannelChangeIn, NotificationChannel, NotificationSettingsUpdateIn
from src.modules.user_vehicle.errors import UserVehicleError

from . import _services

if TYPE_CHECKING:
    from .dependency import AgentToolServices


def build_reminder_tools(services: "AgentToolServices | None" = None):
    provider = services if services is not None else _services

    def owned(session, config):
        who = _services.caller(session, config)
        provider.user_vehicle_service(session).get_owned_active_vehicle(who.user, who.user_vehicle_id)
        return who

    @tool
    def get_reminder_settings(config: RunnableConfig) -> dict:
        """Đọc cài đặt nhắc bảo dưỡng và Email của chủ xe đang chat; áp dụng tất cả xe sở hữu."""
        with provider.open_session() as db:
            try:
                who = owned(db, config)
                result = provider.notification_settings_service(db).get(who.user)
                return {"status": "ok", "data": result.model_dump(mode="json", by_alias=True)}
            except (_services.MissingCallerError, UserVehicleError, NotificationError) as exc:
                return _services.tool_error(exc)

    @tool
    def update_reminder_settings(
        config: RunnableConfig,
        reminders_enabled: StrictBool | None = None,
        email_enabled: StrictBool | None = None,
        reminder_lead_days: StrictInt | None = None,
    ) -> dict:
        """Chỉ đổi phần chủ xe yêu cầu rõ. Bật email cũng bật nhắc; tắt email giữ nhắc trong ứng dụng.

        Email nhận lấy từ danh tính đã xác minh; không nhận địa chỉ email tùy ý.
        Tool lưu cài đặt, không gửi thư hoặc đặt lịch. Chỉ báo đã lưu khi status=ok.
        reminder_lead_days chỉ hợp lệ từ 0 đến 30 ngày; không lưu giá trị ngoài khoảng.
        Tắt mọi nhắc bảo dưỡng: chỉ reminders_enabled=false, giữ nguyên email_enabled
        và số ngày. Chỉ thay email_enabled nếu chủ xe yêu cầu bật/tắt Email rõ ràng.
        """
        with provider.open_session() as db:
            try:
                who = owned(db, config)
                payload = NotificationSettingsUpdateIn(
                    reminders_enabled=True
                    if email_enabled is True and reminders_enabled is None
                    else reminders_enabled,
                    reminder_lead_days=reminder_lead_days,
                    channels=[ChannelChangeIn(channel=NotificationChannel.EMAIL, enabled=email_enabled)]
                    if email_enabled is not None
                    else None,
                )
                result = provider.notification_settings_service(db).update(who.user, payload)
                return {"status": "ok", "data": result.model_dump(mode="json", by_alias=True)}
            except (_services.MissingCallerError, UserVehicleError, NotificationError) as exc:
                return _services.tool_error(exc)

    @tool
    def get_reminder_context(reminder_id: UUID, config: RunnableConfig) -> dict:
        """Giải thích lời nhắc theo ID, dữ liệu tại lúc nhắc, tình trạng hiện tại và trạng thái gửi; chỉ đọc xe của chủ đang chat."""
        with provider.open_session() as db:
            try:
                who = owned(db, config)
                result = provider.reminder_context_service(db).get(who.user, reminder_id)
                if result["userVehicleId"] != str(who.user_vehicle_id):
                    raise NotificationError("Select the vehicle of this reminder first.", code="REMINDER_NOT_FOUND")
                return {"status": "ok", "data": result}
            except (_services.MissingCallerError, UserVehicleError, NotificationError) as exc:
                return _services.tool_error(exc)

    return [get_reminder_settings, update_reminder_settings, get_reminder_context]


get_reminder_settings, update_reminder_settings, get_reminder_context = build_reminder_tools()
