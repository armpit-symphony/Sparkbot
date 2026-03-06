"""
API routes for chat rooms.

Handles room CRUD and membership management.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import (
    add_chat_room_member,
    create_chat_room,
    create_chat_room_invite,
    create_chat_message,
    delete_expired_chat_invites,
    get_chat_room_by_id,
    get_chat_room_member,
    get_chat_room_members,
    get_chat_messages,
    get_user_chat_rooms,
    remove_chat_room_member,
    use_chat_invite,
    validate_chat_invite_token,
)
from app.models import ChatRoom, ChatRoomInvite, ChatRoomMember, ChatUser, RoomRole, UserType
from app.schemas.chat import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
    RoomCreate,
    RoomDetailResponse,
    RoomInviteCreate,
    RoomInviteResponse,
    RoomInviteUse,
    RoomMemberCreate,
    RoomMemberResponse,
    RoomResponse,
    RoomUpdate,
)

router = APIRouter(prefix="/rooms", tags=["chat-rooms"])


@router.get("/", response_model=list[RoomResponse])
def read_chat_rooms(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    current_user: CurrentChatUser = None,
) -> Any:
    """Retrieve rooms. If authenticated, returns user's rooms."""
    if current_user:
        # Return user's rooms
        rooms = get_user_chat_rooms(session, current_user.id)
    else:
        # Return all rooms (public listing)
        rooms = session.exec(
            select(ChatRoom)
            .order_by(ChatRoom.updated_at.desc())
            .offset(skip)
            .limit(limit)
        ).all()
    return rooms


@router.get("/{room_id}", response_model=RoomDetailResponse)
def read_chat_room_by_id(room_id: UUID, session: SessionDep) -> Any:
    """Get a specific room with details."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Get counts
    member_count = len(get_chat_room_members(session, room_id))
    message_count = session.exec(
        select(ChatRoomMember).where(ChatRoomMember.room_id == room_id)
    ).count()
    
    return RoomDetailResponse(
        id=room.id,
        name=room.name,
        description=room.description,
        created_by=room.created_by,
        created_at=room.created_at,
        updated_at=room.updated_at,
        execution_allowed=room.execution_allowed,
        meeting_mode_enabled=room.meeting_mode_enabled,
        meeting_mode_bots_mention_only=room.meeting_mode_bots_mention_only,
        meeting_mode_max_bot_msgs_per_min=room.meeting_mode_max_bot_msgs_per_min,
        owner=room.owner,
        member_count=member_count,
        message_count=message_count,
    )


@router.post("/", response_model=RoomResponse)
def create_chat_room_endpoint(
    *,
    session: SessionDep,
    room_in: RoomCreate,
    current_user: CurrentChatUser,
) -> Any:
    """Create a new chat room."""
    room = create_chat_room(
        session=session,
        name=room_in.name,
        description=room_in.description,
        created_by=current_user.id,
    )
    
    # Auto-add creator as OWNER member
    from app.models import ChatRoomMember, RoomRole
    member = ChatRoomMember(
        room_id=room.id,
        user_id=current_user.id,
        role=RoomRole.OWNER,
    )
    session.add(member)
    session.commit()
    
    return room


@router.patch("/{room_id}", response_model=RoomResponse)
def update_chat_room(
    *,
    session: SessionDep,
    room_id: UUID,
    room_in: RoomUpdate,
    current_user: CurrentChatUser,
) -> Any:
    """Update a room. Only OWNERs can update."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Check ownership
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership or membership.role.value != "OWNER":
        raise HTTPException(status_code=403, detail="Only OWNERs can update rooms")
    
    update_data = room_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(room, field, value)
    
    room.updated_at = datetime.now(timezone.utc)
    session.add(room)
    session.commit()
    session.refresh(room)
    return room


