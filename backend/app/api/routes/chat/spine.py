"""
Guardian Spine inspection endpoints.

Read-only routes for room members and operators to inspect canonical Spine tasks,
events, and derived queues.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import get_chat_room_member
from app.services.guardian.task_master_adapter import task_master_spine
from app.services.guardian.spine import (
    get_spine_overview,
    get_spine_project,
    get_task_lineage,
    get_project_workload_summary,
    list_approval_waiting_queue,
    list_blocked_queue,
    list_executive_directives,
    list_fragmented_tasks,
    list_high_priority_approval_waiting_tasks,
    list_high_priority_blocked_tasks,
    list_orphan_tasks,
    list_project_events,
    list_project_handoffs,
    list_project_tasks,
    list_recent_cross_room_events,
    list_recently_resurfaced_tasks,
    list_registered_spine_producers,
    list_resurfaced_without_followup_tasks,
    list_spine_approvals,
    list_spine_events,
    list_spine_handoffs,
    list_spine_projects,
    list_spine_tasks,
    list_stale_tasks,
    list_stale_unowned_tasks,
    list_tasks_missing_durable_linkage,
    list_tasks_missing_project_linkage,
    list_tasks_missing_source_traceability,
    list_unassigned_executive_directives,
)

router = APIRouter(tags=["chat-spine"])


class SpineTaskResponse(BaseModel):
    task_id: str
    room_id: str
    title: str
    summary: str | None
    project_id: str | None
    type: str
    priority: str
    status: str
    owner_kind: str
    owner_id: str | None
    source_kind: str
    source_ref: str
    created_by_subsystem: str | None
    updated_by_subsystem: str | None
    approval_required: bool
    approval_state: str
    confidence: float
    parent_task_id: str | None
    depends_on: list[str]
    tags: list[str]
    created_at: str
    updated_at: str
    last_progress_at: str
    closed_at: str | None
    chat_task_id: str | None


class SpineEventResponse(BaseModel):
    event_id: str
    event_type: str
    occurred_at: str
    subsystem: str | None
    actor_kind: str
    actor_id: str | None
    source_kind: str
    source_ref: str
    correlation_id: str
    task_id: str | None
    project_id: str | None
    payload: dict[str, Any]


class SpineHandoffResponse(BaseModel):
    id: str
    task_id: str
    room_id: str
    summary: str
    created_at: str
    source_ref: str | None


class SpineOverviewResponse(BaseModel):
    room_id: str
    task_count: int
    status_counts: dict[str, int]
    event_count: int
    awaiting_approval_count: int
    handoff_count: int
    orphan_task_count: int
    unassigned_open_task_count: int
    project_count: int
    projects: list[dict[str, str]]


class SpineProjectResponse(BaseModel):
    project_id: str
    room_id: str | None
    display_name: str
    slug: str
    summary: str | None
    status: str | None
    source_kind: str | None
    source_ref: str | None
    created_by_subsystem: str | None
    updated_by_subsystem: str | None
    tags: list[str]
    parent_project_id: str | None
    created_at: str | None
    updated_at: str


class SpineApprovalResponse(BaseModel):
    id: str
    task_id: str
    requester_id: str | None
    approver_id: str | None
    approval_method: str | None
    state: str
    scope: list[str]
    expires_at: str | None
    created_at: str
    updated_at: str


class SpineTaskLineageResponse(BaseModel):
    task: SpineTaskResponse
    parent: SpineTaskResponse | None
    children: list[SpineTaskResponse]
    dependencies: list[SpineTaskResponse]
    related: list[SpineTaskResponse]
    approvals: list[SpineApprovalResponse]
    handoffs: list[SpineHandoffResponse]


class SpineTaskMasterOverviewResponse(BaseModel):
    open_queue: list[SpineTaskResponse]
    blocked_queue: list[SpineTaskResponse]
    orphan_queue: list[SpineTaskResponse]
    approval_waiting_queue: list[SpineTaskResponse]
    stale_queue: list[SpineTaskResponse]
    recently_resurfaced_queue: list[SpineTaskResponse]
    assignment_ready_queue: list[SpineTaskResponse]
    project_workload_summary: list[dict[str, Any]]


class SpineProducerResponse(BaseModel):
    subsystem: str
    description: str
    event_types: list[str]


def _task_fmt(task) -> SpineTaskResponse:
    return SpineTaskResponse(
        task_id=task.task_id,
        room_id=task.room_id,
        title=task.title,
        summary=task.summary,
        project_id=task.project_id,
        type=task.type,
        priority=task.priority,
        status=task.status,
        owner_kind=task.owner_kind,
        owner_id=task.owner_id,
        source_kind=task.source_kind,
        source_ref=task.source_ref,
        created_by_subsystem=task.created_by_subsystem,
        updated_by_subsystem=task.updated_by_subsystem,
        approval_required=bool(task.approval_required),
        approval_state=task.approval_state,
        confidence=float(task.confidence),
        parent_task_id=task.parent_task_id,
        depends_on=json.loads(task.depends_on_json or "[]"),
        tags=json.loads(task.tags_json or "[]"),
        created_at=task.created_at,
        updated_at=task.updated_at,
        last_progress_at=task.last_progress_at,
        closed_at=task.closed_at,
        chat_task_id=task.chat_task_id,
    )


def _event_fmt(event) -> SpineEventResponse:
    try:
        payload = json.loads(event.payload_json or "{}")
    except Exception:
        payload = {}
    return SpineEventResponse(
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        subsystem=event.subsystem,
        actor_kind=event.actor_kind,
        actor_id=event.actor_id,
        source_kind=event.source_kind,
        source_ref=event.source_ref,
        correlation_id=event.correlation_id,
        task_id=event.task_id,
        project_id=event.project_id,
        payload=payload if isinstance(payload, dict) else {"value": payload},
    )


def _handoff_fmt(handoff) -> SpineHandoffResponse:
    return SpineHandoffResponse(
        id=handoff.id,
        task_id=handoff.task_id,
        room_id=handoff.room_id,
        summary=handoff.summary,
        created_at=handoff.created_at,
        source_ref=handoff.source_ref,
    )


def _project_fmt(project) -> SpineProjectResponse:
    return SpineProjectResponse(
        project_id=project.project_id,
        room_id=project.room_id,
        display_name=project.display_name,
        slug=project.slug,
        summary=project.summary,
        status=project.status,
        source_kind=project.source_kind,
        source_ref=project.source_ref,
        created_by_subsystem=project.created_by_subsystem,
        updated_by_subsystem=project.updated_by_subsystem,
        tags=json.loads(project.tags_json or "[]"),
        parent_project_id=project.parent_project_id,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def _approval_fmt(approval) -> SpineApprovalResponse:
    return SpineApprovalResponse(
        id=approval.id,
        task_id=approval.task_id,
        requester_id=approval.requester_id,
        approver_id=approval.approver_id,
        approval_method=approval.approval_method,
        state=approval.state,
        scope=json.loads(approval.scope_json or "[]"),
        expires_at=approval.expires_at,
        created_at=approval.created_at,
        updated_at=approval.updated_at,
    )


def _require_room_membership(session: SessionDep, room_id: uuid.UUID, current_user: CurrentChatUser) -> None:
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")


def _require_operator(current_user: CurrentChatUser) -> None:
    from app.services.guardian.auth import is_operator_identity

    if not current_user or not is_operator_identity(username=current_user.username, user_type=current_user.type):
        raise HTTPException(status_code=403, detail="Operator access required.")


@router.get("/rooms/{room_id}/spine/tasks", response_model=dict)
def read_room_spine_tasks(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    tasks = list_spine_tasks(room_id=str(room_id), status=status, limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/rooms/{room_id}/spine/events", response_model=dict)
def read_room_spine_events(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    task_id: str | None = None,
    subsystem: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    events = list_spine_events(room_id=str(room_id), task_id=task_id, subsystem=subsystem, limit=limit)
    return {"events": [_event_fmt(event) for event in events], "count": len(events)}


@router.get("/rooms/{room_id}/spine/handoffs", response_model=dict)
def read_room_spine_handoffs(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    task_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    handoffs = list_spine_handoffs(room_id=str(room_id), task_id=task_id, limit=limit)
    return {"handoffs": [_handoff_fmt(handoff) for handoff in handoffs], "count": len(handoffs)}


@router.get("/rooms/{room_id}/spine/overview", response_model=SpineOverviewResponse)
def read_room_spine_overview(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> SpineOverviewResponse:
    _require_room_membership(session, room_id, current_user)
    return SpineOverviewResponse(**get_spine_overview(room_id=str(room_id)))


@router.get("/rooms/{room_id}/spine/projects", response_model=dict)
def read_room_spine_projects(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    projects = list_spine_projects(room_id=str(room_id), limit=limit)
    return {"projects": [_project_fmt(project) for project in projects], "count": len(projects)}


@router.get("/rooms/{room_id}/spine/projects/{project_id}/tasks", response_model=dict)
def read_room_spine_project_tasks(
    room_id: uuid.UUID,
    project_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
    status: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    project = get_spine_project(project_id=project_id)
    if not project or project.room_id != str(room_id):
        raise HTTPException(status_code=404, detail="Project not found")
    tasks = [task for task in list_project_tasks(project_id=project_id, status=status, limit=limit) if task.room_id == str(room_id)]
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/rooms/{room_id}/spine/tasks/orphaned", response_model=dict)
def read_room_spine_orphan_tasks(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    tasks = list_orphan_tasks(room_id=str(room_id), limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/rooms/{room_id}/spine/tasks/{task_id}/lineage", response_model=SpineTaskLineageResponse)
def read_room_spine_task_lineage(
    room_id: uuid.UUID,
    task_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> SpineTaskLineageResponse:
    _require_room_membership(session, room_id, current_user)
    lineage = get_task_lineage(task_id=task_id)
    if not lineage or lineage["task"].room_id != str(room_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return SpineTaskLineageResponse(
        task=_task_fmt(lineage["task"]),
        parent=_task_fmt(lineage["parent"]) if lineage["parent"] else None,
        children=[_task_fmt(item) for item in lineage["children"]],
        dependencies=[_task_fmt(item) for item in lineage["dependencies"]],
        related=[_task_fmt(item) for item in lineage["related"]],
        approvals=[_approval_fmt(item) for item in lineage["approvals"]],
        handoffs=[_handoff_fmt(item) for item in lineage["handoffs"]],
    )


@router.get("/rooms/{room_id}/spine/tasks/{task_id}/approvals", response_model=dict)
def read_room_spine_task_approvals(
    room_id: uuid.UUID,
    task_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    approvals = list_spine_approvals(task_id=task_id, room_id=str(room_id), limit=limit)
    return {"approvals": [_approval_fmt(item) for item in approvals], "count": len(approvals)}


@router.get("/rooms/{room_id}/spine/projects/{project_id}/handoffs", response_model=dict)
def read_room_spine_project_handoffs(
    room_id: uuid.UUID,
    project_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    project = get_spine_project(project_id=project_id)
    if not project or project.room_id != str(room_id):
        raise HTTPException(status_code=404, detail="Project not found")
    handoffs = [handoff for handoff in list_project_handoffs(project_id=project_id, limit=limit) if handoff.room_id == str(room_id)]
    return {"handoffs": [_handoff_fmt(item) for item in handoffs], "count": len(handoffs)}


@router.get("/rooms/{room_id}/spine/projects/{project_id}/events", response_model=dict)
def read_room_spine_project_events(
    room_id: uuid.UUID,
    project_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_room_membership(session, room_id, current_user)
    project = get_spine_project(project_id=project_id)
    if not project or project.room_id != str(room_id):
        raise HTTPException(status_code=404, detail="Project not found")
    events = list_project_events(project_id=project_id, limit=limit)
    return {"events": [{"event_id": event.event_id, "event_type": event.event_type, "occurred_at": event.occurred_at, "subsystem": event.subsystem, "source_kind": event.source_kind, "source_ref": event.source_ref, "payload": json.loads(event.payload_json or "{}")} for event in events], "count": len(events)}


@router.get("/rooms/{room_id}/spine/task-master/overview", response_model=SpineTaskMasterOverviewResponse)
def read_room_spine_task_master_overview(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    limit_per_queue: int = 25,
) -> SpineTaskMasterOverviewResponse:
    _require_room_membership(session, room_id, current_user)
    overview = task_master_spine.overview(room_id=str(room_id), limit_per_queue=limit_per_queue)
    return SpineTaskMasterOverviewResponse(
        open_queue=[_task_fmt(task) for task in overview.open_queue],
        blocked_queue=[_task_fmt(task) for task in overview.blocked_queue],
        orphan_queue=[_task_fmt(task) for task in overview.orphan_queue],
        approval_waiting_queue=[_task_fmt(task) for task in overview.approval_waiting_queue],
        stale_queue=[_task_fmt(task) for task in overview.stale_queue],
        recently_resurfaced_queue=[_task_fmt(task) for task in overview.recently_resurfaced_queue],
        assignment_ready_queue=[_task_fmt(task) for task in overview.assignment_ready_queue],
        project_workload_summary=overview.project_workload_summary,
    )


@router.get("/spine/operator/producers", response_model=dict)
def read_operator_spine_producers(
    current_user: CurrentChatUser,
) -> dict[str, Any]:
    _require_operator(current_user)
    producers = list_registered_spine_producers()
    return {
        "producers": [
            SpineProducerResponse(
                subsystem=producer.subsystem,
                description=producer.description,
                event_types=list(producer.event_types),
            )
            for producer in producers
        ],
        "count": len(producers),
    }


@router.get("/spine/operator/events/recent", response_model=dict)
def read_operator_spine_recent_events(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    events = list_recent_cross_room_events(limit=limit)
    return {"events": [_event_fmt(event) for event in events], "count": len(events)}


@router.get("/spine/operator/queues/open", response_model=dict)
def read_operator_spine_open_queue(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = task_master_spine.open(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/queues/blocked", response_model=dict)
def read_operator_spine_blocked_queue(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_blocked_queue(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/queues/approval-waiting", response_model=dict)
def read_operator_spine_approval_waiting_queue(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_approval_waiting_queue(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/queues/stale", response_model=dict)
def read_operator_spine_stale_queue(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_stale_tasks(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/queues/orphaned", response_model=dict)
def read_operator_spine_orphan_queue(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_orphan_tasks(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/queues/missing-source", response_model=dict)
def read_operator_spine_missing_source_queue(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_tasks_missing_source_traceability(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/queues/missing-project", response_model=dict)
def read_operator_spine_missing_project_queue(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_tasks_missing_project_linkage(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/queues/resurfaced", response_model=dict)
def read_operator_spine_resurfaced_queue(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_recently_resurfaced_tasks(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/queues/executive-directives", response_model=dict)
def read_operator_spine_executive_directives(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_executive_directives(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/projects", response_model=dict)
def read_operator_spine_projects(
    current_user: CurrentChatUser,
    limit: int = 200,
) -> dict[str, Any]:
    _require_operator(current_user)
    projects = list_spine_projects(limit=limit)
    return {"projects": [_project_fmt(project) for project in projects], "count": len(projects)}


@router.get("/spine/operator/projects/workload", response_model=dict)
def read_operator_spine_project_workload(
    current_user: CurrentChatUser,
) -> dict[str, Any]:
    _require_operator(current_user)
    summary = get_project_workload_summary()
    return {"projects": summary, "count": len(summary)}


@router.get("/spine/operator/task-master/overview", response_model=SpineTaskMasterOverviewResponse)
def read_operator_spine_task_master_overview(
    current_user: CurrentChatUser,
    limit_per_queue: int = 25,
) -> SpineTaskMasterOverviewResponse:
    _require_operator(current_user)
    overview = task_master_spine.overview(limit_per_queue=limit_per_queue)
    return SpineTaskMasterOverviewResponse(
        open_queue=[_task_fmt(task) for task in overview.open_queue],
        blocked_queue=[_task_fmt(task) for task in overview.blocked_queue],
        orphan_queue=[_task_fmt(task) for task in overview.orphan_queue],
        approval_waiting_queue=[_task_fmt(task) for task in overview.approval_waiting_queue],
        stale_queue=[_task_fmt(task) for task in overview.stale_queue],
        recently_resurfaced_queue=[_task_fmt(task) for task in overview.recently_resurfaced_queue],
        assignment_ready_queue=[_task_fmt(task) for task in overview.assignment_ready_queue],
        project_workload_summary=overview.project_workload_summary,
    )


@router.get("/spine/operator/signals/high-priority-blocked", response_model=dict)
def read_operator_spine_high_priority_blocked(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_high_priority_blocked_tasks(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/signals/high-priority-approval", response_model=dict)
def read_operator_spine_high_priority_approval(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_high_priority_approval_waiting_tasks(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/signals/stale-unowned", response_model=dict)
def read_operator_spine_stale_unowned(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_stale_unowned_tasks(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/signals/unassigned-executive", response_model=dict)
def read_operator_spine_unassigned_executive(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_unassigned_executive_directives(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/signals/resurfaced-no-followup", response_model=dict)
def read_operator_spine_resurfaced_no_followup(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_resurfaced_without_followup_tasks(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/signals/missing-durable-linkage", response_model=dict)
def read_operator_spine_missing_durable_linkage(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_tasks_missing_durable_linkage(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}


@router.get("/spine/operator/signals/fragmentation", response_model=dict)
def read_operator_spine_fragmentation(
    current_user: CurrentChatUser,
    limit: int = 100,
) -> dict[str, Any]:
    _require_operator(current_user)
    tasks = list_fragmented_tasks(limit=limit)
    return {"tasks": [_task_fmt(task) for task in tasks], "count": len(tasks)}
