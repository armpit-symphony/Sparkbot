"""
Task Master adapter over Guardian Spine.

Task Master is the execution and assignment layer over Spine's canonical
work-state catalog. It should consume Spine as the upstream source of
work-state, then round-trip its actions back into Spine rather than
maintaining conflicting task/project truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import uuid

from sqlmodel import Session

from app.models import ChatTask, TaskStatus
from app.services.guardian import spine


@dataclass(frozen=True)
class TaskMasterQueueSnapshot:
    open_queue: list[spine.SpineTask]
    blocked_queue: list[spine.SpineTask]
    orphan_queue: list[spine.SpineTask]
    approval_waiting_queue: list[spine.SpineTask]
    stale_queue: list[spine.SpineTask]
    recently_resurfaced_queue: list[spine.SpineTask]
    assignment_ready_queue: list[spine.SpineTask]
    executive_directives: list[spine.SpineTask]
    project_workload_summary: list[dict[str, Any]]


class TaskMasterSpineAdapter:
    """Consume Spine queues as primary input and round-trip mutations back into Spine.

    Guardrail:
    direct task/project lifecycle mutation outside this adapter is discouraged.
    Execution-layer callers should use these helpers so the chat-task mirror and
    canonical Spine state move together.
    """

    def overview(self, *, room_id: str | None = None, limit_per_queue: int = 25) -> TaskMasterQueueSnapshot:
        data = spine.get_task_master_overview(room_id=room_id, limit_per_queue=limit_per_queue)
        return TaskMasterQueueSnapshot(
            open_queue=data["open_queue"],
            blocked_queue=data["blocked_queue"],
            orphan_queue=data["orphan_queue"],
            approval_waiting_queue=data["approval_waiting_queue"],
            stale_queue=data["stale_queue"],
            recently_resurfaced_queue=data["recently_resurfaced_queue"],
            assignment_ready_queue=data["assignment_ready_queue"],
            executive_directives=spine.list_executive_directives(room_id=room_id, limit=limit_per_queue),
            project_workload_summary=data["project_workload_summary"],
        )

    def open(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_open_queue(room_id=room_id, limit=limit)

    def assignment_ready(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_assignment_ready_tasks(room_id=room_id, limit=limit)

    def blocked(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_blocked_queue(room_id=room_id, limit=limit)

    def approval_waiting(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_approval_waiting_queue(room_id=room_id, limit=limit)

    def stale(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_stale_tasks(room_id=room_id, limit=limit)

    def orphan(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_orphan_tasks(room_id=room_id, limit=limit)

    def resurfaced(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_recently_resurfaced_tasks(room_id=room_id, limit=limit)

    def executive_directives(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_executive_directives(room_id=room_id, limit=limit)

    def missing_source_traceability(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_tasks_missing_source_traceability(room_id=room_id, limit=limit)

    def missing_project_linkage(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_tasks_missing_project_linkage(room_id=room_id, limit=limit)

    def recent_events(self, *, limit: int = 100) -> list[spine.SpineEvent]:
        return spine.list_recent_cross_room_events(limit=limit)

    def project_workload_summary(self, *, room_id: str | None = None) -> list[dict[str, Any]]:
        return spine.get_project_workload_summary(room_id=room_id)

    def high_priority_blocked(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_high_priority_blocked_tasks(room_id=room_id, limit=limit)

    def high_priority_approval_waiting(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_high_priority_approval_waiting_tasks(room_id=room_id, limit=limit)

    def stale_unowned(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_stale_unowned_tasks(room_id=room_id, limit=limit)

    def unassigned_executive_directives(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_unassigned_executive_directives(room_id=room_id, limit=limit)

    def resurfaced_without_followup(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_resurfaced_without_followup_tasks(room_id=room_id, limit=limit)

    def missing_durable_linkage(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_tasks_missing_durable_linkage(room_id=room_id, limit=limit)

    def fragmentation_indicators(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_fragmented_tasks(room_id=room_id, limit=limit)

    def approval_priority_signals(self, *, room_id: str | None = None, limit: int = 100) -> list[spine.SpineTask]:
        return spine.list_high_priority_approval_waiting_tasks(room_id=room_id, limit=limit)

    def register_created_task(self, *, session: Session, task: ChatTask, actor_id: str, summary: str | None = None) -> dict[str, Any]:
        spine.sync_chat_task_created(session=session, task=task)
        if task.assigned_to:
            return self.assign_task(session=session, task=task, actor_id=actor_id, summary=summary)
        return self.queue_task(session=session, task=task, actor_id=actor_id, summary=summary)

    def _persist_task(self, *, session: Session, task: ChatTask) -> ChatTask:
        task.updated_at = datetime.now(timezone.utc)
        session.add(task)
        session.commit()
        session.refresh(task)
        return task

    def queue_task(self, *, session: Session | None, task: ChatTask, actor_id: str, summary: str | None = None) -> dict[str, Any]:
        return spine.emit_task_master_action(
            session=session,
            task=task,
            action="queued",
            actor_id=actor_id,
            summary=summary or task.description or task.title,
        )

    def assign_task(self, *, session: Session | None, task: ChatTask, actor_id: str, summary: str | None = None) -> dict[str, Any]:
        return spine.emit_task_master_action(
            session=session,
            task=task,
            action="assigned",
            actor_id=actor_id,
            summary=summary or task.description or task.title,
        )

    def block_task(self, *, session: Session | None, task: ChatTask, actor_id: str, summary: str | None = None) -> dict[str, Any]:
        return spine.emit_task_master_action(
            session=session,
            task=task,
            action="blocked",
            actor_id=actor_id,
            summary=summary or task.description or task.title,
        )

    def complete_task(self, *, session: Session, task: ChatTask, actor_id: str, summary: str | None = None) -> ChatTask:
        task.status = TaskStatus.DONE
        task = self._persist_task(session=session, task=task)
        self.emit_status_change(
            session=session,
            task=task,
            actor_id=actor_id,
            action="completed",
            summary=summary,
        )
        return task

    def reopen_task(self, *, session: Session, task: ChatTask, actor_id: str, summary: str | None = None) -> ChatTask:
        task.status = TaskStatus.OPEN
        task = self._persist_task(session=session, task=task)
        self.emit_status_change(
            session=session,
            task=task,
            action="reopened",
            actor_id=actor_id,
            summary=summary or task.description or task.title,
        )
        return task

    def assign_existing_task(
        self,
        *,
        session: Session,
        task: ChatTask,
        assigned_to: uuid.UUID | None,
        actor_id: str,
        summary: str | None = None,
    ) -> ChatTask:
        task.assigned_to = assigned_to
        task = self._persist_task(session=session, task=task)
        if assigned_to:
            self.assign_task(session=session, task=task, actor_id=actor_id, summary=summary)
        else:
            self.change_status(
                session=session,
                task=task,
                actor_id=actor_id,
                summary=summary,
                payload={"assigned_to": None, "status": "open"},
            )
        return task

    def mark_blocked(self, *, session: Session, task: ChatTask, actor_id: str, summary: str | None = None) -> dict[str, Any]:
        return self.emit_status_change(
            session=session,
            task=task,
            action="blocked",
            actor_id=actor_id,
            summary=summary or task.description or task.title,
        )

    def archive_deleted_task(self, *, session: Session, task: ChatTask, actor_id: str, summary: str | None = None) -> dict[str, Any]:
        return self.emit_status_change(
            session=session,
            task=task,
            actor_id=actor_id,
            action="canceled",
            summary=summary or task.description or task.title,
            payload={"deleted_chat_task": True},
        )

    def change_status(
        self,
        *,
        session: Session | None,
        task: ChatTask,
        actor_id: str,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.emit_status_change(
            session=session,
            task=task,
            actor_id=actor_id,
            action="status_changed",
            summary=summary,
            payload=payload,
        )

    def emit_status_change(
        self,
        *,
        session: Session | None,
        task: ChatTask,
        actor_id: str,
        action: str,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return spine.emit_task_master_action(
            session=session,
            task=task,
            action=action,
            actor_id=actor_id,
            summary=summary or task.description or task.title,
            payload=payload,
        )


task_master_spine = TaskMasterSpineAdapter()
