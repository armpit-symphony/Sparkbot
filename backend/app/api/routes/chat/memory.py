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
    add_user_memory,
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
from app.services.guardian.memory_os.index_embed import text_similarity

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
    remove_endpoint: str | None = None
    correct_endpoint: str | None = None


class ForgetMemoryRequest(BaseModel):
    query: str


class CorrectMemoryRequest(BaseModel):
    fact: str


def _memory_confidence(m) -> float:
    base = 0.58
    state = getattr(m, "lifecycle_state", "active") or "active"
    if state == "active":
        base += 0.14
    if getattr(m, "pinned", False):
        base += 0.1
    base += min(int(getattr(m, "mention_count", 0) or 0) * 0.04, 0.16)
    base += min(int(getattr(m, "use_count", 0) or 0) * 0.03, 0.12)
    memory_type = getattr(m, "memory_type", "unknown") or "unknown"
    if memory_type in {"identity", "preference", "employment", "timezone"}:
        base += 0.05
    if getattr(m, "deprecated_by", None):
        base -= 0.35
    if state in {"stale", "archived"}:
        base -= 0.18
    return round(max(0.05, min(base, 0.99)), 2)


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
        confidence=_memory_confidence(m),
        remove_endpoint=f"/api/v1/chat/memory/{m.id}",
        correct_endpoint=f"/api/v1/chat/memory/{m.id}/correct",
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
    effective_limit = max(1, min(int(limit or 8), 100))
    mems = list_memory_rows(
        session,
        user_id=current_user.id,
        state=state,
        memory_type=memory_type,
        include_archived=include_archived,
        include_deleted=include_deleted,
        limit=max(effective_limit, 100),
    )
    ranked = sorted(mems, key=lambda item: (-_memory_confidence(item), str(item.fact)))[:effective_limit]
    return {
        "memories": [_fmt(m) for m in ranked],
        "count": len(ranked),
        "total_available": len(mems),
        "actions": {"remove": "DELETE /api/v1/chat/memory/{id}", "correct": "POST /api/v1/chat/memory/{id}/correct"},
    }


@router.post("/forget")
def forget_memory_by_query(payload: ForgetMemoryRequest, session: SessionDep, current_user: CurrentChatUser) -> dict:
    query = " ".join((payload.query or "").split()).strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    mems = get_user_memories(session, current_user.id)
    best = None
    for mem in mems:
        score = max(text_similarity(query, mem.fact), text_similarity(f"User {query}", mem.fact))
        if best is None or score > best[1]:
            best = (mem, score)
    if best and best[1] >= 0.62:
        mem, score = best
        ok = delete_user_memory(session, mem.id, current_user.id)
        if not ok:
            raise HTTPException(status_code=404, detail="Memory not found")
        try:
            get_guardian_suite().memory.delete_fact_memory(user_id=str(current_user.id), memory_id=str(mem.id))
        except Exception:
            pass
        return {"deleted": str(mem.id), "fact": mem.fact, "score": round(float(score), 4)}
    try:
        result = get_guardian_suite().memory.forget_fact_by_query(user_id=str(current_user.id), query=query)
    except Exception:
        result = {"deleted": False, "reason": "no_match"}
    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail="No matching memory found")
    return result


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


@router.post("/{memory_id}/correct")
def correct_memory(
    memory_id: uuid.UUID,
    payload: CorrectMemoryRequest,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict:
    fact = " ".join((payload.fact or "").split()).strip()
    if not fact:
        raise HTTPException(status_code=400, detail="Fact is required")
    if not delete_user_memory(session, memory_id, current_user.id):
        raise HTTPException(status_code=404, detail="Memory not found")
    try:
        get_guardian_suite().memory.delete_fact_memory(user_id=str(current_user.id), memory_id=str(memory_id))
    except Exception:
        pass
    try:
        mem = add_user_memory(session, current_user.id, fact)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        get_guardian_suite().memory.remember_fact(user_id=str(current_user.id), fact=mem.fact, memory_id=str(mem.id))
    except Exception:
        pass
    return {"corrected": str(memory_id), "new_memory": _fmt(mem)}


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
