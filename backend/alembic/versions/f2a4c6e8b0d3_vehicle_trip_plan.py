"""Owner-declared trips for pre-departure maintenance advice.

Revision ID: f2a4c6e8b0d3
Revises: e4b6c8d0f2a3
"""

import sqlalchemy as sa

from alembic import op

revision = "f2a4c6e8b0d3"
down_revision = "e4b6c8d0f2a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "vehicle_trip_plan",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_vehicle_id", sa.Uuid(), sa.ForeignKey("user_vehicle.id"), nullable=False),
        sa.Column(
            "user_id", sa.BigInteger(), sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("departure_date", sa.Date(), nullable=False),
        sa.Column("return_date", sa.Date()),
        sa.Column("distance_km", sa.Integer(), nullable=False),
        sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_vehicle_id", name="uq_vehicle_trip_plan_vehicle"),
        sa.CheckConstraint("distance_km > 0 AND distance_km <= 20000", name="ck_trip_distance"),
        sa.CheckConstraint("return_date IS NULL OR return_date >= departure_date", name="ck_trip_dates"),
    )


def downgrade():
    op.drop_table("vehicle_trip_plan")
