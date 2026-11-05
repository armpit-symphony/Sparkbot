"""add_roundtable_runner_jobs

Roundtable runner pilot: jobs for agent seats, room pause state, seat presence.
See docs/roundtable-runner.md.

Revision ID: 5e7a1c3d9b20
Revises: 8b7c1e9d4a2f
Create Date: 2026-11-05 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "5e7a1c3d9b20"
down_revision = "8b7c1e9d4a2f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "roundtable_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("seat_id", sa.Uuid(), nullable=False),
        sa.Column("trigger_message_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(length=200), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("claim_token_hash", sa.String(length=128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("reply_message_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["seat_id"], ["chat_users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trigger_message_id"], ["chat_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seat_id", "trigger_message_id", name="uq_roundtable_jobs_seat_trigger"),
    )
    op.create_index(op.f("ix_roundtable_jobs_room_id"), "roundtable_jobs", ["room_id"], unique=False)
    op.create_index(op.f("ix_roundtable_jobs_seat_id"), "roundtable_jobs", ["seat_id"], unique=False)
    op.create_index(op.f("ix_roundtable_jobs_status"), "roundtable_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_roundtable_jobs_created_at"), "roundtable_jobs", ["created_at"], unique=False)

    op.create_table(
        "roundtable_room_state",
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("changed_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["chat_rooms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("room_id"),
    )

    op.create_table(
        "roundtable_seat_presence",
        sa.Column("seat_id", sa.Uuid(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["seat_id"], ["chat_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("seat_id"),
    )


def downgrade():
    op.drop_table("roundtable_seat_presence")
    op.drop_table("roundtable_room_state")
    op.drop_index(op.f("ix_roundtable_jobs_created_at"), table_name="roundtable_jobs")
    op.drop_index(op.f("ix_roundtable_jobs_status"), table_name="roundtable_jobs")
    op.drop_index(op.f("ix_roundtable_jobs_seat_id"), table_name="roundtable_jobs")
    op.drop_index(op.f("ix_roundtable_jobs_room_id"), table_name="roundtable_jobs")
    op.drop_table("roundtable_jobs")
