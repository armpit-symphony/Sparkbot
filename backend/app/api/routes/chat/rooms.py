"""
API routes for chat rooms.

Handles room CRUD and membership management.
"""
import json
import os
import re
import time
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
from app.services.guardian import get_guardian_suite

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


_MEETING_STATUS_VALUES = {
    "continue",
    "needs_user_input",
    "needs_approval",
    "recommendation_ready",
    "solved",
    "blocked",
    "looping",
}

_BREAKGLASS_PIN_TTL_SECONDS = max(60, min(int(os.getenv("SPARKBOT_PIN_PROMPT_TTL_SECONDS", "300")), 1800))
_AWAITING_BREAKGLASS_PIN: dict[str, dict[str, Any]] = {}


def _agent_label(agent_name: str, agent_info: Optional[dict[str, Any]] = None) -> str:
    """Return the user-facing label for an agent."""
    info = agent_info or {}
    emoji = str(info.get("emoji") or "")
    display = "Sparkbot" if agent_name == "sparkbot" else agent_name.replace("_", " ").title()
    return f"{emoji} {display}".strip() if emoji else display


def _meeting_role_instruction(agent_name: str, *, chair: bool) -> str:
    """Return meeting-role instructions tuned for the participant."""
    normalized = agent_name.lower()
    if chair:
        return (
            "You are the meeting chair and facilitator. Frame the objective, keep the room moving, "
            "synthesize distinct inputs, and decide whether another round adds value. Treat the human "
            "as the owner and approver, not as a required speaker between turns. Do not ask who should "
            "speak next or say 'next speaker'."
        )
    if "research" in normalized:
        return (
            "You are the researcher. Contribute evidence, relevant patterns, concrete options, and any "
            "missing facts worth checking. Add new information only; do not paraphrase prior speakers."
        )
    if "analyst" in normalized:
        return (
            "You are the analyst. Focus on tradeoffs, bottlenecks, risks, and decision logic. Challenge "
            "weak assumptions and clarify what would make a recommendation strong."
        )
    if normalized in {"coder", "builder", "engineer", "developer"} or any(
        token in normalized for token in ("build", "code", "engineer", "implement")
    ):
        return (
            "You are the implementation voice. Turn ideas into an operating model, execution plan, or "
            "practical build path. Be concrete about sequence, ownership, and feasibility."
        )
    return (
        "You provide an alternate expert angle. Add distinct value, propose a concrete path forward, "
        "and avoid repeating the prior speaker."
    )


def _parse_meeting_status(raw_text: str, default_status: str) -> tuple[str, str]:
    """Parse STATUS/MESSAGE output from the chair and return (status, public_message)."""
    text = (raw_text or "").strip()
    if not text:
        return default_status, ""

    fenced_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        text = fenced_match.group(1).strip()

    try:
        data = json.loads(text)
    except Exception:
        data = None

    if isinstance(data, dict):
        status = str(data.get("status") or default_status).strip().lower()
        message = str(data.get("message") or "").strip()
        if status not in _MEETING_STATUS_VALUES:
            status = default_status
        return status, message or raw_text.strip()

    status_match = re.search(r"(?im)^status\s*:\s*([a-z_]+)\s*$", text)
    message_match = re.search(r"(?ims)^message\s*:\s*(.+)$", text)
    status = status_match.group(1).strip().lower() if status_match else default_status
    if status not in _MEETING_STATUS_VALUES:
        status = default_status

    if message_match:
        message = message_match.group(1).strip()
    else:
        message = re.sub(r"(?im)^status\s*:\s*[a-z_]+\s*$", "", text).strip()
        message = re.sub(r"(?im)^message\s*:\s*", "", message).strip()
    return status, message


def _chunk_text(text: str, size: int = 80) -> list[str]:
    """Split text into SSE-friendly chunks."""
    return [text[i : i + size] for i in range(0, len(text), size)] if text else []


def _meeting_artifact_markdown(objective: str, status: str, content: str) -> str:
    """Convert a chair synthesis into a durable markdown artifact."""
    heading = {
        "needs_user_input": "Owner Input Needed",
        "needs_approval": "Approval Needed",
        "recommendation_ready": "Recommendation",
        "solved": "Resolution",
        "blocked": "Blocker",
        "looping": "Loop Detected",
    }.get(status, "Meeting Update")
    return (
        f"# {heading}\n\n"
        f"## Objective\n{objective.strip() or '(none noted)'}\n\n"
        f"## Outcome\n{content.strip() or '(none noted)'}\n"
    )


def _breakglass_state_key(*, user_id: str, room_id: UUID) -> str:
    return f"{user_id}:{room_id}"


def _prune_breakglass_pin_state(*, state_key: str | None = None) -> None:
    now = time.time()
    stale_keys = [
        key
        for key, state in _AWAITING_BREAKGLASS_PIN.items()
        if now - float(state.get("created_at", 0.0)) > _BREAKGLASS_PIN_TTL_SECONDS
    ]
    if state_key and state_key in stale_keys:
        _AWAITING_BREAKGLASS_PIN.pop(state_key, None)
        stale_keys.remove(state_key)
    for key in stale_keys:
        _AWAITING_BREAKGLASS_PIN.pop(key, None)


