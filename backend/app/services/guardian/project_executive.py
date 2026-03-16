"""Guardian Project Executive adapter.

Canonical execution boundary for project lifecycle mutations over Guardian Spine.

All explicit project lifecycle changes (create, update, archive, reopen, owner
assignment, task attachment) should route through this adapter.  Signal-driven
auto-creation via _capture_source() bypasses this layer intentionally — it is a
background side-effect of ingesting raw chat/meeting signals and does not
constitute explicit management.

Usage:
    from app.services.guardian.project_executive import project_executive

    project = project_executive.create_project(display_name="My Project", ...)
    project_executive.archive_project(project_id="...", force=False)

Mirror rule (enforced by convention, not by code locks):
    - Guardian Spine (spine.db) is the canonical source of truth for project state.
    - Markdown mirror files under _mirror_root() and any legacy tables that
      reflect project state are downstream, one-way reflections only.
    - Mirror sync is: Spine state → mirror.  Never mirror → Spine.
    - Do not read from a mirror to determine canonical project state.
    - Do not treat a mirror write as a canonical state change.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.services.guardian import spine


class ProjectHasOpenTasksError(Exception):
    """Raised when archiving/canceling a project that still has open tasks.

    Pass force=True to the adapter method to override this guard.
    """

    def __init__(self, task_count: int, task_ids: list[str]) -> None:
        shown = task_ids[:5]
        tail = " (and more)" if len(task_ids) > 5 else ""
        super().__init__(
            f"Project has {task_count} open task(s). "
            f"Close them first, or pass force=True to override. "
            f"Blocking task IDs: {shown}{tail}"
        )
        self.task_count = task_count
        self.task_ids = task_ids


class ProjectNotFoundError(Exception):
    """Raised when a project_id does not exist in the Spine canonical store."""


class ProjectExecutiveAdapter:
    """Canonical project execution boundary over Guardian Spine.

    Enforces:
    - Explicit project creation is traceable via project_lifecycle events.
    - Status transitions are validated against PROJECT_STATUSES.
    - Archiving/canceling with open tasks raises unless force=True.
    - Reopening preserves all prior task state (tasks are not auto-reopened).
    - Task attach/detach preserves full lineage in both the general event log
      and the per-project event log.
    - Owner is only set through this adapter — subsystem events do not
      overwrite project ownership.
    """

    # ── Internal helpers ──────────────────────────────────────────────────

    def _require_project(self, project_id: str) -> spine.SpineProject:
        project = spine.get_spine_project(project_id=project_id)
        if not project:
            raise ProjectNotFoundError(f"Project not found: {project_id!r}")
        return project

    def _open_tasks(self, project_id: str) -> list[spine.SpineTask]:
        tasks = spine.list_project_tasks(project_id=project_id, limit=200)
        return [t for t in tasks if t.status not in {"done", "canceled"}]

    # ── Creation ──────────────────────────────────────────────────────────

    def create_project(
        self,
        *,
        project_id: str | None = None,
        display_name: str,
        summary: str | None = None,
        status: str = "active",
        room_id: str | None = None,
        tags: list[str] | None = None,
        parent_project_id: str | None = None,
        actor_id: str | None = None,
        source_ref: str | None = None,
        session: Any = None,
    ) -> spine.SpineProject:
        """Register a new canonical project.

        Uses emit_project_lifecycle_event so the creation is fully traceable
        in the Spine project event log with subsystem='project_lifecycle'.
        If project_id is omitted, one is derived from display_name.
        """
        resolved_id = (
            project_id
            or spine._slugify(display_name)
            or str(uuid.uuid4()).replace("-", "")[:12]
        )
        spine.emit_project_lifecycle_event(
            room_id=room_id,
            actor_id=actor_id,
            event_type="project.created",
            project=spine.SpineProjectInput(
                project_id=resolved_id,
                display_name=display_name,
                summary=summary,
                status=status,
                room_id=room_id,
                tags=tags or [],
                parent_project_id=parent_project_id,
            ),
            payload={"source_ref": source_ref, "actor_id": actor_id},
            session=session,
        )
        return self._require_project(resolved_id)

    # ── Metadata ──────────────────────────────────────────────────────────

    def update_metadata(
        self,
        *,
        project_id: str,
        display_name: str | None = None,
        summary: str | None = None,
        tags: list[str] | None = None,
        actor_id: str | None = None,
        source_ref: str | None = None,
    ) -> spine.SpineProject:
        """Update mutable descriptive fields without touching status or owner.

        Only provided (non-None) fields are written.  No-op if all are None.
        """
        self._require_project(project_id)
        result = spine.update_project_metadata(
            project_id=project_id,
            display_name=display_name,
            summary=summary,
            tags=tags,
            actor_id=actor_id,
            source_ref=source_ref,
        )
        return result or self._require_project(project_id)

    # ── Owner ─────────────────────────────────────────────────────────────

    def assign_owner(
        self,
        *,
        project_id: str,
        owner_kind: str,
        owner_id: str | None = None,
        actor_id: str | None = None,
        source_ref: str | None = None,
    ) -> spine.SpineProject:
        """Assign or reassign the owner of a project.

        owner_kind must be one of OWNER_KINDS; invalid values are coerced to
        'unassigned' by the underlying spine function.
        """
        self._require_project(project_id)
        result = spine.update_project_owner(
            project_id=project_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            actor_id=actor_id,
            source_ref=source_ref,
        )
        return result or self._require_project(project_id)

    # ── Status transitions ────────────────────────────────────────────────

    def transition_status(
        self,
        *,
        project_id: str,
        new_status: str,
        actor_id: str | None = None,
        reason: str | None = None,
        source_ref: str | None = None,
    ) -> spine.SpineProject:
        """Direct status transition. Validates new_status; raises ValueError for
        unknown values.  Use archive_project() or cancel_project() for guarded
        lifecycle transitions that check for open tasks first.
        """
        self._require_project(project_id)
        result = spine.update_project_status_canonical(
            project_id=project_id,
            new_status=new_status,
            actor_id=actor_id,
            source_ref=source_ref,
            reason=reason,
        )
        return result or self._require_project(project_id)

    def archive_project(
        self,
        *,
        project_id: str,
        actor_id: str | None = None,
        reason: str | None = None,
        force: bool = False,
        source_ref: str | None = None,
    ) -> spine.SpineProject:
        """Transition project to 'archived'.

        Raises ProjectHasOpenTasksError if the project has open tasks,
        unless force=True.  force=True is an explicit operator override and
        should be surfaced as such in any UI calling this method.
        """
        self._require_project(project_id)
        if not force:
            blocking = self._open_tasks(project_id)
            if blocking:
                raise ProjectHasOpenTasksError(len(blocking), [t.task_id for t in blocking])
        return self.transition_status(
            project_id=project_id,
            new_status="archived",
            actor_id=actor_id,
            reason=reason,
            source_ref=source_ref,
        )

    def cancel_project(
        self,
        *,
        project_id: str,
        actor_id: str | None = None,
        reason: str | None = None,
        force: bool = False,
        source_ref: str | None = None,
    ) -> spine.SpineProject:
        """Transition project to 'archived' with reason='canceled'.

        Semantically distinct from archive: cancellation signals intent
        abandonment whereas archival signals completion/retirement.
        Raises ProjectHasOpenTasksError unless force=True.
        """
        self._require_project(project_id)
        if not force:
            blocking = self._open_tasks(project_id)
            if blocking:
                raise ProjectHasOpenTasksError(len(blocking), [t.task_id for t in blocking])
        return self.transition_status(
            project_id=project_id,
            new_status="archived",
            actor_id=actor_id,
            reason=reason or "canceled",
            source_ref=source_ref,
        )

    def reopen_project(
        self,
        *,
        project_id: str,
        new_status: str = "active",
        actor_id: str | None = None,
        source_ref: str | None = None,
    ) -> spine.SpineProject:
        """Reopen an archived/done project back to an active state.

        Does NOT auto-reopen child tasks — task state is managed separately
        through the task lifecycle.  This is intentional: the operator may
        want to re-evaluate which tasks to reopen rather than bulk-reopening.
        """
        self._require_project(project_id)
        safe_status = new_status if new_status in spine.PROJECT_STATUSES else "active"
        return self.transition_status(
            project_id=project_id,
            new_status=safe_status,
            actor_id=actor_id,
            reason="reopened",
            source_ref=source_ref,
        )

    # ── Task attachment ───────────────────────────────────────────────────

    def attach_task(
        self,
        *,
        project_id: str,
        task_id: str,
        actor_id: str | None = None,
        source_ref: str | None = None,
    ) -> dict[str, Any]:
        """Attach an orphan (or re-routed) task to this project.

        Lineage is preserved: the old project_id is recorded in both the
        general event log and the project event log.  If the task was
        already in another project, that prior association is visible in
        history.
        """
        self._require_project(project_id)
        return spine.attach_task_to_project_canonical(
            task_id=task_id,
            project_id=project_id,
            actor_id=actor_id,
            source_ref=source_ref,
        )

    def detach_task(
        self,
        *,
        task_id: str,
        actor_id: str | None = None,
        source_ref: str | None = None,
    ) -> dict[str, Any]:
        """Remove a task from its project, making it an orphan in Spine.

        The detachment event is written to both guardian_spine_events and
        the project event log so the project's history reflects the removal.
        """
        return spine.detach_task_from_project_canonical(
            task_id=task_id,
            actor_id=actor_id,
            source_ref=source_ref,
        )

    # ── Consistency checks ────────────────────────────────────────────────

    def check_open_tasks(self, *, project_id: str) -> list[spine.SpineTask]:
        """Return open tasks that would block archiving/canceling this project.

        Returns an empty list if the project can be closed cleanly.
        """
        self._require_project(project_id)
        return self._open_tasks(project_id)

    # ── Derived operator signal views ─────────────────────────────────────

    def projects_without_owner(
        self, *, room_id: str | None = None, limit: int = 100
    ) -> list[spine.SpineProject]:
        """Projects with no assigned owner (owner_kind = 'unassigned')."""
        return spine.list_projects_without_owner(room_id=room_id, limit=limit)

    def projects_with_stale_open_tasks(
        self, *, stale_days: int = 7, room_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Projects with open tasks not updated within stale_days days."""
        return spine.list_projects_with_stale_open_tasks(
            stale_days=stale_days, room_id=room_id, limit=limit
        )

    def projects_with_candidate_tasks(
        self, *, room_id: str | None = None, min_count: int = 2, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Projects with many unactioned candidate tasks — signals triage backlog."""
        return spine.list_projects_with_candidate_tasks(
            room_id=room_id, min_count=min_count, limit=limit
        )

    def projects_blocked_by_approval(
        self, *, room_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Projects blocked by at least one approval-waiting task."""
        return spine.list_projects_blocked_by_approval(room_id=room_id, limit=limit)

    def projects_with_unassigned_executive_directives(
        self, *, room_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Projects with executive-tagged open tasks that have no owner assigned."""
        return spine.list_projects_with_unassigned_executive_directives(
            room_id=room_id, limit=limit
        )

    def projects_with_unclear_status(
        self, *, room_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Projects where declared status conflicts with actual task state.

        Three signal classes: closed_with_open_tasks, active_but_no_open_tasks,
        active_but_empty.
        """
        return spine.list_projects_with_unclear_status(room_id=room_id, limit=limit)


# Singleton — import and use this rather than instantiating ProjectExecutiveAdapter directly.
project_executive = ProjectExecutiveAdapter()
