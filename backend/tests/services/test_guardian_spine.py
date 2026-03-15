from __future__ import annotations

import importlib
import uuid
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.crud import assign_task, complete_task, create_chat_meeting_artifact, create_chat_message, create_chat_room, create_task, delete_task, get_task
from app.models import ChatRoom, ChatUser, MeetingArtifactType, UserType


def _reload_spine(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian"))
    import app.services.guardian.spine as spine

    return importlib.reload(spine)


def _reload_task_master_adapter(monkeypatch, tmp_path: Path):
    _reload_spine(monkeypatch, tmp_path)
    import app.services.guardian.task_master_adapter as adapter

    return importlib.reload(adapter)


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_room(session: Session) -> tuple[ChatUser, ChatRoom]:
    user = ChatUser(username="sparkbot-user", type=UserType.HUMAN, hashed_password="")
    session.add(user)
    session.commit()
    session.refresh(user)

    room = ChatRoom(name="Sparkbot Ops", created_by=user.id)
    session.add(room)
    session.commit()
    session.refresh(room)
    return user, room


def test_guardian_spine_captures_actionable_message_and_mirror(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        create_chat_message(
            session=session,
            room_id=room.id,
            sender_id=user.id,
            content="We need to test breakglass again before the next release.",
            sender_type="HUMAN",
        )

        tasks = spine.list_spine_tasks(room_id=str(room.id))
        assert len(tasks) == 1
        task = tasks[0]
        assert task.title.lower().startswith("test breakglass again")
        assert task.status == "awaiting_approval"
        assert bool(task.approval_required) is True
        assert task.chat_task_id is not None

        task_file = tmp_path / "guardian" / "spine" / "tasks" / f"{task.task_id}.md"
        assert task_file.exists()
        assert "breakglass" in task_file.read_text().lower()
        handoffs = spine.list_spine_handoffs(room_id=str(room.id), task_id=task.task_id)
        assert len(handoffs) == 1
        overview = spine.get_spine_overview(room_id=str(room.id))
        assert overview["task_count"] == 1
        assert overview["awaiting_approval_count"] == 1
        assert overview["handoff_count"] == 1


def test_guardian_spine_updates_existing_task_on_completion_signal(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        create_chat_message(
            session=session,
            room_id=room.id,
            sender_id=user.id,
            content="We need to test breakglass again.",
            sender_type="HUMAN",
        )
        create_chat_message(
            session=session,
            room_id=room.id,
            sender_id=user.id,
            content="Done testing breakglass again and closed it out.",
            sender_type="HUMAN",
        )

        tasks = spine.list_spine_tasks(room_id=str(room.id))
        assert len(tasks) == 1
        assert tasks[0].status == "done"

        events = spine.list_spine_events(room_id=str(room.id), task_id=tasks[0].task_id)
        assert any(event.event_type == "task.completed" for event in events)
        handoffs = spine.list_spine_handoffs(room_id=str(room.id), task_id=tasks[0].task_id)
        assert len(handoffs) == 2


def test_guardian_spine_captures_meeting_artifact(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        artifact = create_chat_meeting_artifact(
            session=session,
            room_id=room.id,
            created_by_user_id=user.id,
            type=MeetingArtifactType.ACTION_ITEMS.value,
            content_markdown="- [ ] Fix black screen on Research in Motion page",
        )

        tasks = spine.list_spine_tasks(room_id=str(room.id))
        assert len(tasks) == 1
        assert tasks[0].type in {"meeting_followup", "bug"}
        meeting_file = tmp_path / "guardian" / "spine" / "meetings" / f"room-{room.id}-artifact-{artifact.id}.md"
        assert meeting_file.exists()


def test_guardian_spine_ingests_structured_subsystem_events_with_projects_and_lineage(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        result = spine.ingest_executive_decision(
            room_id=str(room.id),
            source_ref="executive-decision-1",
            decision_summary="Create a breakglass hardening project and assign the first review task.",
            project=spine.SpineProjectInput(
                project_id="guardian-spine-breakglass",
                display_name="Guardian Spine Breakglass",
                summary="Track breakglass hardening work across guardians.",
                room_id=str(room.id),
                tags=["guardian-spine", "breakglass"],
            ),
            task=spine.SpineTaskInput(
                title="Review breakglass gating coverage",
                summary="Check approval boundaries across chat and guardian flows.",
                project_id="guardian-spine-breakglass",
                type="ops",
                priority="high",
                tags=["breakglass", "review"],
            ),
            metadata={"project_id": "guardian-spine-breakglass"},
            session=session,
        )

        parent_task_id = result["task_id"]
        assert parent_task_id is not None

        child = spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.progress",
                subsystem="task_master",
                actor_kind="system",
                room_id=str(room.id),
                source=spine.SpineSourceReference(
                    source_kind="task_master",
                    source_ref="task-master-1",
                    room_id=str(room.id),
                ),
                content="Split out a child implementation task with a dependency on the review.",
                task=spine.SpineTaskInput(
                    title="Implement breakglass audit trail checks",
                    summary="Add audit coverage for breakglass approval and closure.",
                    project_id="guardian-spine-breakglass",
                    type="ops",
                    priority="high",
                    status="in_progress",
                    parent_task_id=parent_task_id,
                    depends_on=[parent_task_id],
                    related_task_ids=[parent_task_id],
                    tags=["breakglass", "audit"],
                ),
                payload={"task_master_lane": "security"},
            ),
            session=session,
        )

        projects = spine.list_spine_projects(room_id=str(room.id))
        assert len(projects) == 1
        cataloged = next(project for project in projects if project.project_id == "guardian-spine-breakglass")
        assert cataloged.created_by_subsystem == "executive"

        project_tasks = spine.list_project_tasks(project_id="guardian-spine-breakglass")
        assert len(project_tasks) == 2

        lineage = spine.get_task_lineage(task_id=child["task_id"])
        assert lineage["parent"] is not None
        assert lineage["parent"].task_id == parent_task_id
        assert len(lineage["dependencies"]) == 1
        assert lineage["dependencies"][0].task_id == parent_task_id
        assert len(lineage["related"]) == 1
        assert lineage["related"][0].task_id == parent_task_id

        project_events = spine.list_project_events(project_id="guardian-spine-breakglass")
        assert any(event.event_type == "executive.decision" for event in project_events)


def test_guardian_spine_memory_signal_reopens_work_and_tracks_orphan_tasks(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        create_chat_message(
            session=session,
            room_id=room.id,
            sender_id=user.id,
            content="We need to test breakglass again.",
            sender_type="HUMAN",
        )
        create_chat_message(
            session=session,
            room_id=room.id,
            sender_id=user.id,
            content="Done testing breakglass again and closed it out.",
            sender_type="HUMAN",
        )

        existing = spine.list_spine_tasks(room_id=str(room.id))[0]
        reopened = spine.ingest_memory_signal(
            room_id=str(room.id),
            source_ref="memory-signal-1",
            signal_text="Resurface breakglass verification because new approval changes landed.",
            reopen_task_id=existing.task_id,
            session=session,
        )
        assert reopened["task_id"] == existing.task_id

        refreshed = spine.list_spine_tasks(room_id=str(room.id))[0]
        assert refreshed.status == "open"
        assert any(event.subsystem == "memory" for event in spine.list_spine_events(room_id=str(room.id), task_id=existing.task_id))

        spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="project.updated",
                subsystem="memory",
                actor_kind="system",
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="memory", source_ref="memory-projectless-1", room_id=str(room.id)),
                content="Keep an eye on provider drift in a room-wide watch task.",
                task=spine.SpineTaskInput(
                    title="Watch provider drift signals",
                    summary="Observe provider drift and escalate if it affects routing stability.",
                    project_id=None,
                    type="research",
                    priority="normal",
                    status="open",
                    tags=["memory", "watch"],
                ),
            ),
            session=session,
        )

        orphan_tasks = spine.list_orphan_tasks(room_id=str(room.id))
        assert len(orphan_tasks) == 1
        assert orphan_tasks[0].title == "Watch provider drift signals"


def test_guardian_spine_tracks_room_lifecycle_approvals_and_task_master_round_trip(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    adapter = _reload_task_master_adapter(monkeypatch, tmp_path)
    from app.services.guardian.pending_approvals import consume_pending_approval, discard_pending_approval, store_pending_approval

    with _session() as session:
        user = ChatUser(username="sparkbot-owner", type=UserType.HUMAN, hashed_password="")
        session.add(user)
        session.commit()
        session.refresh(user)

        room = create_chat_room(session=session, name="Ops Board", created_by=user.id, description="Room lifecycle should hit Spine")
        lifecycle_events = spine.list_spine_events(room_id=str(room.id))
        assert any(event.event_type == "room.created" for event in lifecycle_events)

        task = create_task(
            session=session,
            room_id=room.id,
            created_by=user.id,
            title="Queue release checks",
            description="Initial queue task for Task Master round-trip coverage.",
        )
        task = assign_task(session, task.id, user.id)
        task = complete_task(session, task.id)
        task = adapter.task_master_spine.reopen_task(
            session=session,
            task=task,
            actor_id=str(user.id),
            summary=task.description or task.title,
        )

        events = spine.list_spine_events(room_id=str(room.id), task_id=spine.get_spine_task_by_chat_task_id(chat_task_id=str(task.id)).task_id)
        event_types = {event.event_type for event in events}
        assert "task.queued" in event_types
        assert "task.assigned" in event_types
        assert "task.completed" in event_types
        assert "task.reopened" in event_types

        store_pending_approval(
            confirm_id="approval-1",
            tool_name="server_restart",
            tool_args={"service": "sparkbot-v2"},
            user_id=str(user.id),
            room_id=str(room.id),
        )
        consume_pending_approval("approval-1")

        store_pending_approval(
            confirm_id="approval-2",
            tool_name="vault_reveal",
            tool_args={"secret": "demo"},
            user_id=str(user.id),
            room_id=str(room.id),
        )
        discard_pending_approval("approval-2")

        approval_events = spine.list_spine_events(room_id=str(room.id), subsystem="approval", limit=20)
        approval_types = {event.event_type for event in approval_events}
        assert "approval.required" in approval_types
        assert "approval.granted" in approval_types
        assert "approval.discarded" in approval_types


def test_guardian_spine_task_master_views_cover_stale_blocked_resurfaced_and_assignment_ready(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        ready = spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.queued",
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(user.id),
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="task_master", source_ref="queue-1", room_id=str(room.id)),
                content="Queue a reviewable unassigned task.",
                task=spine.SpineTaskInput(
                    title="Review provider routing drift",
                    summary="Unassigned but ready to pick up.",
                    project_id="ops-board",
                    type="research",
                    status="queued",
                    tags=["queue"],
                ),
            ),
            session=session,
        )
        blocked = spine.ingest_task_guardian_result(
            room_id=str(room.id),
            guardian_task_id="tg-1",
            task_name="Nightly release smoke",
            tool_name="web_search",
            verification_status="blocked",
            summary="Nightly release smoke was blocked.",
            recommended_next_action="Needs operator approval before continuing.",
            output_excerpt="blocked by policy",
            user_id=str(user.id),
            escalated=True,
        )

        stale = spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.progress",
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(user.id),
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="task_master", source_ref="queue-2", room_id=str(room.id)),
                content="This task should become stale.",
                task=spine.SpineTaskInput(
                    title="Old integration cleanup",
                    summary="No progress for a long time.",
                    project_id="ops-board",
                    type="maintenance",
                    priority="high",
                    status="in_progress",
                    owner_kind="unassigned",
                    tags=["stale"],
                ),
            ),
            session=session,
        )
        with spine._conn() as conn:
            conn.execute(
                "UPDATE guardian_spine_tasks SET last_progress_at = ? WHERE task_id = ?",
                ("2020-01-01T00:00:00+00:00", stale["task_id"]),
            )

        completed = spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.completed",
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(user.id),
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="task_master", source_ref="queue-3", room_id=str(room.id)),
                content="Complete then resurface later.",
                task=spine.SpineTaskInput(
                    title="Revisit token guardian checks",
                    summary="Completed work that memory will reopen.",
                    project_id="ops-board",
                    type="ops",
                    status="done",
                    tags=["memory"],
                ),
            ),
            session=session,
        )
        spine.ingest_memory_signal(
            room_id=str(room.id),
            source_ref="memory-queue-1",
            signal_text="Resurface token guardian checks after model stack changes.",
            reopen_task_id=completed["task_id"],
            session=session,
        )

        overview = spine.get_task_master_overview(room_id=str(room.id), limit_per_queue=10)
        assert any(task.task_id == ready["task_id"] for task in overview["assignment_ready_queue"])
        assert any(task.task_id == blocked["task_id"] for task in overview["blocked_queue"])
        assert any(task.task_id == stale["task_id"] for task in overview["stale_queue"])
        assert any(task.title == "Revisit token guardian checks" for task in overview["recently_resurfaced_queue"])


