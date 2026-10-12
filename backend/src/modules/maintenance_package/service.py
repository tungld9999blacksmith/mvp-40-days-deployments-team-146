"""Build maintenance packages from verified maintenance and price data.

The optimizer is deliberately deterministic. The LLM may explain these
packages, but it never chooses service items or calculates their prices.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from src.common.core.identity.vehicle_user import VehicleUser
from src.common.core.maintenance.maintenance_rule import MaintenanceRule
from src.common.core.vehicle import UserVehicle
from src.modules.cost_estimate.service import CostEstimationService
from src.modules.user_vehicle.service import UserVehicleService

_SAFETY_MARKERS = (
    "BRAKE", "PHANH", "TIRE", "TYRE", "LỐP", "LOP", "STEERING", "LÁI", "LAI",
    "CHASSIS", "KHUNG GẦM", "KHUNG GAM", "SUSPENSION", "TREO", "WHEEL", "BÁNH XE", "BANH XE",
)
_OPTIONAL_MARKERS = (
    "CABIN", "FILTER", "LỌC GIÓ", "LOC GIO", "SOFTWARE", "FIRMWARE", "CLEAN", "VỆ SINH",
    "VE SINH", "WASH", "ĐIỀU HÒA", "DIEU HOA", "AIR_CONDITION",
)
_PACKAGE_LABELS = {
    "ESSENTIAL": "Thiết yếu",
    "BALANCED": "Cân bằng",
    "COMPREHENSIVE": "Toàn diện",
}


def _tier(rule: MaintenanceRule) -> str:
    text = f"{rule.item_code} {rule.item_name}".upper()
    if any(marker in text for marker in _SAFETY_MARKERS):
        return "REQUIRED"
    if any(marker in text for marker in _OPTIONAL_MARKERS):
        return "OPTIONAL"
    return "RECOMMENDED"


def _history_codes(history: list[Any], valid_codes: set[str]) -> set[str]:
    """Accept only exact item-code tokens from free-text history."""
    found: set[str] = set()
    for record in history:
        text = (record.items_done or "").upper()
        tokens = set(re.findall(r"[A-Z0-9_]{2,50}", text))
        found.update(tokens & valid_codes)
    return found


class MaintenancePackageService:
    """Application service combining existing vehicle and estimate services."""

    def __init__(
        self,
        session: Session,
        vehicles: UserVehicleService,
        estimates: CostEstimationService,
    ) -> None:
        self._db = session
        self._vehicles = vehicles
        self._estimates = estimates

    def recommend(
        self,
        user: VehicleUser,
        vehicle: UserVehicle,
        *,
        workshop_id: UUID | None,
        budget_vnd: Decimal | None = None,
        available_minutes: int | None = None,
        priority: str = "BALANCED",
    ) -> dict[str, Any]:
        status = self._vehicles.get_maintenance_status(vehicle)
        milestone = status.next_milestone
        if status.due_status == "UNKNOWN" or milestone is None:
            return {
                "status": "INSUFFICIENT_DATA",
                "message": "Chưa đủ dữ liệu để xác định mốc bảo dưỡng và tạo gói.",
                "packages": [],
            }

        estimate = self._estimates.estimate_for_request(
            user,
            vehicle,
            odo_milestone=milestone.odo_milestone_km,
            workshop_id=workshop_id,
        )
        if estimate.status != "READY" or estimate.workshop is None:
            return {
                "status": "ESTIMATE_UNAVAILABLE",
                "message": "Chưa có dự toán đã xác minh để tạo gói.",
                "packages": [],
            }

        rules = list(
            self._db.exec(
                select(MaintenanceRule).where(
                    MaintenanceRule.model_id == vehicle.external_model_id,
                    MaintenanceRule.odo_milestone == milestone.odo_milestone_km,
                )
            ).all()
        )
        rule_by_code = {rule.item_code: rule for rule in rules}
        history = self._vehicles.list_service_records(vehicle).items
        completed_codes = _history_codes(history, set(rule_by_code))

        items: list[dict[str, Any]] = []
        for priced in estimate.items:
            rule = rule_by_code.get(priced.item_code)
            if rule is None:
                continue
            items.append(
                {
                    "item_code": priced.item_code,
                    "item_name": priced.item_name,
                    "tier": _tier(rule),
                    "price": str(priced.price),
                    "covered": priced.covered,
                    "price_source": priced.price_source,
                    "duration_minutes": rule.estimated_duration_minutes,
                    "seen_in_service_history": priced.item_code in completed_codes,
                }
            )

        # Every package needs a useful minimum. If the schedule has no known
        # safety marker, promote the first scheduled item without inventing one.
        if items and not any(item["tier"] == "REQUIRED" for item in items):
            items[0]["tier"] = "REQUIRED"

        required = [item for item in items if item["tier"] == "REQUIRED"]
        recommended = [item for item in items if item["tier"] == "RECOMMENDED"]
        optional = [item for item in items if item["tier"] == "OPTIONAL"]

        essential = list(required)
        # Package definitions are stable, so a package selected in one turn
        # can be revalidated when the proposal is created in a later turn.
        # Constraints select/reject a package; they never silently mutate it.
        balanced = required + recommended
        comprehensive = required + recommended + optional

        variants = (
            ("ESSENTIAL", essential),
            ("BALANCED", balanced),
            ("COMPREHENSIVE", comprehensive),
        )
        packages = [
            self._package(code, selected, items, budget_vnd, available_minutes)
            for code, selected in variants
        ]
        result = {
            "status": "READY",
            "source": "BACKEND_OPTIMIZER",
            "due_status": status.due_status,
            "milestone": {
                "odo_milestone_km": milestone.odo_milestone_km,
                "month_milestone": milestone.month_milestone,
            },
            "workshop": estimate.workshop.model_dump(mode="json"),
            "warranty_status": estimate.warranty_status,
            "currency": estimate.currency,
            "has_reference_price": estimate.has_reference_price,
            "constraints": {
                "budget_vnd": str(budget_vnd) if budget_vnd is not None else None,
                "available_minutes": available_minutes,
                "priority": priority,
            },
            "history": {
                "record_count": len(history),
                "matched_item_codes": sorted(completed_codes),
                "note": "Lịch sử chỉ dùng để giải thích; không tự loại hạng mục thuộc mốc hiện tại.",
            },
            "packages": packages,
            "recommended_package_code": self._recommended_code(packages, priority),
            "disclaimer": (
                "Đây là dự toán trước khi xưởng kiểm tra xe. Xưởng xác nhận tình trạng, phạm vi công việc và giá cuối cùng."
            ),
        }
        result["recommendation_token"] = self._token(result, status.remaining_km, status.remaining_days)
        return result

    @staticmethod
    def _token(result: dict[str, Any], remaining_km: int | None, remaining_days: int | None) -> str:
        """Fingerprint only server facts that define the offered packages.

        User constraints are intentionally excluded: package definitions are
        stable and the token protects the schedule, history, workshop and price
        snapshot that the owner actually reviewed.
        """
        source = {
            "due_status": result["due_status"],
            "remaining_km": remaining_km,
            "remaining_days": remaining_days,
            "milestone": result["milestone"],
            "workshop": result["workshop"],
            "warranty_status": result["warranty_status"],
            "has_reference_price": result["has_reference_price"],
            "history": result["history"],
            "packages": [
                {
                    "package_code": package["package_code"],
                    "items": package["items"],
                    "estimated_total": package["estimated_total"],
                    "estimated_duration_minutes": package["estimated_duration_minutes"],
                }
                for package in result["packages"]
            ],
        }
        payload = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _total(items: list[dict[str, Any]]) -> Decimal:
        return sum((Decimal(item["price"]) for item in items), Decimal(0))

    @classmethod
    def _within(
        cls,
        items: list[dict[str, Any]],
        budget_vnd: Decimal | None,
        available_minutes: int | None,
    ) -> bool:
        return (
            (budget_vnd is None or cls._total(items) <= budget_vnd)
            and (available_minutes is None or sum(item["duration_minutes"] for item in items) <= available_minutes)
        )

    @classmethod
    def _package(
        cls,
        code: str,
        selected: list[dict[str, Any]],
        all_items: list[dict[str, Any]],
        budget_vnd: Decimal | None,
        available_minutes: int | None,
    ) -> dict[str, Any]:
        selected_codes = {item["item_code"] for item in selected}
        total = cls._total(selected)
        duration = sum(item["duration_minutes"] for item in selected)
        required_total = cls._total([item for item in all_items if item["tier"] == "REQUIRED"])
        required_duration = sum(item["duration_minutes"] for item in all_items if item["tier"] == "REQUIRED")
        exceeds_minimum = (
            (budget_vnd is not None and required_total > budget_vnd)
            or (available_minutes is not None and required_duration > available_minutes)
        )
        fits = cls._within(selected, budget_vnd, available_minutes)
        return {
            "package_code": code,
            "name": _PACKAGE_LABELS[code],
            "items": selected,
            "item_codes": [item["item_code"] for item in selected],
            "omitted_item_codes": [item["item_code"] for item in all_items if item["item_code"] not in selected_codes],
            "estimated_total": str(total),
            "estimated_duration_minutes": duration,
            "constraint_status": "EXCEEDS_REQUIRED_MINIMUM" if exceeds_minimum else ("FITS" if fits else "EXCEEDS"),
        }

    @staticmethod
    def _recommended_code(packages: list[dict[str, Any]], priority: str) -> str | None:
        requested = priority.upper()
        if requested in _PACKAGE_LABELS:
            match = next(package for package in packages if package["package_code"] == requested)
            if match["constraint_status"] == "FITS":
                return requested
        balanced = next(package for package in packages if package["package_code"] == "BALANCED")
        if balanced["constraint_status"] == "FITS":
            return "BALANCED"
        essential = next(package for package in packages if package["package_code"] == "ESSENTIAL")
        return "ESSENTIAL" if essential["constraint_status"] == "FITS" else None
