"""create_chat_tables

Revision ID: 2c8b4e0f1a7d
Revises: b3197ab91f7c
Create Date: 2026-03-05 12:00:00.000000

This migration was reconstructed. The original was never committed —
it existed only in the developer's local DB (same pattern as _write_test).
All six chat tables are created here in FK-dependency order.

Note: chat_rooms.persona is NOT included here; it is added by a1f4c8e9d203.
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '2c8b4e0f1a7d'
down_revision = 'b3197ab91f7c'
branch_labels = None
depends_on = None


def upgrade():
    # Create shared PostgreSQL enum types up front to avoid double-create
    # when the same type is referenced by more than one table below.
    op.execute("CREATE TYPE usertype AS ENUM ('HUMAN', 'BOT')")
    op.execute("CREATE TYPE roomrole AS ENUM ('OWNER', 'MOD', 'MEMBER', 'VIEWER', 'BOT')")
    op.execute("CREATE TYPE meetingartifacttype AS ENUM ('AGENDA', 'NOTES', 'DECISIONS', 'ACTION_ITEMS')")

    usertype = sa.Enum('HUMAN', 'BOT', name='usertype', create_type=False)
    roomrole = sa.Enum('OWNER', 'MOD', 'MEMBER', 'VIEWER', 'BOT', name='roomrole', create_type=False)
    meetingartifacttype = sa.Enum('AGENDA', 'NOTES', 'DECISIONS', 'ACTION_ITEMS', name='meetingartifacttype', create_type=False)

    # 1. chat_users — no FK dependencies on other chat tables
    op.create_table('chat_users',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('username', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('hashed_password', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('type', usertype, nullable=False),
        sa.Column('bot_service_key_hash', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('bot_auto_mode', sa.Boolean(), nullable=False),
        sa.Column('bot_display_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('bot_slug', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
        sa.UniqueConstraint('bot_slug'),
    )
    op.create_index(op.f('ix_chat_users_username'), 'chat_users', ['username'], unique=True)
    op.create_index(op.f('ix_chat_users_bot_slug'), 'chat_users', ['bot_slug'], unique=True)

    # 2. chat_rooms — FK → chat_users.id
    # Note: persona column is added later by migration a1f4c8e9d203
    op.create_table('chat_rooms',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('execution_allowed', sa.Boolean(), nullable=False),
        sa.Column('meeting_mode_enabled', sa.Boolean(), nullable=False),
        sa.Column('meeting_mode_bots_mention_only', sa.Boolean(), nullable=False),
        sa.Column('meeting_mode_max_bot_msgs_per_min', sa.Integer(), nullable=False),
        sa.Column('meeting_mode_note_taker_bot_slug', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['chat_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # 3. chat_room_members — FK → chat_rooms.id (CASCADE), chat_users.id
    op.create_table('chat_room_members',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('room_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('role', roomrole, nullable=False),
        sa.Column('joined_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['room_id'], ['chat_rooms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['chat_users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_room_members_room_id'), 'chat_room_members', ['room_id'], unique=False)
    op.create_index(op.f('ix_chat_room_members_user_id'), 'chat_room_members', ['user_id'], unique=False)

    # 4. chat_messages — FK → chat_rooms.id (CASCADE), chat_users.id, chat_messages.id (self-ref)
    op.create_table('chat_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('room_id', sa.Uuid(), nullable=False),
        sa.Column('sender_id', sa.Uuid(), nullable=False),
        sa.Column('sender_type', usertype, nullable=False),
        sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('meta_json', sa.JSON(), nullable=True),
        sa.Column('reply_to_id', sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(['room_id'], ['chat_rooms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sender_id'], ['chat_users.id']),
        sa.ForeignKeyConstraint(['reply_to_id'], ['chat_messages.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_messages_room_id'), 'chat_messages', ['room_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_sender_id'), 'chat_messages', ['sender_id'], unique=False)
    op.create_index(op.f('ix_chat_messages_created_at'), 'chat_messages', ['created_at'], unique=False)

    # 5. chat_room_invites — FK → chat_rooms.id (CASCADE), chat_users.id
    op.create_table('chat_room_invites',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('room_id', sa.Uuid(), nullable=False),
        sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('usage_limit', sa.Integer(), nullable=True),
        sa.Column('used_count', sa.Integer(), nullable=False),
        sa.Column('role', roomrole, nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['chat_users.id']),
        sa.ForeignKeyConstraint(['room_id'], ['chat_rooms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash'),
    )
    op.create_index(op.f('ix_chat_room_invites_room_id'), 'chat_room_invites', ['room_id'], unique=False)

    # 6. chat_meeting_artifacts — FK → chat_rooms.id (CASCADE), chat_users.id
    op.create_table('chat_meeting_artifacts',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('room_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=False),
        sa.Column('type', meetingartifacttype, nullable=False),
        sa.Column('window_start_ts', sa.DateTime(), nullable=True),
        sa.Column('window_end_ts', sa.DateTime(), nullable=True),
        sa.Column('content_markdown', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('meta_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['chat_users.id']),
        sa.ForeignKeyConstraint(['room_id'], ['chat_rooms.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_chat_meeting_artifacts_room_id'), 'chat_meeting_artifacts', ['room_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_chat_meeting_artifacts_room_id'), table_name='chat_meeting_artifacts')
    op.drop_table('chat_meeting_artifacts')

    op.drop_index(op.f('ix_chat_room_invites_room_id'), table_name='chat_room_invites')
    op.drop_table('chat_room_invites')

    op.drop_index(op.f('ix_chat_messages_created_at'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_sender_id'), table_name='chat_messages')
    op.drop_index(op.f('ix_chat_messages_room_id'), table_name='chat_messages')
    op.drop_table('chat_messages')

    op.drop_index(op.f('ix_chat_room_members_user_id'), table_name='chat_room_members')
    op.drop_index(op.f('ix_chat_room_members_room_id'), table_name='chat_room_members')
    op.drop_table('chat_room_members')

    op.drop_table('chat_rooms')

    op.drop_index(op.f('ix_chat_users_bot_slug'), table_name='chat_users')
    op.drop_index(op.f('ix_chat_users_username'), table_name='chat_users')
    op.drop_table('chat_users')

    op.execute("DROP TYPE IF EXISTS meetingartifacttype")
    op.execute("DROP TYPE IF EXISTS roomrole")
    op.execute("DROP TYPE IF EXISTS usertype")