def test_task_master_adapter_uses_spine_as_primary_source_and_global_views(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    adapter = _reload_task_master_adapter(monkeypatch, tmp_path)
    with _session() as session:
        user, room_a = _seed_room(session)
        room_b = create_chat_room(session=session, name="Ops Queue B", created_by=user.id, description="Cross-room view coverage")

        create_task(
            session=session,
            room_id=room_a.id,
            created_by=user.id,
            title="Open room A queue item",
            description="Should appear in the global open queue.",
        )

        task_b = create_task(
            session=session,
            room_id=room_b.id,
            created_by=user.id,
            title="Blocked room B queue item",
            description="Will become blocked for the adapter view.",
        )
        adapter.task_master_spine.block_task(
            session=session,
            task=task_b,
            actor_id=str(user.id),
            summary=task_b.description or task_b.title,
        )

        spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.progress",
                subsystem="memory",
                actor_kind="system",
                room_id=str(room_b.id),
                source=spine.SpineSourceReference(source_kind="memory", source_ref="memory-global-1", room_id=str(room_b.id)),
                content="Resurfaced a room B task for follow-up.",
                task=spine.SpineTaskInput(
                    title="Resurfaced room B work",
                    summary="Memory reopened this task.",
                    project_id=None,
                    type="ops",
                    status="open",
                    tags=["memory", "resurfaced"],
                ),
            ),
            session=session,
        )
        spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.updated",
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(user.id),
                room_id=str(room_a.id),
                source=spine.SpineSourceReference(source_kind="", source_ref="", room_id=str(room_a.id)),
                content="Missing source traceability edge case.",
                task=spine.SpineTaskInput(
                    title="Traceability gap task",
                    summary="Intentionally missing source fields.",
                    project_id=None,
                    type="maintenance",
                    status="open",
                ),
            ),
            session=session,
        )

        overview = adapter.task_master_spine.overview(limit_per_queue=25)
        assert any(task.room_id == str(room_a.id) for task in overview.open_queue)
        assert any(task.room_id == str(room_b.id) for task in overview.blocked_queue)
        assert any("Resurfaced room B work" == task.title for task in overview.recently_resurfaced_queue)

        assert any(task.title == "Traceability gap task" for task in adapter.task_master_spine.missing_source_traceability(limit=25))
        assert any(task.title == "Traceability gap task" for task in adapter.task_master_spine.missing_project_linkage(limit=25))

        recent_events = adapter.task_master_spine.recent_events(limit=25)
        seen_rooms = {event.room_id for event in recent_events}
        assert str(room_a.id) in seen_rooms
        assert str(room_b.id) in seen_rooms