@router.delete("/{room_id}")
def delete_chat_room(
    *,
    session: SessionDep,
    room_id: UUID,
    current_user: CurrentChatUser,
) -> dict:
    """Delete a room. Only OWNERs can delete."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Check ownership
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership or membership.role.value != "OWNER":
        raise HTTPException(status_code=403, detail="Only OWNERs can delete rooms")
    
    session.delete(room)
    session.commit()
    return {"message": "Room deleted successfully"}


# ============== Membership Endpoints ==============

@router.get("/{room_id}/members", response_model=list[RoomMemberResponse])
def read_chat_room_members(room_id: UUID, session: SessionDep) -> Any:
    """Get all members of a room."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    members = get_chat_room_members(session, room_id)
    return members


@router.post("/{room_id}/members", response_model=RoomMemberResponse)
def add_chat_room_member(
    *,
    session: SessionDep,
    room_id: UUID,
    member_in: RoomMemberCreate,
    current_user: CurrentChatUser,
) -> Any:
    """Add a member to a room. Only OWNERs/MODs can add members."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Check permissions
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="You are not a member of this room")
    
    role_value = membership.role.value
    if role_value not in ["OWNER", "MOD"]:
        raise HTTPException(status_code=403, detail="Only OWNERs and MODs can add members")
    
    member = add_chat_room_member(
        session=session,
        room_id=room_id,
        user_id=member_in.user_id,
        role=member_in.role.value,
    )
    return member


@router.delete("/{room_id}/members/{user_id}")
def remove_chat_room_member(
    *,
    session: SessionDep,
    room_id: UUID,
    user_id: UUID,
    current_user: CurrentChatUser,
) -> dict:
    """Remove a member from a room."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Check permissions (can remove self, or OWNER/MOD can remove others)
    current_membership = get_chat_room_member(session, room_id, current_user.id)
    if not current_membership:
        raise HTTPException(status_code=403, detail="You are not a member of this room")
    
    target_membership = get_chat_room_member(session, room_id, user_id)
    if not target_membership:
        raise HTTPException(status_code=404, detail="Target user is not a member")
    
    # Can't remove OWNER
    if target_membership.role.value == "OWNER":
        raise HTTPException(status_code=403, detail="Cannot remove room OWNER")
    
    # Permission check
    if user_id != current_user.id:
        role_value = current_membership.role.value
        if role_value not in ["OWNER", "MOD"]:
            raise HTTPException(status_code=403, detail="Only OWNERs and MODs can remove other members")
    
    remove_chat_room_member(session, room_id, user_id)
    return {"message": "Member removed successfully"}


@router.get("/{room_id}/members/me", response_model=RoomMemberResponse)
def get_my_chat_membership(room_id: UUID, session: SessionDep, current_user: CurrentChatUser) -> Any:
    """Get current user's membership in a room."""
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=404, detail="You are not a member of this room")
    return membership


# ============== Invite Endpoints ==============

