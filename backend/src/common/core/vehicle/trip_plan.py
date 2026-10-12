"""One owner-declared upcoming trip per vehicle; never an observed ODO record."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, ForeignKey, UniqueConstraint
from sqlmodel import Field, SQLModel


class VehicleTripPlan(SQLModel, table=True):
    __tablename__ = "vehicle_trip_plan"
    __table_args__ = (
        UniqueConstraint("user_vehicle_id", name="uq_vehicle_trip_plan_vehicle"),
        CheckConstraint("distance_km > 0 AND distance_km <= 20000", name="ck_trip_distance"),
        CheckConstraint("return_date IS NULL OR return_date >= departure_date", name="ck_trip_dates"),
    )
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_vehicle_id: UUID = Field(foreign_key="user_vehicle.id", nullable=False)
    user_id: int = Field(
        sa_column=Column(BigInteger, ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False)
    )
    departure_date: date
    return_date: date | None = None
    distance_km: int
    reminder_enabled: bool = False
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), sa_column=Column(DateTime(timezone=True), nullable=False)
    )
