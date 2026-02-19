"""
API routes for chat users.

Handles user CRUD operations for the chat system.
"""
from datetime import timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import CurrentChatUser, SessionDep
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models import ChatUser, UserType
from app.schemas.chat import ChatUserCreate, ChatUserResponse, ChatUserUpdate

router = APIRouter(prefix="/users", tags=["chat-users"])


class ChatLoginRequest(BaseModel):
    """Request body for chat passphrase login."""
    passphrase: str


class ChatLoginResponse(BaseModel):
    """Response for successful chat login."""
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=ChatLoginResponse)
def chat_login(request: ChatLoginRequest) -> ChatLoginResponse:
    """
    Simple passphrase login for Sparkbot chat access.

    Takes a passphrase and returns a JWT token if valid.
    """
    if not request.passphrase:
        raise HTTPException(
            status_code=400,
            detail="Passphrase required"
        )

    if request.passphrase != settings.SPARKBOT_PASSPHRASE:
        raise HTTPException(
            status_code=401,
            detail="Invalid passphrase"
        )

    # Create access token for chat user
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject="sparkbot-user",
        expires_delta=access_token_expires
    )

    return ChatLoginResponse(
        access_token=access_token,
        token_type="bearer"
    )


@router.get("/", response_model=list[ChatUserResponse])
def read_chat_users(session: SessionDep, skip: int = 0, limit: int = 100) -> Any:
    """Retrieve all chat users."""
    users = session.exec(
        select(ChatUser)
        .order_by(ChatUser.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return users


@router.get("/{user_id}", response_model=ChatUserResponse)
def read_chat_user_by_id(user_id: UUID, session: SessionDep) -> Any:
    """Get a specific user by ID."""
    user = session.get(ChatUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/username/{username}", response_model=ChatUserResponse)
def read_chat_user_by_username(username: str, session: SessionDep) -> Any:
    """Get a specific user by username."""
    user = session.exec(
        select(ChatUser).where(ChatUser.username == username)
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/slug/{slug}", response_model=ChatUserResponse)
def read_chat_user_by_slug(slug: str, session: SessionDep) -> Any:
    """Get a bot user by slug."""
    user = session.exec(
        select(ChatUser).where(ChatUser.bot_slug == slug)
    ).first()
    if not user:
        raise HTTPException(status_code=404, detail="Bot not found")
    return user


@router.post("/", response_model=ChatUserResponse)
def create_chat_user(
    *,
    session: SessionDep,
    user_in: ChatUserCreate,
    current_user: CurrentChatUser,
) -> Any:
    """Create a new chat user (admin only)."""
    # Check if username exists
    existing = session.exec(
        select(ChatUser).where(ChatUser.username == user_in.username)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")
    
    user = ChatUser(
        username=user_in.username,
        type=user_in.type,
        bot_display_name=user_in.bot_display_name,
        bot_slug=user_in.bot_slug,
        bot_auto_mode=user_in.bot_auto_mode,
        hashed_password=get_password_hash(user_in.password) if user_in.password else None,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.patch("/{user_id}", response_model=ChatUserResponse)
def update_chat_user(
    *,
    session: SessionDep,
    user_id: UUID,
    user_in: ChatUserUpdate,
    current_user: CurrentChatUser,
) -> Any:
    """Update a user."""
    user = session.get(ChatUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if user_in.username:
        # Check if new username is taken
        existing = session.exec(
            select(ChatUser).where(ChatUser.username == user_in.username)
        ).first()
        if existing and existing.id != user_id:
            raise HTTPException(status_code=409, detail="Username already exists")
        user.username = user_in.username
    
    if user_in.bot_display_name is not None:
        user.bot_display_name = user_in.bot_display_name
    if user_in.bot_auto_mode is not None:
        user.bot_auto_mode = user_in.bot_auto_mode
    
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.delete("/{user_id}")
def delete_chat_user(
    *,
    session: SessionDep,
    user_id: UUID,
    current_user: CurrentChatUser,
) -> dict:
    """Delete a user."""
    user = session.get(ChatUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    session.delete(user)
    session.commit()
    return {"message": "User deleted successfully"}


class BootstrapResponse(BaseModel):
    """Response for bootstrap endpoint."""
    room_id: str
    room_name: str


@router.post("/bootstrap", response_model=BootstrapResponse)
def chat_bootstrap(
    *,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> BootstrapResponse:
    """
    Bootstrap chat: ensure Sparkbot DM room exists and return it.
    
    Creates a DM room with the bot user if it doesn't exist,
    ensures both the user and bot are members.
    """
    from app.models import ChatRoom, ChatRoomMember, RoomRole
    from app.crud import get_chat_user_by_username
    
    # Find or create bot user
    bot_user = get_chat_user_by_username(session, "sparkbot")
    if not bot_user:
        # Create bot user
        bot_user = ChatUser(
            username="sparkbot",
            user_type=UserType.BOT,
            passphrase_hash=get_password_hash("sparkbot"),
        )
        session.add(bot_user)
        session.commit()
        session.refresh(bot_user)
    
    # Find or create Sparkbot DM room (DM between user and bot)
    room_name = f"Sparkbot DM"
    
    # Check if room already exists for this user
    existing_room = session.execute(
        select(ChatRoom)
        .where(ChatRoom.name == room_name)
        .join(ChatRoomMember, ChatRoom.id == ChatRoomMember.room_id)
        .where(ChatRoomMember.user_id == current_user.id)
    ).first()
    
    if existing_room:
        room = existing_room[0]
    else:
        # Create new room
        room = ChatRoom(
            name=room_name,
            created_by=current_user.id,
            is_direct_message=True,
        )
        session.add(room)
        session.commit()
        session.refresh(room)
        
        # Add user as member
        user_member = ChatRoomMember(
            room_id=room.id,
            user_id=current_user.id,
            role=RoomRole.OWNER,
        )
        session.add(user_member)
        
        # Add bot as member
        bot_member = ChatRoomMember(
            room_id=room.id,
            user_id=bot_user.id,
            role=RoomRole.MEMBER,
        )
        session.add(bot_member)
        session.commit()
    
    return BootstrapResponse(room_id=str(room.id), room_name=room.name)
