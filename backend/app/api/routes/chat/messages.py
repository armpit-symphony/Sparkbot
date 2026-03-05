"""
API routes for chat messages.

Handles message history retrieval.
"""
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import (
    create_chat_message,
    get_chat_message_by_id,
    get_chat_messages,
)
from app.models import ChatMessage, ChatRoom, ChatRoomMember, ChatUser, RoomRole, UserType
from app.schemas.chat import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
    MessageUpdate,
)

router = APIRouter(prefix="/messages", tags=["chat-messages"])

# Configuration
SPARKBOT_URL = "http://127.0.0.1:8080"
logger = logging.getLogger(__name__)


async def call_sparkbot_inline(message: str) -> str | None:
    """
    Call the npm sparkbot on port 8080 to get a response.
    
    Returns bot response text or None if it fails.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{SPARKBOT_URL}/chat",
                json={"message": message},
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("response", None)
            else:
                logger.error(f"Bot returned {response.status_code}: {response.text}")
                return None
    except Exception as e:
        logger.error(f"Bot call failed: {e}")
        return None


def get_sparkbot_user(session: Session) -> ChatUser | None:
    """Get or create the sparkbot user."""
    bot = session.exec(
        select(ChatUser).where(ChatUser.username == "sparkbot")
    ).scalar_one_or_none()
    return bot


@router.get("/{room_id}", response_model=MessageListResponse)
def read_chat_messages(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser = None,
    skip: int = 0,
    limit: int = 50,
    before: datetime = None,
) -> Any:
    """Get message history for a room.
    
    Requires room membership for private rooms.
    """
    # Check membership if user is authenticated
    if current_user:
        membership = session.exec(
            select(ChatRoomMember)
            .where(ChatRoomMember.room_id == room_id)
            .where(ChatRoomMember.user_id == current_user.id)
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this room")
    
    messages, total, has_more = get_chat_messages(
        session=session,
        room_id=room_id,
        before=before,
        limit=limit,
    )
    
    # Enrich messages with sender info
    enriched_messages = []
    for msg in messages:
        sender = session.get(ChatUser, msg.sender_id)
        enriched_messages.append(
            MessageResponse(
                id=msg.id,
                room_id=msg.room_id,
                sender_id=msg.sender_id,
                sender_type=msg.sender_type,
                content=msg.content,
                created_at=msg.created_at,
                meta_json=msg.meta_json,
                reply_to_id=msg.reply_to_id,
                sender_username=sender.username if sender else "unknown",
                sender_display_name=sender.bot_display_name if sender else None,
            )
        )
    
    return MessageListResponse(
        messages=enriched_messages,
        total=total,
        has_more=has_more,
    )


@router.get("/{room_id}/search", response_model=MessageListResponse)
def search_room_messages(
    room_id: UUID,
    q: str,
    session: SessionDep,
    current_user: CurrentChatUser = None,
    limit: int = 30,
) -> Any:
    """Search messages in a room by content (case-insensitive)."""
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")

    if current_user:
        membership = session.exec(
            select(ChatRoomMember)
            .where(ChatRoomMember.room_id == room_id)
            .where(ChatRoomMember.user_id == current_user.id)
        ).first()
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this room")

    results = session.exec(
        select(ChatMessage)
        .where(ChatMessage.room_id == room_id)
        .where(ChatMessage.content.ilike(f"%{q}%"))
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    ).all()

    enriched = []
    for msg in results:
        sender = session.get(ChatUser, msg.sender_id)
        enriched.append(MessageResponse(
            id=msg.id,
            room_id=msg.room_id,
            sender_id=msg.sender_id,
            sender_type=msg.sender_type,
            content=msg.content,
            created_at=msg.created_at,
            meta_json=msg.meta_json,
            reply_to_id=msg.reply_to_id,
            sender_username=sender.username if sender else "unknown",
            sender_display_name=sender.bot_display_name if sender else None,
        ))

    return MessageListResponse(messages=enriched, total=len(enriched), has_more=False)


@router.get("/{room_id}/message/{message_id}", response_model=MessageResponse)
def read_chat_message(
    room_id: UUID,
    message_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser = None,
) -> Any:
    """Get a specific message."""
    message = get_chat_message_by_id(session, message_id)
    if not message or message.room_id != room_id:
        raise HTTPException(status_code=404, detail="Message not found")
    
    sender = session.get(ChatUser, message.sender_id)
    return MessageResponse(
        id=message.id,
        room_id=message.room_id,
        sender_id=message.sender_id,
        sender_type=message.sender_type,
        content=message.content,
        created_at=message.created_at,
        meta_json=message.meta_json,
        reply_to_id=message.reply_to_id,
        sender_username=sender.username if sender else "unknown",
        sender_display_name=sender.bot_display_name if sender else None,
    )


@router.post("/{room_id}", response_model=MessageResponse)
async def create_chat_message(
    room_id: UUID,
    message_in: MessageCreate,
    session: SessionDep,
    current_user: CurrentChatUser = None,
) -> Any:
    """Create a new message in a room via REST API.
    
    Note: For real-time chat, use the WebSocket endpoint instead.
    This is useful for bots or integrations.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    # Check membership and role
    membership = session.exec(
        select(ChatRoomMember)
        .where(ChatRoomMember.room_id == room_id)
        .where(ChatRoomMember.user_id == current_user.id)
    ).first()
    
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot send messages")
    
    message = create_chat_message(
        session=session,
        room_id=room_id,
        sender_id=current_user.id,
        content=message_in.content,
        sender_type=current_user.type.value if hasattr(current_user, 'type') else "HUMAN",
        reply_to_id=message_in.reply_to_id,
    )
    
    # Get user type from ChatUser
    chat_user = session.get(ChatUser, current_user.id)
    
    # Trigger bot response (inline, non-blocking for response but waits for bot)
    if message.content and message.content.strip():
        logger.info(f"Triggering bot for message: {message.content[:50]}")
        bot_response = await call_sparkbot_inline(message.content)
        logger.info(f"Bot response: {bot_response}")
        if bot_response:
            # Get sparkbot user
            bot_user = get_sparkbot_user(session)
            if bot_user:
                # Create bot response message
                bot_message = create_chat_message(
                    session=session,
                    room_id=room_id,
                    sender_id=bot_user.id,
                    content=bot_response,
                    sender_type=UserType.BOT.value,
                    reply_to_id=message.id,
                )
                logger.info(f"Bot response created: {bot_message.id}")
    
    return MessageResponse(
        id=message.id,
        room_id=message.room_id,
        sender_id=message.sender_id,
        sender_type=message.sender_type,
        content=message.content,
        created_at=message.created_at,
        meta_json=message.meta_json,
        reply_to_id=message.reply_to_id,
        sender_username=chat_user.username if chat_user else "unknown",
        sender_display_name=chat_user.bot_display_name if chat_user else None,
    )


