"""Policy telemetry and confirmed-booking attribution, without raw ODO.

Revision ID: c7d9b1e3f5a2
Revises: a9c4e2f6b8d1
"""

import sqlalchemy as sa

from alembic import op

revision = "c7d9b1e3f5a2"
down_revision = "a9c4e2f6b8d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reminder_policy_evaluation",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("vehicle_user.user_id"), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), sa.ForeignKey("user_vehicle.id"), nullable=False),
        sa.Column("evaluation_day", sa.Date(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("forecast_status", sa.String(40), nullable=False),
        sa.Column("baseline_level", sa.String(16)),
        sa.Column("candidate_level", sa.String(16)),
        sa.Column("actual_level", sa.String(16)),
        sa.Column("lead_days", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("algorithm_version", sa.String(32), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_vehicle_id", "evaluation_day", "mode", name="uq_usage_evaluation_vehicle_day_mode"),
        sa.CheckConstraint("duration_ms >= 0", name="ck_usage_evaluation_duration"),
        sa.CheckConstraint("mode IN ('shadow', 'on')", name="ck_usage_evaluation_mode"),
    )
    for name in ("user_id", "user_vehicle_id", "evaluation_day", "calculated_at"):
        op.create_index(f"ix_reminder_policy_evaluation_{name}", "reminder_policy_evaluation", [name])
    op.create_table(
        "reminder_booking_attribution",
        sa.Column("booking_id", sa.Uuid(), sa.ForeignKey("booking.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("reminder_id", sa.Uuid(), sa.ForeignKey("reminder.id", ondelete="SET NULL")),
        sa.Column("match_method", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("match_method IN ('DIRECT', 'RECENT_REMINDER')", name="ck_usage_attribution_method"),
    )
    for name in ("reminder_id", "confirmed_at"):
        op.create_index(f"ix_reminder_booking_attribution_{name}", "reminder_booking_attribution", [name])


def downgrade():
    op.drop_table("reminder_booking_attribution")
    op.drop_table("reminder_policy_evaluation")
