"""
API routes for chat users.

Handles user CRUD operations for the chat system.
"""
import time
from collections import defaultdict
from datetime import timedelta
from threading import Lock
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import CurrentChatUser, SessionDep
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models import ChatUser, UserType
from app.schemas.chat import ChatUserCreate, ChatUserResponse, ChatUserUpdate
from app.services.guardian import get_guardian_suite

router = APIRouter(prefix="/users", tags=["chat-users"])

_chat_login_attempts: dict[str, list[float]] = defaultdict(list)
_chat_rate_lock = Lock()
_CHAT_MAX_ATTEMPTS = 5
_CHAT_WINDOW_SECONDS = 15 * 60


def _check_chat_rate_limit(ip: str) -> None:
    now = time.time()
    with _chat_rate_lock:
        _chat_login_attempts[ip] = [
            ts for ts in _chat_login_attempts[ip] if now - ts < _CHAT_WINDOW_SECONDS
        ]
        if len(_chat_login_attempts[ip]) >= _CHAT_MAX_ATTEMPTS:
            raise HTTPException(
                status_code=429,
                detail="Too many chat login attempts. Try again later.",
                headers={"Retry-After": str(_CHAT_WINDOW_SECONDS)},
            )


def _record_failed_chat_attempt(ip: str) -> None:
    with _chat_rate_lock:
        _chat_login_attempts[ip].append(time.time())


def _get_or_create_chat_user(
    session: SessionDep,
    *,
    username: str,
    user_type: UserType = UserType.HUMAN,
    bot_display_name: str | None = None,
    bot_slug: str | None = None,
) -> ChatUser:
    user = session.execute(
        select(ChatUser).where(ChatUser.username == username)
    ).scalar_one_or_none()
    if user:
        return user

    user = ChatUser(
        username=username,
        type=user_type,
        is_active=True,
        hashed_password=None,
        bot_display_name=bot_display_name,
        bot_slug=bot_slug,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class ChatLoginRequest(BaseModel):
    """Request body for chat passphrase login."""
    passphrase: str


class ChatLoginResponse(BaseModel):
    """Response for successful chat login."""
    access_token: str
    token_type: str = "bearer"


_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _is_local_request(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in _LOCAL_HOSTS


@router.post("/login")
def chat_login(request: Request, body: ChatLoginRequest, session: SessionDep) -> Response:
    """
    Simple passphrase login for Sparkbot chat access.

    In V1 local mode (desktop install) passphrase is skipped entirely for
    requests from localhost — the machine is the trust boundary.
    Passphrase is only enforced for hosted/remote deployments.

    Sets an HttpOnly cookie with the JWT (XSS-safe).
    Also returns the token in the body for backward compatibility.
    """
    client_ip = request.client.host if request.client else "unknown"

    # V1 local desktop: localhost requests are always trusted — no passphrase needed.
    local_desktop = settings.V1_LOCAL_MODE and _is_local_request(request)

    if not local_desktop:
        _check_chat_rate_limit(client_ip)
        if not body.passphrase:
            raise HTTPException(status_code=400, detail="Passphrase required")
        if body.passphrase != settings.SPARKBOT_PASSPHRASE:
            _record_failed_chat_attempt(client_ip)
            raise HTTPException(status_code=401, detail="Invalid passphrase")

    chat_user = _get_or_create_chat_user(session, username="sparkbot-user")

    # Create access token for chat user
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(chat_user.id),
        expires_delta=access_token_expires
    )

    max_age = int(access_token_expires.total_seconds())
    # Relax cookie security for local/development so plain-HTTP clients work
    _local = settings.ENVIRONMENT in ("local", "development")
    response = JSONResponse(
        {
            "success": True,
            "access_token": access_token,
            "token_type": "bearer",
        }
    )
    response.set_cookie(
        key="chat_token",
        value=access_token,
        httponly=True,
        secure=not _local,
        samesite="lax" if _local else "strict",
        max_age=max_age,
        path="/api",
    )
    return response


@router.delete("/session")
def chat_logout(response: Response) -> dict:
    """Clear the HttpOnly chat session cookie."""
    response.delete_cookie(key="chat_token", path="/api")
    return {"success": True}


@router.get("/", response_model=list[ChatUserResponse])
def read_chat_users(session: SessionDep, current_user: CurrentChatUser, skip: int = 0, limit: int = 100) -> Any:
    """Retrieve all chat users."""
    users = session.exec(
        select(ChatUser)
        .order_by(ChatUser.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return users


@router.get("/{user_id}", response_model=ChatUserResponse)
def read_chat_user_by_id(user_id: UUID, session: SessionDep, current_user: CurrentChatUser) -> Any:
    """Get a specific user by ID."""
    user = session.get(ChatUser, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/username/{username}", response_model=ChatUserResponse)
def read_chat_user_by_username(username: str, session: SessionDep, current_user: CurrentChatUser) -> Any:
    """Get a specific user by username."""
    user = session.execute(
        select(ChatUser).where(ChatUser.username == username)
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.get("/slug/{slug}", response_model=ChatUserResponse)
def read_chat_user_by_slug(slug: str, session: SessionDep, current_user: CurrentChatUser) -> Any:
    """Get a bot user by slug."""
    user = session.execute(
        select(ChatUser).where(ChatUser.bot_slug == slug)
    ).scalar_one_or_none()
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
    existing = session.execute(
        select(ChatUser).where(ChatUser.username == user_in.username)
    ).scalar_one_or_none()
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
    if user.id != current_user.id and not get_guardian_suite().auth.is_operator_identity(
        username=current_user.username, user_type=current_user.type
    ):
        raise HTTPException(status_code=403, detail="Cannot modify another user's account")
    
    if user_in.username:
        # Check if new username is taken
        existing = session.execute(
            select(ChatUser).where(ChatUser.username == user_in.username)
        ).scalar_one_or_none()
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
    if user.id != current_user.id and not get_guardian_suite().auth.is_operator_identity(
        username=current_user.username, user_type=current_user.type
    ):
        raise HTTPException(status_code=403, detail="Cannot delete another user's account")
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
    from app.crud import default_dm_execution_allowed
    from app.models import ChatRoom, ChatRoomMember, RoomRole
    
    # Find or create bot user
    bot_user = _get_or_create_chat_user(
        session,
        username="sparkbot",
        user_type=UserType.BOT,
        bot_display_name="Sparkbot",
        bot_slug="sparkbot",
    )
    
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
            execution_allowed=default_dm_execution_allowed(room_name),
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