@router.patch("/{room_id}/message/{message_id}", response_model=MessageResponse)
def update_chat_message(
    room_id: UUID,
    message_id: UUID,
    message_in: MessageUpdate,
    session: SessionDep,
    current_user: CurrentChatUser = None,
) -> Any:
    """Update a message. Only the sender can edit their own messages."""
    message = get_chat_message_by_id(session, message_id)
    if not message or message.room_id != room_id:
        raise HTTPException(status_code=404, detail="Message not found")
    
    if message.sender_id != current_user.id:
        raise HTTPException(status_code=403, detail="Can only edit your own messages")
    
    # Bots can't edit messages
    if message.sender_type == UserType.BOT:
        raise HTTPException(status_code=403, detail="Bot messages cannot be edited")
    
    message.content = message_in.content
    session.add(message)
    session.commit()
    session.refresh(message)
    
    sender = session.get(ChatUser, message.sender_id)
    return MessageResponse(
        id=message.id,
        room_id=message.room_id,
        sender_id=message.sender_id,
        sender_type=message.sender_type,
        content=message.content,
        created_at=message.created_at,
        meta_json=message.meta_json,
        reply_to_id=message.reply_to_id,
        sender_username=sender.username if sender else "unknown",
        sender_display_name=sender.bot_display_name if sender else None,
    )


@router.delete("/{room_id}/message/{message_id}")
def delete_chat_message(
    room_id: UUID,
    message_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser = None,
) -> dict:
    """Delete a message. Only the sender can delete their own messages."""
    message = get_chat_message_by_id(session, message_id)
    if not message or message.room_id != room_id:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Check if user can delete
    membership = session.exec(
        select(ChatRoomMember)
        .where(ChatRoomMember.room_id == room_id)
        .where(ChatRoomMember.user_id == current_user.id)
    ).first()
    
    # Can delete own messages, or OWNER/MOD can delete any
    can_delete = (
        message.sender_id == current_user.id or
        (membership and membership.role.value in ["OWNER", "MOD"])
    )
    
    if not can_delete:
        raise HTTPException(status_code=403, detail="Cannot delete this message")
    
    session.delete(message)
    session.commit()
    return {"message": "Message deleted successfully"}