def test_guardian_spine_structured_emitters_cover_project_meeting_worker_and_handoff(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        project = spine.SpineProjectInput(
            project_id="ops-hardening",
            display_name="Ops Hardening",
            summary="Track hardening work across guardians.",
            room_id=str(room.id),
            tags=["ops", "hardening"],
        )
        spine.emit_project_lifecycle_event(
            room_id=str(room.id),
            actor_id=str(user.id),
            event_type="project.created",
            project=project,
            payload={"origin": "test"},
            session=session,
        )
        meeting_result = spine.emit_meeting_output_event(
            room_id=str(room.id),
            actor_id=str(user.id),
            artifact_type="action_items",
            artifact_id="artifact-1",
            content_markdown="- [ ] Validate hardening rollout\n- [ ] Confirm release checklist",
            session=session,
        )
        spine.emit_worker_status_event(
            room_id=str(room.id),
            actor_id="agent_frontend",
            worker_name="frontend",
            source_ref="worker-status-1",
            status_text="Investigating rollout regressions in the release checklist.",
            session=session,
        )
        spine.emit_handoff_event(
            room_id=str(room.id),
            task_id=meeting_result["task_id"],
            summary="Hand off action item review to the release operator.",
            source_ref="handoff-1",
            session=session,
        )

        projects = spine.list_spine_projects(room_id=str(room.id))
        assert any(item.project_id == "ops-hardening" for item in projects)

        events = spine.list_spine_events(room_id=str(room.id), limit=20)
        event_types = {event.event_type for event in events}
        assert "project.created" in event_types
        assert "meeting.action_items.created" in event_types
        assert "worker.status" in event_types
        assert "handoff.created" in event_types

        handoffs = spine.list_spine_handoffs(room_id=str(room.id), task_id=meeting_result["task_id"])
        assert any("release operator" in handoff.summary.lower() for handoff in handoffs)


def test_guardian_spine_global_views_cover_approval_breakglass_and_executive_continuity(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        create_chat_message(
            session=session,
            room_id=room.id,
            sender_id=user.id,
            content="We need to deploy Sparkbot and restart the service in production.",
            sender_type="HUMAN",
        )

        task = spine.list_spine_tasks(room_id=str(room.id))[0]
        assert task.status == "awaiting_approval"
        assert any(item.task_id == task.task_id for item in spine.list_approval_waiting_queue(limit=25))

        spine.emit_breakglass_event(
            room_id=str(room.id),
            user_id=str(user.id),
            event_type="breakglass.requested",
            confirm_id="bg-1",
        )
        spine.emit_breakglass_event(
            room_id=str(room.id),
            user_id=str(user.id),
            event_type="breakglass.opened",
            confirm_id="bg-1",
            payload={"scope": ["service_control"]},
        )

        spine.ingest_executive_decision(
            room_id=str(room.id),
            source_ref="exec-global-1",
            decision_summary="Create an executive directive for release readiness.",
            task=spine.SpineTaskInput(
                title="Executive release directive",
                summary="Track release readiness decisions.",
                project_id="release-readiness",
                type="ops",
                priority="high",
                status="open",
                tags=["executive"],
            ),
            project=spine.SpineProjectInput(
                project_id="release-readiness",
                display_name="Release Readiness",
                summary="Coordinate release readiness work.",
                room_id=str(room.id),
                tags=["release"],
            ),
            session=session,
        )

        directives = spine.list_executive_directives(limit=25)
        assert any(item.title == "Executive release directive" for item in directives)

        recent_events = spine.list_recent_cross_room_events(limit=25)
        assert any(event.event_type == "breakglass.opened" for event in recent_events)

        workload = spine.get_project_workload_summary()
        assert any(item["project_id"] == "release-readiness" for item in workload)


def test_task_master_adapter_unifies_create_assign_complete_reopen_and_delete(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    adapter = _reload_task_master_adapter(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        task = create_task(
            session=session,
            room_id=room.id,
            created_by=user.id,
            title="Unify task lifecycle routing",
            description="Exercise the canonical task mutation path.",
        )
        task = adapter.task_master_spine.assign_existing_task(
            session=session,
            task=task,
            assigned_to=user.id,
            actor_id=str(user.id),
            summary=task.description or task.title,
        )
        task = adapter.task_master_spine.complete_task(
            session=session,
            task=task,
            actor_id=str(user.id),
            summary=task.description or task.title,
        )
        task = adapter.task_master_spine.reopen_task(
            session=session,
            task=task,
            actor_id=str(user.id),
            summary=task.description or task.title,
        )
        deleted = delete_task(session, task.id, actor_id=user.id)
        assert deleted is True
        assert get_task(session, task.id) is None

        spine_task = next(task for task in spine.list_spine_tasks(room_id=str(room.id), limit=20) if task.title == "Unify task lifecycle routing")
        assert spine_task.status == "canceled"

        events = spine.list_spine_events(room_id=str(room.id), task_id=spine_task.task_id, limit=20)
        event_types = {event.event_type for event in events}
        assert "task.queued" in event_types
        assert "task.assigned" in event_types
        assert "task.completed" in event_types
        assert "task.reopened" in event_types
        assert "task.canceled" in event_types


def test_approval_grant_resumes_waiting_task_through_spine(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    from app.services.guardian.pending_approvals import consume_pending_approval, store_pending_approval

    with _session() as session:
        user, room = _seed_room(session)

        create_chat_message(
            session=session,
            room_id=room.id,
            sender_id=user.id,
            content="We need to deploy Sparkbot and restart the service in production.",
            sender_type="HUMAN",
        )
        waiting = spine.list_spine_tasks(room_id=str(room.id))[0]
        assert waiting.status == "awaiting_approval"

        store_pending_approval(
            confirm_id="resume-approval-1",
            tool_name="service_restart",
            tool_args={"service": "sparkbot-v2"},
            user_id=str(user.id),
            room_id=str(room.id),
        )
        consume_pending_approval("resume-approval-1")

        refreshed = spine.get_spine_task(task_id=waiting.task_id)
        assert refreshed is not None
        assert refreshed.approval_state == "granted"
        assert refreshed.status == "in_progress"


def test_guardian_spine_derived_operator_signals_cover_priority_followup_and_fragmentation(monkeypatch, tmp_path) -> None:
    spine = _reload_spine(monkeypatch, tmp_path)
    adapter = _reload_task_master_adapter(monkeypatch, tmp_path)
    with _session() as session:
        user, room = _seed_room(session)

        high_blocked = spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.blocked",
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(user.id),
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="task_master", source_ref="sig-1", room_id=str(room.id)),
                content="Critical blocker",
                task=spine.SpineTaskInput(
                    title="Critical blocked release item",
                    summary="Blocked release item.",
                    project_id="release-signals",
                    type="ops",
                    priority="critical",
                    status="blocked",
                ),
            ),
            session=session,
        )
        high_approval = spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="approval.required",
                subsystem="approval",
                actor_kind="system",
                actor_id=str(user.id),
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="approval", source_ref="sig-2", room_id=str(room.id)),
                content="High priority approval wait",
                task=spine.SpineTaskInput(
                    title="High priority approval item",
                    summary="Needs approval.",
                    project_id="release-signals",
                    type="ops",
                    priority="high",
                    status="awaiting_approval",
                    approval_required=True,
                    approval_state="required",
                ),
            ),
            session=session,
        )
        stale = spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.progress",
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(user.id),
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="task_master", source_ref="sig-3", room_id=str(room.id)),
                content="Unowned stale item",
                task=spine.SpineTaskInput(
                    title="Unowned stale task",
                    summary="This should go stale without owner.",
                    project_id="release-signals",
                    type="maintenance",
                    priority="high",
                    status="in_progress",
                    owner_kind="unassigned",
                ),
            ),
            session=session,
        )
        with spine._conn() as conn:
            conn.execute(
                "UPDATE guardian_spine_tasks SET last_progress_at = ? WHERE task_id = ?",
                ("2020-01-01T00:00:00+00:00", stale["task_id"]),
            )
            conn.commit()

        executive = spine.ingest_executive_decision(
            room_id=str(room.id),
            source_ref="sig-4",
            decision_summary="Create an unassigned executive directive.",
            task=spine.SpineTaskInput(
                title="Executive directive with no owner",
                summary="Needs assignment.",
                project_id="release-signals",
                type="ops",
                priority="high",
                status="open",
                owner_kind="unassigned",
                tags=["executive"],
            ),
            session=session,
        )
        resurfaced = spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.completed",
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(user.id),
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="task_master", source_ref="sig-5", room_id=str(room.id)),
                content="Complete before resurfacing.",
                task=spine.SpineTaskInput(
                    title="Resurface with no follow-up",
                    summary="Will be reopened by memory.",
                    project_id="release-signals",
                    type="ops",
                    status="done",
                    tags=["memory"],
                ),
            ),
            session=session,
        )
        spine.ingest_memory_signal(
            room_id=str(room.id),
            source_ref="sig-6",
            signal_text="Memory resurfaced this item.",
            reopen_task_id=resurfaced["task_id"],
            session=session,
        )
        spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type="task.updated",
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(user.id),
                room_id=str(room.id),
                source=spine.SpineSourceReference(source_kind="", source_ref="", room_id=str(room.id)),
                content="Fragmented edge case.",
                task=spine.SpineTaskInput(
                    title="Fragmented no-link task",
                    summary="Missing durable linkage and project.",
                    project_id=None,
                    type="maintenance",
                    status="open",
                ),
            ),
            session=session,
        )

        assert any(task.task_id == high_blocked["task_id"] for task in adapter.task_master_spine.high_priority_blocked(limit=25))
        assert any(task.task_id == high_approval["task_id"] for task in adapter.task_master_spine.high_priority_approval_waiting(limit=25))
        assert any(task.task_id == stale["task_id"] for task in adapter.task_master_spine.stale_unowned(limit=25))
        assert any(task.task_id == executive["task_id"] for task in adapter.task_master_spine.unassigned_executive_directives(limit=25))
        assert any(task.task_id == resurfaced["task_id"] for task in adapter.task_master_spine.resurfaced_without_followup(limit=25))
        assert any(task.title == "Fragmented no-link task" for task in adapter.task_master_spine.missing_durable_linkage(limit=25))
        assert any(task.title == "Fragmented no-link task" for task in adapter.task_master_spine.fragmentation_indicators(limit=25))
