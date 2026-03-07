"""add_custom_agents

Revision ID: c4e8b2f9a017
Revises: a1f4c8e9d203
Create Date: 2026-03-07 00:01:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e8b2f9a017'
down_revision = 'a1f4c8e9d203'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'custom_agents',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('emoji', sa.String(10), nullable=False, server_default='🤖'),
        sa.Column('description', sa.String(300), nullable=False, server_default=''),
        sa.Column('system_prompt', sa.Text(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['chat_users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_custom_agents_name'), 'custom_agents', ['name'], unique=True)


def downgrade():
    op.drop_index(op.f('ix_custom_agents_name'), table_name='custom_agents')
    op.drop_table('custom_agents')
