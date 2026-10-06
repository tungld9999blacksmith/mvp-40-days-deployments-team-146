from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class AgentCtx:
    """Ngữ cảnh thực thi đáng tin cậy của Agent được nạp từ backend đã xác thực.

    Tuyệt đối KHÔNG đưa vào tool arguments mà LLM nhìn thấy (phòng thủ Prompt Injection / IDOR).
    Được truyền qua RunnableConfig: config={"configurable": {"ctx": agent_ctx}}.

    - user_id: ID chủ xe (kiểu int theo bảng vehicle_user)
    - vehicle_id: UUID xe đang làm việc
    - conversation_id: UUID cuộc hội thoại hiện tại
    - source_message_id: UUID tin nhắn kích hoạt lượt gọi (tùy chọn)
    - operation_key: Khóa thao tác duy nhất dùng cho Idempotency (tùy chọn)
    - tz: Múi giờ người dùng (mặc định: Asia/Ho_Chi_Minh)
    """

    user_id: int | str
    vehicle_id: UUID | str
    conversation_id: UUID | str
    source_message_id: UUID | str | None = None
    operation_key: str | None = None
    tz: str = "Asia/Ho_Chi_Minh"
