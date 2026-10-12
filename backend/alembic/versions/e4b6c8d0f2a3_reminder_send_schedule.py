"""Owner delivery windows and durable reminder scheduling.

Revision ID: e4b6c8d0f2a3
Revises: c7d9b1e3f5a2
"""

import sqlalchemy as sa

from alembic import op

revision = "e4b6c8d0f2a3"
down_revision = "c7d9b1e3f5a2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("email_outbox", sa.Column("uncertain_attempt_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE email_outbox SET uncertain_attempt_at = first_attempt_at WHERE accepted_at IS NULL")
    for name in ("preferred_send_time", "quiet_hours_start", "quiet_hours_end"):
        op.add_column("user_notification_setting", sa.Column(name, sa.String(5)))
    op.add_column(
        "user_notification_setting",
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Ho_Chi_Minh"),
    )
    for name in ("next_eligible_send_at", "schedule_expires_at", "lease_until"):
        op.add_column("reminder_delivery", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column("reminder_delivery", sa.Column("claim_token", sa.String(36)))
    op.create_index("ix_reminder_delivery_due", "reminder_delivery", ["next_eligible_send_at"])
    # Existing pending/retry rows become discoverable without changing feed time.
    op.execute(
        "UPDATE reminder_delivery SET next_eligible_send_at = CURRENT_TIMESTAMP WHERE status = 'pending' OR (status = 'failed' AND error_code IN ('TIMEOUT', 'RATE_LIMITED', 'UNAVAILABLE'))"
    )


def downgrade():
    op.drop_column("email_outbox", "uncertain_attempt_at")
    op.drop_index("ix_reminder_delivery_due", table_name="reminder_delivery")
    for name in ("claim_token", "lease_until", "schedule_expires_at", "next_eligible_send_at"):
        op.drop_column("reminder_delivery", name)
    for name in ("timezone", "quiet_hours_end", "quiet_hours_start", "preferred_send_time"):
        op.drop_column("user_notification_setting", name)
