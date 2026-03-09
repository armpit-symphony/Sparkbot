"""
Audit log API — read-only access to the bot action log.

Every tool call made by the LLM is recorded in audit_logs. These endpoints
allow operators to review what the bot has done, filter by tool or room, and
verify that actions were appropriate.

GET /chat/audit            — recent entries, filterable
GET /chat/audit/{entry_id} — single entry with full result text
"""
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import get_audit_logs, get_chat_room_member
from app.models import AuditLog

router = APIRouter(tags=["audit"])


@router.get("/audit")
def list_audit_logs(
    session: SessionDep,
    current_user: CurrentChatUser,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    tool: Optional[str] = Query(default=None, description="Filter by tool name"),
    room_id: Optional[str] = Query(default=None, description="Filter by room UUID"),
) -> dict:
    """
    Return recent bot audit log entries.

    Results are newest-first. Use `tool` to filter by tool name (e.g. `web_search`)
    or `room_id` to scope to a specific room.
    """
    if not room_id:
        raise HTTPException(status_code=400, detail="room_id is required")
    try:
        room_uuid = uuid.UUID(room_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid room_id UUID")
    membership = get_chat_room_member(session, room_uuid, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    rows, total = get_audit_logs(
        session=session,
        limit=limit,
        offset=offset,
        tool_name=tool,
        room_id=room_uuid,
    )

    return {
        "items": [_format_entry(e) for e in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/audit/{entry_id}")
def get_audit_entry(
    entry_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict:
    """Return a single audit log entry with full tool input and result."""
    entry = session.get(AuditLog, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit entry not found")
    if entry.room_id:
        membership = get_chat_room_member(session, entry.room_id, current_user.id)
        if not membership:
            raise HTTPException(status_code=403, detail="Not a member of this room")
    return _format_entry(entry, full=True)


def _format_entry(entry: AuditLog, full: bool = False) -> dict:
    import json
    try:
        input_data = json.loads(entry.tool_input)
    except Exception:
        input_data = entry.tool_input

    result = entry.tool_result if full else entry.tool_result[:200]

    return {
        "id": str(entry.id),
        "created_at": entry.created_at.isoformat(),
        "tool_name": entry.tool_name,
        "tool_input": input_data,
        "tool_result": result,
        "agent_name": entry.agent_name,
        "model": entry.model,
        "user_id": str(entry.user_id) if entry.user_id else None,
        "room_id": str(entry.room_id) if entry.room_id else None,
    }
