"""
Task Guardian room endpoints + Break-Glass + Guardian Vault endpoints.

Room members can inspect scheduled jobs and recent runs.
OWNER/MOD members can create, pause/resume, and trigger jobs.
Break-glass and vault endpoints are operator-only (require privileged session for writes).
"""
import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import get_chat_room_by_id, get_chat_room_member
from app.models import RoomRole
from app.services.guardian.task_guardian import (
    get_task,
    list_runs,
    list_tasks,
    run_task_once,
    schedule_task,
    set_task_enabled,
)

router = APIRouter(tags=["chat-guardian"])


def _require_guardian_operator(current_user: CurrentChatUser) -> None:
    from app.services.guardian.auth import is_operator_identity

    if not is_operator_identity(username=current_user.username, user_type=current_user.type):
        raise HTTPException(status_code=403, detail="Guardian operator access required.")


# ── Break-Glass ────────────────────────────────────────────────────────────────

class BreakGlassRequest(BaseModel):
    pin: str = Field(..., min_length=1, max_length=128)


@router.get("/guardian/breakglass/status")
def breakglass_status(current_user: CurrentChatUser) -> dict[str, Any]:
    """Return current privileged session status for the calling user."""
    from app.services.guardian.auth import get_active_session

    _require_guardian_operator(current_user)
    session = get_active_session(str(current_user.id))
    if session:
        return {
            "active": True,
            "session_id": session.session_id,
            "ttl_remaining": session.ttl_remaining(),
            "scopes": session.scopes,
        }
    return {"active": False}


