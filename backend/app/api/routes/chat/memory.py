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

router = APIRouter(prefix="/memory", tags=["chat-memory"])


class MemoryResponse(BaseModel):
    id: str
    fact: str
    created_at: str


def _fmt(m) -> MemoryResponse:
    return MemoryResponse(id=str(m.id), fact=m.fact, created_at=m.created_at.isoformat())


@router.get("/")
def list_memories(session: SessionDep, current_user: CurrentChatUser) -> Any:
    mems = get_user_memories(session, current_user.id)
    return {"memories": [_fmt(m) for m in mems], "count": len(mems)}


@router.delete("/{memory_id}")
def remove_memory(memory_id: uuid.UUID, session: SessionDep, current_user: CurrentChatUser) -> dict:
    ok = delete_user_memory(session, memory_id, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": str(memory_id)}


@router.delete("/")
def clear_memories(session: SessionDep, current_user: CurrentChatUser) -> dict:
    count = clear_user_memories(session, current_user.id)
    return {"cleared": count}
