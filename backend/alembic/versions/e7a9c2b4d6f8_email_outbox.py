"""Maintenance-email outbox and reminder snapshot.

Revision ID: e7a9c2b4d6f8
Revises: d4f1a7c3e9b2
"""

import sqlalchemy as sa

from alembic import op

revision = "e7a9c2b4d6f8"
down_revision = "d4f1a7c3e9b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reminder", sa.Column("details", sa.JSON(), nullable=True))
    op.add_column("reminder", sa.Column("resolution_reason", sa.String(32), nullable=True))
    # Freeze the schema here so later model changes cannot change this revision.
    op.create_table(
        "email_vehicle_gate",
        sa.Column("user_vehicle_id", sa.Uuid(), sa.ForeignKey("user_vehicle.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "email_outbox",
        sa.Column(
            "delivery_id", sa.Uuid(), sa.ForeignKey("reminder_delivery.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("vehicle_user.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_vehicle_id", sa.Uuid(), sa.ForeignKey("user_vehicle.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("recipient_hash", sa.String(64), nullable=False),
        sa.Column("recipient", sa.String(255)),
        sa.Column("payload", sa.JSON()),
        sa.Column("provider_message_id", sa.String(255), unique=True),
        sa.Column("delivery_state", sa.String(32), nullable=False),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("retry_until", sa.DateTime(timezone=True)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("claim_token", sa.String(36)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in ("user_id", "user_vehicle_id", "recipient_hash", "delivery_state", "next_attempt_at"):
        op.create_index(f"ix_email_outbox_{column}", "email_outbox", [column])
    op.create_table(
        "email_suppression",
        sa.Column("recipient_hash", sa.String(64), primary_key=True),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "email_webhook_event",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("provider_message_id", sa.String(255), nullable=False),
        sa.Column("delivery_id", sa.Uuid()),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("recipient_hash", sa.String(64)),
        sa.Column("source_at", sa.DateTime(timezone=True)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
    )
    for column in ("provider_message_id", "delivery_id"):
        op.create_index(f"ix_email_webhook_event_{column}", "email_webhook_event", [column])


def downgrade():
    for name in ("email_webhook_event", "email_suppression", "email_outbox", "email_vehicle_gate"):
        op.drop_table(name)
    op.drop_column("reminder", "resolution_reason")
    op.drop_column("reminder", "details")
