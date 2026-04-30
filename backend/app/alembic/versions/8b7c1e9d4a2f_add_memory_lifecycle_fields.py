"""add_memory_lifecycle_fields

Revision ID: 8b7c1e9d4a2f
Revises: c4e8b2f9a017
Create Date: 2026-04-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8b7c1e9d4a2f"
down_revision = "c4e8b2f9a017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_memories", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("memory_type", sa.String(length=50), nullable=False, server_default="unknown"))
    op.add_column("user_memories", sa.Column("scope_type", sa.String(length=50), nullable=False, server_default="user"))
    op.add_column("user_memories", sa.Column("scope_id", sa.String(length=120), nullable=True))
    op.add_column("user_memories", sa.Column("lifecycle_state", sa.String(length=50), nullable=False, server_default="active"))
    op.add_column("user_memories", sa.Column("stale_reason", sa.Text(), nullable=True))
    op.add_column("user_memories", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("delete_proposed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("delete_proposed_reason", sa.Text(), nullable=True))
    op.add_column("user_memories", sa.Column("delete_approved_by", sa.String(length=120), nullable=True))
    op.add_column("user_memories", sa.Column("delete_approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("retention_policy", sa.String(length=120), nullable=True))
    op.add_column("user_memories", sa.Column("deprecated_by", sa.String(length=120), nullable=True))
    op.add_column("user_memories", sa.Column("deprecated_reason", sa.Text(), nullable=True))
    op.add_column("user_memories", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_memories", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("last_retrieved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("last_injected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_memories", sa.Column("mention_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_memories", sa.Column("soft_deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_memories", sa.Column("soft_delete_reason", sa.Text(), nullable=True))
    op.execute("UPDATE user_memories SET updated_at = created_at WHERE updated_at IS NULL")
    op.create_index(op.f("ix_user_memories_memory_type"), "user_memories", ["memory_type"], unique=False)
    op.create_index(op.f("ix_user_memories_lifecycle_state"), "user_memories", ["lifecycle_state"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_user_memories_lifecycle_state"), table_name="user_memories")
    op.drop_index(op.f("ix_user_memories_memory_type"), table_name="user_memories")
    op.drop_column("user_memories", "soft_delete_reason")
    op.drop_column("user_memories", "soft_deleted_at")
    op.drop_column("user_memories", "mention_count")
    op.drop_column("user_memories", "use_count")
    op.drop_column("user_memories", "last_injected_at")
    op.drop_column("user_memories", "last_retrieved_at")
    op.drop_column("user_memories", "last_used_at")
    op.drop_column("user_memories", "pinned")
    op.drop_column("user_memories", "expires_at")
    op.drop_column("user_memories", "deprecated_reason")
    op.drop_column("user_memories", "deprecated_by")
    op.drop_column("user_memories", "retention_policy")
    op.drop_column("user_memories", "delete_approved_at")
    op.drop_column("user_memories", "delete_approved_by")
    op.drop_column("user_memories", "delete_proposed_reason")
    op.drop_column("user_memories", "delete_proposed_at")
    op.drop_column("user_memories", "archived_at")
    op.drop_column("user_memories", "stale_reason")
    op.drop_column("user_memories", "lifecycle_state")
    op.drop_column("user_memories", "scope_id")
    op.drop_column("user_memories", "scope_type")
    op.drop_column("user_memories", "memory_type")
    op.drop_column("user_memories", "updated_at")
