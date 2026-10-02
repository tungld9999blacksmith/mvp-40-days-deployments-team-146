"""Service progress — stage order and derived current stage (us-057 BR-1301..1303, EDGE-1304).

Pure logic only.
"""

from __future__ import annotations

from src.common.core.maintenance.booking import BookingStatus
from src.common.core.maintenance.service_progress import ServiceStage

St = ServiceStage

# BR-1302 — the next valid stages from each stage (None = no entry yet).
NEXT_STAGES: dict[ServiceStage | None, tuple[ServiceStage, ...]] = {
    None: (St.CHECKED_IN,),
    St.CHECKED_IN: (St.INSPECTING,),
    St.INSPECTING: (St.SERVICING,),
    St.SERVICING: (St.WAITING_PARTS, St.QUALITY_CHECK),
    St.WAITING_PARTS: (St.SERVICING,),
    St.QUALITY_CHECK: (St.READY_FOR_PICKUP, St.SERVICING),
    St.READY_FOR_PICKUP: (),
}

# Stages the workshop owner writes; CHECKED_IN / INSPECTING come from the F8 hook.
OWNER_STAGES: frozenset[ServiceStage] = frozenset(
    {St.SERVICING, St.WAITING_PARTS, St.QUALITY_CHECK, St.READY_FOR_PICKUP}
)

# BR-1305 — stages that notify the vehicle owner.
NOTIFY_STAGES: frozenset[ServiceStage] = frozenset({St.WAITING_PARTS, St.READY_FOR_PICKUP})

FROZEN_STATUSES: frozenset[BookingStatus] = frozenset({BookingStatus.COMPLETED, BookingStatus.CANCELLED})

NOTE_MAX = 500
WAITING_PARTS_NOTE_MIN = 10

STAGE_LABEL_VI: dict[ServiceStage, str] = {
    St.CHECKED_IN: "Đã tiếp nhận",
    St.INSPECTING: "Đang kiểm tra",
    St.SERVICING: "Đang bảo dưỡng",
    St.WAITING_PARTS: "Chờ phụ tùng",
    St.QUALITY_CHECK: "Kiểm tra chất lượng",
    St.READY_FOR_PICKUP: "Sẵn sàng giao xe",
}


def derived_stage(status: BookingStatus) -> ServiceStage | None:
    """EDGE-1304 — no entry yet: infer the stage from the booking status."""
    if status == BookingStatus.CHECKED_IN:
        return St.CHECKED_IN
    if status in (BookingStatus.IN_PROGRESS, BookingStatus.COMPLETED):
        return St.INSPECTING
    return None


def owner_next_stages(status: BookingStatus, current: ServiceStage | None) -> list[ServiceStage]:
    """Stages the owner may append now — none unless the booking is in progress."""
    if status != BookingStatus.IN_PROGRESS:
        return []
    return [s for s in NEXT_STAGES.get(current, ()) if s in OWNER_STAGES]


def note_valid(stage: ServiceStage, note: str | None) -> bool:
    """BR-1303 — waiting for parts needs 10..500 chars; other stages ≤ 500."""
    length = len(note or "")
    if stage == St.WAITING_PARTS:
        return WAITING_PARTS_NOTE_MIN <= length <= NOTE_MAX
    return length <= NOTE_MAX
