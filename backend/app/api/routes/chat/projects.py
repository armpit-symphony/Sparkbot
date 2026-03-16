"""Project management endpoints (via ProjectExecutiveAdapter).

POST   /rooms/{room_id}/projects                                 — create project
PATCH  /rooms/{room_id}/projects/{project_id}                   — update metadata / transition status / assign owner
DELETE /rooms/{room_id}/projects/{project_id}                   — archive project
POST   /rooms/{room_id}/projects/{project_id}/tasks/{task_id}   — attach task
DELETE /rooms/{room_id}/projects/{project_id}/tasks/{task_id}   — detach task
"""
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import get_chat_room_member
from app.models import RoomRole
from app.services.guardian.project_executive import (
    ProjectHasOpenTasksError,
    ProjectNotFoundError,
    project_executive,
)

router = APIRouter(tags=["chat-projects"])


def _require_room_access(session: SessionDep, room_id: uuid.UUID, current_user: CurrentChatUser):
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    return membership


def _require_mod_or_owner(membership) -> None:
    if membership.role not in {RoomRole.OWNER, RoomRole.MOD}:
        raise HTTPException(status_code=403, detail="Only OWNERs and MODs can manage projects")


def _fmt_project(p) -> dict[str, Any]:
    return {
        "project_id": p.project_id,
        "display_name": p.display_name,
        "slug": p.slug,
        "status": p.status,
        "room_id": p.room_id,
        "owner_kind": p.owner_kind,
        "owner_id": p.owner_id,
        "tags": p.tags if isinstance(p.tags, list) else [],
        "summary": p.summary,
        "source_kind": p.source_kind,
        "source_ref": p.source_ref,
        "parent_project_id": p.parent_project_id,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


class ProjectCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=2000)
    status: str = Field(default="active")
    tags: list[str] = Field(default_factory=list)
    parent_project_id: Optional[str] = None


class ProjectUpdate(BaseModel):
    # Metadata fields
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=2000)
    tags: Optional[list[str]] = None
    # Status transition
    new_status: Optional[str] = None
    reason: Optional[str] = None
    # Owner assignment
    owner_kind: Optional[str] = None
    owner_id: Optional[str] = None


@router.post("/rooms/{room_id}/projects", response_model=dict)
def create_room_project(
    room_id: uuid.UUID,
    project_in: ProjectCreate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    membership = _require_room_access(session, room_id, current_user)
    _require_mod_or_owner(membership)

    if project_in.status not in {"proposed", "active", "blocked", "done", "archived"}:
        raise HTTPException(status_code=400, detail=f"Invalid status: {project_in.status!r}")

    try:
        project = project_executive.create_project(
            display_name=project_in.display_name,
            summary=project_in.summary,
            status=project_in.status,
            room_id=str(room_id),
            tags=project_in.tags,
            parent_project_id=project_in.parent_project_id,
            actor_id=str(current_user.id),
            source_ref=f"room:{room_id}",
            session=session,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return _fmt_project(project)


@router.patch("/rooms/{room_id}/projects/{project_id}", response_model=dict)
def update_room_project(
    room_id: uuid.UUID,
    project_id: str,
    project_in: ProjectUpdate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    membership = _require_room_access(session, room_id, current_user)
    _require_mod_or_owner(membership)

    actor_id = str(current_user.id)
    source_ref = f"room:{room_id}"

    try:
        # Apply metadata update if any metadata fields provided
        if any(v is not None for v in [project_in.display_name, project_in.summary, project_in.tags]):
            project_executive.update_metadata(
                project_id=project_id,
                display_name=project_in.display_name,
                summary=project_in.summary,
                tags=project_in.tags,
                actor_id=actor_id,
                source_ref=source_ref,
            )

        # Apply status transition if provided
        if project_in.new_status is not None:
            if project_in.new_status in {"archived"}:
                project_executive.archive_project(
                    project_id=project_id,
                    actor_id=actor_id,
                    reason=project_in.reason,
                    force=False,
                    source_ref=source_ref,
                )
            else:
                project_executive.transition_status(
                    project_id=project_id,
                    new_status=project_in.new_status,
                    actor_id=actor_id,
                    reason=project_in.reason,
                    source_ref=source_ref,
                )

        # Apply owner assignment if provided
        if project_in.owner_kind is not None:
            project_executive.assign_owner(
                project_id=project_id,
                owner_kind=project_in.owner_kind,
                owner_id=project_in.owner_id,
                actor_id=actor_id,
                source_ref=source_ref,
            )

        project = project_executive._require_project(project_id)
        return _fmt_project(project)

    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id!r}")
    except ProjectHasOpenTasksError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.delete("/rooms/{room_id}/projects/{project_id}")
def archive_room_project(
    room_id: uuid.UUID,
    project_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
    force: bool = False,
) -> dict:
    membership = _require_room_access(session, room_id, current_user)
    _require_mod_or_owner(membership)

    try:
        project_executive.archive_project(
            project_id=project_id,
            actor_id=str(current_user.id),
            reason="archived via API",
            force=force,
            source_ref=f"room:{room_id}",
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id!r}")
    except ProjectHasOpenTasksError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return {"archived": True, "project_id": project_id}


@router.post("/rooms/{room_id}/projects/{project_id}/tasks/{task_id}")
def attach_task_to_project(
    room_id: uuid.UUID,
    project_id: str,
    task_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict:
    membership = _require_room_access(session, room_id, current_user)
    _require_mod_or_owner(membership)

    try:
        result = project_executive.attach_task(
            project_id=project_id,
            task_id=task_id,
            actor_id=str(current_user.id),
            source_ref=f"room:{room_id}",
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_id!r}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result or {"attached": True, "project_id": project_id, "task_id": task_id}


@router.delete("/rooms/{room_id}/projects/{project_id}/tasks/{task_id}")
def detach_task_from_project(
    room_id: uuid.UUID,
    project_id: str,
    task_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict:
    _require_room_access(session, room_id, current_user)

    try:
        result = project_executive.detach_task(
            task_id=task_id,
            actor_id=str(current_user.id),
            source_ref=f"room:{room_id}",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return result or {"detached": True, "project_id": project_id, "task_id": task_id}
