"""
Task Guardian room endpoints.

Room members can inspect scheduled jobs and recent runs.
OWNER/MOD members can create, pause/resume, and trigger jobs.
"""
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
                "message": run.message,
                "output_excerpt": run.output_excerpt,
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
