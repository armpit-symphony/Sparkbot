"""
Pydantic schemas for chat models.

Extends the base template schemas with chat-specific schemas.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import MeetingArtifactType, RoomRole, UserType


# ============== User Schemas ==============

class ChatUserBase(BaseModel):
    username: str = Field(..., max_length=100)
    type: UserType = UserType.HUMAN
    bot_display_name: Optional[str] = Field(None, max_length=100)
    bot_slug: Optional[str] = Field(None, max_length=50)
    bot_auto_mode: bool = False


class ChatUserCreate(ChatUserBase):
    password: Optional[str] = Field(None, min_length=8, max_length=128)


class ChatUserUpdate(BaseModel):
    username: Optional[str] = Field(None, max_length=100)
    bot_display_name: Optional[str] = Field(None, max_length=100)
    bot_auto_mode: Optional[bool] = None


class ChatUserResponse(ChatUserBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


# ============== Room Schemas ==============

class RoomBase(BaseModel):
    name: str = Field(..., max_length=200)
    description: Optional[str] = None


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    execution_allowed: Optional[bool] = None
    meeting_mode_enabled: Optional[bool] = None
    meeting_mode_bots_mention_only: Optional[bool] = None
    meeting_mode_max_bot_msgs_per_min: Optional[int] = None


class RoomResponse(RoomBase):
    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    execution_allowed: bool
    meeting_mode_enabled: bool
    meeting_mode_bots_mention_only: bool
    meeting_mode_max_bot_msgs_per_min: int

    class Config:
        from_attributes = True


class RoomDetailResponse(RoomResponse):
    owner: "ChatUserResponse"
    member_count: int
    message_count: int


# ============== Room Member Schemas ==============

class RoomMemberBase(BaseModel):
    role: RoomRole = RoomRole.MEMBER


class RoomMemberCreate(RoomMemberBase):
    user_id: UUID


class RoomMemberUpdate(BaseModel):
    role: RoomRole


class RoomMemberResponse(RoomMemberBase):
    id: UUID
    room_id: UUID
    user_id: UUID
    joined_at: datetime
    user: "ChatUserResponse"

    class Config:
        from_attributes = True


# ============== Message Schemas ==============

class MessageBase(BaseModel):
    content: str
    reply_to_id: Optional[UUID] = None


class MessageCreate(MessageBase):
    pass


class MessageUpdate(BaseModel):
    content: str


class MessageResponse(MessageBase):
    id: UUID
    room_id: UUID
    sender_id: UUID
    sender_type: UserType
    created_at: datetime
    meta_json: Optional[dict] = None
    sender_username: str
    sender_display_name: Optional[str] = None

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    total: int
    has_more: bool


# ============== Room Invite Schemas ==============

class RoomInviteBase(BaseModel):
    role: RoomRole = RoomRole.MEMBER
    usage_limit: Optional[int] = None
    expires_at: Optional[datetime] = None


class RoomInviteCreate(RoomInviteBase):
    pass


class RoomInviteResponse(RoomInviteBase):
    id: UUID
    room_id: UUID
    token_hash: str
    created_by: UUID
    created_at: datetime
    used_count: int

    class Config:
        from_attributes = True


class RoomInviteUse(BaseModel):
    invite_token: str


# ============== Meeting Artifact Schemas ==============

class MeetingArtifactBase(BaseModel):
    type: MeetingArtifactType
    window_start_ts: Optional[datetime] = None
    window_end_ts: Optional[datetime] = None
    content_markdown: str


class MeetingArtifactCreate(MeetingArtifactBase):
    pass


class MeetingArtifactResponse(MeetingArtifactBase):
    id: UUID
    room_id: UUID
    created_at: datetime
    created_by_user_id: UUID
    meta_json: Optional[dict] = None

    class Config:
        from_attributes = True


# Update forward references
RoomDetailResponse.model_rebuild()
RoomMemberResponse.model_rebuild()
