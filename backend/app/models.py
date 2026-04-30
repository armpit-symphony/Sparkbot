"""
SQLModel database models for the application.

Includes base template models and chat-specific models.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import Optional

from pydantic import EmailStr
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey, Enum, JSON
from sqlmodel import Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============== Base Template Models ==============

# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# Shared properties
class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


# Properties to receive on item creation
class ItemCreate(ItemBase):
    pass


# Properties to receive on item update
class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore


# Database model, database table inferred from class name
class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


# Properties to return via API, id is always required
class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# ============== Chat-Specific Models ==============

class UserType(str, PyEnum):
    HUMAN = "HUMAN"
    BOT = "BOT"


class RoomRole(str, PyEnum):
    OWNER = "OWNER"
    MOD = "MOD"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"
    BOT = "BOT"


class MeetingArtifactType(str, PyEnum):
    AGENDA = "agenda"
    NOTES = "notes"
    DECISIONS = "decisions"
    ACTION_ITEMS = "action_items"


# Database model for chat user
class ChatUser(SQLModel, table=True):
    """
    User model for the chat system.
    Separate from the main User model for template authentication.
    """
    __tablename__ = "chat_users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    username: str = Field(max_length=100, unique=True, nullable=False, index=True)
    hashed_password: Optional[str] = Field(default=None, max_length=255)  # Null for bots with service key only
    is_active: bool = Field(default=True)
    type: UserType = Field(default=UserType.HUMAN)
    
    # Bot-specific fields
    bot_service_key_hash: Optional[str] = Field(default=None, max_length=255)  # Hashed service key for bots
    bot_auto_mode: bool = Field(default=False)  # Auto-respond to all messages in joined rooms
    bot_display_name: Optional[str] = Field(default=None, max_length=100)  # Display name (e.g., "Sparkbot")
    bot_slug: Optional[str] = Field(default=None, max_length=50, unique=True, index=True)  # @sparkbot mention slug
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    owned_rooms: list["ChatRoom"] = Relationship(back_populates="owner")
    memberships: list["ChatRoomMember"] = Relationship(back_populates="user")
    messages: list["ChatMessage"] = Relationship(back_populates="sender")


# Database model for chat room
class ChatRoom(SQLModel, table=True):
    __tablename__ = "chat_rooms"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=200, nullable=False)
    description: Optional[str] = None
    created_by: uuid.UUID = Field(foreign_key="chat_users.id", nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Room persona — optional system-prompt prefix injected before every LLM call
    persona: Optional[str] = Field(default=None, max_length=500)

    # GO/NO-GO Gate per room
    execution_allowed: bool = Field(default=False)  # Room-level gate (default: NO-GO)

    # Meeting Mode
    meeting_mode_enabled: bool = Field(default=False)
    meeting_mode_bots_mention_only: bool = Field(default=True)
    meeting_mode_max_bot_msgs_per_min: int = Field(default=3)
    meeting_mode_note_taker_bot_slug: Optional[str] = Field(default=None, max_length=50)

    # Relationships
    owner: ChatUser = Relationship(back_populates="owned_rooms")
    members: list["ChatRoomMember"] = Relationship(back_populates="room", cascade_delete=True)
    messages: list["ChatMessage"] = Relationship(back_populates="room", cascade_delete=True)
    invites: list["ChatRoomInvite"] = Relationship(back_populates="room", cascade_delete=True)
    meeting_artifacts: list["ChatMeetingArtifact"] = Relationship(back_populates="room", cascade_delete=True)


# Database model for room membership
class ChatRoomMember(SQLModel, table=True):
    __tablename__ = "chat_room_members"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(foreign_key="chat_rooms.id", ondelete="CASCADE", nullable=False, index=True)
    user_id: uuid.UUID = Field(foreign_key="chat_users.id", nullable=False, index=True)
    role: RoomRole = Field(default=RoomRole.MEMBER)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    room: ChatRoom = Relationship(back_populates="members")
    user: ChatUser = Relationship(back_populates="memberships")


# Database model for messages
class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(foreign_key="chat_rooms.id", ondelete="CASCADE", nullable=False, index=True)
    sender_id: uuid.UUID = Field(foreign_key="chat_users.id", nullable=False, index=True)
    sender_type: UserType = Field(default=UserType.HUMAN)
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    
    # Bot message metadata (provider, mode, cost, latency, etc.)
    meta_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    
    # Message threading (optional)
    reply_to_id: Optional[uuid.UUID] = Field(default=None, foreign_key="chat_messages.id", nullable=True)
    
    # Relationships
    room: ChatRoom = Relationship(back_populates="messages")
    sender: ChatUser = Relationship(back_populates="messages")


# Database model for room invites
class ChatRoomInvite(SQLModel, table=True):
    __tablename__ = "chat_room_invites"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(foreign_key="chat_rooms.id", ondelete="CASCADE", nullable=False, index=True)
    token_hash: str = Field(max_length=255, nullable=False, unique=True)  # Hashed invite token
    created_by: uuid.UUID = Field(foreign_key="chat_users.id", nullable=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None  # Null = never expires
    usage_limit: Optional[int] = None
    used_count: int = Field(default=0)
    role: RoomRole = Field(default=RoomRole.MEMBER)

    # Relationships
    room: ChatRoom = Relationship(back_populates="invites")


# Database model for meeting artifacts
class ChatMeetingArtifact(SQLModel, table=True):
    __tablename__ = "chat_meeting_artifacts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(foreign_key="chat_rooms.id", ondelete="CASCADE", nullable=False, index=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by_user_id: uuid.UUID = Field(foreign_key="chat_users.id", nullable=False)
    type: MeetingArtifactType = Field(default=MeetingArtifactType.NOTES)
    window_start_ts: Optional[datetime] = None
    window_end_ts: Optional[datetime] = None
    content_markdown: str
    meta_json: Optional[dict] = Field(default=None, sa_column=Column(JSON))

    room: ChatRoom = Relationship(back_populates="meeting_artifacts")


class TaskStatus(str, PyEnum):
    OPEN = "open"
    DONE = "done"


class ChatTask(SQLModel, table=True):
    """
    Room-scoped task/todo item.

    Created from chat (via LLM tools) or the REST API.
    Tasks are visible to all room members and can be assigned to any member.
    """
    __tablename__ = "chat_tasks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(foreign_key="chat_rooms.id", ondelete="CASCADE", nullable=False, index=True)
    created_by: uuid.UUID = Field(foreign_key="chat_users.id", nullable=False)
    assigned_to: Optional[uuid.UUID] = Field(default=None, foreign_key="chat_users.id", nullable=True)
    title: str = Field(max_length=500)
    description: Optional[str] = Field(default=None)
    status: TaskStatus = Field(default=TaskStatus.OPEN)
    due_date: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    room: "ChatRoom" = Relationship()


class ReminderStatus(str, PyEnum):
    PENDING = "pending"
    FIRED = "fired"
    CANCELLED = "cancelled"


class ReminderRecurrence(str, PyEnum):
    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


class Reminder(SQLModel, table=True):
    """
    Scheduled bot message for a room.

    The background scheduler polls every 60 s and fires any reminder
    whose fire_at <= now and status == pending. Recurring reminders are
    rescheduled automatically after firing.
    """
    __tablename__ = "reminders"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    room_id: uuid.UUID = Field(foreign_key="chat_rooms.id", ondelete="CASCADE", nullable=False, index=True)
    created_by: uuid.UUID = Field(foreign_key="chat_users.id", nullable=False)
    message: str = Field(max_length=1000)
    fire_at: datetime = Field(index=True)
    recurrence: ReminderRecurrence = Field(default=ReminderRecurrence.ONCE)
    status: ReminderStatus = Field(default=ReminderStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserMemory(SQLModel, table=True):
    """
    Persistent per-user memory facts.

    The bot stores facts it learns about a user (name, timezone, preferences,
    ongoing projects, etc.) so they survive restarts and are injected into
    every system prompt for that user.
    """
    __tablename__ = "user_memories"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(index=True, nullable=False)
    fact: str = Field(max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    memory_type: str = Field(default="unknown", max_length=50, index=True)
    scope_type: str = Field(default="user", max_length=50)
    scope_id: Optional[str] = Field(default=None, max_length=120)
    lifecycle_state: str = Field(default="active", max_length=50, index=True)
    stale_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    archived_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    delete_proposed_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    delete_proposed_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    delete_approved_by: Optional[str] = Field(default=None, max_length=120)
    delete_approved_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    retention_policy: Optional[str] = Field(default=None, max_length=120)
    deprecated_by: Optional[str] = Field(default=None, max_length=120)
    deprecated_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    expires_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    pinned: bool = Field(default=False)
    last_used_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    last_retrieved_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    last_injected_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    use_count: int = Field(default=0)
    mention_count: int = Field(default=0)
    soft_deleted_at: Optional[datetime] = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore
    soft_delete_reason: Optional[str] = Field(default=None, sa_column=Column(Text))


class AuditLog(SQLModel, table=True):
    """
    Immutable record of every bot tool call.

    Captures who triggered it (user_id), which room, which tool, the input
    arguments, the result (truncated), and which agent/model was active.
    Used for accountability, debugging, and transparency.
    """
    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    user_id: Optional[uuid.UUID] = Field(default=None, index=True)
    room_id: Optional[uuid.UUID] = Field(default=None, index=True)
    tool_name: str = Field(index=True, max_length=100)
    tool_input: str = Field(default="{}")       # JSON-encoded args
    tool_result: str = Field(default="")         # truncated result (≤1000 chars)
    agent_name: Optional[str] = Field(default=None, max_length=50)
    model: Optional[str] = Field(default=None, max_length=100)


class CustomAgent(SQLModel, table=True):
    """User-spawned named agents stored in DB; loaded into runtime registry at startup."""
    __tablename__ = "custom_agents"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=50, nullable=False, sa_column_kwargs={"unique": True}, index=True)
    emoji: str = Field(max_length=10, default="🤖")
    description: str = Field(max_length=300, default="")
    system_prompt: str = Field(default="", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: Optional[uuid.UUID] = Field(default=None, foreign_key="chat_users.id")


# Re-export chat models for convenience
ChatUser.update_forward_refs()
ChatRoom.update_forward_refs()
ChatRoomMember.update_forward_refs()
ChatMessage.update_forward_refs()
ChatRoomInvite.update_forward_refs()
ChatMeetingArtifact.update_forward_refs()