@router.get("/{room_id}/invites", response_model=list[RoomInviteResponse])
def get_chat_room_invites(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    """Get all invites for a room. Only OWNERs/MODs can view invites."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership or membership.role.value not in ["OWNER", "MOD"]:
        raise HTTPException(status_code=403, detail="Only OWNERs and MODs can view invites")
    
    invites = session.exec(
        select(ChatRoomInvite)
        .where(ChatRoomInvite.room_id == room_id)
        .order_by(ChatRoomInvite.created_at.desc())
    ).all()
    return invites


@router.post("/{room_id}/invites", response_model=RoomInviteResponse)
def create_chat_room_invite(
    *,
    session: SessionDep,
    room_id: UUID,
    invite_in: RoomInviteCreate,
    current_user: CurrentChatUser,
) -> Any:
    """Create an invite for a room. Only OWNERs/MODs can create invites."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership or membership.role.value not in ["OWNER", "MOD"]:
        raise HTTPException(status_code=403, detail="Only OWNERs and MODs can create invites")
    
    invite, token = create_chat_room_invite(
        session=session,
        room_id=room_id,
        created_by=current_user.id,
        role=invite_in.role.value,
        usage_limit=invite_in.usage_limit,
        expires_at=invite_in.expires_at,
    )
    
    # Return invite with the raw token (note: normally you'd want to return the full object with a custom schema)
    return RoomInviteResponse(
        id=invite.id,
        room_id=invite.room_id,
        token_hash=invite.token_hash,
        created_by=invite.created_by,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        usage_limit=invite.usage_limit,
        used_count=invite.used_count,
        role=invite.role,
    )


@router.post("/{room_id}/join")
def join_chat_room(
    *,
    session: SessionDep,
    room_id: UUID,
    invite_data: RoomInviteUse,
    current_user: CurrentChatUser,
) -> dict:
    """Join a room using an invite token."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    # Check if already a member
    if get_chat_room_member(session, room_id, current_user.id):
        raise HTTPException(status_code=400, detail="Already a member of this room")
    
    # Validate invite
    invite = validate_chat_invite_token(session, room_id, invite_data.invite_token)
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid or expired invite")
    
    # Use the invite
    if not use_chat_invite(session, invite):
        raise HTTPException(status_code=400, detail="Invite usage limit reached")
    
    # Add member
    add_chat_room_member(session, room_id, current_user.id, role=invite.role.value)
    
    return {"message": "Successfully joined room"}


@router.delete("/{room_id}/invites/{invite_id}")
def delete_chat_room_invite(
    *,
    session: SessionDep,
    room_id: UUID,
    invite_id: UUID,
    current_user: CurrentChatUser,
) -> dict:
    """Delete an invite. Only OWNERs/MODs can delete invites."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership or membership.role.value not in ["OWNER", "MOD"]:
        raise HTTPException(status_code=403, detail="Only OWNERs and MODs can delete invites")
    
    invite = session.get(ChatRoomInvite, invite_id)
    if not invite or invite.room_id != room_id:
        raise HTTPException(status_code=404, detail="Invite not found")
    
    session.delete(invite)
    session.commit()
    return {"message": "Invite deleted successfully"}


@router.post("/invites/cleanup")
def cleanup_expired_chat_invites(session: SessionDep, current_user: CurrentChatUser) -> dict:
    """Clean up expired invites. Admin only."""
    count = delete_expired_chat_invites(session)
    return {"message": f"Deleted {count} expired invites"}


# ============== Message Endpoints (Frontend API Compatibility) ==============

@router.get("/{room_id}/messages", response_model=MessageListResponse)
def get_room_messages(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser = None,
    skip: int = 0,
    limit: int = 50,
) -> Any:
    """Get message history for a room.
    
    Frontend-compatible endpoint: /api/v1/chat/rooms/{room_id}/messages
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
        before=None,
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


from typing import Optional, Any, Union


class StreamMessageRequest(MessageCreate):
    """Extended message request with optional confirm_id for write-tool confirmation."""
    confirm_id: Optional[str] = None


class SendMessageResponse(BaseModel):
    human: MessageResponse
    bot: Optional[MessageResponse] = None

@router.post("/{room_id}/messages", response_model=SendMessageResponse)
def send_room_message(
    room_id: UUID,
    message_in: MessageCreate,
    session: SessionDep,
    current_user: CurrentChatUser = None,
) -> Any:
    """Send a message to a room.
    
    Frontend-compatible endpoint: /api/v1/chat/rooms/{room_id}/messages
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    from app.crud import get_chat_room_member
    
    # Check membership and role
    membership = get_chat_room_member(session, room_id, current_user.id)
    
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot send messages")
    
    message = create_chat_message(
        session=session,
        room_id=room_id,
        sender_id=current_user.id,
        content=message_in.content,
        sender_type=current_user.type.value if hasattr(current_user.type, 'value') else "HUMAN",
        reply_to_id=message_in.reply_to_id,
    )
    
    sender = session.get(ChatUser, current_user.id)
    
    # Auto-reply from Sparkbot (call npm bot on port 8080 for all rooms)
    bot_response = None
    if message.content and message.content.strip():
        try:
            # Find or create bot user
            bot_user = session.exec(select(ChatUser).where(ChatUser.username == "sparkbot")).scalar_one_or_none()
            if not bot_user:
                bot_user = ChatUser(
                    username="sparkbot",
                    user_type=UserType.BOT,
                    passphrase_hash="",
                )
                session.add(bot_user)
                session.commit()
                session.refresh(bot_user)
            
            # Direct LLM call with conversation history
            import litellm
            from app.api.routes.chat.llm import SYSTEM_PROMPT as LLM_SYSTEM_PROMPT, get_model

            try:
                # Build conversation history (last 20 messages, oldest first)
                history_msgs, _, _ = get_chat_messages(
                    session=session, room_id=room_id, limit=20
                )
                openai_history = []
                for m in history_msgs:
                    if str(m.id) == str(message.id):
                        continue  # skip the message we just inserted
                    role = "assistant" if str(m.sender_type).upper() == "BOT" else "user"
                    openai_history.append({"role": role, "content": m.content})
                openai_history.append({"role": "user", "content": message.content})

                msgs = [{"role": "system", "content": LLM_SYSTEM_PROMPT}] + openai_history
                resp = litellm.completion(
                    model=get_model(str(current_user.id)),
                    messages=msgs,
                    temperature=0.2,
                )
                bot_text = (resp.choices[0].message.content or "").strip()
                if not bot_text:
                    raise RuntimeError("Empty model response")

                bot_reply = create_chat_message(
                    session=session,
                    room_id=room_id,
                    sender_id=bot_user.id,
                    content=bot_text,
                    sender_type="BOT",
                    reply_to_id=message.id,
                )
                bot_response = MessageResponse(
                    id=bot_reply.id,
                    room_id=bot_reply.room_id,
                    sender_id=bot_reply.sender_id,
                    sender_type=bot_reply.sender_type,
                    content=bot_reply.content,
                    created_at=bot_reply.created_at,
                    meta_json=bot_reply.meta_json,
                    reply_to_id=bot_reply.reply_to_id,
                    sender_username=bot_user.username,
                    sender_display_name=bot_user.bot_display_name,
                )
            except Exception as bot_err:
                raise HTTPException(status_code=502, detail=f"LLM_CALL_FAILED: {bot_err}")
        except Exception as e:
            from fastapi import HTTPException
            if isinstance(e, HTTPException):
                raise
            print(f"BOT_REPLY_ERROR: {e}")
    
    human_response = MessageResponse(
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
    
    return SendMessageResponse(human=human_response, bot=bot_response)


@router.post("/{room_id}/messages/stream")
async def stream_room_message(
    room_id: UUID,
    message_in: StreamMessageRequest,
    session: SessionDep,
    current_user: CurrentChatUser = None,
) -> StreamingResponse:
    """Stream bot response as Server-Sent Events (text/event-stream).

    Events emitted:
      data: {"type": "human_message", "message_id": "..."}
      data: {"type": "token", "token": "..."}
      data: {"type": "done", "message_id": "..."}
      data: {"type": "error", "error": "..."}
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot send messages")

    # ── Confirmed write-tool execution path ───────────────────────────────────
    if message_in.confirm_id:
        from app.api.routes.chat.llm import consume_pending
        from app.api.routes.chat.tools import execute_tool

        pending = consume_pending(message_in.confirm_id)
        if not pending:
            raise HTTPException(status_code=400, detail="Confirmation expired or invalid")

        tool_name = pending["tool"]
        tool_args = pending["args"]
        user_id_str = str(current_user.id)

        async def confirmed_stream():
            try:
                from app.api.deps import get_db as _get_db
                db2 = next(_get_db())
                result = await execute_tool(tool_name, tool_args, user_id=user_id_str, session=db2, room_id=str(room_id))
                # Save bot reply
                bot_user2 = db2.exec(select(ChatUser).where(ChatUser.username == "sparkbot")).scalar_one_or_none()
                if not bot_user2:
                    bot_user2 = ChatUser(username="sparkbot", user_type=UserType.BOT, passphrase_hash="")
                    db2.add(bot_user2)
                    db2.commit()
                    db2.refresh(bot_user2)
                bot_reply2 = create_chat_message(
                    session=db2,
                    room_id=room_id,
                    sender_id=bot_user2.id,
                    content=result,
                    sender_type="BOT",
                )
                done_id = str(bot_reply2.id)
                db2.close()
                # Stream result as tokens then done
                for chunk in [result[i:i+80] for i in range(0, len(result), 80)]:
                    yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'message_id': done_id})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

        return StreamingResponse(
            confirmed_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Save human message now, before streaming starts
    message = create_chat_message(
        session=session,
        room_id=room_id,
        sender_id=current_user.id,
        content=message_in.content,
        sender_type=current_user.type.value if hasattr(current_user.type, "value") else "HUMAN",
        reply_to_id=message_in.reply_to_id,
    )
    human_msg_id = str(message.id)
    human_msg_uuid = message.id  # capture before session closes — do NOT use message.id inside the generator

    # Detect @agentname routing before building the LLM prompt.
    from app.api.routes.chat.agents import resolve_agent_from_message, get_agent
    agent_name, agent_content = resolve_agent_from_message(message_in.content)

    # Build conversation history (before this message)
    history_msgs, _, _ = get_chat_messages(session=session, room_id=room_id, limit=20)
    openai_history = []
    for m in history_msgs:
        if str(m.id) == human_msg_id:
            continue
        role = "assistant" if str(m.sender_type).upper() == "BOT" else "user"
        openai_history.append({"role": role, "content": m.content})
    openai_history.append({"role": "user", "content": agent_content})

    # Build personalised system prompt — use agent prompt or default, then inject memories
    from app.api.routes.chat.llm import SYSTEM_PROMPT as LLM_SYSTEM_PROMPT
    from app.crud import get_user_memories
    memories = get_user_memories(session, current_user.id)

    base_prompt = LLM_SYSTEM_PROMPT
    if agent_name:
        agent = get_agent(agent_name)
        if agent and agent.get("system_prompt"):
            base_prompt = agent["system_prompt"]

    if memories:
        mem_block = "\n".join(f"- {m.fact}" for m in memories)
        system_prompt = base_prompt + f"\n\n## What you know about this user:\n{mem_block}"
    else:
        system_prompt = base_prompt

    user_id_str = str(current_user.id)

    async def event_stream():
        from app.api.deps import get_db

        yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"

        full_text = ""
        try:
            from app.api.routes.chat.llm import stream_chat_with_tools
            db = next(get_db())
            async for event in stream_chat_with_tools(
                [{"role": "system", "content": system_prompt}] + openai_history,
                user_id=user_id_str,
                db_session=db,
                room_id=str(room_id),
                agent_name=agent_name,
            ):
                if event["type"] == "token":
                    full_text += event["token"]
                    yield f"data: {json.dumps({'type': 'token', 'token': event['token']})}\n\n"
                elif event["type"] in ("tool_start", "tool_done"):
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            return

        # Save completed bot message (reuse the db session opened for tool calls)
        try:
            bot_user = db.exec(
                select(ChatUser).where(ChatUser.username == "sparkbot")
            ).scalar_one_or_none()
            if not bot_user:
                bot_user = ChatUser(username="sparkbot", user_type=UserType.BOT, passphrase_hash="")
                db.add(bot_user)
                db.commit()
                db.refresh(bot_user)
            bot_reply = create_chat_message(
                session=db,
                room_id=room_id,
                sender_id=bot_user.id,
                content=full_text,
                sender_type="BOT",
                reply_to_id=human_msg_uuid,
            )
            bot_reply_id = str(bot_reply.id)  # capture before session closes
            db.close()
            done_event: dict = {"type": "done", "message_id": bot_reply_id}
            if agent_name:
                done_event["agent"] = agent_name
            yield f"data: {json.dumps(done_event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Save failed: {e}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
