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


# Re-export chat models for convenience
ChatUser.update_forward_refs()
ChatRoom.update_forward_refs()
ChatRoomMember.update_forward_refs()
ChatMessage.update_forward_refs()
ChatRoomInvite.update_forward_refs()
ChatMeetingArtifact.update_forward_refs()
