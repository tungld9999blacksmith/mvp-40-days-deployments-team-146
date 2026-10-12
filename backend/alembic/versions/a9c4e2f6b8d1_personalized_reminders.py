"""Opt-in driving usage reminders and minimal consent audit."""

import sqlalchemy as sa

from alembic import op

revision = "a9c4e2f6b8d1"
down_revision = "f8b2d6a4c1e9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("user_notification_setting") as batch:
        batch.add_column(
            sa.Column("personalized_reminders_enabled", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch.add_column(sa.Column("personalization_policy_version", sa.String(64)))
        batch.add_column(sa.Column("personalization_consent_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("personalization_revoked_at", sa.DateTime(timezone=True)))
    op.create_table(
        "reminder_personalization_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('GRANTED', 'REVOKED', 'DERIVED_DATA_DELETED')", name="ck_personalization_action"
        ),
    )
    op.create_index("ix_reminder_personalization_event_user_id", "reminder_personalization_event", ["user_id"])
    op.create_index("ix_reminder_personalization_event_occurred_at", "reminder_personalization_event", ["occurred_at"])


def downgrade():
    op.drop_table("reminder_personalization_event")
    with op.batch_alter_table("user_notification_setting") as batch:
        for column in (
            "personalization_revoked_at",
            "personalization_consent_at",
            "personalization_policy_version",
            "personalized_reminders_enabled",
        ):
            batch.drop_column(column)
