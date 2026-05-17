from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from app.crud import create_chat_meeting_artifact, get_chat_meeting_artifacts

MEETING_ASSIGNMENTS_SOURCE = "meeting_assignments"


def parse_meeting_assignments(text: str, participant_handles: list[str]) -> list[dict[str, str]]:
    """Extract durable assignment records from a manager assignment turn."""
    handles = [handle.strip().lower() for handle in participant_handles if handle.strip()]
    if not handles:
        return []
    assignments: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        compact = re.sub(r"^[\-\*\d.)\[\]\s]+", "", line).strip()
        if not compact:
            continue
        for handle in handles:
            if handle in seen:
                continue
            match = re.search(rf"@?{re.escape(handle)}\b\s*(?::|-)\s*(.+)", compact, re.IGNORECASE)
            if not match:
                continue
            assignment = re.sub(r"\s+", " ", match.group(1)).strip()
            if not assignment:
                continue
            assignments.append({"handle": handle, "assignment": assignment[:500]})
            seen.add(handle)
            break
    return assignments


def assignments_to_markdown(assignments: list[dict[str, str]]) -> str:
    if not assignments:
        return "## Assignments\n\n_No structured assignments captured._"
    lines = ["## Assignments", ""]
    for item in assignments:
        handle = item.get("handle", "").strip() or "participant"
        assignment = item.get("assignment", "").strip() or "Assignment not captured."
        lines.append(f"- **@{handle}:** {assignment}")
    return "\n".join(lines)


def persist_meeting_assignments(
    *,
    session: Session,
    room_id: Any,
    created_by_user_id: Any,
    chair_handle: str,
    participant_handles: list[str],
    assignment_text: str,
    meeting_phase: str = "assignments",
) -> list[dict[str, str]]:
    assignments = parse_meeting_assignments(assignment_text, participant_handles)
    if not assignments:
        return []
    create_chat_meeting_artifact(
        session=session,
        room_id=room_id,
        created_by_user_id=created_by_user_id,
        type="action_items",
        content_markdown=assignments_to_markdown(assignments),
        meta_json={
            "source": MEETING_ASSIGNMENTS_SOURCE,
            "assigned_by": chair_handle,
            "meeting_phase": meeting_phase,
            "assignments": assignments,
            "assignment_count": len(assignments),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "memory_rollup": False,
        },
    )
    return assignments


def latest_meeting_assignments(*, session: Session, room_id: Any) -> list[dict[str, str]]:
    for artifact in get_chat_meeting_artifacts(session=session, room_id=room_id, type="action_items", limit=20):
        meta = artifact.meta_json or {}
        if not isinstance(meta, dict) or meta.get("source") != MEETING_ASSIGNMENTS_SOURCE:
            continue
        assignments = meta.get("assignments")
        if isinstance(assignments, list):
            return [item for item in assignments if isinstance(item, dict)]
    return []
