"""add_room_persona

Revision ID: a1f4c8e9d203
Revises: 744de3c4a850
Create Date: 2026-03-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1f4c8e9d203'
down_revision = '744de3c4a850'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_rooms', sa.Column('persona', sa.String(500), nullable=True))


def downgrade():
    op.drop_column('chat_rooms', 'persona')
