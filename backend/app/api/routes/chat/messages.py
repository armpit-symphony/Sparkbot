"""
API routes for chat messages.

Handles message history retrieval.
"""
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
from app.models import ChatMessage, ChatRoomMember, ChatUser, RoomRole, UserType
from app.schemas.chat import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
    MessageUpdate,
)

router = APIRouter(prefix="/messages", tags=["chat-messages"])


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
def create_chat_message(
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
