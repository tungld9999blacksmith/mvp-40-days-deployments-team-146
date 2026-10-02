"""User-vehicle module — due-status calculation (read model RM-401).

Pure functions only: no FastAPI, no Session. The service loads the inputs from
the database and calls ``calculate_due_status``; the API, the AI agent tool and
the reminder job (F7) all go through the same function (FEAT-VEH-001 BR-008).

Algorithm: ``docs/specs/sprint-2/entity/us-017-sprint-2-spec.entity.md`` RM-401 §4.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum

# Vietnam has no daylight saving time, so a fixed offset is exact.
VN_TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


class DueStatus(StrEnum):
    NORMAL = "NORMAL"
    DUE_SOON = "DUE_SOON"
    OVERDUE = "OVERDUE"
    UNKNOWN = "UNKNOWN"


class DueReason(StrEnum):
    KM = "KM"
    TIME = "TIME"
    BOTH = "BOTH"


class CalculationBasis(StrEnum):
    KM_AND_TIME = "KM_AND_TIME"
    TIME_ONLY = "TIME_ONLY"


class UnknownReason(StrEnum):
    OEM_DATA_NOT_SYNCED = "OEM_DATA_NOT_SYNCED"
    NO_MAINTENANCE_RULE = "NO_MAINTENANCE_RULE"


class LastServiceType(StrEnum):
    OEM_SERVICE_RECORD = "OEM_SERVICE_RECORD"
    EV_CARE_SERVICE_RECORD = "EV_CARE_SERVICE_RECORD"
    PURCHASE_DATE = "PURCHASE_DATE"


@dataclass(frozen=True)
class DueConfig:
    due_soon_km: int = 500
    due_soon_days: int = 14
    # Past the end of the rule table the milestone repeats by a fixed step (Q-301).
    recurring_km: int = 12_000
    recurring_months: int = 12
    odo_stale_days: int = 30


@dataclass(frozen=True)
class RuleItem:
    """One ``maintenance_rule`` row."""

    odo_milestone: int
    month_milestone: int
    item_code: str
    item_name: str
    is_covered_by_warranty: bool


@dataclass(frozen=True)
class Odometer:
    odo_km: int
    recorded_at: datetime
    is_stale: bool = False


@dataclass(frozen=True)
class LastService:
    type: LastServiceType
    date: date
    odo_km: int | None


@dataclass(frozen=True)
class MilestoneItem:
    item_code: str
    item_name: str
    is_covered_by_warranty: bool


@dataclass(frozen=True)
class NextMilestone:
    odo_milestone_km: int
    month_milestone: int
    due_date: date
    is_recurring: bool
    items: list[MilestoneItem] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.odo_milestone_km:,} km / {self.month_milestone} months"


@dataclass(frozen=True)
class DueResult:
    due_status: DueStatus
    due_reason: DueReason | None = None
    calculation_basis: CalculationBasis | None = None
    unknown_reason: UnknownReason | None = None
    next_milestone: NextMilestone | None = None
    remaining_km: int | None = None
    remaining_days: int | None = None
    odometer: Odometer | None = None
    last_service: LastService | None = None


def today_vn(now: datetime) -> date:
    """Calendar date in Asia/Ho_Chi_Minh for a UTC (or naive-UTC) instant."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(VN_TZ).date()


def add_months(start: date, months: int) -> date:
    """Add calendar months, clamping to the month end (Jan 31 + 1 -> Feb 28/29)."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def unknown(reason: UnknownReason, odometer: Odometer | None = None) -> DueResult:
    return DueResult(due_status=DueStatus.UNKNOWN, unknown_reason=reason, odometer=odometer)


def _reason(km: bool, time: bool) -> DueReason:
    if km and time:
        return DueReason.BOTH
    return DueReason.KM if km else DueReason.TIME


def calculate_due_status(
    *,
    rules: list[RuleItem],
    purchase_date: date,
    odometer: Odometer | None,
    last_service: LastService | None,
    today: date,
    config: DueConfig,
) -> DueResult:
    """Compute the next milestone and the due status (FF BR-001, BR-002, BR-005..BR-007)."""
    if not rules:
        return unknown(UnknownReason.NO_MAINTENANCE_RULE, odometer)

    # Distinct (km, months) milestones in ascending km order, with their items.
    items_by_milestone: dict[tuple[int, int], list[MilestoneItem]] = {}
    for rule in sorted(rules, key=lambda r: (r.odo_milestone, r.month_milestone, r.item_code)):
        items_by_milestone.setdefault((rule.odo_milestone, rule.month_milestone), []).append(
            MilestoneItem(rule.item_code, rule.item_name, rule.is_covered_by_warranty)
        )
    milestones = list(items_by_milestone)

    def is_done(km: int, months: int) -> bool:
        # No "early service" window yet: deferred (Q-302, docs/specs/sprint-2/pending-questions.md).
        if last_service is None:
            return False
        if last_service.odo_km is not None and last_service.odo_km >= km:
            return True
        return last_service.date >= add_months(purchase_date, months)

    done = [m for m in milestones if is_done(*m)]
    if not done:
        next_km, next_months = milestones[0]
        recurring = False
    elif done[-1] != milestones[-1]:
        next_km, next_months = milestones[milestones.index(done[-1]) + 1]
        recurring = False
    else:
        # BR-007: past the end of the table -> fixed step (Q-301).
        step_km, step_months = config.recurring_km, config.recurring_months
        next_km, next_months = done[-1][0] + step_km, done[-1][1] + step_months
        while is_done(next_km, next_months):
            next_km, next_months = next_km + step_km, next_months + step_months
        recurring = True

    items = items_by_milestone[milestones[0] if recurring else (next_km, next_months)]
    due_date = add_months(purchase_date, next_months)
    milestone = NextMilestone(next_km, next_months, due_date, recurring, items)

    remaining_days = (due_date - today).days
    remaining_km = next_km - odometer.odo_km if odometer is not None else None

    overdue_km = remaining_km is not None and remaining_km < 0
    overdue_time = remaining_days < 0
    soon_km = remaining_km is not None and remaining_km <= config.due_soon_km
    soon_time = remaining_days <= config.due_soon_days

    if overdue_km or overdue_time:
        status, reason = DueStatus.OVERDUE, _reason(overdue_km, overdue_time)
    elif soon_km or soon_time:
        status, reason = DueStatus.DUE_SOON, _reason(soon_km, soon_time)
    else:
        status, reason = DueStatus.NORMAL, None

    return DueResult(
        due_status=status,
        due_reason=reason,
        calculation_basis=(CalculationBasis.KM_AND_TIME if odometer is not None else CalculationBasis.TIME_ONLY),
        next_milestone=milestone,
        remaining_km=remaining_km,
        remaining_days=remaining_days,
        odometer=odometer,
        last_service=last_service or LastService(LastServiceType.PURCHASE_DATE, purchase_date, 0),
    )
