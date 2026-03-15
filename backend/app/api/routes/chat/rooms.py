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
    create_chat_meeting_artifact,
    delete_expired_chat_invites,
    get_chat_room_by_id,
    get_chat_room_member,
    get_chat_room_members,
    get_chat_messages,
    get_chat_meeting_artifacts,
    get_user_chat_rooms,
    remove_chat_room_member,
    use_chat_invite,
    validate_chat_invite_token,
)
from app.models import ChatMessage, ChatRoom, ChatRoomInvite, ChatRoomMember, ChatUser, RoomRole, UserType
from app.schemas.chat import (
    MeetingArtifactCreate,
    MeetingArtifactResponse,
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


def _get_or_create_agent_bot_user(db, agent_name: str) -> "ChatUser":
    """Return the bot ChatUser for a named agent, creating it on first call."""
    from app.api.routes.chat.agents import get_agent as _get_agent
    username = "sparkbot" if agent_name == "sparkbot" else f"agent_{agent_name}"
    bot_user = db.exec(select(ChatUser).where(ChatUser.username == username)).scalar_one_or_none()
    if not bot_user:
        agent_info = _get_agent(agent_name) or {}
        emoji = str(agent_info.get("emoji") or "")
        display_name = f"{emoji} {agent_name.title()}".strip() if emoji else agent_name.title()
        bot_user = ChatUser(username=username, type=UserType.BOT, hashed_password="", bot_display_name=display_name)
        db.add(bot_user)
        db.commit()
        db.refresh(bot_user)
    return bot_user


def _require_room_access(
    session: SessionDep,
    room_id: UUID,
    current_user: CurrentChatUser,
) -> ChatRoomMember:
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    return membership


@router.get("/", response_model=list[RoomResponse])
def read_chat_rooms(
    session: SessionDep,
    current_user: CurrentChatUser,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """Retrieve rooms for the authenticated user."""
    return get_user_chat_rooms(session, current_user.id)


@router.get("/{room_id}", response_model=RoomDetailResponse)
def read_chat_room_by_id(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    """Get a specific room with details."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    
    # Get counts
    member_count = len(get_chat_room_members(session, room_id))
    message_count_row = session.exec(
        select(ChatMessage).where(ChatMessage.room_id == room_id)
    ).all()
    message_count = len(message_count_row)
    
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
    # create_chat_room already adds the creator as OWNER via add_chat_room_member
    room = create_chat_room(
        session=session,
        name=room_in.name,
        description=room_in.description,
        created_by=current_user.id,
    )
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
def read_chat_room_members(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    """Get all members of a room."""
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    
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
    current_user: CurrentChatUser,
    skip: int = 0,
    limit: int = 50,
) -> Any:
    """Get message history for a room.
    
    Frontend-compatible endpoint: /api/v1/chat/rooms/{room_id}/messages
    """
    _require_room_access(session, room_id, current_user)
    
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
    participants: Optional[list[str]] = None  # round-table agent handles e.g. ["researcher","analyst"]


class SendMessageResponse(BaseModel):
    human: MessageResponse
    bot: Optional[MessageResponse] = None

@router.post("/{room_id}/messages", response_model=SendMessageResponse)
def send_room_message(
    room_id: UUID,
    message_in: MessageCreate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    """Send a message to a room.
    
    Frontend-compatible endpoint: /api/v1/chat/rooms/{room_id}/messages
    """
    membership = _require_room_access(session, room_id, current_user)
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
                    type=UserType.BOT,
                    hashed_password="",
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
    current_user: CurrentChatUser,
) -> StreamingResponse:
    """Stream bot response as Server-Sent Events (text/event-stream).

    Events emitted:
      data: {"type": "human_message", "message_id": "..."}
      data: {"type": "token", "token": "..."}
      data: {"type": "done", "message_id": "..."}
      data: {"type": "error", "error": "..."}
    """
    membership = _require_room_access(session, room_id, current_user)
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot send messages")
    room = get_chat_room_by_id(session, room_id)

    # ── Confirmed write-tool execution path ───────────────────────────────────
    if message_in.confirm_id:
        from app.api.routes.chat.llm import (
            consume_pending,
            mask_tool_result_for_external,
            redact_tool_call_for_audit,
            serialize_tool_args_for_audit,
        )
        from app.api.routes.chat.tools import execute_tool
        from app.services.guardian.executive import exec_with_guard
        from app.services.guardian.auth import is_operator_identity, is_operator_privileged
        from app.services.guardian.policy import decide_tool_use
        from app.services.guardian.verifier import (
            format_verifier_note,
            should_verify_interactive_tool_run,
            verify_interactive_tool_run,
        )

        pending = consume_pending(message_in.confirm_id)
        if not pending:
            raise HTTPException(status_code=400, detail="Confirmation expired or invalid")

        tool_name = pending["tool"]
        tool_args = pending["args"]
        user_id_str = str(current_user.id)
        user_is_operator = is_operator_identity(username=current_user.username, user_type=current_user.type)
        user_is_privileged = is_operator_privileged(user_id_str)

        async def confirmed_stream():
            try:
                from app.api.deps import get_db as _get_db
                from app.crud import create_audit_log
                from app.services.guardian.memory import remember_tool_event
                db2 = next(_get_db())
                decision = decide_tool_use(
                    tool_name,
                    tool_args if isinstance(tool_args, dict) else {},
                    room_execution_allowed=room.execution_allowed,
                    is_operator=user_is_operator,
                    is_privileged=user_is_privileged,
                )
                create_audit_log(
                    session=db2,
                    tool_name="policy_decision",
                    tool_input=json.dumps(
                        {
                            "tool_name": tool_name,
                            "tool_args": json.loads(serialize_tool_args_for_audit(tool_name, tool_args)),
                            "confirmed": True,
                        }
                    ),
                    tool_result=decision.to_json(),
                    user_id=current_user.id,
                    room_id=room_id,
                    model=None,
                )
                if decision.action == "deny":
                    verification = None
                    result = f"POLICY DENIED: {decision.reason}"
                else:
                    result = await exec_with_guard(
                        tool_name=tool_name,
                        action_type=decision.action_type,
                        expected_outcome=f"Confirmed tool execution for {tool_name}",
                        perform_fn=lambda: execute_tool(
                            tool_name,
                            tool_args,
                            user_id=user_id_str,
                            session=db2,
                            room_id=str(room_id),
                        ),
                        metadata={"room_id": str(room_id), "user_id": user_id_str, "confirmed": True},
                    )
                    verification = None
                    if should_verify_interactive_tool_run(
                        action_type=decision.action_type,
                        high_risk=decision.high_risk,
                    ):
                        verification = verify_interactive_tool_run(
                            tool_name=tool_name,
                            output=str(result),
                            execution_status="success",
                        )
                outward_result = mask_tool_result_for_external(tool_name, tool_args, result)
                if verification is not None:
                    outward_result = f"{outward_result}\n\n{format_verifier_note(verification)}"
                redacted_input, redacted_result = redact_tool_call_for_audit(tool_name, tool_args, result)
                if verification is not None:
                    redacted_result = f"{redacted_result}\n\n{format_verifier_note(verification)}"
                create_audit_log(
                    session=db2,
                    tool_name=tool_name,
                    tool_input=redacted_input,
                    tool_result=redacted_result,
                    user_id=current_user.id,
                    room_id=room_id,
                    model=None,
                )
                try:
                    remember_tool_event(
                        user_id=user_id_str,
                        room_id=str(room_id),
                        tool_name=tool_name,
                        args=tool_args if isinstance(tool_args, dict) else {},
                        result=redacted_result,
                    )
                except Exception:
                    pass
                # Save bot reply
                bot_user2 = db2.exec(select(ChatUser).where(ChatUser.username == "sparkbot")).scalar_one_or_none()
                if not bot_user2:
                    bot_user2 = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
                    db2.add(bot_user2)
                    db2.commit()
                    db2.refresh(bot_user2)
                bot_reply2 = create_chat_message(
                    session=db2,
                    room_id=room_id,
                    sender_id=bot_user2.id,
                    content=outward_result,
                    sender_type="BOT",
                )
                done_id = str(bot_reply2.id)
                db2.close()
                # Stream result as tokens then done
                for chunk in [outward_result[i:i+80] for i in range(0, len(outward_result), 80)]:
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
    from app.services.guardian.memory import build_memory_context, remember_chat_message

    try:
        remember_chat_message(
            user_id=str(current_user.id),
            room_id=str(room_id),
            role="user",
            content=agent_content,
        )
    except Exception:
        pass

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

    # Inject room persona prefix if set
    if room.persona and room.persona.strip():
        base_prompt = room.persona.strip() + "\n\n" + base_prompt

    if memories:
        mem_block = "\n".join(f"- {m.fact}" for m in memories)
        system_prompt = base_prompt + f"\n\n## What you know about this user:\n{mem_block}"
    else:
        system_prompt = base_prompt

    try:
        memory_context = build_memory_context(
            user_id=str(current_user.id),
            room_id=str(room_id),
            query=agent_content,
        )
    except Exception:
        memory_context = ""
    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    user_id_str = str(current_user.id)

    # Check for /breakglass slash command before routing to LLM
    _breakglass_content = (message_in.content or "").strip()
    if _breakglass_content.lower() in {"/breakglass", "/breakglass close"}:
        from app.services.guardian.auth import (
            close_privileged_session,
            get_active_session,
            is_operator_identity,
        )

        async def breakglass_stream():
            yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"
            session = get_active_session(user_id_str)
            if not is_operator_identity(username=current_user.username, user_type=current_user.type):
                msg = "Break-glass is restricted to configured Sparkbot operators."
            elif _breakglass_content.lower() == "/breakglass close":
                if session:
                    close_privileged_session(user_id_str)
                    msg = "Break-glass mode is now closed."
                else:
                    msg = "Break-glass mode is not currently active."
            elif session:
                ttl_min = session.ttl_remaining() // 60
                msg = f"Break-glass mode is already active. Session expires in {ttl_min} minute(s). Use /breakglass close to end it."
            else:
                msg = (
                    "To open break-glass privileged mode, POST to /api/v1/chat/guardian/breakglass "
                    "with your operator PIN, or use the Telegram bot: send /breakglass and enter your PIN."
                )
            from app.api.deps import get_db as _get_db
            db2 = next(_get_db())
            from sqlmodel import select as _sel
            from app.models import ChatUser, UserType
            from app.crud import create_chat_message as _ccm
            bot_u = db2.exec(_sel(ChatUser).where(ChatUser.username == "sparkbot")).scalar_one_or_none()
            if not bot_u:
                bot_u = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
                db2.add(bot_u)
                db2.commit()
                db2.refresh(bot_u)
            bot_msg = _ccm(session=db2, room_id=room_id, sender_id=bot_u.id, content=msg, sender_type="BOT")
            db2.close()
            yield f"data: {json.dumps({'type': 'token', 'token': msg})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'message_id': str(bot_msg.id)})}\n\n"

        return StreamingResponse(
            breakglass_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    from app.services.guardian.auth import is_operator_identity as _is_operator_identity
    from app.services.guardian.auth import is_operator_privileged as _is_priv
    _user_is_operator = _is_operator_identity(username=current_user.username, user_type=current_user.type)
    _user_is_privileged = _is_priv(user_id_str)

    async def event_stream():
        from app.api.deps import get_db

        yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"

        full_text = ""
        awaiting_confirmation = False
        routing_payload = None
        try:
            from app.api.routes.chat.llm import stream_chat_with_tools
            db = next(get_db())
            async for event in stream_chat_with_tools(
                [{"role": "system", "content": system_prompt}] + openai_history,
                user_id=user_id_str,
                db_session=db,
                room_id=str(room_id),
                agent_name=agent_name,
                room_execution_allowed=room.execution_allowed,
                is_operator=_user_is_operator,
                is_privileged=_user_is_privileged,
            ):
                if event["type"] == "token":
                    full_text += event["token"]
                    yield f"data: {json.dumps({'type': 'token', 'token': event['token']})}\n\n"
                elif event["type"] == "routing":
                    routing_payload = event.get("payload")
                    yield f"data: {json.dumps(event)}\n\n"
                elif event["type"] in ("tool_start", "tool_done"):
                    yield f"data: {json.dumps(event)}\n\n"
                elif event["type"] == "confirm_required":
                    awaiting_confirmation = True
                    yield f"data: {json.dumps(event)}\n\n"
                    break
                elif event["type"] == "privileged_required":
                    awaiting_confirmation = True
                    yield f"data: {json.dumps(event)}\n\n"
                    break
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            return

        if awaiting_confirmation:
            db.close()
            return

        # Save completed bot message — use per-agent bot user when agent is named
        try:
            _bot_agent = agent_name or "sparkbot"
            bot_user = _get_or_create_agent_bot_user(db, _bot_agent)
            bot_reply = create_chat_message(
                session=db,
                room_id=room_id,
                sender_id=bot_user.id,
                content=full_text,
                sender_type="BOT",
                reply_to_id=human_msg_uuid,
                meta_json={"token_guardian": routing_payload, "agent": _bot_agent} if (routing_payload or agent_name) else None,
            )
            bot_reply_id = str(bot_reply.id)  # capture before session closes
            try:
                remember_chat_message(
                    user_id=user_id_str,
                    room_id=str(room_id),
                    role="assistant",
                    content=full_text,
                )
            except Exception:
                pass
            db.close()
            done_event: dict = {"type": "done", "message_id": bot_reply_id}
            if agent_name:
                done_event["agent"] = agent_name
            yield f"data: {json.dumps(done_event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Save failed: {e}'})}\n\n"

    # ── Multi-agent round table stream ─────────────────────────────────────────
    # When `participants` is set and the message has no @mention, loop through
    # each named agent and generate a response. Each agent saves its own message.
    participants_requested = [p.strip().lower() for p in (message_in.participants or []) if p.strip()]

    if participants_requested and not agent_name:
        from app.api.routes.chat.agents import get_agent as _get_agent_info
        from app.api.routes.chat.llm import stream_chat_with_tools as _sct

        async def multi_agent_stream():
            yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"
            for p_handle in participants_requested:
                # "sparkbot" maps to the default bot (not a custom agent)
                if p_handle == "sparkbot":
                    agent_info = {
                        "emoji": "🤖",
                        "system_prompt": LLM_SYSTEM_PROMPT,
                    }
                else:
                    agent_info = _get_agent_info(p_handle)
                if not agent_info:
                    continue  # skip unknown agents

                # Build per-agent system prompt
                p_base = str(agent_info.get("system_prompt") or LLM_SYSTEM_PROMPT)
                if room.persona and room.persona.strip():
                    p_base = room.persona.strip() + "\n\n" + p_base
                if memories:
                    mem_block = "\n".join(f"- {m.fact}" for m in memories)
                    p_system = p_base + f"\n\n## What you know about this user:\n{mem_block}"
                else:
                    p_system = p_base
                if memory_context:
                    p_system += f"\n\n{memory_context}"

                emoji = str(agent_info.get("emoji") or "")
                label = f"{emoji} {p_handle.title()}".strip()
                yield f"data: {json.dumps({'type': 'agent_start', 'agent': p_handle, 'label': label})}\n\n"

                agent_full_text = ""
                agent_routing_payload = None
                try:
                    from app.api.deps import get_db as _get_db2
                    db2 = next(_get_db2())
                    async for event in _sct(
                        [{"role": "system", "content": p_system}] + openai_history,
                        user_id=user_id_str,
                        db_session=db2,
                        room_id=str(room_id),
                        agent_name=p_handle,
                        room_execution_allowed=room.execution_allowed,
                        is_operator=_user_is_operator,
                        is_privileged=_user_is_privileged,
                    ):
                        if event["type"] == "token":
                            agent_full_text += event["token"]
                            yield f"data: {json.dumps({'type': 'token', 'token': event['token'], 'agent': p_handle})}\n\n"
                        elif event["type"] == "routing":
                            agent_routing_payload = event.get("payload")
                        elif event["type"] in ("tool_start", "tool_done"):
                            yield f"data: {json.dumps(event)}\n\n"
                        elif event["type"] in ("confirm_required", "privileged_required"):
                            yield f"data: {json.dumps(event)}\n\n"
                            break
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'agent': p_handle})}\n\n"
                    continue

                if agent_full_text:
                    try:
                        bot_user = _get_or_create_agent_bot_user(db2, p_handle)
                        bot_msg = create_chat_message(
                            session=db2,
                            room_id=room_id,
                            sender_id=bot_user.id,
                            content=agent_full_text,
                            sender_type="BOT",
                            reply_to_id=human_msg_uuid,
                            meta_json={"agent": p_handle, "token_guardian": agent_routing_payload},
                        )
                        agent_msg_id = str(bot_msg.id)  # capture before session closes
                        try:
                            remember_chat_message(user_id=user_id_str, room_id=str(room_id), role="assistant", content=agent_full_text)
                        except Exception:
                            pass
                        db2.close()
                        yield f"data: {json.dumps({'type': 'agent_done', 'agent': p_handle, 'message_id': agent_msg_id})}\n\n"
                    except Exception as e:
                        yield f"data: {json.dumps({'type': 'error', 'error': f'Save failed for {p_handle}: {e}'})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            multi_agent_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Meeting Artifacts ──────────────────────────────────────────────────────────

from fastapi import Query as _Query


@router.get("/{room_id}/artifacts", response_model=list[MeetingArtifactResponse])
def list_meeting_artifacts(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    artifact_type: str | None = _Query(None, alias="type"),
    limit: int = 20,
) -> Any:
    """List meeting artifacts for a room. Requires membership."""
    _require_room_access(session, room_id, current_user)
    artifacts = get_chat_meeting_artifacts(session=session, room_id=room_id, limit=limit)
    if artifact_type:
        artifacts = [a for a in artifacts if a.type.value == artifact_type]
    return artifacts


@router.post("/{room_id}/artifacts", response_model=MeetingArtifactResponse)
def create_meeting_artifact_endpoint(
    room_id: UUID,
    artifact_in: MeetingArtifactCreate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    """Manually create a meeting artifact. OWNER/MOD only."""
    membership = _require_room_access(session, room_id, current_user)
    if membership.role.value not in ("OWNER", "MOD"):
        raise HTTPException(status_code=403, detail="Only OWNERs and MODs can create artifacts")
    artifact = create_chat_meeting_artifact(
        session=session,
        room_id=room_id,
        created_by_user_id=current_user.id,
        type=artifact_in.type.value,
        content_markdown=artifact_in.content_markdown,
        window_start_ts=artifact_in.window_start_ts,
        window_end_ts=artifact_in.window_end_ts,
    )
    return artifact


@router.post("/{room_id}/artifacts/generate")
async def generate_meeting_notes_endpoint(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    """LLM-generate meeting notes from room transcript. OWNER/MOD only."""
    membership = _require_room_access(session, room_id, current_user)
    if membership.role.value not in ("OWNER", "MOD"):
        raise HTTPException(status_code=403, detail="Only OWNERs and MODs can generate notes")
    from datetime import timezone as _tz
    from app.services.guardian.meeting_recorder import generate_meeting_notes
    from app.api.routes.chat.llm import get_model
    model = get_model(str(current_user.id))
    result = await generate_meeting_notes(
        session=session,
        room_id=room_id,
        user_id=current_user.id,
        model=model,
        window_end_ts=datetime.now(_tz.utc),
    )
    return result
