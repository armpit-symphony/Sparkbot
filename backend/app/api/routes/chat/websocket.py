"""
WebSocket chat endpoint.

Real-time chat functionality with JWT authentication,
room membership validation, and message broadcasting.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Set
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db
from app.core.security import decode_token
from app.crud import (
    add_chat_room_member,
    create_chat_message,
    get_chat_message_by_id,
    get_chat_messages,
    get_chat_room_by_id,
    get_chat_room_member,
    get_chat_user_by_id,
    get_chat_user_by_username,
    get_chat_user_by_slug,
)
from app.models import ChatRoomMember, ChatUser, RoomRole, UserType
from app.models import ChatMessage

logger = logging.getLogger(__name__)

ws_router = APIRouter(tags=["websocket"])


@ws_router.websocket("/ws")
async def websocket_main(websocket: WebSocket, token: str = Query(..., description="JWT access token")):
    """
    Main WebSocket endpoint for chat.
    
    Connect with: ws://host/ws?token={access_token}
    
    Client-to-Server Messages:
    - {"type": "join_room", "payload": {"room_id": "..."}}
    - {"type": "leave_room", "payload": {"room_id": "..."}}
    - {"type": "message", "payload": {"room_id": "...", "content": "...", ...}}
    - {"type": "typing", "payload": {"room_id": "...", "is_typing": true/false}}
    - {"type": "ping"}
    """
    # Validate token and get user
    db = next(get_db())
    user = await get_current_chat_user_from_token(token, db)
    if not user:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    
    await websocket.accept()
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "join_room":
                room_id = data.get("payload", {}).get("room_id")
                if room_id:
                    await ws_manager.join_room(websocket, room_id, str(user.id))
            
            elif msg_type == "leave_room":
                room_id = data.get("payload", {}).get("room_id")
                if room_id:
                    await ws_manager.leave_room(websocket, room_id, str(user.id))
            
            elif msg_type == "message":
                payload = data.get("payload", {})
                room_id = payload.get("room_id")
                content = payload.get("content")
                if room_id and content:
                    message = await ws_manager.send_message(
                        db, room_id, str(user.id), content, "HUMAN"
                    )
            
            elif msg_type == "typing":
                payload = data.get("payload", {})
                room_id = payload.get("room_id")
                is_typing = payload.get("is_typing", False)
                if room_id:
                    await ws_manager.send_typing(
                        room_id, str(user.id), user.username or user.bot_name or "Unknown", is_typing
                    )
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        pass
    finally:
        # Clean up all connections for this user
        for room_id in list(ws_manager.user_rooms.get(str(user.id), set())):
            await ws_manager.leave_room(websocket, room_id, str(user.id))


class ConnectionManager:
    """Manages WebSocket connections for chat rooms."""
    
    def __init__(self):
        # room_id -> {user_id -> WebSocket}
        self.connections: Dict[str, Dict[str, WebSocket]] = {}
        # room_id -> set of user_ids
        self.room_users: Dict[str, Set[str]] = {}
        # user_id -> set of room_ids
        self.user_rooms: Dict[str, Set[str]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    async def connect(
        self,
        websocket: WebSocket,
        room_id: str,
        user_id: str,
    ) -> None:
        """Register a new WebSocket connection."""
        async with self._lock:
            if room_id not in self.connections:
                self.connections[room_id] = {}
                self.room_users[room_id] = set()
            
            self.connections[room_id][user_id] = websocket
            self.room_users[room_id].add(user_id)
            
            if user_id not in self.user_rooms:
                self.user_rooms[user_id] = set()
            self.user_rooms[user_id].add(room_id)
        
        logger.info(f"[WS] User {user_id} connected to room {room_id}")
    
    async def disconnect(self, room_id: str, user_id: str) -> None:
        """Remove a WebSocket connection."""
        async with self._lock:
            if room_id in self.connections and user_id in self.connections[room_id]:
                del self.connections[room_id][user_id]
                self.room_users[room_id].discard(user_id)
                
                if not self.connections[room_id]:
                    del self.connections[room_id]
                    del self.room_users[room_id]
            
            if user_id in self.user_rooms:
                self.user_rooms[user_id].discard(room_id)
                if not self.user_rooms[user_id]:
                    del self.user_rooms[user_id]
        
        logger.info(f"[WS] User {user_id} disconnected from room {room_id}")
    
    async def broadcast(
        self,
        room_id: str,
        message: dict,
        exclude_user: Optional[str] = None,
    ) -> None:
        """Broadcast a message to all users in a room."""
        if room_id not in self.connections:
            return
        
        disconnected = []
        for user_id, websocket in list(self.connections[room_id].items()):
            if exclude_user and user_id == exclude_user:
                continue
            
            try:
                if websocket.client_state == websocket.application_state.CONNECTED:
                    await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"[WS] Failed to send to {user_id}: {e}")
                disconnected.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected:
            await self.disconnect(room_id, user_id)
    
    def get_online_users(self, room_id: str) -> list[str]:
        """Get list of online user IDs in a room."""
        return list(self.room_users.get(room_id, set()))

    async def join_room(self, websocket: WebSocket, room_id: str, user_id: str) -> None:
        """Join a user to a room (alias for connect)."""
        await self.connect(websocket, room_id, user_id)

    async def leave_room(self, websocket: WebSocket, room_id: str, user_id: str) -> None:
        """Leave a room (alias for disconnect)."""
        await self.disconnect(room_id, user_id)

    async def send_message(
        self,
        db: Session,
        room_id: str,
        user_id: str,
        content: str,
        sender_type: str = "HUMAN",
    ) -> ChatMessage:
        """Save and broadcast a message to a room."""
        # Create message in database
        message = create_chat_message(
            db,
            room_id=UUID(room_id),
            sender_id=UUID(user_id),
            content=content,
            sender_type=sender_type,
        )
        
        # Broadcast to room
        msg_dict = {
            "type": "message",
            "message": {
                "id": str(message.id),
                "room_id": room_id,
                "sender_id": user_id,
                "content": content,
                "created_at": message.created_at.isoformat(),
            }
        }
        await self.broadcast(room_id, msg_dict)
        return message

    async def send_typing(
        self,
        room_id: str,
        user_id: str,
        username: str,
        is_typing: bool,
    ) -> None:
        """Broadcast typing status to a room."""
        await self.broadcast(room_id, {
            "type": "typing",
            "payload": {
                "room_id": room_id,
                "user_id": user_id,
                "username": username,
                "is_typing": is_typing,
            }
        })


# Singleton connection manager
ws_manager = ConnectionManager()


async def get_current_chat_user_from_token(
    token: str,
    db: Session,
) -> Optional[ChatUser]:
    """Validate JWT token and return chat user."""
    try:
        payload = decode_token(token)
        if payload is None:
            return None
        
        user_id = payload.get("sub")
        if not user_id:
            return None
        
        # Try to parse as UUID first (for regular user IDs)
        try:
            user_uuid = UUID(user_id)
            user = get_chat_user_by_id(db, user_uuid)
            if user and user.is_active:
                return user
        except ValueError:
            # Not a UUID - try looking up by username or slug
            pass
        
        # Try by username (for "sparkbot-user" style subjects)
        user = get_chat_user_by_username(db, user_id)
        if user and user.is_active:
            return user
        
        # Try by slug (for bot users)
        user = get_chat_user_by_slug(db, user_id)
        if user and user.is_active:
            return user
        
        return None
    except Exception as e:
        logger.error(f"[WS] Token validation error: {e}")
        return None


async def chat_message_to_dict(
    message: ChatMessage,
    db: Session,
) -> dict:
    """Convert message model to dict for JSON serialization."""
    sender = get_chat_user_by_id(db, message.sender_id)
    return {
        "id": str(message.id),
        "room_id": str(message.room_id),
        "sender_id": str(message.sender_id),
        "sender_type": message.sender_type.value,
        "sender_username": sender.username if sender else "unknown",
        "sender_display_name": sender.bot_display_name if sender else None,
        "content": message.content,
        "created_at": message.created_at.isoformat(),
        "meta": message.meta_json,
        "reply_to_id": str(message.reply_to_id) if message.reply_to_id else None,
    }


@ws_router.websocket("/ws/rooms/{room_id}")
async def websocket_chat(
    websocket: WebSocket,
    room_id: str,
    token: str = Query(..., description="JWT access token"),
):
    """
    WebSocket endpoint for real-time chat.
    
    Connect with: ws://host/ws/rooms/{room_id}?token={access_token}
    
    Client-to-Server Messages:
    - {"type": "message", "content": "...", "client_msg_id": "...", "reply_to_id": "..."}
    - {"type": "ping"}
    
    Server-to-Client Messages:
    - {"type": "connected", "room_id": "...", "messages": [...], "online_users": [...]}
    - {"type": "message", "message": {...}}
    - {"type": "presence", "action": "joined|left", "user": {...}}
    - {"type": "pong"}
    - {"type": "error", "message": "..."}
    """
    # Validate room exists
    db = next(get_db())
    room_uuid = None
    try:
        room_uuid = UUID(room_id)
    except ValueError:
        await websocket.close(code=4000, reason="Invalid room ID format")
        return
    
    room = get_chat_room_by_id(db, room_uuid)
    if not room:
        await websocket.close(code=4004, reason="Room not found")
        return
    
    # Validate token and get user
    user = await get_current_chat_user_from_token(token, db)
    if not user:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    
    # Verify room membership
    membership = get_chat_room_member(db, room_uuid, user.id)
    if not membership:
        await websocket.close(code=4003, reason="Not a member of this room")
        return
    
    # Check if VIEWERs can connect (they can view but not send)
    can_send = membership.role not in [RoomRole.VIEWER]
    
    # Accept connection
    await websocket.accept()
    
    # Register connection
    await ws_manager.connect(websocket, room_id, str(user.id))
    
    try:
        # Send initial data
        messages, total, has_more = get_chat_messages(db, room_uuid, limit=50)
        
        # Get online users
        online_user_ids = ws_manager.get_online_users(room_id)
        online_users = []
        for uid in online_user_ids:
            u = get_chat_user_by_id(db, UUID(uid))
            if u:
                online_users.append({
                    "user_id": str(u.id),
                    "username": u.username,
                    "type": u.type.value,
                    "display_name": u.bot_display_name,
                })
        
        await websocket.send_json({
            "type": "connected",
            "room_id": room_id,
            "room_name": room.name,
            "messages": [await chat_message_to_dict(m, db) for m in messages],
            "total_messages": total,
            "online_users": online_users,
            "can_send": can_send,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        # Broadcast presence
        await ws_manager.broadcast(room_id, {
            "type": "presence",
            "action": "joined",
            "user": {
                "user_id": str(user.id),
                "username": user.username,
                "type": user.type.value,
                "display_name": user.bot_display_name,
            },
            "online_users": online_users,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        # Main message loop
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type", "")
                
                if msg_type == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                
                elif msg_type == "message":
                    if not can_send:
                        await websocket.send_json({
                            "type": "error",
                            "message": "VIEWERs cannot send messages",
                        })
                        continue
                    
                    content = data.get("content", "").strip()
                    if not content:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Message content cannot be empty",
                        })
                        continue
                    
                    client_msg_id = data.get("client_msg_id")
                    reply_to_id = data.get("reply_to_id")
                    if reply_to_id:
                        try:
                            reply_to_id = UUID(reply_to_id)
                        except ValueError:
                            reply_to_id = None
                    
                    # Create message
                    message = create_chat_message(
                        session=db,
                        room_id=room_uuid,
                        sender_id=user.id,
                        content=content,
                        sender_type=user.type.value,
                        reply_to_id=reply_to_id,
                    )
                    
                    # Send ack
                    await websocket.send_json({
                        "type": "ack",
                        "client_msg_id": client_msg_id,
                        "message_id": str(message.id),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                    
                    # Broadcast to room
                    msg_dict = await chat_message_to_dict(message, db)
                    await ws_manager.broadcast(room_id, {
                        "type": "message",
                        "message": msg_dict,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown message type: {msg_type}",
                    })
            
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
            except Exception as e:
                logger.error(f"[WS] Message handling error: {e}")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)[:200],
                    })
                except:
                    break
    
    finally:
        # Disconnect and broadcast
        await ws_manager.disconnect(room_id, str(user.id))
        
        # Broadcast leaving
        online_users = []
        for uid in ws_manager.get_online_users(room_id):
            u = get_chat_user_by_id(db, UUID(uid))
            if u:
                online_users.append({
                    "user_id": str(u.id),
                    "username": u.username,
                    "type": u.type.value,
                    "display_name": u.bot_display_name,
                })
        
        await ws_manager.broadcast(room_id, {
            "type": "presence",
            "action": "left",
            "user": {
                "user_id": str(user.id),
                "username": user.username,
                "type": user.type.value,
                "display_name": user.bot_display_name,
            },
            "online_users": online_users,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        db.close()
