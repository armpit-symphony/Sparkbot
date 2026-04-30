"""
User memory endpoints.

GET    /chat/memory          — list current user's stored memories
DELETE /chat/memory/{id}     — delete a specific memory
DELETE /chat/memory          — clear all memories
"""
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import (
    clear_user_memories,
    delete_user_memory,
    get_user_memories,
    list_delete_proposals,
    restore_soft_deleted_memory,
)
from app.crud import (
    list_memories as list_memory_rows,
)
from app.services.guardian import get_guardian_suite

router = APIRouter(prefix="/memory", tags=["chat-memory"])


class MemoryResponse(BaseModel):
    id: str
    fact: str
    created_at: str
    memory_type: str = "unknown"
    lifecycle_state: str = "active"
    confidence: float | None = None
    verification_state: str | None = None
    pinned: bool = False
    updated_at: str | None = None
    last_used_at: str | None = None
    use_count: int = 0
    mention_count: int = 0
    stale_reason: str | None = None
    delete_proposed_reason: str | None = None


def _fmt(m) -> MemoryResponse:
    return MemoryResponse(
        id=str(m.id),
        fact=m.fact,
        created_at=m.created_at.isoformat(),
        memory_type=getattr(m, "memory_type", "unknown") or "unknown",
        lifecycle_state=getattr(m, "lifecycle_state", "active") or "active",
        pinned=bool(getattr(m, "pinned", False)),
        updated_at=m.updated_at.isoformat() if getattr(m, "updated_at", None) else None,
        last_used_at=m.last_used_at.isoformat() if getattr(m, "last_used_at", None) else None,
        use_count=int(getattr(m, "use_count", 0) or 0),
        mention_count=int(getattr(m, "mention_count", 0) or 0),
        stale_reason=getattr(m, "stale_reason", None),
        delete_proposed_reason=getattr(m, "delete_proposed_reason", None),
    )


@router.get("/")
def list_memories(session: SessionDep, current_user: CurrentChatUser) -> Any:
    guardian_suite = get_guardian_suite()
    mems = get_user_memories(session, current_user.id)
    return {
        "memories": [_fmt(m) for m in mems],
        "count": len(mems),
        "memory_guardian_enabled": guardian_suite.memory.memory_guardian_enabled(),
    }


@router.get("/inspect")
def inspect_memories(
    session: SessionDep,
    current_user: CurrentChatUser,
    state: str | None = None,
    memory_type: str | None = None,
    include_archived: bool = False,
    include_deleted: bool = False,
    limit: int = 100,
) -> Any:
    mems = list_memory_rows(
        session,
        user_id=current_user.id,
        state=state,
        memory_type=memory_type,
        include_archived=include_archived,
        include_deleted=include_deleted,
        limit=limit,
    )
    return {"memories": [_fmt(m) for m in mems], "count": len(mems)}


@router.get("/proposals/delete")
def delete_proposals(session: SessionDep, current_user: CurrentChatUser, limit: int = 100) -> Any:
    mems = list_delete_proposals(session, user_id=current_user.id, limit=limit)
    return {"memories": [_fmt(m) for m in mems], "count": len(mems)}


@router.post("/{memory_id}/restore")
def restore_memory(memory_id: uuid.UUID, session: SessionDep, current_user: CurrentChatUser) -> dict:
    ok = restore_soft_deleted_memory(
        session,
        memory_id,
        operator_id=str(current_user.id),
        user_id=current_user.id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"restored": str(memory_id)}


@router.delete("/{memory_id}")
def remove_memory(memory_id: uuid.UUID, session: SessionDep, current_user: CurrentChatUser) -> dict:
    ok = delete_user_memory(session, memory_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    try:
        get_guardian_suite().memory.delete_fact_memory(user_id=str(current_user.id), memory_id=str(memory_id))
    except Exception:
        pass
    return {"deleted": str(memory_id)}


@router.delete("/")
def clear_memories(session: SessionDep, current_user: CurrentChatUser) -> dict:
    count = clear_user_memories(session, current_user.id)
    cleared_events = 0
    try:
        cleared_events = get_guardian_suite().memory.clear_user_memory_events(user_id=str(current_user.id))
    except Exception:
        pass
    return {"cleared": count, "cleared_memory_events": cleared_events}
