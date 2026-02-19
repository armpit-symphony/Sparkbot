"""
Bot Integration API for Sparkbot v2

Connects chat system to npm bot running on port 8080.
"""
import uuid
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.api.deps import CurrentChatUser, SessionDep, get_current_user
from app.crud import (
    create_chat_message,
    get_chat_message_by_id,
    get_chat_room_by_id,
    get_chat_messages,
)
from app.models import ChatUser, UserType

router = APIRouter(prefix="/chat", tags=["chat"])

# Configuration
SPARKBOT_URL = "http://127.0.0.1:8080"


class MessageSendRequest(BaseModel):
    """Request body for sending a message."""
    content: str
    reply_to_id: Optional[str] = None


class MessageResponse(BaseModel):
    """Response for a sent message."""
    id: str
    room_id: str
    sender_id: str
    sender_type: str
    content: str
    created_at: datetime
    reply_to_id: Optional[str] = None
    bot_response: Optional[str] = None


class BotMessageResponse(BaseModel):
    """Response from bot integration."""
    message: MessageResponse
    bot_response: str
    success: bool
    error: Optional[str] = None


async def call_sparkbot(message: str) -> str:
    """
    Call the npm sparkbot on port 8080.
    
    Args:
        message: User message to process
        
    Returns:
        Bot response text
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{SPARKBOT_URL}/chat",
                json={"message": message},
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("response", "No response from bot")
            else:
                raise HTTPException(
                    status_code=502,
                    detail=f"Bot returned status {response.status_code}: {response.text}"
                )
                
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Bot request timed out")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Bot communication error: {str(e)}")


@router.post("/rooms/{room_id}/messages", response_model=BotMessageResponse)
async def send_message_with_bot(
    room_id: str,
    request: MessageSendRequest,
    session: SessionDep,
    current_user: CurrentChatUser = None,
):
    """
    Send a message to a room and get bot response.
    
    Flow:
    1. Save user message to database
    2. Call npm bot on :8080
    3. Save bot response to database
    4. Return both messages
    
    Requires authentication for non-public rooms.
    """
    # Parse room_id as UUID
    try:
        room_uuid = uuid.UUID(room_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid room ID format")
    
    # Check room exists
    room = get_chat_room_by_id(session, room_uuid)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Create sender info
    sender_id = current_user.id if current_user else uuid.uuid4()
    sender_type = UserType.HUMAN if current_user else UserType.UNKNOWN
    
    # Step 1: Save user message
    user_message = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=sender_id,
        content=request.content,
        sender_type=sender_type.value if hasattr(sender_type, 'value') else sender_type,
    )
    
    # Step 2: Call npm bot
    try:
        bot_response_text = await call_sparkbot(request.content)
    except HTTPException as e:
        # Bot failed, still return user message
        return BotMessageResponse(
            message=MessageResponse(
                id=str(user_message.id),
                room_id=room_id,
                sender_id=str(sender_id),
                sender_type=sender_type.value,
                content=request.content,
                created_at=user_message.created_at,
                reply_to_id=request.reply_to_id,
                bot_response=None,
            ),
            bot_response="",
            success=False,
            error=e.detail,
        )
    
    # Step 3: Save bot response as message
    bot_message = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=sender_id,  # Same user gets bot response
        sender_type=UserType.BOT.value,
        content=bot_response_text,
        reply_to_id=user_message.id,
    )
    
    # Step 4: Return combined response
    return BotMessageResponse(
        message=MessageResponse(
            id=str(user_message.id),
            room_id=room_id,
            sender_id=str(sender_id),
            sender_type=sender_type.value,
            content=request.content,
            created_at=user_message.created_at,
            reply_to_id=request.reply_to_id,
            bot_response=bot_response_text,
        ),
        bot_response=bot_response_text,
        success=True,
        error=None,
    )


@router.get("/rooms/{room_id}/messages/with-bot", response_model=BotMessageResponse)
async def get_messages_with_bot_status(
    room_id: str,
    message_id: str,
    session: SessionDep,
    current_user: CurrentChatUser = None,
):
    """
    Get a specific message and its bot response.
    
    Useful for checking if a message triggered a bot response.
    """
    # Parse UUIDs
    try:
        room_uuid = uuid.UUID(room_id)
        message_uuid = uuid.UUID(message_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid ID format")
    
    message = get_chat_message_by_id(session, message_uuid)
    if not message or message.room_id != room_uuid:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Find bot response (reply to this message from bot)
    messages, total, has_more = get_chat_messages(
        session=session,
        room_id=room_uuid,
        before=None,
        limit=10,
    )
    
    bot_response_text = None
    for msg in messages:
        if msg.reply_to_id == message_uuid and msg.sender_type == UserType.BOT:
            bot_response_text = msg.content
            break
    
    return BotMessageResponse(
        message=MessageResponse(
            id=str(message.id),
            room_id=room_id,
            sender_id=str(message.sender_id),
            sender_type=message.sender_type.value,
            content=message.content,
            created_at=message.created_at,
            reply_to_id=str(message.reply_to_id) if message.reply_to_id else None,
            bot_response=bot_response_text,
        ),
        bot_response=bot_response_text or "",
        success=bool(bot_response_text),
        error=None if bot_response_text else "No bot response found",
    )


@router.get("/bot/health")
async def bot_health_check():
    """
    Check if npm bot on port 8080 is healthy.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{SPARKBOT_URL}/health")
            
            if response.status_code == 200:
                data = response.json()
                return {
                    "status": "healthy",
                    "bot_status": data,
                    "integration": "connected",
                }
            else:
                return {
                    "status": "unhealthy",
                    "bot_http_status": response.status_code,
                    "integration": "disconnected",
                }
                
    except httpx.TimeoutException:
        return {
            "status": "timeout",
            "integration": "disconnected",
            "error": "Bot health check timed out",
        }
    except Exception as e:
        return {
            "status": "error",
            "integration": "disconnected",
            "error": str(e),
        }