def _set_breakglass_pin_state(
    *,
    user_id: str,
    room_id: UUID,
    confirm_id: str | None,
    justification: str = "",
) -> None:
    _prune_breakglass_pin_state()
    _AWAITING_BREAKGLASS_PIN[_breakglass_state_key(user_id=user_id, room_id=room_id)] = {
        "confirm_id": confirm_id,
        "created_at": time.time(),
        "justification": justification.strip(),
    }


def _pop_breakglass_pin_state(*, user_id: str, room_id: UUID) -> dict[str, Any] | None:
    _prune_breakglass_pin_state(state_key=_breakglass_state_key(user_id=user_id, room_id=room_id))
    return _AWAITING_BREAKGLASS_PIN.pop(_breakglass_state_key(user_id=user_id, room_id=room_id), None)


def _peek_breakglass_pin_state(*, user_id: str, room_id: UUID) -> dict[str, Any] | None:
    key = _breakglass_state_key(user_id=user_id, room_id=room_id)
    _prune_breakglass_pin_state(state_key=key)
    return _AWAITING_BREAKGLASS_PIN.get(key)


def _latest_privileged_pending_approval_id(*, session: Session, room_id: UUID) -> str | None:
    try:
        messages, _, _ = get_chat_messages(session=session, room_id=room_id, limit=20)
    except Exception:
        return None
    for message in reversed(messages):
        meta_json = message.meta_json or {}
        if not isinstance(meta_json, dict) or not meta_json.get("privileged_required"):
            continue
        confirm_id = str(meta_json.get("confirm_id") or "").strip()
        if confirm_id:
            return confirm_id
    return None


