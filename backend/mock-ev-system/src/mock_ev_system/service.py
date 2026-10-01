"""Business logic / data access cho mock EV system.

Mỗi nhóm entity có một class Service, nhận Session qua constructor.
Router chỉ gọi service — không truy vấn DB trực tiếp.
"""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import String
from sqlmodel import Session, select

from .models import (
    MaintenanceItem,
    MaintenanceSchedule,
    Owner,
    ServiceCenter,
    ServiceHistory,
    Vehicle,
    VehicleModel,
    VehicleUsage,
    Warranty,
    WarrantyClaim,
    WarrantyPolicy,
)


# ── Vehicle & Owner ──────────────────────────────────────────────────


class VehicleService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_vehicles(self) -> list[Vehicle]:
        return list(self.session.exec(select(Vehicle)).all())

    def get_vehicle(self, vehicle_id: str) -> Vehicle | None:
        return self.session.get(Vehicle, vehicle_id)

    def get_vehicle_by_vin(self, vin: str) -> Vehicle | None:
        stmt = select(Vehicle).where(Vehicle.vin == vin)
        return self.session.exec(stmt).first()

    def get_vehicle_by_plate(self, license_plate: str) -> Vehicle | None:
        stmt = select(Vehicle).where(
            Vehicle.license_plate == license_plate
        )
        return self.session.exec(stmt).first()


class OwnerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_owners(self) -> list[Owner]:
        return list(self.session.exec(select(Owner)).all())

    def get_owner(self, owner_id: str) -> Owner | None:
        return self.session.get(Owner, owner_id)

    def get_owner_vehicles(self, owner_id: str) -> list[Vehicle]:
        stmt = select(Vehicle).where(
            Vehicle.current_owner_id == owner_id
        )
        return list(self.session.exec(stmt).all())


# ── Usage ────────────────────────────────────────────────────────────


class UsageService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_usage(self, vehicle_id: str) -> VehicleUsage | None:
        return self.session.get(VehicleUsage, vehicle_id)


# ── Warranty ─────────────────────────────────────────────────────────


class WarrantyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_policies_by_model(self, model_id: str) -> list[WarrantyPolicy]:
        stmt = select(WarrantyPolicy).where(
            WarrantyPolicy.model_id == model_id
        )
        return list(self.session.exec(stmt).all())

    def get_warranties_for_vehicle(
        self, vehicle_id: str
    ) -> list[Warranty]:
        stmt = select(Warranty).where(Warranty.vehicle_id == vehicle_id)
        return list(self.session.exec(stmt).all())

    def get_claims_for_vehicle(
        self, vehicle_id: str
    ) -> list[WarrantyClaim]:
        stmt = select(WarrantyClaim).where(
            WarrantyClaim.vehicle_id == vehicle_id
        )
        return list(self.session.exec(stmt).all())

    def get_claim(self, claim_id: str) -> WarrantyClaim | None:
        return self.session.get(WarrantyClaim, claim_id)


# ── Maintenance ──────────────────────────────────────────────────────


class MaintenanceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_schedule_by_model(
        self, model_id: str
    ) -> list[MaintenanceSchedule]:
        stmt = (
            select(MaintenanceSchedule)
            .where(MaintenanceSchedule.model_id == model_id)
            .order_by(MaintenanceSchedule.milestone_km)
        )
        return list(self.session.exec(stmt).all())

    def get_items_for_schedule(
        self, schedule_id: str
    ) -> list[MaintenanceItem]:
        stmt = select(MaintenanceItem).where(
            MaintenanceItem.schedule_id == schedule_id
        )
        return list(self.session.exec(stmt).all())

    def get_service_history(
        self, vehicle_id: str
    ) -> list[ServiceHistory]:
        stmt = (
            select(ServiceHistory)
            .where(ServiceHistory.vehicle_id == vehicle_id)
            .order_by(ServiceHistory.service_date.desc())  # type: ignore[union-attr]
        )
        return list(self.session.exec(stmt).all())

    def add_service_record(
        self,
        vehicle_id: str,
        service_center_id: str,
        service_date: date,
        km_at_service: int,
        items_done: str,
        total_cost: Decimal,
        is_periodic: bool = True,
    ) -> ServiceHistory:
        """Record a completed service visit (as a dealer system would)."""
        record = ServiceHistory(
            order_id=f"SH-{uuid4().hex[:8].upper()}",
            vehicle_id=vehicle_id,
            service_center_id=service_center_id,
            service_date=service_date,
            km_at_service=km_at_service,
            items_done=items_done,
            is_periodic=is_periodic,
            total_cost=total_cost,
        )
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def compute_next_maintenance(
        self, vehicle_id: str
    ) -> dict | None:
        """Tính mốc bảo dưỡng tiếp theo dựa trên km hiện tại & lịch sử."""
        vehicle = self.session.get(Vehicle, vehicle_id)
        if not vehicle:
            return None

        usage = self.session.get(VehicleUsage, vehicle_id)
        if not usage:
            return None

        current_km = usage.current_km

        # Lấy tất cả mốc cho model này
        schedules = self.get_schedule_by_model(vehicle.model_id)
        if not schedules:
            return None

        # Lấy lịch sử bảo dưỡng gần nhất
        history = self.get_service_history(vehicle_id)
        last_service_km = history[0].km_at_service if history else 0
        last_service_date = history[0].service_date if history else vehicle.manufacture_date

        # Tìm mốc tiếp theo: mốc nhỏ nhất có milestone_km > last_service_km
        next_schedule = None
        for s in schedules:
            if s.milestone_km > last_service_km:
                next_schedule = s
                break

        if not next_schedule:
            # Đã qua hết mốc — tính lại theo chu kỳ (quay vòng mốc đầu)
            cycle_km = schedules[0].milestone_km  # 10.000
            next_milestone_km = (
                (current_km // cycle_km) + 1
            ) * cycle_km
            next_schedule = schedules[0]  # dùng mốc đầu tiên
            overdue = current_km >= next_milestone_km
        else:
            next_milestone_km = next_schedule.milestone_km
            overdue = current_km >= next_milestone_km

        # Tính estimated cost
        items = self.get_items_for_schedule(next_schedule.schedule_id)
        estimated_cost = sum(
            item.reference_price
            for item in items
            if not item.is_covered_by_warranty
        )

        return {
            "vehicle_id": vehicle_id,
            "current_km": current_km,
            "last_service_km": last_service_km,
            "last_service_date": str(last_service_date),
            "next_milestone_km": next_milestone_km,
            "next_milestone_description": next_schedule.description,
            "km_until_next": max(0, next_milestone_km - current_km),
            "overdue": overdue,
            "estimated_cost": float(estimated_cost),
            "items": [
                {
                    "item_name": item.item_name,
                    "is_covered_by_warranty": item.is_covered_by_warranty,
                    "reference_price": float(item.reference_price),
                }
                for item in items
            ],
        }


# ── Lookup ───────────────────────────────────────────────────────────


class LookupService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_models(self) -> list[VehicleModel]:
        return list(self.session.exec(select(VehicleModel)).all())

    def get_model(self, model_id: str) -> VehicleModel | None:
        return self.session.get(VehicleModel, model_id)

    def list_service_centers(self) -> list[ServiceCenter]:
        return list(self.session.exec(select(ServiceCenter)).all())

    def get_service_center(self, center_id: str) -> ServiceCenter | None:
        return self.session.get(ServiceCenter, center_id)

    def get_service_center_by_manager_email(self, email: str) -> ServiceCenter | None:
        stmt = select(ServiceCenter).where(
            ServiceCenter.manager_email == email.strip().lower()
        )
        return self.session.exec(stmt).first()


# ── Data admin (bulk import / generic query) ─────────────────────────


# Entity name (as used by the API) → table model, in foreign-key order so a
# single import payload can contain parents and children together.
ENTITIES: dict[str, type] = {
    "vehicle_models": VehicleModel,
    "owners": Owner,
    "service_centers": ServiceCenter,
    "vehicles": Vehicle,
    "vehicle_usage": VehicleUsage,
    "warranty_policies": WarrantyPolicy,
    "warranties": Warranty,
    "warranty_claims": WarrantyClaim,
    "maintenance_schedules": MaintenanceSchedule,
    "maintenance_items": MaintenanceItem,
    "service_history": ServiceHistory,
}
_MODEL_BY_TABLE = {model.__tablename__: model for model in ENTITIES.values()}


class DataImportError(ValueError):
    """A record could not be imported; carries where it failed."""

    def __init__(self, entity: str, index: int, message: str) -> None:
        super().__init__(f"{entity}[{index}]: {message}")
        self.entity = entity
        self.index = index
        self.message = message


class DataAdminService:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def primary_key(model: type) -> str:
        return model.__table__.primary_key.columns.keys()[0]

    def describe(self) -> list[dict]:
        result = []
        for name, model in ENTITIES.items():
            count = len(self.session.exec(select(model)).all())
            result.append({
                "entity": name,
                "table": model.__tablename__,
                "primary_key": self.primary_key(model),
                "fields": list(model.__table__.columns.keys()),
                "count": count,
            })
        return result

    def query(
        self, entity: str, filters: dict[str, str], limit: int, offset: int
    ) -> tuple[int, list[dict]]:
        model = ENTITIES[entity]
        columns = model.__table__.columns
        stmt = select(model)
        for field, value in filters.items():
            if field not in columns:
                raise KeyError(field)
            stmt = stmt.where(columns[field].cast(String) == value)
        rows = list(self.session.exec(stmt).all())
        page = rows[offset: offset + limit]
        return len(rows), [row.model_dump(mode="json") for row in page]

    def import_data(self, data: dict[str, list[dict]], mode: str) -> dict[str, dict]:
        """Insert or upsert records of several entities in one transaction.

        ``mode="insert"`` fails on an existing primary key; ``"upsert"`` replaces it.
        """
        unknown = set(data) - set(ENTITIES)
        if unknown:
            raise DataImportError(sorted(unknown)[0], -1, "unknown entity")

        summary: dict[str, dict] = {}
        try:
            for name, model in ENTITIES.items():
                records = data.get(name) or []
                if not records:
                    continue
                pk = self.primary_key(model)
                created = updated = 0
                for index, raw in enumerate(records):
                    try:
                        obj = model.model_validate(raw)
                    except Exception as exc:  # pydantic ValidationError
                        raise DataImportError(name, index, str(exc)) from exc
                    key = getattr(obj, pk)
                    if key is None:
                        raise DataImportError(name, index, f"missing primary key '{pk}'")
                    # SQLite does not enforce foreign keys by default — check them here.
                    for column in model.__table__.columns:
                        for fk in column.foreign_keys:
                            value = getattr(obj, column.key)
                            parent = fk.column.table
                            if value is not None and self.session.get(
                                _MODEL_BY_TABLE[parent.name], value
                            ) is None:
                                raise DataImportError(
                                    name, index, f"{column.key}={value} not found in {parent.name}"
                                )
                    existing = self.session.get(model, key)
                    if existing is not None:
                        if mode == "insert":
                            raise DataImportError(name, index, f"{pk}={key} already exists")
                        for field in model.__table__.columns.keys():
                            setattr(existing, field, getattr(obj, field))
                        self.session.add(existing)
                        updated += 1
                    else:
                        self.session.add(obj)
                        created += 1
                    try:
                        self.session.flush()
                    except Exception as exc:  # IntegrityError: FK / unique
                        raise DataImportError(name, index, str(getattr(exc, "orig", exc))) from exc
                summary[name] = {"created": created, "updated": updated}
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return summary

    def delete(self, entity: str, key: str) -> bool:
        obj = self.session.get(ENTITIES[entity], key)
        if obj is None:
            return False
        self.session.delete(obj)
        self.session.commit()
        return True

