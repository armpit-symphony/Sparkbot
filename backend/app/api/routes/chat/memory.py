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
from app.crud import add_user_memory, clear_user_memories, delete_user_memory, get_user_memories
from app.services.guardian import get_guardian_suite

router = APIRouter(prefix="/memory", tags=["chat-memory"])


class MemoryResponse(BaseModel):
    id: str
    fact: str
    created_at: str


def _fmt(m) -> MemoryResponse:
    return MemoryResponse(id=str(m.id), fact=m.fact, created_at=m.created_at.isoformat())


@router.get("/")
def list_memories(session: SessionDep, current_user: CurrentChatUser) -> Any:
    guardian_suite = get_guardian_suite()
    mems = get_user_memories(session, current_user.id)
    return {
        "memories": [_fmt(m) for m in mems],
        "count": len(mems),
        "memory_guardian_enabled": guardian_suite.memory.memory_guardian_enabled(),
    }


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