def _looks_like_self_inspection_query(content: str) -> bool:
    normalized = (content or "").strip().lower()
    if not normalized:
        return False
    patterns = (
        r"\b(?:what|which)\s+version(?:\s+of)?\s+sparkbot\b",
        r"\bwhat\s+version\s+are\s+you\s+running\b",
        r"\bversion\s+of\s+sparkbot\b",
        r"\b(ai stack|model stack|runtime state|safe operational state)\b",
        r"\bwhat (?:ai )?(?:stack|model|provider|route)\b",
        r"\bwhat are you running\b",
        r"\btoken guardian\b",
        r"\bcross[- ]provider fallback\b",
        r"\bdefault (?:provider|model|route)\b",
        r"\bagent overrides?\b",
        r"\bollama\b",
        r"\bopenrouter\b",
        r"\bbreakglass|break-glass\b",
        r"\bprovider/model\b",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def _render_runtime_state_markdown(runtime_state: dict[str, Any]) -> str:
    app_version = str(runtime_state.get("app_version") or "").strip()
    backend_version = str(runtime_state.get("backend_version") or "").strip()
    frontend_version = str(runtime_state.get("frontend_version") or "").strip()
    desktop_shell_version = str(runtime_state.get("desktop_shell_version") or "").strip()
    default_selection = runtime_state.get("default_selection") or {}
    model_stack = runtime_state.get("model_stack") or {}
    routing_policy = runtime_state.get("routing_policy") or {}
    agent_overrides = runtime_state.get("agent_overrides") or {}
    breakglass = runtime_state.get("breakglass") or {}
    ollama_status = runtime_state.get("ollama_status") or {}
    providers = runtime_state.get("providers") or {}

    def _bool_label(value: Any, *, yes: str = "on", no: str = "off", unknown: str = "unknown") -> str:
        if value is None:
            return unknown
        return yes if bool(value) else no

    override_lines = []
    for agent_name, override in agent_overrides.items():
        route = str((override or {}).get("route") or "default")
        model = str((override or {}).get("model") or "").strip()
        override_lines.append(f"- `{agent_name}`: `{route}`{f' via `{model}`' if model else ''}")
    if not override_lines:
        override_lines.append("- none")

    provider_lines = []
    for provider_name in ("ollama", "openrouter", "openai", "anthropic", "google", "groq", "minimax"):
        info = providers.get(provider_name)
        if not info:
            continue
        provider_lines.append(
            f"- `{provider_name}`: configured={_bool_label(info.get('configured'), yes='yes', no='no')} "
            f"reachable={_bool_label(info.get('reachable'), yes='yes', no='no')} "
            f"models_available={_bool_label(info.get('models_available'), yes='yes', no='no')}"
        )

    lines = [
        "## Sparkbot Runtime State",
        f"- app version: `{app_version or 'unknown'}`",
        f"- backend version: `{backend_version or 'unknown'}`",
        f"- frontend version: `{frontend_version or 'unknown'}`",
        f"- desktop shell version: `{desktop_shell_version or 'unknown'}`",
        f"- active model: `{runtime_state.get('active_model') or 'unknown'}`",
        f"- primary stack model: `{model_stack.get('primary') or 'unknown'}`",
        f"- backup stack model 1: `{model_stack.get('backup_1') or 'none'}`",
        f"- backup stack model 2: `{model_stack.get('backup_2') or 'none'}`",
        f"- heavy-hitter model: `{model_stack.get('heavy_hitter') or 'unknown'}`",
        f"- default provider: `{default_selection.get('provider') or 'unknown'}`",
        f"- default model: `{default_selection.get('model') or 'unknown'}`",
        f"- default route mode: `{runtime_state.get('default_route_mode') or 'unknown'}`",
        f"- Token Guardian: `{runtime_state.get('token_guardian_mode') or 'unknown'}`",
        f"- cross-provider fallback: `{_bool_label(routing_policy.get('cross_provider_fallback'))}`",
        f"- Ollama reachable: `{_bool_label(ollama_status.get('reachable'), yes='yes', no='no')}`",
        f"- Ollama base URL: `{ollama_status.get('base_url') or runtime_state.get('local_runtime', {}).get('base_url') or 'unknown'}`",
        f"- OpenRouter configured: `{_bool_label(runtime_state.get('openrouter_configured'), yes='yes', no='no')}`",
        f"- breakglass active: `{_bool_label(breakglass.get('active'), yes='yes', no='no')}`",
    ]
    if breakglass.get("active"):
        lines.append(f"- breakglass TTL remaining: `{int(breakglass.get('ttl_remaining') or 0)}` seconds")

    lines.extend(["", "## Agent Overrides", *override_lines, "", "## Provider Status", *(provider_lines or ["- none"])])
    return "\n".join(lines)


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
    user_id_str = str(current_user.id)
    raw_content = message_in.content or ""
    stripped_content = raw_content.strip()

    async def _stream_confirmed_tool(confirm_id: str, *, prelude: str | None = None):
        from app.api.routes.chat.llm import (
            consume_pending,
            mask_tool_result_for_external,
            redact_tool_call_for_audit,
            serialize_tool_args_for_audit,
        )
        from app.api.routes.chat.tools import execute_tool
        guardian_suite = get_guardian_suite()

        pending = consume_pending(confirm_id)
        if not pending:
            yield f"data: {json.dumps({'type': 'error', 'error': 'Confirmation expired or invalid'})}\n\n"
            return

        tool_name = pending["tool"]
        tool_args = pending["args"]
        user_id_str = str(current_user.id)
        user_is_operator = guardian_suite.auth.is_operator_identity(username=current_user.username, user_type=current_user.type)
        user_is_privileged = guardian_suite.auth.is_operator_privileged(user_id_str)

        try:
            from app.api.deps import get_db as _get_db
            from app.crud import create_audit_log
            db2 = next(_get_db())
            decision = guardian_suite.policy.decide_tool_use(
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
                result = await guardian_suite.executive.exec_with_guard(
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
                if guardian_suite.verifier.should_verify_interactive_tool_run(
                    action_type=decision.action_type,
                    high_risk=decision.high_risk,
                ):
                    verification = guardian_suite.verifier.verify_interactive_tool_run(
                        tool_name=tool_name,
                        output=str(result),
                        execution_status="success",
                    )
            outward_result = mask_tool_result_for_external(tool_name, tool_args, result)
            if verification is not None:
                outward_result = f"{outward_result}\n\n{guardian_suite.verifier.format_verifier_note(verification)}"
            if prelude:
                outward_result = f"{prelude}\n\n{outward_result}"
            redacted_input, redacted_result = redact_tool_call_for_audit(tool_name, tool_args, result)
            if verification is not None:
                redacted_result = f"{redacted_result}\n\n{guardian_suite.verifier.format_verifier_note(verification)}"
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
                guardian_suite.memory.remember_tool_event(
                    user_id=user_id_str,
                    room_id=str(room_id),
                    tool_name=tool_name,
                    args=tool_args if isinstance(tool_args, dict) else {},
                    result=redacted_result,
                )
            except Exception:
                pass
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
            for chunk in [outward_result[i:i+80] for i in range(0, len(outward_result), 80)]:
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'message_id': done_id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    # ── Confirmed write-tool execution path ───────────────────────────────────
    if message_in.confirm_id:
        return StreamingResponse(
            _stream_confirmed_tool(message_in.confirm_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    pending_pin_state = _peek_breakglass_pin_state(user_id=user_id_str, room_id=room_id)
    if pending_pin_state and stripped_content and stripped_content.lower() not in {"/breakglass", "/breakglass close"}:
        from app.crud import create_audit_log
        from app.services.guardian.auth import (
            get_active_session,
            is_locked_out,
            is_operator_identity,
            open_privileged_session,
            verify_pin,
        )

        async def breakglass_pin_stream():
            from app.services.guardian.spine import emit_breakglass_event

            confirm_id = str(pending_pin_state.get("confirm_id") or "").strip() or None
            lower_content = stripped_content.lower()
            sanitized_human = "/breakglass cancel" if lower_content in {"/cancel", "/deny", "no"} else "/breakglass PIN"
            human_msg = create_chat_message(
                session=session,
                room_id=room_id,
                sender_id=current_user.id,
                content=sanitized_human,
                sender_type=current_user.type.value if hasattr(current_user.type, "value") else "HUMAN",
                reply_to_id=message_in.reply_to_id,
                meta_json={"breakglass_pin_submission": True},
            )
            yield f"data: {json.dumps({'type': 'human_message', 'message_id': str(human_msg.id)})}\n\n"

            if lower_content in {"/cancel", "/deny", "no"}:
                _pop_breakglass_pin_state(user_id=user_id_str, room_id=room_id)
                emit_breakglass_event(
                    room_id=str(room_id),
                    user_id=user_id_str,
                    event_type="breakglass.cancelled",
                    confirm_id=confirm_id,
                )
                msg = (
                    "Breakglass request cancelled. "
                    "If you still want to run the waiting privileged action, type `/breakglass` again."
                    if confirm_id
                    else "Breakglass request cancelled."
                )
            elif not is_operator_identity(username=current_user.username, user_type=current_user.type):
                _pop_breakglass_pin_state(user_id=user_id_str, room_id=room_id)
                msg = "Breakglass is restricted to configured Sparkbot operators."
            elif is_locked_out(user_id_str):
                _pop_breakglass_pin_state(user_id=user_id_str, room_id=room_id)
                msg = "Too many failed PIN attempts. Wait 5 minutes, then type `/breakglass` to try again."
            elif verify_pin(user_id_str, stripped_content):
                stored_justification = str(pending_pin_state.get("justification") or "").strip()
                _pop_breakglass_pin_state(user_id=user_id_str, room_id=room_id)
                priv_session = get_active_session(user_id_str) or open_privileged_session(
                    user_id_str,
                    operator=str(current_user.username or user_id_str),
                    justification=stored_justification,
                )
                try:
                    create_audit_log(
                        session=session,
                        tool_name="breakglass_session_open",
                        tool_input=json.dumps(
                            {
                                "operator": str(current_user.username or user_id_str),
                                "session_id": priv_session.session_id,
                                "justification": priv_session.justification,
                                "expires_at": priv_session.expires_at_local(),
                                "ttl_seconds": priv_session.ttl_remaining(),
                                "room_id": str(room_id),
                            }
                        ),
                        tool_result="ok",
                        user_id=current_user.id,
                        room_id=room_id,
                    )
                except Exception:
                    pass
                emit_breakglass_event(
                    room_id=str(room_id),
                    user_id=user_id_str,
                    event_type="breakglass.opened",
                    confirm_id=confirm_id,
                    payload={"session_id": priv_session.session_id},
                )
                if confirm_id:
                    async for event in _stream_confirmed_tool(
                        confirm_id,
                        prelude="Breakglass approved for this action.",
                    ):
                        yield event
                    return
                expires_at_str = priv_session.expires_at_local()
                justification_line = f"\nReason: *{priv_session.justification}*\n" if priv_session.justification else "\n"
                msg = (
                    f"Breakglass approved. Privileged mode active until **{expires_at_str}**.\n"
                    f"{justification_line}\n"
                    "Scope: `vault`, `service_control`.\n"
                    "Send your privileged request as a new message, or use `/breakglass close` to exit."
                )
            else:
                _set_breakglass_pin_state(user_id=user_id_str, room_id=room_id, confirm_id=confirm_id)
                try:
                    create_audit_log(
                        session=session,
                        tool_name="breakglass_pin_failed",
                        tool_input=json.dumps({"operator": str(current_user.username or user_id_str), "room_id": str(room_id)}),
                        tool_result="failed",
                        user_id=current_user.id,
                        room_id=room_id,
                    )
                except Exception:
                    pass
                emit_breakglass_event(
                    room_id=str(room_id),
                    user_id=user_id_str,
                    event_type="breakglass.pin_failed",
                    confirm_id=confirm_id,
                )
                msg = "Incorrect operator PIN. Try again, or reply `NO` to cancel."

            bot_user = _get_or_create_agent_bot_user(session, "sparkbot")
            bot_msg = create_chat_message(
                session=session,
                room_id=room_id,
                sender_id=bot_user.id,
                content=msg,
                sender_type="BOT",
                reply_to_id=human_msg.id,
                meta_json={"breakglass": True, "confirm_id": confirm_id} if confirm_id else {"breakglass": True},
            )
            for chunk in _chunk_text(msg):
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'message_id': str(bot_msg.id)})}\n\n"

        return StreamingResponse(
            breakglass_pin_stream(),
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
    guardian_suite = get_guardian_suite()

    try:
        guardian_suite.memory.remember_chat_message(
            user_id=str(current_user.id),
            room_id=str(room_id),
            role="user",
            content=agent_content,
        )
    except Exception:
        pass

    if _looks_like_self_inspection_query(agent_content):
        from app.api.routes.chat.model import build_safe_runtime_state

        async def runtime_state_stream():
            yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"
            runtime_state = await build_safe_runtime_state(current_user)
            runtime_text = _render_runtime_state_markdown(runtime_state)
            bot_user = _get_or_create_agent_bot_user(session, "sparkbot")
            bot_msg = create_chat_message(
                session=session,
                room_id=room_id,
                sender_id=bot_user.id,
                content=runtime_text,
                sender_type="BOT",
                reply_to_id=human_msg_uuid,
                meta_json={"safe_runtime_state": True},
            )
            try:
                remember_chat_message(
                    user_id=user_id_str,
                    room_id=str(room_id),
                    role="assistant",
                    content=runtime_text,
                )
            except Exception:
                pass
            for chunk in _chunk_text(runtime_text):
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'message_id': str(bot_msg.id)})}\n\n"

        return StreamingResponse(
            runtime_state_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

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
        memory_context = guardian_suite.memory.build_memory_context(
            user_id=str(current_user.id),
            room_id=str(room_id),
            query=agent_content,
        )
    except Exception:
        memory_context = ""
    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    # Inject room context — name, description, Computer Control gate
    _room_ctx_parts = [f"Room: {room.name}"]
    if room.description and room.description.strip():
        _room_ctx_parts.append(f"Purpose: {room.description.strip()}")
    _room_ctx_parts.append(
        "Computer Control: ON — local machine, browser, terminal, and comms tools are enabled"
        if room.execution_allowed
        else "Computer Control: OFF — privileged commands, edits, browser writes, vault access, and comms sends require operator PIN"
    )
    system_prompt += "\n\n## Room Context\n" + "\n".join(_room_ctx_parts)

    # Check for /breakglass slash command before routing to LLM
    _breakglass_content = (message_in.content or "").strip()
    _breakglass_lower = _breakglass_content.lower()
    _breakglass_inline_justification = (
        _breakglass_content[len("/breakglass"):].strip()
        if _breakglass_lower.startswith("/breakglass") and _breakglass_lower not in {"/breakglass", "/breakglass close"}
        else ""
    )
    if _breakglass_lower in {"/breakglass", "/breakglass close"} or _breakglass_inline_justification:
        from app.crud import create_audit_log

        async def breakglass_stream():
            from app.services.guardian.spine import emit_breakglass_event

            yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"
            priv_session = guardian_suite.auth.get_active_session(user_id_str)
            pending_confirm_id = _latest_privileged_pending_approval_id(session=session, room_id=room_id)
            if not guardian_suite.auth.is_operator_identity(username=current_user.username, user_type=current_user.type):
                msg = "Break-glass is restricted to configured Sparkbot operators."
            elif _breakglass_content.lower() == "/breakglass close":
                if priv_session:
                    guardian_suite.auth.close_privileged_session(user_id_str)
                    _pop_breakglass_pin_state(user_id=user_id_str, room_id=room_id)
                    try:
                        create_audit_log(
                            session=session,
                            tool_name="breakglass_session_close",
                            tool_input=json.dumps(
                                {
                                    "operator": str(current_user.username or user_id_str),
                                    "session_id": priv_session.session_id,
                                    "room_id": str(room_id),
                                }
                            ),
                            tool_result="ok",
                            user_id=current_user.id,
                            room_id=room_id,
                        )
                    except Exception:
                        pass
                    emit_breakglass_event(
                        room_id=str(room_id),
                        user_id=user_id_str,
                        event_type="breakglass.closed",
                        payload={"session_id": priv_session.session_id},
                    )
                    msg = "Breakglass mode is now closed."
                else:
                    msg = "Breakglass mode is not currently active."
            elif priv_session and pending_confirm_id:
                async for event in _stream_confirmed_tool(
                    pending_confirm_id,
                    prelude="Breakglass already active. Continuing the waiting privileged action.",
                ):
                    yield event
                return
            elif priv_session:
                msg = (
                    f"Breakglass mode is already active. Session expires at **{priv_session.expires_at_local()}**. "
                    "Use `/breakglass close` to end it."
                )
            else:
                _set_breakglass_pin_state(
                    user_id=user_id_str,
                    room_id=room_id,
                    confirm_id=pending_confirm_id,
                    justification=_breakglass_inline_justification,
                )
                emit_breakglass_event(
                    room_id=str(room_id),
                    user_id=user_id_str,
                    event_type="breakglass.requested",
                    confirm_id=pending_confirm_id,
                )
                if _breakglass_inline_justification:
                    msg = (
                        f"Breakglass requested — reason: *{_breakglass_inline_justification}*\n\n"
                        "Please enter your operator PIN. Reply `NO` to cancel."
                    )
                else:
                    msg = (
                        "Breakglass requested. Please enter your operator PIN "
                        "(or include a reason next time: `/breakglass <reason>`).\n\n"
                        "Reply `NO` to cancel."
                    )
            bot_u = _get_or_create_agent_bot_user(session, "sparkbot")
            bot_msg = create_chat_message(
                session=session,
                room_id=room_id,
                sender_id=bot_u.id,
                content=msg,
                sender_type="BOT",
                reply_to_id=human_msg_uuid,
                meta_json={"breakglass": True, "confirm_id": pending_confirm_id} if pending_confirm_id else {"breakglass": True},
            )
            for chunk in _chunk_text(msg):
                yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'message_id': str(bot_msg.id)})}\n\n"

        return StreamingResponse(
            breakglass_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    _user_is_operator = guardian_suite.auth.is_operator_identity(username=current_user.username, user_type=current_user.type)
    _user_is_privileged = guardian_suite.auth.is_operator_privileged(user_id_str)

    async def event_stream():
        from app.api.deps import get_db

        yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"

        full_text = ""
        confirm_event = None
        privileged_event = None
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
                    confirm_event = event
                    yield f"data: {json.dumps(event)}\n\n"
                    break
                elif event["type"] == "privileged_required":
                    privileged_event = event
                    break
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            return

        if confirm_event:
            db.close()
            return

        if privileged_event:
            prompt_text = (
                "Computer Control is off for this room. Type `/breakglass` to continue, then enter your PIN."
            )
            try:
                bot_user = _get_or_create_agent_bot_user(db, agent_name or "sparkbot")
                meta_json: dict[str, Any] = {
                    "privileged_required": True,
                    "confirm_id": privileged_event.get("confirm_id"),
                    "tool": privileged_event.get("tool"),
                    "risk": privileged_event.get("risk"),
                }
                if agent_name:
                    meta_json["agent"] = agent_name
                bot_reply = create_chat_message(
                    session=db,
                    room_id=room_id,
                    sender_id=bot_user.id,
                    content=prompt_text,
                    sender_type="BOT",
                    reply_to_id=human_msg_uuid,
                    meta_json=meta_json,
                )
                try:
                    remember_chat_message(
                        user_id=user_id_str,
                        room_id=str(room_id),
                        role="assistant",
                        content=prompt_text,
                    )
                except Exception:
                    pass
                db.close()
                for chunk in _chunk_text(prompt_text):
                    yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
                done_event: dict[str, Any] = {"type": "done", "message_id": str(bot_reply.id)}
                if agent_name:
                    done_event["agent"] = agent_name
                yield f"data: {json.dumps(done_event)}\n\n"
                return
            except Exception as e:
                db.close()
                yield f"data: {json.dumps({'type': 'error', 'error': f'Save failed: {e}'})}\n\n"
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
                guardian_suite.memory.remember_chat_message(
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

        def _lookup_agent_info(agent_handle: str) -> Optional[dict[str, Any]]:
            if agent_handle == "sparkbot":
                return {
                    "emoji": "🤖",
                    "system_prompt": LLM_SYSTEM_PROMPT,
                }
            return _get_agent_info(agent_handle)

        async def _run_agent_turn(
            *,
            participant_handle: str,
            discussion_history: list[dict[str, str]],
            objective: str,
            phase_prompt: str,
            chair_handle: str,
            parse_status: bool = False,
            default_status: str = "recommendation_ready",
        ) -> dict[str, Any]:
            agent_info = _lookup_agent_info(participant_handle)
            if not agent_info:
                return {"content": "", "status": None, "halted": False, "events": []}

            p_base = str(agent_info.get("system_prompt") or LLM_SYSTEM_PROMPT)
            if room.persona and room.persona.strip():
                p_base = room.persona.strip() + "\n\n" + p_base

            role_instruction = _meeting_role_instruction(
                participant_handle,
                chair=participant_handle == chair_handle,
            )
            p_base += (
                "\n\n## Autonomous roundtable protocol\n"
                "This is an autonomous meeting room. Continue the discussion without waiting for the owner "
                "between turns. One participant speaks at a time, but the handoff is automatic. Avoid filler, "
                "avoid generic agreement, and do not ask for the next speaker.\n\n"
                f"## Your role\n{role_instruction}"
            )

            if memories:
                mem_block = "\n".join(f"- {m.fact}" for m in memories)
                p_system = p_base + f"\n\n## What you know about this user:\n{mem_block}"
            else:
                p_system = p_base
            if memory_context:
                p_system += f"\n\n{memory_context}"

            label = _agent_label(participant_handle, agent_info)
            emitted_events = [
                f"data: {json.dumps({'type': 'agent_start', 'agent': participant_handle, 'label': label})}\n\n"
            ]

            agent_full_text = ""
            agent_routing_payload = None
            stop_event = None
            db2 = None
            try:
                from app.api.deps import get_db as _get_db2

                db2 = next(_get_db2())
                turn_messages = [{"role": "system", "content": p_system}] + discussion_history + [
                    {
                        "role": "user",
                        "content": (
                            f"Meeting objective from the owner:\n{objective.strip() or agent_content.strip()}\n\n"
                            f"{phase_prompt}"
                        ).strip(),
                    }
                ]
                async for event in _sct(
                    turn_messages,
                    user_id=user_id_str,
                    db_session=db2,
                    room_id=str(room_id),
                    agent_name=participant_handle,
                    room_execution_allowed=room.execution_allowed,
                    is_operator=_user_is_operator,
                    is_privileged=_user_is_privileged,
                ):
                    if event["type"] == "token":
                        agent_full_text += event["token"]
                        if not parse_status:
                            emitted_events.append(
                                f"data: {json.dumps({'type': 'token', 'token': event['token'], 'agent': participant_handle})}\n\n"
                            )
                    elif event["type"] == "routing":
                        agent_routing_payload = event.get("payload")
                    elif event["type"] in ("tool_start", "tool_done"):
                        emitted_events.append(f"data: {json.dumps(event)}\n\n")
                    elif event["type"] in ("confirm_required", "privileged_required"):
                        stop_event = event
                        emitted_events.append(f"data: {json.dumps(event)}\n\n")
                        break
            except Exception as e:
                if db2:
                    db2.close()
                emitted_events.append(
                    f"data: {json.dumps({'type': 'error', 'error': str(e), 'agent': participant_handle, 'fatal': False})}\n\n"
                )
                return {"content": "", "status": "blocked", "halted": False, "failed": True, "events": emitted_events}

            if stop_event:
                if db2:
                    db2.close()
                return {"content": "", "status": "needs_approval", "halted": True, "events": emitted_events}

            public_text = agent_full_text.strip()
            meeting_status = None
            if parse_status:
                meeting_status, public_text = _parse_meeting_status(agent_full_text, default_status=default_status)
                for chunk in _chunk_text(public_text):
                    emitted_events.append(
                        f"data: {json.dumps({'type': 'token', 'token': chunk, 'agent': participant_handle})}\n\n"
                    )

            if not public_text:
                if db2:
                    db2.close()
                return {"content": "", "status": meeting_status, "halted": False, "events": emitted_events}

            try:
                bot_user = _get_or_create_agent_bot_user(db2, participant_handle)
                meta_json: dict[str, Any] = {"agent": participant_handle}
                if agent_routing_payload:
                    meta_json["token_guardian"] = agent_routing_payload
                if meeting_status:
                    meta_json["meeting_status"] = meeting_status
                bot_msg = create_chat_message(
                    session=db2,
                    room_id=room_id,
                    sender_id=bot_user.id,
                    content=public_text,
                    sender_type="BOT",
                    reply_to_id=human_msg_uuid,
                    meta_json=meta_json,
                )
                agent_msg_id = str(bot_msg.id)
                try:
                    remember_chat_message(
                        user_id=user_id_str,
                        room_id=str(room_id),
                        role="assistant",
                        content=public_text,
                    )
                except Exception:
                    pass
                if meeting_status and meeting_status != "continue":
                    try:
                        create_chat_meeting_artifact(
                            session=db2,
                            room_id=room_id,
                            created_by_user_id=current_user.id,
                            type="notes",
                            content_markdown=_meeting_artifact_markdown(objective, meeting_status, public_text),
                            meta_json={
                                "source": "autonomous_meeting",
                                "agent": participant_handle,
                                "meeting_status": meeting_status,
                            },
                        )
                    except Exception:
                        pass
                discussion_history.append({"role": "assistant", "content": f"{label}: {public_text}"})
                db2.close()
                emitted_events.append(
                    f"data: {json.dumps({'type': 'agent_done', 'agent': participant_handle, 'message_id': agent_msg_id})}\n\n"
                )
                return {
                    "content": public_text,
                    "status": meeting_status,
                    "halted": False,
                    "events": emitted_events,
                }
            except Exception as e:
                if db2:
                    db2.close()
                emitted_events.append(
                    f"data: {json.dumps({'type': 'error', 'error': f'Save failed for {participant_handle}: {e}', 'agent': participant_handle, 'fatal': False})}\n\n"
                )
                return {"content": "", "status": "blocked", "halted": False, "failed": True, "events": emitted_events}

        async def autonomous_meeting_stream(valid_participants: list[str]):
            yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"

            chair_handle = "sparkbot" if "sparkbot" in valid_participants else valid_participants[0]
            specialists = [handle for handle in valid_participants if handle != chair_handle]
            discussion_history = list(openai_history)
            objective = agent_content.strip() or message_in.content.strip()
            minimum_turns = 2 if not specialists else min(10, max(4, (len(valid_participants) * 2) + 1))
            room_cap = max(int(room.meeting_mode_max_bot_msgs_per_min or 0), 0)
            max_bot_turns = min(10, max(minimum_turns, room_cap))
            turns_used = 0

            opening_prompt = (
                "Current phase: initial framing.\n"
                "Frame the problem, define the working objective, and explain how the room should approach it. "
                "Keep it concise and actionable. Do not ask for the next speaker."
            )
            opening_result = await _run_agent_turn(
                participant_handle=chair_handle,
                discussion_history=discussion_history,
                objective=objective,
                phase_prompt=opening_prompt,
                chair_handle=chair_handle,
            )
            for event in opening_result["events"]:
                yield event
            turns_used += 1
            if opening_result.get("halted"):
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            for participant_handle in specialists:
                if turns_used >= max_bot_turns - 1:
                    break
                gather_prompt = (
                    "Current phase: perspective gathering.\n"
                    "Contribute the most useful view from your role. Add distinct evidence, options, tradeoffs, "
                    "or implementation guidance that has not already been said. End with a concrete takeaway. "
                    "Do not ask for another speaker and do not repeat the objective."
                )
                gather_result = await _run_agent_turn(
                    participant_handle=participant_handle,
                    discussion_history=discussion_history,
                    objective=objective,
                    phase_prompt=gather_prompt,
                    chair_handle=chair_handle,
                )
                for event in gather_result["events"]:
                    yield event
                turns_used += 1
                if gather_result.get("halted"):
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

            synthesis_prompt = (
                "Current phase: synthesis.\n"
                "Assess whether the room should continue or stop. Return exactly in this format:\n"
                "STATUS: <continue|needs_user_input|needs_approval|recommendation_ready|solved|blocked|looping>\n"
                "MESSAGE:\n"
                "## Recommendation\n"
                "<one clear recommendation>\n\n"
                "## Action Plan\n"
                "- [ ] <step 1>\n"
                "- [ ] <step 2>\n"
                "- [ ] <step 3>\n\n"
                "## Owner Input Or Approval\n"
                "- <single approval, decision, or 'none'>\n\n"
                "## Stop Reason\n"
                "- <why continue or stop now>\n\n"
                "Choose continue only if another round is likely to add substantial value. If approval or missing "
                "owner input is needed, state that explicitly. Do not write generic discussion summaries."
            )
            synthesis_result = await _run_agent_turn(
                participant_handle=chair_handle,
                discussion_history=discussion_history,
                objective=objective,
                phase_prompt=synthesis_prompt,
                chair_handle=chair_handle,
                parse_status=True,
                default_status="recommendation_ready",
            )
            for event in synthesis_result["events"]:
                yield event
            turns_used += 1
            if synthesis_result.get("halted"):
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            status = synthesis_result.get("status") or "recommendation_ready"
            can_refine = status == "continue" and specialists and turns_used < max_bot_turns
            final_prompt = (
                "Current phase: final synthesis.\n"
                "Return exactly in this format:\n"
                "STATUS: <needs_user_input|needs_approval|recommendation_ready|solved|blocked|looping>\n"
                "MESSAGE:\n"
                "## Recommendation\n"
                "<best recommendation>\n\n"
                "## Action Plan\n"
                "- [ ] <specific next action>\n"
                "- [ ] <specific next action>\n"
                "- [ ] <specific next action>\n\n"
                "## Owners\n"
                "- <owner> — <responsibility>\n\n"
                "## Open Questions / Approval Needed\n"
                "- <item or 'none'>\n\n"
                "## Stop Reason\n"
                "- <why the room is stopping>\n\n"
                "Do not choose continue in this phase. Do not ask for the next speaker. Produce a real plan, not generic advice."
            )
            if can_refine:
                for participant_handle in specialists:
                    if turns_used >= max_bot_turns - 1:
                        break
                    refine_prompt = (
                        "Current phase: challenge and refinement.\n"
                        "Focus on weak assumptions, missing constraints, or higher-value alternatives in the current "
                        "direction. Add only non-duplicative value and keep it tight. If a concrete plan should be "
                        "rewritten, rewrite it instead of discussing it abstractly."
                    )
                    refine_result = await _run_agent_turn(
                        participant_handle=participant_handle,
                        discussion_history=discussion_history,
                        objective=objective,
                        phase_prompt=refine_prompt,
                        chair_handle=chair_handle,
                    )
                    for event in refine_result["events"]:
                        yield event
                    turns_used += 1
                    if refine_result.get("halted"):
                        yield f"data: {json.dumps({'type': 'done'})}\n\n"
                        return

                final_result = await _run_agent_turn(
                    participant_handle=chair_handle,
                    discussion_history=discussion_history,
                    objective=objective,
                    phase_prompt=final_prompt,
                    chair_handle=chair_handle,
                    parse_status=True,
                    default_status="recommendation_ready",
                )
                for event in final_result["events"]:
                    yield event
                if final_result.get("halted"):
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return
            elif status == "continue":
                final_result = await _run_agent_turn(
                    participant_handle=chair_handle,
                    discussion_history=discussion_history,
                    objective=objective,
                    phase_prompt=final_prompt,
                    chair_handle=chair_handle,
                    parse_status=True,
                    default_status="recommendation_ready",
                )
                for event in final_result["events"]:
                    yield event
                if final_result.get("halted"):
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

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
                    yield f"data: {json.dumps({'type': 'error', 'error': str(e), 'agent': p_handle, 'fatal': False})}\n\n"
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
                            guardian_suite.memory.remember_chat_message(user_id=user_id_str, room_id=str(room_id), role="assistant", content=agent_full_text)
                        except Exception:
                            pass
                        db2.close()
                        yield f"data: {json.dumps({'type': 'agent_done', 'agent': p_handle, 'message_id': agent_msg_id})}\n\n"
                    except Exception as e:
                        yield f"data: {json.dumps({'type': 'error', 'error': f'Save failed for {p_handle}: {e}', 'agent': p_handle, 'fatal': False})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        valid_participants: list[str] = []
        seen_participants: set[str] = set()
        for p_handle in participants_requested:
            if p_handle in seen_participants:
                continue
            if not _lookup_agent_info(p_handle):
                continue
            seen_participants.add(p_handle)
            valid_participants.append(p_handle)

        if participants_requested and not valid_participants:
            async def unresolved_participants_stream():
                yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"
                message_text = (
                    "No valid meeting participants were resolved for this room. "
                    "Relaunch the meeting from Workstation or rewire the invited desks so each seat maps to a real chat agent."
                )
                yield f"data: {json.dumps({'type': 'error', 'error': message_text})}\n\n"

            return StreamingResponse(
                unresolved_participants_stream(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        if room.meeting_mode_enabled and valid_participants:
            return StreamingResponse(
                autonomous_meeting_stream(valid_participants),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

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
        meta_json=artifact_in.meta_json,
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
    from app.api.routes.chat.llm import get_model
    model = get_model(str(current_user.id))
    result = await get_guardian_suite().meeting_recorder.generate_meeting_notes(
        session=session,
        room_id=room_id,
        user_id=current_user.id,
        model=model,
        window_end_ts=datetime.now(_tz.utc),
    )
    return result
