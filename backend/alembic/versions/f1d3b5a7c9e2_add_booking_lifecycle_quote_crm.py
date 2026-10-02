"""add booking lifecycle, quote review and post-service CRM columns (sprint 3-4)

Implements the schema parts of:

* us-033 / us-037 — ``booking.attendance_confirmed_at``; ENT-426
  ``booking_status_event`` (append-only status history, BR-ENT-490..493).
* us-053 — ``booking.odo_milestone``, ``booking.reschedule_count``; ENT-428
  ``booking_reschedule``.
* us-049 — ``quote.submitted_at`` / ``result_seen_at``; ``quote_item``
  warranty / price-source / reviewer note; one pending quote per milestone.
* us-041 — ``follow_up`` answer + classification + closing columns (CHECKs
  rewritten); ``support_ticket`` priority / resolution note / started_at.
* us-057 — ``service_progress`` actor + source (``updated_by`` deprecated).

* us-033 — ENT-424 ``booking_reminder`` / ENT-425 ``booking_reminder_delivery``
  (24h appointment reminder job); us-041 — ``follow_up_delivery``.

Revision ID: f1d3b5a7c9e2
Revises: e2b6a4c8d1f7
Create Date: 2026-10-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

_NOW = sa.func.now()

# revision identifiers, used by Alembic.
revision: str = "f1d3b5a7c9e2"
down_revision: str | Sequence[str] | None = "e2b6a4c8d1f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

actor_type = postgresql.ENUM(
    "vehicle_owner", "workshop_owner", "system", name="booking_actor_type_enum", create_type=False
)
booking_status = postgresql.ENUM(name="booking_status_enum", create_type=False)
ticket_priority = postgresql.ENUM("normal", "high", name="support_ticket_priority_enum", create_type=False)
reminder_kind = postgresql.ENUM("before_24h", name="booking_reminder_kind_enum", create_type=False)
reminder_status = postgresql.ENUM(
    "scheduled", "sent", "failed", "skipped", name="booking_reminder_status_enum", create_type=False
)
channel = postgresql.ENUM(name="reminder_channel_enum", create_type=False)
delivery_status = postgresql.ENUM(name="notification_delivery_status_enum", create_type=False)


def _delivery_table(name: str, parent_col: str, parent_table: str, unique_name: str) -> None:
    """Per-channel delivery result, same shape as ``reminder_delivery`` (us-021)."""
    op.create_table(
        name,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            parent_col,
            sa.Uuid(),
            sa.ForeignKey(f"{parent_table}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", channel, nullable=False),
        sa.Column("status", delivery_status, server_default="pending", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.UniqueConstraint(parent_col, "channel", name=unique_name),
        sa.CheckConstraint("attempts >= 0", name=f"ck_{name}_attempts"),
        sa.CheckConstraint("status <> 'sent' OR sent_at IS NOT NULL", name=f"ck_{name}_sent_at"),
    )
    op.create_index(
        f"ix_{name}_retry",
        name,
        ["status", "attempts"],
        postgresql_where=sa.text("status = 'failed'"),
    )


def upgrade() -> None:
    bind = op.get_bind()
    actor_type.create(bind, checkfirst=True)
    ticket_priority.create(bind, checkfirst=True)

    # ── booking (us-033, us-053) ──────────────────────────────────────────
    op.add_column("booking", sa.Column("attendance_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("booking", sa.Column("odo_milestone", sa.Integer(), nullable=True))
    op.add_column(
        "booking",
        sa.Column("reschedule_count", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.create_check_constraint("ck_booking_odo_milestone", "booking", "odo_milestone IS NULL OR odo_milestone > 0")
    op.create_check_constraint("ck_booking_reschedule_count", "booking", "reschedule_count >= 0")

    # ── ENT-426 booking_status_event ─────────────────────────────────────
    op.create_table(
        "booking_status_event",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("booking_id", sa.Uuid(), sa.ForeignKey("booking.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", booking_status, nullable=True),
        sa.Column("to_status", booking_status, nullable=False),
        sa.Column("actor_type", actor_type, nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("vehicle_user.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_workshop_owner_id",
            sa.Uuid(),
            sa.ForeignKey("workshop_owner.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint("from_status IS DISTINCT FROM to_status", name="ck_bse_status_changed"),
        sa.CheckConstraint("to_status <> 'cancelled' OR reason_code IS NOT NULL", name="ck_bse_cancel_reason"),
        sa.CheckConstraint("reason_code IS DISTINCT FROM 'OTHER' OR note IS NOT NULL", name="ck_bse_other_note"),
        sa.CheckConstraint(
            "actor_type <> 'system' OR (actor_user_id IS NULL AND actor_workshop_owner_id IS NULL)",
            name="ck_bse_system_actor",
        ),
    )
    op.create_index("ix_bse_booking_created", "booking_status_event", ["booking_id", "created_at"])

    # ── ENT-428 booking_reschedule ───────────────────────────────────────
    op.create_table(
        "booking_reschedule",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("booking_id", sa.Uuid(), sa.ForeignKey("booking.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=False),
        sa.Column("from_time_slot", sa.Time(), nullable=False),
        sa.Column("to_date", sa.Date(), nullable=False),
        sa.Column("to_time_slot", sa.Time(), nullable=False),
        sa.Column("actor_type", actor_type, nullable=False),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("vehicle_user.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("chat_message.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.CheckConstraint(
            "to_date <> from_date OR to_time_slot <> from_time_slot",
            name="ck_booking_reschedule_changed",
        ),
    )
    op.create_index("ix_booking_reschedule_booking_created", "booking_reschedule", ["booking_id", "created_at"])

    # ── quote / quote_item (us-049) ──────────────────────────────────────
    op.add_column("quote", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("quote", sa.Column("result_seen_at", sa.DateTime(timezone=True), nullable=True))
    # Rows reviewed before this revision have no submission time: use created_at.
    op.execute("UPDATE quote SET submitted_at = created_at WHERE status <> 'draft'")
    op.create_check_constraint("ck_quote_submitted_at", "quote", "status = 'draft' OR submitted_at IS NOT NULL")
    op.create_check_constraint(
        "ck_quote_reviewed_after_submit",
        "quote",
        "reviewed_at IS NULL OR submitted_at IS NULL OR reviewed_at >= submitted_at",
    )
    op.create_index(
        "uq_quote_pending_per_milestone",
        "quote",
        ["user_vehicle_id", "workshop_id", "odo_milestone"],
        unique=True,
        postgresql_where=sa.text("status = 'pending_approval'"),
    )
    op.add_column(
        "quote_item",
        sa.Column("is_covered_by_warranty", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("quote_item", sa.Column("price_source", sa.String(20), nullable=True))
    op.add_column("quote_item", sa.Column("reviewer_note", sa.String(255), nullable=True))
    op.create_check_constraint(
        "ck_quote_item_covered_zero",
        "quote_item",
        "NOT is_covered_by_warranty OR (estimated_price = 0 AND (approved_price IS NULL OR approved_price = 0))",
    )

    # ── follow_up (us-041) ───────────────────────────────────────────────
    op.add_column("follow_up", sa.Column("rating", sa.SmallInteger(), nullable=True))
    op.add_column("follow_up", sa.Column("feedback_intent", sa.String(32), nullable=True))
    op.add_column("follow_up", sa.Column("classification_confidence", sa.Numeric(3, 2), nullable=True))
    op.add_column("follow_up", sa.Column("classified_by", sa.String(16), nullable=True))
    op.add_column("follow_up", sa.Column("closed_reason", sa.String(32), nullable=True))
    op.add_column("follow_up", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    # Legacy closed rows (if any) get a reason so the new CHECK holds.
    op.execute(
        "UPDATE follow_up SET closed_reason = 'PROCESSED', closed_at = updated_at "
        "WHERE status = 'closed' AND closed_reason IS NULL"
    )
    op.drop_constraint("ck_follow_up_sent_at", "follow_up", type_="check")
    op.create_check_constraint(
        "ck_follow_up_sent_at",
        "follow_up",
        "status = 'pending' OR sent_at IS NOT NULL OR closed_reason = 'NOT_ELIGIBLE'",
    )
    op.drop_constraint("ck_follow_up_responded", "follow_up", type_="check")
    op.create_check_constraint(
        "ck_follow_up_responded",
        "follow_up",
        "status <> 'responded' OR (responded_at IS NOT NULL AND rating IS NOT NULL)",
    )
    op.create_check_constraint("ck_follow_up_rating", "follow_up", "rating IS NULL OR rating BETWEEN 1 AND 5")
    op.create_check_constraint(
        "ck_follow_up_closed",
        "follow_up",
        "(status = 'closed') = (closed_reason IS NOT NULL AND closed_at IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_follow_up_confidence",
        "follow_up",
        "classification_confidence IS NULL OR classification_confidence BETWEEN 0 AND 1",
    )
    # NOT VALID: legacy PROCESSED rows may lack a rating; new rows are checked.
    op.execute(
        "ALTER TABLE follow_up ADD CONSTRAINT ck_follow_up_processed CHECK ("
        "closed_reason IS DISTINCT FROM 'PROCESSED' "
        "OR (rating IS NOT NULL AND responded_at IS NOT NULL AND classified_by IS NOT NULL)"
        ") NOT VALID"
    )
    op.create_index(
        "ix_follow_up_sent_sent_at",
        "follow_up",
        ["sent_at"],
        postgresql_where=sa.text("status = 'sent'"),
    )

    # ── support_ticket (us-041) ──────────────────────────────────────────
    op.add_column(
        "support_ticket",
        sa.Column("priority", ticket_priority, server_default="normal", nullable=False),
    )
    op.add_column("support_ticket", sa.Column("resolution_note", sa.Text(), nullable=True))
    op.add_column("support_ticket", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE support_ticket SET started_at = updated_at WHERE status = 'in_progress' AND started_at IS NULL")
    op.execute("UPDATE support_ticket SET resolution_note = '' WHERE status = 'resolved' AND resolution_note IS NULL")
    op.create_unique_constraint("ux_support_ticket_follow_up", "support_ticket", ["follow_up_id"])
    op.create_check_constraint(
        "ck_support_ticket_resolution",
        "support_ticket",
        "status <> 'resolved' OR resolution_note IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_support_ticket_started",
        "support_ticket",
        "status <> 'in_progress' OR started_at IS NOT NULL",
    )

    # ── service_progress (us-057) ────────────────────────────────────────
    op.add_column(
        "service_progress",
        sa.Column("actor_type", actor_type, server_default="system", nullable=False),
    )
    op.add_column(
        "service_progress",
        sa.Column(
            "actor_workshop_owner_id",
            sa.Uuid(),
            sa.ForeignKey("workshop_owner.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "service_progress",
        sa.Column("source", sa.String(32), server_default="BOARD", nullable=False),
    )
    op.create_check_constraint(
        "ck_service_progress_owner_actor",
        "service_progress",
        "actor_type <> 'workshop_owner' OR actor_workshop_owner_id IS NOT NULL",
    )
    op.execute(
        "ALTER TABLE service_progress ADD CONSTRAINT ck_service_progress_waiting_parts_note "
        "CHECK (stage <> 'waiting_parts' OR char_length(note) BETWEEN 10 AND 500) NOT VALID"
    )
    op.create_index("ix_service_progress_booking_created", "service_progress", ["booking_id", "created_at"])

    # ── ENT-424 / ENT-425 booking reminders (us-033) ─────────────────────
    reminder_kind.create(bind, checkfirst=True)
    reminder_status.create(bind, checkfirst=True)
    op.create_table(
        "booking_reminder",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("booking_id", sa.Uuid(), sa.ForeignKey("booking.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", reminder_kind, server_default="before_24h", nullable=False),
        sa.Column("appointment_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", reminder_status, server_default="scheduled", nullable=False),
        sa.Column("skip_reason", sa.String(32), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.UniqueConstraint("booking_id", "kind", "appointment_at", name="ux_booking_reminder_booking_kind_appt"),
        sa.CheckConstraint("scheduled_at < appointment_at", name="ck_booking_reminder_schedule_before_appt"),
        sa.CheckConstraint(
            "(status = 'skipped') = (skip_reason IS NOT NULL)",
            name="ck_booking_reminder_skip_reason",
        ),
        sa.CheckConstraint("status <> 'sent' OR sent_at IS NOT NULL", name="ck_booking_reminder_sent_at"),
    )
    op.create_index(
        "ix_booking_reminder_due",
        "booking_reminder",
        ["scheduled_at"],
        postgresql_where=sa.text("status = 'scheduled'"),
    )
    _delivery_table(
        "booking_reminder_delivery",
        "booking_reminder_id",
        "booking_reminder",
        "ux_booking_reminder_delivery_channel",
    )

    # ── follow_up_delivery (us-041) ──────────────────────────────────────
    _delivery_table("follow_up_delivery", "follow_up_id", "follow_up", "ux_follow_up_delivery_channel")


def downgrade() -> None:
    for name in ("follow_up_delivery", "booking_reminder_delivery"):
        op.drop_index(f"ix_{name}_retry", table_name=name)
        op.drop_table(name)
    op.drop_index("ix_booking_reminder_due", table_name="booking_reminder")
    op.drop_table("booking_reminder")

    op.drop_index("ix_service_progress_booking_created", table_name="service_progress")
    op.drop_constraint("ck_service_progress_waiting_parts_note", "service_progress", type_="check")
    op.drop_constraint("ck_service_progress_owner_actor", "service_progress", type_="check")
    op.drop_column("service_progress", "source")
    op.drop_column("service_progress", "actor_workshop_owner_id")
    op.drop_column("service_progress", "actor_type")

    op.drop_constraint("ck_support_ticket_started", "support_ticket", type_="check")
    op.drop_constraint("ck_support_ticket_resolution", "support_ticket", type_="check")
    op.drop_constraint("ux_support_ticket_follow_up", "support_ticket", type_="unique")
    op.drop_column("support_ticket", "started_at")
    op.drop_column("support_ticket", "resolution_note")
    op.drop_column("support_ticket", "priority")

    op.drop_index("ix_follow_up_sent_sent_at", table_name="follow_up")
    for name in (
        "ck_follow_up_processed",
        "ck_follow_up_confidence",
        "ck_follow_up_closed",
        "ck_follow_up_rating",
        "ck_follow_up_responded",
        "ck_follow_up_sent_at",
    ):
        op.drop_constraint(name, "follow_up", type_="check")
    op.create_check_constraint("ck_follow_up_sent_at", "follow_up", "status = 'pending' OR sent_at IS NOT NULL")
    op.create_check_constraint(
        "ck_follow_up_responded",
        "follow_up",
        "status <> 'responded' OR (responded_at IS NOT NULL AND customer_response IS NOT NULL)",
    )
    for column in (
        "closed_at",
        "closed_reason",
        "classified_by",
        "classification_confidence",
        "feedback_intent",
        "rating",
    ):
        op.drop_column("follow_up", column)

    op.drop_constraint("ck_quote_item_covered_zero", "quote_item", type_="check")
    op.drop_column("quote_item", "reviewer_note")
    op.drop_column("quote_item", "price_source")
    op.drop_column("quote_item", "is_covered_by_warranty")
    op.drop_index("uq_quote_pending_per_milestone", table_name="quote")
    op.drop_constraint("ck_quote_reviewed_after_submit", "quote", type_="check")
    op.drop_constraint("ck_quote_submitted_at", "quote", type_="check")
    op.drop_column("quote", "result_seen_at")
    op.drop_column("quote", "submitted_at")

    op.drop_index("ix_booking_reschedule_booking_created", table_name="booking_reschedule")
    op.drop_table("booking_reschedule")
    op.drop_index("ix_bse_booking_created", table_name="booking_status_event")
    op.drop_table("booking_status_event")

    op.drop_constraint("ck_booking_reschedule_count", "booking", type_="check")
    op.drop_constraint("ck_booking_odo_milestone", "booking", type_="check")
    op.drop_column("booking", "reschedule_count")
    op.drop_column("booking", "odo_milestone")
    op.drop_column("booking", "attendance_confirmed_at")

    bind = op.get_bind()
    reminder_status.drop(bind, checkfirst=True)
    reminder_kind.drop(bind, checkfirst=True)
    ticket_priority.drop(bind, checkfirst=True)
    actor_type.drop(bind, checkfirst=True)
