"""add booking capacity: slot blocks + workshop confirmation mode (FEAT-BOOK-001, F6)

Implements ``docs/specs/sprint-3/entity/us-029-sprint-3-spec.entity.md``:

* ENT-418 ``workshop_slot_block`` — technician slots blocked by the workshop
  owner (BR-005 ``blocked`` term).
* ``workshop.booking_confirmation_mode`` — ``auto`` / ``manual`` (BR-014, Q-405).
* A ``BEFORE INSERT/UPDATE`` trigger on ``booking`` that rejects a slot beyond
  capacity (Q-ENT-451, PRD §8): it locks the workshop row (serialising all
  capacity-affecting writes per workshop) and recomputes the BR-005 formula.

Revision ID: e2b6a4c8d1f7
Revises: d9a3e5b7f2c1
Create Date: 2026-09-29
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2b6a4c8d1f7"
down_revision: str | Sequence[str] | None = "d9a3e5b7f2c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

confirmation_mode = postgresql.ENUM(
    "auto", "manual", name="booking_confirmation_mode_enum", create_type=False
)
slot_block_reason = postgresql.ENUM(
    "phone_booking", "walk_in", "maintenance", "other",
    name="slot_block_reason_enum", create_type=False,
)

# Statuses that occupy a technician slot (F6 BR-005).
_OCCUPYING = "('pending','confirmed','checked_in','in_progress')"

_CAPACITY_GUARD_FN = f"""
CREATE OR REPLACE FUNCTION booking_capacity_guard() RETURNS trigger AS $$
DECLARE
    capacity  integer;
    blocked   integer;
    occupied  integer;
BEGIN
    IF NEW.status NOT IN {_OCCUPYING} THEN
        RETURN NEW;
    END IF;

    -- Serialise every capacity-affecting write for this workshop (final guard
    -- behind the Redis lock + in-transaction re-check — F6 BR-001).
    SELECT total_technicians - emergency_slots_reserved
      INTO capacity
      FROM workshop
     WHERE id = NEW.workshop_id
     FOR UPDATE;

    IF capacity IS NULL THEN
        RETURN NEW;  -- unknown workshop: let the FK constraint reject it
    END IF;

    SELECT COALESCE(SUM(blocked_count), 0)
      INTO blocked
      FROM workshop_slot_block
     WHERE workshop_id = NEW.workshop_id
       AND block_date  = NEW.booking_date
       AND time_slot   = NEW.time_slot;

    SELECT COUNT(*)
      INTO occupied
      FROM booking
     WHERE workshop_id  = NEW.workshop_id
       AND booking_date = NEW.booking_date
       AND time_slot    = NEW.time_slot
       AND status IN {_OCCUPYING}
       AND id <> NEW.id;

    IF occupied + 1 > capacity - blocked THEN
        RAISE EXCEPTION 'SLOT_FULL: workshop % % % is at capacity',
            NEW.workshop_id, NEW.booking_date, NEW.time_slot
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_CAPACITY_GUARD_TRIGGER = """
CREATE TRIGGER trg_booking_capacity_guard
    BEFORE INSERT OR UPDATE OF status, workshop_id, booking_date, time_slot
    ON booking
    FOR EACH ROW EXECUTE FUNCTION booking_capacity_guard();
"""


def upgrade() -> None:
    bind = op.get_bind()

    # ── workshop.booking_confirmation_mode (BR-014, Q-405 default 'auto') ──
    confirmation_mode.create(bind, checkfirst=True)
    op.add_column(
        "workshop",
        sa.Column(
            "booking_confirmation_mode",
            confirmation_mode,
            nullable=False,
            server_default="auto",
        ),
    )

    # ── ENT-418 workshop_slot_block ───────────────────────────────────────
    slot_block_reason.create(bind, checkfirst=True)
    op.create_table(
        "workshop_slot_block",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "workshop_id",
            sa.Uuid(),
            sa.ForeignKey("workshop.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("block_date", sa.Date(), nullable=False),
        sa.Column("time_slot", sa.Time(), nullable=False),
        sa.Column("blocked_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("reason", slot_block_reason, server_default="other", nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column(
            "created_by",
            sa.Uuid(),
            sa.ForeignKey("workshop_owner.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("blocked_count > 0", name="ck_slot_block_count_positive"),
        sa.UniqueConstraint(
            "workshop_id", "block_date", "time_slot", name="ux_slot_block_ws_date_slot"
        ),
    )
    op.execute("ALTER TABLE workshop_slot_block ENABLE ROW LEVEL SECURITY")

    # ── Overbooking guard on booking (Q-ENT-451, PRD §8) ──────────────────
    op.execute(_CAPACITY_GUARD_FN)
    op.execute(_CAPACITY_GUARD_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_booking_capacity_guard ON booking")
    op.execute("DROP FUNCTION IF EXISTS booking_capacity_guard()")

    op.drop_table("workshop_slot_block")
    op.drop_column("workshop", "booking_confirmation_mode")

    bind = op.get_bind()
    slot_block_reason.drop(bind, checkfirst=True)
    confirmation_mode.drop(bind, checkfirst=True)
