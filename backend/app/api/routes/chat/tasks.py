"""
Task/todo management endpoints.

GET    /chat/rooms/{room_id}/tasks                — list tasks (filter by status)
POST   /chat/rooms/{room_id}/tasks                — create a task
PATCH  /chat/rooms/{room_id}/tasks/{task_id}      — update status or assignee
DELETE /chat/rooms/{room_id}/tasks/{task_id}      — delete a task
"""
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import (
    create_task,
    delete_task,
    get_chat_room_member,
    get_task,
    get_tasks,
)
from app.models import TaskStatus

router = APIRouter(tags=["chat-tasks"])


class TaskResponse(BaseModel):
    id: str
    room_id: str
    created_by: str
    assigned_to: Optional[str]
    title: str
    description: Optional[str]
    status: str
    due_date: Optional[str]
    created_at: str
    updated_at: str


def _fmt(t) -> TaskResponse:
    return TaskResponse(
        id=str(t.id),
        room_id=str(t.room_id),
        created_by=str(t.created_by),
        assigned_to=str(t.assigned_to) if t.assigned_to else None,
        title=t.title,
        description=t.description,
        status=t.status.value if hasattr(t.status, "value") else str(t.status),
        due_date=t.due_date.isoformat() if t.due_date else None,
        created_at=t.created_at.isoformat(),
        updated_at=t.updated_at.isoformat(),
    )


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assigned_to: Optional[str] = None   # user UUID string
    due_date: Optional[str] = None      # ISO 8601 date or datetime


class TaskUpdate(BaseModel):
    status: Optional[str] = None        # "open" or "done"
    assigned_to: Optional[str] = None   # user UUID string or null to unassign


@router.get("/rooms/{room_id}/tasks", response_model=dict)
def list_room_tasks(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    filter: str = "open",
) -> Any:
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    status_map = {"open": TaskStatus.OPEN, "done": TaskStatus.DONE, "all": None}
    if filter not in status_map:
        raise HTTPException(status_code=400, detail="filter must be open, done, or all")

    tasks = get_tasks(session, room_id, status=status_map[filter])
    return {"tasks": [_fmt(t) for t in tasks], "count": len(tasks)}


@router.post("/rooms/{room_id}/tasks", response_model=TaskResponse)
def create_room_task(
    room_id: uuid.UUID,
    task_in: TaskCreate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    assigned_uuid: Optional[uuid.UUID] = None
    if task_in.assigned_to:
        try:
            assigned_uuid = uuid.UUID(task_in.assigned_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid assigned_to UUID")

    due: Optional[datetime] = None
    if task_in.due_date:
        try:
            due = datetime.fromisoformat(task_in.due_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid due_date format")

    task = create_task(
        session=session,
        room_id=room_id,
        created_by=current_user.id,
        title=task_in.title,
        description=task_in.description,
        assigned_to=assigned_uuid,
        due_date=due,
    )
    try:
        from app.services.guardian.task_master_adapter import task_master_spine
        task_master_spine.register_created_task(task=task, session=session, actor_id=str(current_user.id))
    except Exception:
        pass
    return _fmt(task)


@router.patch("/rooms/{room_id}/tasks/{task_id}", response_model=TaskResponse)
def update_room_task(
    room_id: uuid.UUID,
    task_id: uuid.UUID,
    task_in: TaskUpdate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    task = get_task(session, task_id)
    if not task or task.room_id != room_id:
        raise HTTPException(status_code=404, detail="Task not found")

    from app.services.guardian.task_master_adapter import task_master_spine

    if task_in.status == "done":
        task = task_master_spine.complete_task(
            session=session,
            task=task,
            actor_id=str(current_user.id),
            summary=task.description or task.title,
        )
    elif task_in.status == "open":
        task = task_master_spine.reopen_task(
            session=session,
            task=task,
            actor_id=str(current_user.id),
            summary=task.description or task.title,
        )

    if "assigned_to" in task_in.model_fields_set:
        new_assignee = uuid.UUID(task_in.assigned_to) if task_in.assigned_to else None
        task = task_master_spine.assign_existing_task(
            session=session,
            task=task,
            assigned_to=new_assignee,
            actor_id=str(current_user.id),
        )

    return _fmt(task)


@router.delete("/rooms/{room_id}/tasks/{task_id}")
def delete_room_task(
    room_id: uuid.UUID,
    task_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict:
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    task = get_task(session, task_id)
    if not task or task.room_id != room_id:
        raise HTTPException(status_code=404, detail="Task not found")

    try:
        from app.services.guardian.task_master_adapter import task_master_spine
        task_master_spine.archive_deleted_task(task=task, session=session, actor_id=str(current_user.id))
    except Exception:
        pass
    delete_task(session, task_id, actor_id=current_user.id)
    return {"deleted": str(task_id)}
