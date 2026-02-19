"""
CRUD operations for the application.

Includes base template CRUD and chat-specific operations.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlmodel import Session, delete

from app.core.security import get_password_hash, verify_password
from app.models import (
    ChatMeetingArtifact,
    ChatMessage,
    ChatRoom,
    ChatRoomInvite,
    ChatRoomMember,
    ChatUser,
    Item,
    ItemCreate,
    MeetingArtifactType,
    RoomRole,
    User,
    UserCreate,
    UserUpdate,
    UserType,
)


# ============== Base Template CRUD ==============

def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.execute(statement).scalar_one_or_none()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user


def create_item(*, session: Session, item_in: ItemCreate, owner_id: uuid.UUID) -> Item:
    db_item = Item.model_validate(item_in, update={"owner_id": owner_id})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


# ============== Chat User CRUD ==============

def get_chat_user_by_id(session: Session, user_id: uuid.UUID) -> Optional[ChatUser]:
    return session.get(ChatUser, user_id)


def get_chat_user_by_username(session: Session, username: str) -> Optional[ChatUser]:
    return session.execute(select(ChatUser).where(ChatUser.username == username)).scalar_one_or_none()


def get_chat_user_by_slug(session: Session, slug: str) -> Optional[ChatUser]:
    return session.execute(select(ChatUser).where(ChatUser.bot_slug == slug)).scalar_one_or_none()


def create_chat_user(
    session: Session,
    username: str,
    password: Optional[str] = None,
    user_type: str = "HUMAN",
    **kwargs,
) -> ChatUser:
    user = ChatUser(
        username=username,
        hashed_password=get_password_hash(password) if password else None,
        type=user_type,
        **kwargs,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_chat_bot_user(
    session: Session,
    username: str,
    slug: str,
    display_name: str,
    service_key: str,
    **kwargs,
) -> ChatUser:
    user = ChatUser(
        username=username,
        hashed_password=None,  # Bots use service key auth
        type="BOT",
        bot_slug=slug,
        bot_display_name=display_name,
        bot_service_key_hash=get_password_hash(service_key),
        **kwargs,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_chat_user(session: Session, username: str, password: str) -> Optional[ChatUser]:
    user = get_chat_user_by_username(session, username)
    if not user:
        return None
    if not user.hashed_password:
        return None
    verified, _ = verify_password(password, user.hashed_password)
    if not verified:
        return None
    return user


# ============== Chat Room CRUD ==============

def get_chat_room_by_id(session: Session, room_id: uuid.UUID) -> Optional[ChatRoom]:
    return session.get(ChatRoom, room_id)


def create_chat_room(
    session: Session,
    name: str,
    created_by: uuid.UUID,
    description: Optional[str] = None,
) -> ChatRoom:
    room = ChatRoom(
        name=name,
        description=description,
        created_by=created_by,
    )
    session.add(room)
    session.commit()
    session.refresh(room)
    
    # Auto-add creator as OWNER
    add_chat_room_member(session, room.id, created_by, role="OWNER")
    
    return room


def get_user_chat_rooms(session: Session, user_id: uuid.UUID) -> list[ChatRoom]:
    statement = (
        select(ChatRoom)
        .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
        .where(ChatRoomMember.user_id == user_id)
        .order_by(ChatRoom.updated_at.desc())
    )
    return list(session.execute(statement).scalars().all())


# ============== Chat Room Member CRUD ==============

def add_chat_room_member(
    session: Session,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = "MEMBER",
) -> ChatRoomMember:
    # Check if already a member
    existing = get_chat_room_member(session, room_id, user_id)
    if existing:
        return existing
    
    member = ChatRoomMember(
        room_id=room_id,
        user_id=user_id,
        role=RoomRole(role),
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def get_chat_room_member(session: Session, room_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ChatRoomMember]:
    return session.execute(
        select(ChatRoomMember)
        .where(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
    ).scalar_one_or_none()


def get_chat_room_members(session: Session, room_id: uuid.UUID) -> list[ChatRoomMember]:
    return list(
        session.execute(
            select(ChatRoomMember)
            .where(ChatRoomMember.room_id == room_id)
            .order_by(ChatRoomMember.joined_at)
        ).scalars().all()
    )


def remove_chat_room_member(session: Session, room_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Remove a member from a chat room. Returns True if removed, False if not found."""
    member = session.execute(
        select(ChatRoomMember)
        .where(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
    ).scalar_one_or_none()
    
    if member:
        session.delete(member)
        session.commit()
        return True
    return False


# ============== Chat Message CRUD ==============

def create_chat_message(
    session: Session,
    room_id: uuid.UUID,
    sender_id: uuid.UUID,
    content: str,
    sender_type: str = "HUMAN",
    reply_to_id: Optional[uuid.UUID] = None,
    meta_json: Optional[dict] = None,
) -> ChatMessage:
    message = ChatMessage(
        room_id=room_id,
        sender_id=sender_id,
        sender_type=UserType(sender_type),
        content=content,
        reply_to_id=reply_to_id,
        meta_json=meta_json,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    
    # Update room's updated_at
    room = get_chat_room_by_id(session, room_id)
    if room:
        room.updated_at = datetime.now(timezone.utc)
        session.add(room)
        session.commit()
    
    return message


def get_chat_messages(
    session: Session,
    room_id: uuid.UUID,
    before: Optional[datetime] = None,
    limit: int = 50,
) -> tuple[list[ChatMessage], int, bool]:
    """Get messages for a room, optionally paginated."""
    # Build query
    query = select(ChatMessage).where(ChatMessage.room_id == room_id)
    
    if before:
        query = query.where(ChatMessage.created_at < before)
    
    # Get total count - properly extract integer from row
    count_result = session.execute(select(func.count()).select_from(query.subquery())).one()
    total = int(count_result[0]) if count_result else 0
    
    # Get messages with proper ORM mapping
    messages = list(
        session.execute(
            query.order_by(ChatMessage.created_at.desc())
            .limit(limit + 1)  # Fetch one extra to check has_more
        ).scalars().all()
    )
    
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]
    
    # Reverse to get chronological order
    messages.reverse()
    
    return messages, total, has_more


def get_chat_message_by_id(session: Session, message_id: uuid.UUID) -> Optional[ChatMessage]:
    return session.get(ChatMessage, message_id)


# ============== Chat Room Invite CRUD ==============

def create_chat_room_invite(
    session: Session,
    room_id: uuid.UUID,
    created_by: uuid.UUID,
    role: str = "MEMBER",
    usage_limit: Optional[int] = None,
    expires_at: Optional[datetime] = None,
) -> tuple[ChatRoomInvite, str]:
    # Generate token and hash it
    import secrets
    token = secrets.token_urlsafe(32)
    token_hash = get_password_hash(token)
    
    invite = ChatRoomInvite(
        room_id=room_id,
        token_hash=token_hash,
        created_by=created_by,
        role=RoomRole(role),
        usage_limit=usage_limit,
        expires_at=expires_at,
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    
    # Return invite with the raw token (only time it's available)
    return invite, token


def validate_chat_invite_token(
    session: Session,
    room_id: uuid.UUID,
    token: str,
) -> Optional[ChatRoomInvite]:
    invites = list(
        session.execute(
            select(ChatRoomInvite)
            .where(ChatRoomInvite.room_id == room_id)
            .where(ChatRoomInvite.used_count < (ChatRoomInvite.usage_limit or 999999))
            .where(
                (ChatRoomInvite.expires_at.is_(None)) | 
                (ChatRoomInvite.expires_at > datetime.now(timezone.utc))
            )
        ).scalars().all()
    )
    
    for invite in invites:
        verified, _ = verify_password(token, invite.token_hash)
        if verified:
            return invite
    
    return None


def use_chat_invite(session: Session, invite: ChatRoomInvite) -> bool:
    """Increment usage count if within limits."""
    if invite.usage_limit and invite.used_count >= invite.usage_limit:
        return False
    
    invite.used_count += 1
    session.add(invite)
    session.commit()
    return True


def delete_expired_chat_invites(session: Session) -> int:
    """Delete expired invites and return count."""
    result = session.execute(
        delete(ChatRoomInvite).where(
            and_(
                ChatRoomInvite.expires_at.isnot(None),
                ChatRoomInvite.expires_at < datetime.now(timezone.utc),
            )
        )
    )
    session.commit()
    return result.rowcount


# ============== Chat Meeting Artifact CRUD ==============

def create_chat_meeting_artifact(
    session: Session,
    room_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    type: str,
    content_markdown: str,
    window_start_ts: Optional[datetime] = None,
    window_end_ts: Optional[datetime] = None,
    meta_json: Optional[dict] = None,
) -> ChatMeetingArtifact:
    artifact = ChatMeetingArtifact(
        room_id=room_id,
        created_by_user_id=created_by_user_id,
        type=MeetingArtifactType(type),
        content_markdown=content_markdown,
        window_start_ts=window_start_ts,
        window_end_ts=window_end_ts,
        meta_json=meta_json,
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    return artifact


def get_chat_meeting_artifacts(
    session: Session,
    room_id: uuid.UUID,
    type: Optional[str] = None,
    limit: int = 50,
) -> list[ChatMeetingArtifact]:
    query = select(ChatMeetingArtifact).where(ChatMeetingArtifact.room_id == room_id)
    
    if type:
        query = query.where(ChatMeetingArtifact.type == MeetingArtifactType(type))
    
    return list(
        session.execute(
            query.order_by(ChatMeetingArtifact.created_at.desc())
            .limit(limit)
        ).scalars().all()
    )