@router.post("/guardian/breakglass")
def breakglass_open(
    body: BreakGlassRequest,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    """Open a privileged break-glass session using the operator PIN."""
    from app.services.guardian.auth import (
        is_locked_out,
        open_privileged_session,
        verify_pin,
    )
    from app.crud import create_audit_log

    _require_guardian_operator(current_user)
    user_id = str(current_user.id)
    if is_locked_out(user_id):
        raise HTTPException(status_code=429, detail="Too many failed PIN attempts. Try again in 5 minutes.")

    if not verify_pin(user_id, body.pin):
        try:
            create_audit_log(
                session=session,
                tool_name="breakglass_pin_failed",
                tool_input=json.dumps({"operator": str(current_user.username)}),
                tool_result="failed",
                user_id=current_user.id,
            )
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Incorrect PIN.")

    priv_session = open_privileged_session(user_id, operator=str(current_user.username))
    try:
        create_audit_log(
            session=session,
            tool_name="breakglass_session_open",
            tool_input=json.dumps({"operator": str(current_user.username), "session_id": priv_session.session_id}),
            tool_result="ok",
            user_id=current_user.id,
        )
    except Exception:
        pass

    return {
        "active": True,
        "session_id": priv_session.session_id,
        "ttl_remaining": priv_session.ttl_remaining(),
        "scopes": priv_session.scopes,
    }


@router.delete("/guardian/breakglass")
def breakglass_close(
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    """Explicitly close the privileged session."""
    from app.services.guardian.auth import close_privileged_session, get_active_session
    from app.crud import create_audit_log

    _require_guardian_operator(current_user)
    user_id = str(current_user.id)
    priv_session = get_active_session(user_id)
    close_privileged_session(user_id)
    if priv_session:
        try:
            create_audit_log(
                session=session,
                tool_name="breakglass_session_close",
                tool_input=json.dumps({"operator": str(current_user.username), "session_id": priv_session.session_id}),
                tool_result="ok",
                user_id=current_user.id,
            )
        except Exception:
            pass
    return {"closed": True}


# ── Guardian Vault ─────────────────────────────────────────────────────────────

class VaultAddRequest(BaseModel):
    alias: str = Field(..., min_length=1, max_length=120)
    value: str = Field(..., min_length=1)
    category: str = Field(default="general", max_length=60)
    notes: Optional[str] = Field(default=None, max_length=500)
    access_policy: str = Field(default="use_only")


@router.get("/guardian/vault")
def vault_list_endpoint(current_user: CurrentChatUser) -> dict[str, Any]:
    """List all vault secret aliases and metadata (no plaintext values)."""
    _require_guardian_operator(current_user)
    try:
        from app.services.guardian.vault import vault_list
        entries = vault_list()
        return {"items": entries, "count": len(entries)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/guardian/vault")
def vault_add_endpoint(
    body: VaultAddRequest,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    """Add an encrypted secret to the vault. Requires break-glass privileged mode."""
    from app.services.guardian.auth import get_active_session
    from app.crud import create_audit_log

    _require_guardian_operator(current_user)
    user_id = str(current_user.id)
    priv_session = get_active_session(user_id)
    if not priv_session:
        raise HTTPException(
            status_code=403,
            detail="Break-glass privileged mode required. POST to /guardian/breakglass with your PIN first.",
        )
    try:
        from app.services.guardian.vault import vault_add
        result = vault_add(
            alias=body.alias,
            value=body.value,
            category=body.category,
            notes=body.notes,
            policy=body.access_policy,
            operator=str(current_user.username),
            session_id=priv_session.session_id,
        )
        try:
            create_audit_log(
                session=session,
                tool_name="vault_add",
                tool_input=json.dumps({"alias": body.alias}),
                tool_result="ok",
                user_id=current_user.id,
            )
        except Exception:
            pass
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.delete("/guardian/vault/{alias}")
def vault_delete_endpoint(
    alias: str,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    """Delete a vault secret. Requires break-glass privileged mode."""
    from app.services.guardian.auth import get_active_session
    from app.crud import create_audit_log

    _require_guardian_operator(current_user)
    user_id = str(current_user.id)
    priv_session = get_active_session(user_id)
    if not priv_session:
        raise HTTPException(
            status_code=403,
            detail="Break-glass privileged mode required. POST to /guardian/breakglass with your PIN first.",
        )
    try:
        from app.services.guardian.vault import vault_delete
        ok = vault_delete(
            alias=alias,
            operator=str(current_user.username),
            session_id=priv_session.session_id,
        )
        if not ok:
            raise HTTPException(status_code=404, detail=f"Secret '{alias}' not found.")
        try:
            create_audit_log(
                session=session,
                tool_name="vault_delete",
                tool_input=json.dumps({"alias": alias}),
                tool_result="ok",
                user_id=current_user.id,
            )
        except Exception:
            pass
        return {"deleted": True, "alias": alias}
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


class GuardianTaskCreate(BaseModel):
    name: str = Field(..., max_length=120)
    tool_name: str = Field(..., max_length=100)
    schedule: str = Field(..., max_length=200)
    tool_args: dict = Field(default_factory=dict)


class GuardianTaskUpdate(BaseModel):
    enabled: bool


def _require_room_access(session: SessionDep, room_id: uuid.UUID, current_user: CurrentChatUser):
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    return room, membership


def _require_room_operator(role: RoomRole) -> None:
    if role not in {RoomRole.OWNER, RoomRole.MOD}:
        raise HTTPException(status_code=403, detail="Only OWNERs and MODs can manage Task Guardian jobs")


@router.get("/rooms/{room_id}/guardian/tasks")
def list_room_guardian_tasks(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    limit: int = 20,
) -> dict[str, Any]:
    _require_room_access(session, room_id, current_user)
    tasks = list_tasks(room_id=str(room_id), limit=limit)
    return {
        "items": [
            {
                "id": task.id,
                "name": task.name,
                "tool_name": task.tool_name,
                "schedule": task.schedule,
                "enabled": bool(task.enabled),
                "next_run_at": task.next_run_at,
                "last_run_at": task.last_run_at,
                "last_status": task.last_status,
                "last_message": task.last_message,
                "last_verification_status": task.last_verification_status,
                "last_confidence": task.last_confidence,
                "last_evidence_json": task.last_evidence_json,
            }
            for task in tasks
        ],
        "count": len(tasks),
    }


@router.get("/rooms/{room_id}/guardian/runs")
def list_room_guardian_runs(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    limit: int = 20,
) -> dict[str, Any]:
    _require_room_access(session, room_id, current_user)
    runs = list_runs(room_id=str(room_id), limit=limit)
    return {
        "items": [
            {
                "run_id": run.run_id,
                "task_id": run.task_id,
                "status": run.status,
                "verification_status": run.verification_status,
                "confidence": run.confidence,
                "message": run.message,
                "output_excerpt": run.output_excerpt,
                "evidence_json": run.evidence_json,
                "recommended_next_action": run.recommended_next_action,
                "created_at": run.created_at,
            }
            for run in runs
        ],
        "count": len(runs),
    }


@router.post("/rooms/{room_id}/guardian/tasks")
def create_room_guardian_task(
    room_id: uuid.UUID,
    task_in: GuardianTaskCreate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict[str, Any]:
    _, membership = _require_room_access(session, room_id, current_user)
    _require_room_operator(membership.role)

    try:
        task = schedule_task(
            name=task_in.name.strip(),
            tool_name=task_in.tool_name.strip(),
            tool_args=task_in.tool_args,
            schedule=task_in.schedule.strip(),
            room_id=str(room_id),
            user_id=str(current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return task


@router.patch("/rooms/{room_id}/guardian/tasks/{task_id}")
def update_room_guardian_task(
    room_id: uuid.UUID,
    task_id: str,
    task_in: GuardianTaskUpdate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict[str, Any]:
    _, membership = _require_room_access(session, room_id, current_user)
    _require_room_operator(membership.role)

    task = get_task(task_id)
    if not task or task.room_id != str(room_id):
        raise HTTPException(status_code=404, detail="Task Guardian job not found")

    if not set_task_enabled(task_id, task_in.enabled):
        raise HTTPException(status_code=404, detail="Task Guardian job not found")

    return {"task_id": task_id, "enabled": task_in.enabled}


@router.post("/rooms/{room_id}/guardian/tasks/{task_id}/run")
async def run_room_guardian_task(
    room_id: uuid.UUID,
    task_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict[str, Any]:
    _, membership = _require_room_access(session, room_id, current_user)
    _require_room_operator(membership.role)

    task = get_task(task_id)
    if not task or task.room_id != str(room_id):
        raise HTTPException(status_code=404, detail="Task Guardian job not found")

    result = await run_task_once(task, session)
    return result
