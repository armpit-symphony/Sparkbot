from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlmodel import Session

from app.models import (
    ChatMeetingArtifact,
    ChatMessage,
    ChatRoom,
    ChatTask,
    ChatUser,
    TaskStatus,
    UserType,
)

AUTO_CREATE_THRESHOLD = max(
    0.5,
    min(float(os.getenv("SPARKBOT_GUARDIAN_SPINE_AUTO_CREATE_THRESHOLD", "0.85")), 1.0),
)
REVIEW_THRESHOLD = max(
    0.2,
    min(float(os.getenv("SPARKBOT_GUARDIAN_SPINE_REVIEW_THRESHOLD", "0.60")), 1.0),
)

TASK_TYPES = {
    "bug",
    "feature",
    "ops",
    "research",
    "approval",
    "handoff",
    "meeting_followup",
    "documentation",
    "maintenance",
}
TASK_PRIORITIES = {"low", "normal", "high", "critical"}
PROJECT_STATUSES = {"proposed", "active", "blocked", "done", "archived"}
TASK_STATUSES = {
    "candidate",
    "open",
    "triaged",
    "queued",
    "in_progress",
    "blocked",
    "awaiting_approval",
    "awaiting_input",
    "in_review",
    "done",
    "canceled",
}
APPROVAL_STATES = {"not_required", "required", "requested", "granted", "denied"}
OWNER_KINDS = {"human", "sparkbot", "agent", "unassigned"}
LINK_TYPES = {"duplicate", "related", "parent_child", "mirror", "dependency"}

_NEW_TASK_PATTERNS = (
    re.compile(r"\b(?:need to|needs to|should|have to|must|please fix|please update|can you handle|follow up on)\b", re.I),
    re.compile(r"\b(?:fix|implement|test|investigate|review|ship|deploy|document|update|revisit|handle)\b", re.I),
)
_BLOCKER_PATTERNS = (
    re.compile(r"\bblocked\b", re.I),
    re.compile(r"\bwaiting on\b", re.I),
    re.compile(r"\bcan(?:not|'t) until\b", re.I),
    re.compile(r"\bneeds approval\b", re.I),
)
_COMPLETION_PATTERNS = (
    re.compile(r"\bdone\b", re.I),
    re.compile(r"\bfixed\b", re.I),
    re.compile(r"\bdeployed\b", re.I),
    re.compile(r"\bshipped\b", re.I),
    re.compile(r"\bcompleted\b", re.I),
    re.compile(r"\bmerged\b", re.I),
    re.compile(r"\bclosed\b", re.I),
)
_PROGRESS_PATTERNS = (
    re.compile(r"\bstill working on\b", re.I),
    re.compile(r"\binvestigating\b", re.I),
    re.compile(r"\bprogress\b", re.I),
    re.compile(r"\bnext step\b", re.I),
    re.compile(r"\bhandoff\b", re.I),
    re.compile(r"\bin review\b", re.I),
)
_APPROVAL_GRANTED_PATTERNS = (
    re.compile(r"\bbreakglass approved\b", re.I),
    re.compile(r"\bapproval granted\b", re.I),
    re.compile(r"\bapproved for this action\b", re.I),
)
_APPROVAL_DENIED_PATTERNS = (
    re.compile(r"\bapproval denied\b", re.I),
    re.compile(r"\bdenied\b", re.I),
)
_APPROVAL_REQUIRED_PATTERNS = (
    re.compile(r"\bproduction deploy\b", re.I),
    re.compile(r"\bserver change\b", re.I),
    re.compile(r"\bsecret access\b", re.I),
    re.compile(r"\bdestructive\b", re.I),
    re.compile(r"\badmin panel\b", re.I),
    re.compile(r"\bprivate data\b", re.I),
    re.compile(r"\bsystem-level\b", re.I),
    re.compile(r"\bbreakglass\b", re.I),
    re.compile(r"\bpin\b", re.I),
    re.compile(r"\bdeploy\b", re.I),
    re.compile(r"\bservice restart\b", re.I),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guardian_spine_tasks (
  task_id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT,
  project_id TEXT,
  type TEXT NOT NULL,
  priority TEXT NOT NULL,
  status TEXT NOT NULL,
  owner_kind TEXT NOT NULL,
  owner_id TEXT,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  created_by_guardian TEXT NOT NULL,
  approval_required INTEGER NOT NULL DEFAULT 0,
  approval_state TEXT NOT NULL DEFAULT 'not_required',
  confidence REAL NOT NULL,
  parent_task_id TEXT,
  depends_on_json TEXT NOT NULL DEFAULT '[]',
  tags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_progress_at TEXT NOT NULL,
  closed_at TEXT,
  source_excerpt TEXT,
  chat_task_id TEXT
);

CREATE TABLE IF NOT EXISTS guardian_spine_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  room_id TEXT,
  subsystem TEXT,
  actor_kind TEXT NOT NULL,
  actor_id TEXT,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  correlation_id TEXT NOT NULL,
  task_id TEXT,
  project_id TEXT,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardian_spine_links (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  related_task_id TEXT NOT NULL,
  link_type TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardian_spine_assignments (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  owner_kind TEXT NOT NULL,
  owner_id TEXT,
  assigned_at TEXT NOT NULL,
  assigned_by TEXT
);

CREATE TABLE IF NOT EXISTS guardian_spine_approvals (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  requester_id TEXT,
  approver_id TEXT,
  approval_method TEXT,
  state TEXT NOT NULL,
  scope_json TEXT NOT NULL DEFAULT '[]',
  expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardian_spine_handoffs (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  room_id TEXT NOT NULL,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL,
  source_ref TEXT
);

CREATE TABLE IF NOT EXISTS guardian_spine_projects (
  project_id TEXT PRIMARY KEY,
  room_id TEXT,
  display_name TEXT NOT NULL,
  slug TEXT NOT NULL UNIQUE,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guardian_spine_project_events (
  event_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  room_id TEXT,
  subsystem TEXT,
  source_kind TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_guardian_spine_tasks_room_id ON guardian_spine_tasks(room_id);
CREATE INDEX IF NOT EXISTS idx_guardian_spine_tasks_status ON guardian_spine_tasks(status);
CREATE INDEX IF NOT EXISTS idx_guardian_spine_tasks_project_id ON guardian_spine_tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_guardian_spine_events_room_source ON guardian_spine_events(source_kind, source_ref);
CREATE INDEX IF NOT EXISTS idx_guardian_spine_events_task_id ON guardian_spine_events(task_id);
CREATE INDEX IF NOT EXISTS idx_guardian_spine_links_task_id ON guardian_spine_links(task_id);
CREATE INDEX IF NOT EXISTS idx_guardian_spine_project_events_project_id ON guardian_spine_project_events(project_id);
"""


@dataclass(frozen=True)
class SpineTask:
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
    created_by_guardian: str
    created_by_subsystem: str | None
    updated_by_subsystem: str | None
    approval_required: int
    approval_state: str
    confidence: float
    parent_task_id: str | None
    depends_on_json: str
    tags_json: str
    created_at: str
    updated_at: str
    last_progress_at: str
    closed_at: str | None
    source_excerpt: str | None
    chat_task_id: str | None


@dataclass(frozen=True)
class SpineEvent:
    event_id: str
    event_type: str
    occurred_at: str
    room_id: str | None
    subsystem: str | None
    actor_kind: str
    actor_id: str | None
    source_kind: str
    source_ref: str
    correlation_id: str
    task_id: str | None
    project_id: str | None
    payload_json: str


@dataclass(frozen=True)
class SpineHandoff:
    id: str
    task_id: str
    room_id: str
    summary: str
    created_at: str
    source_ref: str | None


@dataclass(frozen=True)
class SpineProject:
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
    tags_json: str | None
    parent_project_id: str | None
    created_at: str | None
    updated_at: str


@dataclass(frozen=True)
class SpineApproval:
    id: str
    task_id: str
    requester_id: str | None
    approver_id: str | None
    approval_method: str | None
    state: str
    scope_json: str
    expires_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SpineLink:
    id: str
    task_id: str
    related_task_id: str
    link_type: str
    created_at: str


@dataclass(frozen=True)
class SpineProjectEvent:
    event_id: str
    project_id: str
    event_type: str
    occurred_at: str
    room_id: str | None
    subsystem: str | None
    source_kind: str
    source_ref: str
    payload_json: str


class SpineSourceReference(BaseModel):
    source_kind: str = Field(default="system")
    source_ref: str
    room_id: str | None = None


class SpineProjectInput(BaseModel):
    project_id: str
    display_name: str
    summary: str | None = None
    status: str = "active"
    room_id: str | None = None
    parent_project_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class SpineTaskInput(BaseModel):
    task_id: str | None = None
    title: str
    summary: str | None = None
    project_id: str | None = None
    type: str = "feature"
    priority: str = "normal"
    status: str = "open"
    owner_kind: str = "unassigned"
    owner_id: str | None = None
    parent_task_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    related_task_ids: list[str] = Field(default_factory=list)
    approval_required: bool = False
    approval_state: str = "not_required"
    confidence: float = 1.0
    tags: list[str] = Field(default_factory=list)


class SpineSubsystemEvent(BaseModel):
    event_type: str
    subsystem: str
    actor_kind: str = "system"
    actor_id: str | None = None
    room_id: str | None = None
    correlation_id: str | None = None
    source: SpineSourceReference
    content: str | None = None
    project: SpineProjectInput | None = None
    task: SpineTaskInput | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SpineProducerRegistration(BaseModel):
    subsystem: str
    description: str
    event_types: list[str] = Field(default_factory=list)


_PRODUCER_REGISTRY: dict[str, SpineProducerRegistration] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _data_root() -> Path:
    root = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    if root:
        return Path(root).expanduser()
    return Path(__file__).resolve().parents[4] / "data" / "guardian"


def _db_path() -> Path:
    root = _data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "spine.db"


def _mirror_root() -> Path:
    root = _data_root() / "spine"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row["name"]) for row in rows}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    if column in _table_columns(conn, table):
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    _ensure_column(conn, "guardian_spine_tasks", "created_by_subsystem", "TEXT")
    _ensure_column(conn, "guardian_spine_tasks", "updated_by_subsystem", "TEXT")
    _ensure_column(conn, "guardian_spine_events", "room_id", "TEXT")
    _ensure_column(conn, "guardian_spine_events", "subsystem", "TEXT")
    _ensure_column(conn, "guardian_spine_project_events", "room_id", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "summary", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "status", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "source_kind", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "source_ref", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "created_by_subsystem", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "updated_by_subsystem", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "tags_json", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "parent_project_id", "TEXT")
    _ensure_column(conn, "guardian_spine_projects", "created_at", "TEXT")

    conn.execute(
        """
        UPDATE guardian_spine_tasks
        SET created_by_subsystem = COALESCE(created_by_subsystem, created_by_guardian, 'guardian_spine'),
            updated_by_subsystem = COALESCE(updated_by_subsystem, created_by_guardian, 'guardian_spine')
        """
    )
    conn.execute(
        """
        UPDATE guardian_spine_projects
        SET summary = COALESCE(summary, ''),
            status = COALESCE(status, 'active'),
            source_kind = COALESCE(source_kind, 'system'),
            source_ref = COALESCE(source_ref, project_id),
            created_by_subsystem = COALESCE(created_by_subsystem, 'guardian_spine'),
            updated_by_subsystem = COALESCE(updated_by_subsystem, created_by_subsystem, 'guardian_spine'),
            tags_json = COALESCE(tags_json, '[]'),
            created_at = COALESCE(created_at, updated_at)
        """
    )


def _init_store() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)
        _ensure_schema_migrations(conn)


def register_spine_producer(registration: SpineProducerRegistration) -> SpineProducerRegistration:
    _PRODUCER_REGISTRY[registration.subsystem] = registration
    return registration


def list_registered_spine_producers() -> list[SpineProducerRegistration]:
    if not _PRODUCER_REGISTRY:
        for registration in (
            SpineProducerRegistration(subsystem="guardian_spine", description="Natural-language intake from chat and meeting artifacts.", event_types=["message.created", "meeting.note.created", "task.created", "task.updated"]),
            SpineProducerRegistration(subsystem="task_master", description="Task lifecycle and queue/status actions from room tasks and Task Master flows.", event_types=["task.queued", "task.assigned", "task.completed", "task.reopened", "task.blocked"]),
            SpineProducerRegistration(subsystem="memory", description="Memory resurfacing and reopen signals.", event_types=["memory.signal"]),
            SpineProducerRegistration(subsystem="executive", description="Executive decisions and directives.", event_types=["executive.decision"]),
            SpineProducerRegistration(subsystem="approval", description="Approval and breakglass state changes.", event_types=["approval.required", "approval.granted", "approval.denied", "breakglass.requested", "breakglass.opened", "breakglass.closed"]),
            SpineProducerRegistration(subsystem="task_guardian", description="Scheduled task progress, verifier, and escalation updates.", event_types=["task.progress", "task.blocked", "task.completed", "handoff.created"]),
            SpineProducerRegistration(subsystem="room_lifecycle", description="Room and project-room lifecycle observations.", event_types=["room.created", "room.updated"]),
            SpineProducerRegistration(subsystem="meeting", description="Structured meeting notes, decisions, and action items.", event_types=["meeting.summary.created", "meeting.decisions.created", "meeting.action_items.created"]),
            SpineProducerRegistration(subsystem="handoff", description="Explicit handoff creation and update events.", event_types=["handoff.created", "handoff.updated"]),
            SpineProducerRegistration(subsystem="project_lifecycle", description="Explicit project creation and update lifecycle events.", event_types=["project.created", "project.updated"]),
            SpineProducerRegistration(subsystem="worker", description="Worker agent progress and status updates.", event_types=["worker.status"]),
        ):
            register_spine_producer(registration)
    return list(_PRODUCER_REGISTRY.values())


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower())
    return text.strip("-") or "general"


def _clean_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    return cleaned


def _normalize_for_compare(text: str) -> str:
    cleaned = _slugify(text).replace("-", " ")
    return cleaned


def _json_loads_list(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _first_sentence(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)
    return parts[0]


def _project_from_room(room_name: str | None) -> tuple[str, str]:
    label = (room_name or "sparkbot").strip() or "sparkbot"
    slug = _slugify(label)
    return slug, label


def _generate_task_id(conn: sqlite3.Connection) -> str:
    prefix = f"TASK-{_now().strftime('%Y%m%d')}-"
    rows = conn.execute(
        "SELECT task_id FROM guardian_spine_tasks WHERE task_id LIKE ? ORDER BY task_id DESC LIMIT 1",
        (f"{prefix}%",),
    ).fetchall()
    if not rows:
        return f"{prefix}001"
    last = str(rows[0]["task_id"]).split("-")[-1]
    try:
        next_num = int(last) + 1
    except ValueError:
        next_num = 1
    return f"{prefix}{next_num:03d}"


def _record_project(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    room_id: str | None,
    display_name: str,
    summary: str | None = None,
    status: str = "active",
    source_kind: str = "system",
    source_ref: str | None = None,
    created_by_subsystem: str = "guardian_spine",
    updated_by_subsystem: str | None = None,
    tags: list[str] | None = None,
    parent_project_id: str | None = None,
) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO guardian_spine_projects
        (project_id, room_id, display_name, slug, summary, status, source_kind, source_ref, created_by_subsystem, updated_by_subsystem, tags_json, parent_project_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(project_id) DO UPDATE SET
          room_id=excluded.room_id,
          display_name=excluded.display_name,
          slug=excluded.slug,
          summary=excluded.summary,
          status=excluded.status,
          source_kind=excluded.source_kind,
          source_ref=excluded.source_ref,
          updated_by_subsystem=excluded.updated_by_subsystem,
          tags_json=excluded.tags_json,
          parent_project_id=excluded.parent_project_id,
          updated_at=excluded.updated_at
        """,
        (
            project_id,
            room_id,
            display_name,
            _slugify(project_id),
            summary or "",
            status if status in PROJECT_STATUSES else "active",
            source_kind,
            source_ref or project_id,
            created_by_subsystem,
            updated_by_subsystem or created_by_subsystem,
            json.dumps(tags or [], ensure_ascii=False),
            parent_project_id,
            now,
            now,
        ),
    )


def _emit_event(
    conn: sqlite3.Connection,
    *,
    event_type: str,
    room_id: str | None = None,
    subsystem: str = "guardian_spine",
    actor_kind: str,
    actor_id: str | None,
    source_kind: str,
    source_ref: str,
    correlation_id: str,
    payload: dict[str, Any],
    task_id: str | None = None,
    project_id: str | None = None,
) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO guardian_spine_events
        (event_id, event_type, occurred_at, room_id, subsystem, actor_kind, actor_id, source_kind, source_ref, correlation_id, task_id, project_id, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            event_type,
            _now_iso(),
            room_id,
            subsystem,
            actor_kind,
            actor_id,
            source_kind,
            source_ref,
            correlation_id,
            task_id,
            project_id,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    return event_id


def _emit_project_event(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    event_type: str,
    room_id: str | None,
    subsystem: str,
    source_kind: str,
    source_ref: str,
    payload: dict[str, Any],
) -> str:
    event_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO guardian_spine_project_events
        (event_id, project_id, event_type, occurred_at, room_id, subsystem, source_kind, source_ref, payload_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            project_id,
            event_type,
            _now_iso(),
            room_id,
            subsystem,
            source_kind,
            source_ref,
            json.dumps(payload, ensure_ascii=False),
        ),
    )
    return event_id


def _add_link(conn: sqlite3.Connection, *, task_id: str, related_task_id: str, link_type: str) -> None:
    if link_type not in LINK_TYPES or not related_task_id or task_id == related_task_id:
        return
    existing = conn.execute(
        """
        SELECT id FROM guardian_spine_links
        WHERE task_id = ? AND related_task_id = ? AND link_type = ?
        LIMIT 1
        """,
        (task_id, related_task_id, link_type),
    ).fetchone()
    if existing:
        return
    conn.execute(
        """
        INSERT INTO guardian_spine_links (id, task_id, related_task_id, link_type, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), task_id, related_task_id, link_type, _now_iso()),
    )


def _record_assignment(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    owner_kind: str,
    owner_id: str | None,
    assigned_by: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO guardian_spine_assignments (id, task_id, owner_kind, owner_id, assigned_at, assigned_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), task_id, owner_kind, owner_id, _now_iso(), assigned_by),
    )


def _record_approval(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    requester_id: str | None,
    approver_id: str | None,
    approval_method: str | None,
    state: str,
    scope: list[str] | None = None,
    expires_at: str | None = None,
) -> None:
    now = _now_iso()
    conn.execute(
        """
        INSERT INTO guardian_spine_approvals (id, task_id, requester_id, approver_id, approval_method, state, scope_json, expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            task_id,
            requester_id,
            approver_id,
            approval_method,
            state,
            json.dumps(scope or [], ensure_ascii=False),
            expires_at,
            now,
            now,
        ),
    )


def _record_handoff(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    room_id: str,
    summary: str,
    source_ref: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO guardian_spine_handoffs (id, task_id, room_id, summary, created_at, source_ref)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), task_id, room_id, summary[:2000], _now_iso(), source_ref),
    )


def _write_handoff(task: SpineTask, event_type: str, note: str) -> None:
    handoff_dir = _mirror_root() / "handoffs"
    handoff_dir.mkdir(parents=True, exist_ok=True)
    path = handoff_dir / f"{_now().date().isoformat()}-handoff.md"
    line = f"- {_now_iso()} `{event_type}` [{task.task_id}] {task.title}: {note}\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def _write_meeting_mirror(*, source_ref: str, room_name: str, content: str, task_refs: list[str]) -> None:
    meeting_dir = _mirror_root() / "meetings"
    meeting_dir.mkdir(parents=True, exist_ok=True)
    path = meeting_dir / f"{_slugify(source_ref)}.md"
    lines = [
        f"# Meeting Capture — {room_name}",
        "",
        f"- source_ref: `{source_ref}`",
        f"- generated_at: `{_now_iso()}`",
        "",
        "## Content",
        content.strip() or "(empty)",
        "",
        "## Linked Tasks",
    ]
    if task_refs:
        lines.extend(f"- `{task_id}`" for task_id in task_refs)
    else:
        lines.append("- none")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_task_markdown(task: SpineTask, room_name: str | None = None) -> None:
    mirror_root = _mirror_root()
    tasks_dir = mirror_root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    depends_on = _json_loads_list(task.depends_on_json)
    tags = _json_loads_list(task.tags_json)
    source_label = room_name or task.room_id

    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT occurred_at, event_type, payload_json
            FROM guardian_spine_events
            WHERE task_id = ?
            ORDER BY occurred_at ASC
            LIMIT 20
            """,
            (task.task_id,),
        ).fetchall()

    activity = []
    for row in rows:
        try:
            payload = json.loads(str(row["payload_json"]) or "{}")
        except Exception:
            payload = {}
        summary = payload.get("summary") or payload.get("message") or payload.get("status") or row["event_type"]
        activity.append(f"- {row['occurred_at']} {row['event_type']}: {summary}")

    frontmatter = [
        "---",
        f"id: {task.task_id}",
        f"title: {task.title}",
        f"project: {task.project_id or ''}",
        f"type: {task.type}",
        f"priority: {task.priority}",
        f"status: {task.status}",
        f"owner_kind: {task.owner_kind}",
        f"owner_id: {task.owner_id or ''}",
        f"source_kind: {task.source_kind}",
        f"source_ref: {task.source_ref}",
        f"approval_required: {'true' if bool(task.approval_required) else 'false'}",
        f"approval_state: {task.approval_state}",
        f"confidence: {task.confidence:.2f}",
        f"parent_task_id: {task.parent_task_id or ''}",
        f"depends_on: {json.dumps(depends_on, ensure_ascii=False)}",
        f"tags: {json.dumps(tags, ensure_ascii=False)}",
        f"created_at: {task.created_at}",
        f"updated_at: {task.updated_at}",
        f"last_progress_at: {task.last_progress_at}",
        f"closed_at: {task.closed_at or ''}",
        "---",
        "",
        "## Summary",
        task.summary or "(none)",
        "",
        "## Source",
        f"- {task.source_ref}",
        f"- {source_label}",
        "",
        "## Next Action",
        _next_action_for_task(task),
        "",
        "## Activity Log",
    ]
    if activity:
        frontmatter.extend(activity)
    else:
        frontmatter.append("- none")
    (tasks_dir / f"{task.task_id}.md").write_text("\n".join(frontmatter).rstrip() + "\n", encoding="utf-8")


def _write_project_mirror(*, project_id: str, room_name_map: dict[str, str]) -> None:
    project_slug = _slugify(project_id)
    project_dir = _mirror_root() / "projects" / project_slug
    project_dir.mkdir(parents=True, exist_ok=True)

    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM guardian_spine_tasks
            WHERE project_id = ?
            ORDER BY CASE status WHEN 'done' THEN 1 ELSE 0 END, priority DESC, updated_at DESC
            """,
            (project_id,),
        ).fetchall()
    tasks = [SpineTask(**dict(row)) for row in rows]
    open_count = sum(1 for task in tasks if task.status != "done")
    blocked_count = sum(1 for task in tasks if task.status == "blocked")
    approval_count = sum(1 for task in tasks if task.status == "awaiting_approval")

    summary_lines = [
        f"# Project Summary — {project_id}",
        "",
        f"- updated_at: `{_now_iso()}`",
        f"- open_tasks: `{open_count}`",
        f"- blocked_tasks: `{blocked_count}`",
        f"- awaiting_approval: `{approval_count}`",
    ]
    (project_dir / "summary.md").write_text("\n".join(summary_lines).rstrip() + "\n", encoding="utf-8")

    task_lines = [f"# Project Tasks — {project_id}", ""]
    if tasks:
        for task in tasks:
            room_label = room_name_map.get(task.room_id, task.room_id)
            task_lines.append(
                f"- [{task.task_id}] {task.title} — `{task.status}` — `{task.priority}` — room `{room_label}`"
            )
    else:
        task_lines.append("- none")
    (project_dir / "tasks.md").write_text("\n".join(task_lines).rstrip() + "\n", encoding="utf-8")


def _render_task(task_id: str) -> SpineTask | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM guardian_spine_tasks WHERE task_id = ?", (task_id,)).fetchone()
    return SpineTask(**dict(row)) if row else None


def _task_similarity(a: str, b: str) -> float:
    return SequenceMatcher(a=_normalize_for_compare(a), b=_normalize_for_compare(b)).ratio()


def _infer_due_at(text: str) -> str | None:
    lowered = text.lower()
    base = _now()
    if "tomorrow" in lowered:
        return (base + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat()
    if "today" in lowered or "asap" in lowered:
        return base.replace(hour=23, minute=0, second=0, microsecond=0).isoformat()
    next_week = re.search(r"\bnext week\b", lowered)
    if next_week:
        return (base + timedelta(days=7)).replace(hour=17, minute=0, second=0, microsecond=0).isoformat()
    return None


def _infer_priority(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("critical", "release blocker", "urgent", "production down", "sev1")):
        return "critical"
    if any(token in lowered for token in ("high priority", "blocker", "must", "today", "asap")):
        return "high"
    if any(token in lowered for token in ("later", "nice to have", "eventually", "low priority")):
        return "low"
    return "normal"


def _infer_type(text: str, source_kind: str, approval_required: bool) -> str:
    lowered = text.lower()
    if approval_required:
        return "approval"
    if source_kind == "meeting.note.created":
        return "meeting_followup"
    if any(token in lowered for token in ("bug", "fix", "broken", "error", "black screen", "regression")):
        return "bug"
    if any(token in lowered for token in ("research", "investigate", "look into", "compare")):
        return "research"
    if any(token in lowered for token in ("deploy", "server", "ops", "restart", "service")):
        return "ops"
    if any(token in lowered for token in ("doc", "readme", "documentation", "write up")):
        return "documentation"
    if any(token in lowered for token in ("cleanup", "refactor", "maintenance")):
        return "maintenance"
    if any(token in lowered for token in ("handoff", "follow up")):
        return "handoff"
    return "feature"


def _approval_required(text: str) -> bool:
    return any(pattern.search(text) for pattern in _APPROVAL_REQUIRED_PATTERNS)


def _extract_tags(text: str, task_type: str, approval_required: bool, source_kind: str) -> list[str]:
    lowered = text.lower()
    tags = {task_type, source_kind.replace(".", "-")}
    if approval_required:
        tags.add("approval")
    for token in ("frontend", "backend", "release", "research", "meeting", "deploy", "breakglass", "token-guardian"):
        if token.replace("-", " ") in lowered or token in lowered:
            tags.add(token)
    return sorted(tags)


def _task_signal(text: str) -> tuple[str | None, float]:
    lowered = text.lower()
    if any(pattern.search(lowered) for pattern in _APPROVAL_GRANTED_PATTERNS):
        return "approval_granted", 0.95
    if any(pattern.search(lowered) for pattern in _APPROVAL_DENIED_PATTERNS):
        return "approval_denied", 0.9
    if any(pattern.search(lowered) for pattern in _COMPLETION_PATTERNS):
        return "completion", 0.9
    if any(pattern.search(lowered) for pattern in _BLOCKER_PATTERNS):
        return "blocked", 0.88
    if any(pattern.search(lowered) for pattern in _PROGRESS_PATTERNS):
        return "progress", 0.72
    if any(pattern.search(lowered) for pattern in _NEW_TASK_PATTERNS):
        return "new_task", 0.9
    if re.search(r"^- \[ \]", text, re.M):
        return "new_task", 0.9
    return None, 0.0


def _extract_title(text: str) -> str:
    sentence = _first_sentence(text)
    cleaned = re.sub(
        r"^(?:we need to|need to|needs to|please|can you|let'?s|i(?:'ll| will)|we should|should)\s+",
        "",
        sentence,
        flags=re.I,
    ).strip(" -:.,")
    if not cleaned:
        cleaned = sentence
    cleaned = cleaned[:180].strip()
    if not cleaned:
        return "Follow up"
    if cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _summary_from_text(text: str) -> str:
    cleaned = _clean_text(text)
    return cleaned[:600]


def _extract_owner(
    *,
    session: Session,
    room_id: str,
    text: str,
    actor_kind: str,
    actor_id: str | None,
    actor_username: str | None,
) -> tuple[str, str | None]:
    lowered = text.lower()
    # Prefer explicit first-person ownership.
    if re.search(r"\b(i[' ]?ll|i will|i can take|i'll do)\b", lowered):
        if actor_kind in {"human", "sparkbot", "agent"}:
            return actor_kind if actor_kind in OWNER_KINDS else "unassigned", actor_id
    if re.search(r"\bsparkbot\b", lowered):
        return "sparkbot", "sparkbot"
    if actor_kind == "agent":
        return "agent", actor_username or actor_id
    if actor_kind == "human" and actor_id:
        return "human", actor_id
    return "unassigned", None


def _find_candidate_match(
    conn: sqlite3.Connection,
    *,
    room_id: str,
    title: str,
    summary: str,
    project_id: str,
    source_ref: str,
) -> tuple[SpineTask | None, float]:
    rows = conn.execute(
        """
        SELECT * FROM guardian_spine_tasks
        WHERE room_id = ? AND status != 'done' AND status != 'canceled'
        ORDER BY updated_at DESC
        LIMIT 25
        """,
        (room_id,),
    ).fetchall()
    exact_source = next((SpineTask(**dict(row)) for row in rows if str(row["source_ref"]) == source_ref), None)
    if exact_source:
        return exact_source, 1.0
    best_task = None
    best_score = 0.0
    for row in rows:
        task = SpineTask(**dict(row))
        score = max(
            _task_similarity(task.title, title),
            _task_similarity(task.source_excerpt or task.summary or task.title, title),
            _task_similarity(task.title, summary),
            _task_similarity(task.source_excerpt or task.summary or task.title, summary),
        )
        if task.project_id == project_id:
            score += 0.05
        if score > best_score:
            best_task = task
            best_score = score
    return best_task, min(best_score, 1.0)


def _next_action_for_task(task: SpineTask) -> str:
    if task.status == "awaiting_approval":
        return "Wait for breakglass or explicit approval before execution."
    if task.status == "blocked":
        return "Resolve the blocker or missing dependency before resuming."
    if task.status == "done":
        return "No further action required."
    return task.summary or "Review the linked source and continue the next concrete step."


def _mirror_status(status: str) -> TaskStatus:
    return TaskStatus.DONE if status == "done" else TaskStatus.OPEN


def _sync_chat_task_mirror(session: Session, *, spine_task: SpineTask) -> str | None:
    if not spine_task.room_id:
        return None
    room_uuid = uuid.UUID(spine_task.room_id)
    room = session.get(ChatRoom, room_uuid)
    if room is None:
        return None
    assigned_uuid = None
    if spine_task.owner_kind == "human" and spine_task.owner_id:
        try:
            assigned_uuid = uuid.UUID(spine_task.owner_id)
        except Exception:
            assigned_uuid = None

    existing = None
    if spine_task.chat_task_id:
        try:
            existing = session.get(ChatTask, uuid.UUID(spine_task.chat_task_id))
        except Exception:
            existing = None

    due_at = _infer_due_at(spine_task.summary or spine_task.source_excerpt or spine_task.title)
    due_dt = datetime.fromisoformat(due_at) if due_at else None

    if existing is None:
        existing = ChatTask(
            room_id=room_uuid,
            created_by=uuid.UUID(spine_task.owner_id) if spine_task.owner_kind == "human" and spine_task.owner_id else room.created_by,
            assigned_to=assigned_uuid,
            title=spine_task.title,
            description=spine_task.summary,
            status=_mirror_status(spine_task.status),
            due_date=due_dt,
        )
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return str(existing.id)

    existing.title = spine_task.title
    existing.description = spine_task.summary
    existing.status = _mirror_status(spine_task.status)
    existing.assigned_to = assigned_uuid
    existing.due_date = due_dt
    existing.updated_at = _now()
    session.add(existing)
    session.commit()
    session.refresh(existing)
    return str(existing.id)


def _upsert_task(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    room_id: str,
    title: str,
    summary: str,
    project_id: str,
    task_type: str,
    priority: str,
    status: str,
    owner_kind: str,
    owner_id: str | None,
    source_kind: str,
    source_ref: str,
    created_by_guardian: str,
    created_by_subsystem: str,
    updated_by_subsystem: str,
    approval_required: bool,
    approval_state: str,
    confidence: float,
    parent_task_id: str | None,
    depends_on: list[str],
    tags: list[str],
    source_excerpt: str,
    chat_task_id: str | None = None,
) -> None:
    now = _now_iso()
    existing = conn.execute(
        "SELECT created_at, chat_task_id FROM guardian_spine_tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    created_at = str(existing["created_at"]) if existing else now
    effective_chat_task_id = chat_task_id or (str(existing["chat_task_id"]) if existing and existing["chat_task_id"] else None)
    conn.execute(
        """
        INSERT INTO guardian_spine_tasks
        (task_id, room_id, title, summary, project_id, type, priority, status, owner_kind, owner_id, source_kind, source_ref,
         created_by_guardian, created_by_subsystem, updated_by_subsystem, approval_required, approval_state, confidence, parent_task_id, depends_on_json, tags_json, created_at,
         updated_at, last_progress_at, closed_at, source_excerpt, chat_task_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task_id) DO UPDATE SET
          room_id=excluded.room_id,
          title=excluded.title,
          summary=excluded.summary,
          project_id=excluded.project_id,
          type=excluded.type,
          priority=excluded.priority,
          status=excluded.status,
          owner_kind=excluded.owner_kind,
          owner_id=excluded.owner_id,
          source_kind=excluded.source_kind,
          source_ref=excluded.source_ref,
          created_by_subsystem=guardian_spine_tasks.created_by_subsystem,
          updated_by_subsystem=excluded.updated_by_subsystem,
          approval_required=excluded.approval_required,
          approval_state=excluded.approval_state,
          confidence=excluded.confidence,
          parent_task_id=excluded.parent_task_id,
          depends_on_json=excluded.depends_on_json,
          tags_json=excluded.tags_json,
          updated_at=excluded.updated_at,
          last_progress_at=excluded.last_progress_at,
          closed_at=excluded.closed_at,
          source_excerpt=excluded.source_excerpt,
          chat_task_id=excluded.chat_task_id
        """,
        (
            task_id,
            room_id,
            title,
            summary,
            project_id,
            task_type if task_type in TASK_TYPES else "feature",
            priority if priority in TASK_PRIORITIES else "normal",
            status if status in TASK_STATUSES else "open",
            owner_kind if owner_kind in OWNER_KINDS else "unassigned",
            owner_id,
            source_kind,
            source_ref,
            created_by_guardian,
            created_by_subsystem,
            updated_by_subsystem,
            1 if approval_required else 0,
            approval_state if approval_state in APPROVAL_STATES else "not_required",
            confidence,
            parent_task_id,
            json.dumps(depends_on, ensure_ascii=False),
            json.dumps(tags, ensure_ascii=False),
            created_at,
            now,
            now,
            now if status == "done" else None,
            source_excerpt,
            effective_chat_task_id,
        ),
    )


def _candidate_payload(
    *,
    source_type: str,
    source_id: str,
    room_id: str,
    excerpt: str,
    actor: str | None,
    confidence: float,
    suggested_title: str,
    suggested_owner: str | None,
    suggested_project: str | None,
    signal: str,
) -> dict[str, Any]:
    return {
        "source_type": source_type,
        "source_id": source_id,
        "room_id": room_id,
        "raw_text_excerpt": excerpt,
        "actor": actor,
        "confidence": round(confidence, 2),
        "suggested_title": suggested_title,
        "suggested_owner": suggested_owner,
        "suggested_project": suggested_project,
        "signal": signal,
    }


def _normalized_payload(
    *,
    title: str,
    summary: str,
    project: str,
    task_type: str,
    priority: str,
    suggested_owner: str | None,
    due_at: str | None,
    approval_required: bool,
    tags: list[str],
    dependencies: list[str],
) -> dict[str, Any]:
    return {
        "title": title,
        "summary": summary,
        "project": project,
        "type": task_type,
        "priority": priority,
        "suggested_owner": suggested_owner,
        "due_at": due_at,
        "approval_required": approval_required,
        "tags": tags,
        "dependencies": dependencies,
    }


def _project_payload(project: SpineProject) -> dict[str, Any]:
    return {
        "project_id": project.project_id,
        "display_name": project.display_name,
        "status": project.status or "active",
        "room_id": project.room_id,
        "source_kind": project.source_kind,
        "source_ref": project.source_ref,
    }


def _create_or_update_project(
    conn: sqlite3.Connection,
    *,
    project_id: str,
    room_id: str | None,
    display_name: str,
    summary: str | None,
    status: str,
    source_kind: str,
    source_ref: str,
    subsystem: str,
    tags: list[str] | None = None,
    parent_project_id: str | None = None,
) -> None:
    _record_project(
        conn,
        project_id=project_id,
        room_id=room_id,
        display_name=display_name,
        summary=summary,
        status=status,
        source_kind=source_kind,
        source_ref=source_ref,
        created_by_subsystem=subsystem,
        updated_by_subsystem=subsystem,
        tags=tags,
        parent_project_id=parent_project_id,
    )
    _emit_project_event(
        conn,
        project_id=project_id,
        event_type="project.updated",
        room_id=room_id,
        subsystem=subsystem,
        source_kind=source_kind,
        source_ref=source_ref,
        payload={
            "project_id": project_id,
            "display_name": display_name,
            "summary": summary,
            "status": status,
            "room_id": room_id,
            "tags": tags or [],
            "parent_project_id": parent_project_id,
        },
    )


def _capture_source(
    *,
    session: Session,
    room_id: str,
    room_name: str,
    source_kind: str,
    source_ref: str,
    actor_kind: str,
    actor_id: str | None,
    actor_username: str | None,
    content: str,
) -> list[str]:
    cleaned = _clean_text(content)
    if not cleaned:
        return []

    _init_store()
    signal, confidence = _task_signal(cleaned)
    project_id, project_label = _project_from_room(room_name)
    correlation_id = source_ref
    task_refs: list[str] = []

    with _conn() as conn:
        _record_project(
            conn,
            project_id=project_id,
            room_id=room_id,
            display_name=project_label,
            summary=f"Auto-cataloged project for room {room_name}",
            status="active",
            source_kind=source_kind,
            source_ref=source_ref,
            created_by_subsystem="guardian_spine",
            updated_by_subsystem="guardian_spine",
            tags=["auto-cataloged", source_kind.replace(".", "-")],
        )
        _emit_project_event(
            conn,
            project_id=project_id,
            event_type="project.updated",
            room_id=room_id,
            subsystem="guardian_spine",
            source_kind=source_kind,
            source_ref=source_ref,
            payload={"display_name": project_label, "room_id": room_id},
        )
        _emit_event(
            conn,
            event_type=source_kind,
            room_id=room_id,
            subsystem="guardian_spine",
            actor_kind=actor_kind,
            actor_id=actor_id,
            source_kind=source_kind,
            source_ref=source_ref,
            correlation_id=correlation_id,
            payload={"content": cleaned[:800], "room_id": room_id, "room_name": room_name, "actor_username": actor_username},
            project_id=project_id,
        )

        if not signal:
            conn.commit()
            return []

        title = _extract_title(cleaned)
        owner_kind, owner_id = _extract_owner(
            session=session,
            room_id=room_id,
            text=cleaned,
            actor_kind=actor_kind,
            actor_id=actor_id,
            actor_username=actor_username,
        )
        due_at = _infer_due_at(cleaned)
        approval_required = _approval_required(cleaned)
        task_type = _infer_type(cleaned, source_kind=source_kind, approval_required=approval_required)
        priority = _infer_priority(cleaned)
        tags = _extract_tags(cleaned, task_type=task_type, approval_required=approval_required, source_kind=source_kind)
        candidate = _candidate_payload(
            source_type=source_kind,
            source_id=source_ref,
            room_id=room_id,
            excerpt=cleaned[:280],
            actor=actor_username or actor_id,
            confidence=confidence,
            suggested_title=title,
            suggested_owner=owner_id,
            suggested_project=project_id,
            signal=signal,
        )
        _emit_event(
            conn,
            event_type="task.candidate.created",
            room_id=room_id,
            subsystem="guardian_spine",
            actor_kind=actor_kind,
            actor_id=actor_id,
            source_kind=source_kind,
            source_ref=source_ref,
            correlation_id=correlation_id,
            payload=candidate,
            project_id=project_id,
        )

        if confidence < REVIEW_THRESHOLD:
            conn.commit()
            return []

        summary = _summary_from_text(cleaned)
        normalized = _normalized_payload(
            title=title,
            summary=summary,
            project=project_id,
            task_type=task_type,
            priority=priority,
            suggested_owner=owner_id,
            due_at=due_at,
            approval_required=approval_required,
            tags=tags,
            dependencies=[],
        )
        _emit_event(
            conn,
            event_type="task.candidate.normalized",
            room_id=room_id,
            subsystem="guardian_spine",
            actor_kind=actor_kind,
            actor_id=actor_id,
            source_kind=source_kind,
            source_ref=source_ref,
            correlation_id=correlation_id,
            payload=normalized,
            project_id=project_id,
        )

        matched_task, match_score = _find_candidate_match(
            conn,
            room_id=room_id,
            title=title,
            summary=summary,
            project_id=project_id,
            source_ref=source_ref,
        )

        match_threshold = 0.84 if signal == "new_task" else 0.55

        if signal in {"completion", "blocked", "progress", "approval_granted", "approval_denied"} and not matched_task:
            conn.commit()
            return []

        if signal == "new_task" and confidence < AUTO_CREATE_THRESHOLD:
            conn.commit()
            return []

        if matched_task and match_score >= match_threshold:
            if signal == "new_task":
                _emit_event(
                    conn,
                    event_type="task.duplicate.detected",
                    room_id=room_id,
                    subsystem="guardian_spine",
                    actor_kind=actor_kind,
                    actor_id=actor_id,
                    source_kind=source_kind,
                    source_ref=source_ref,
                    correlation_id=correlation_id,
                    payload={"matched_task_id": matched_task.task_id, "score": round(match_score, 2)},
                    task_id=matched_task.task_id,
                    project_id=project_id,
                )
                _add_link(conn, task_id=matched_task.task_id, related_task_id=matched_task.task_id, link_type="related")
            next_status = matched_task.status
            next_approval_state = matched_task.approval_state
            if signal == "completion":
                next_status = "done"
            elif signal == "blocked":
                next_status = "blocked"
            elif signal == "progress":
                next_status = "in_progress"
            elif signal == "approval_granted":
                next_status = "in_progress" if matched_task.status == "awaiting_approval" else matched_task.status
                next_approval_state = "granted"
            elif signal == "approval_denied":
                next_status = "blocked"
                next_approval_state = "denied"

            _upsert_task(
                conn,
                task_id=matched_task.task_id,
                room_id=matched_task.room_id,
                title=matched_task.title,
                summary=summary or matched_task.summary or matched_task.title,
                project_id=matched_task.project_id or project_id,
                task_type=matched_task.type,
                priority=matched_task.priority,
                status=next_status,
                owner_kind=matched_task.owner_kind,
                owner_id=matched_task.owner_id,
                source_kind=matched_task.source_kind,
                source_ref=matched_task.source_ref,
                created_by_guardian=matched_task.created_by_guardian,
                created_by_subsystem=matched_task.created_by_subsystem or matched_task.created_by_guardian,
                updated_by_subsystem="guardian_spine",
                approval_required=bool(matched_task.approval_required),
                approval_state=next_approval_state,
                confidence=max(matched_task.confidence, confidence),
                parent_task_id=matched_task.parent_task_id,
                depends_on=_json_loads_list(matched_task.depends_on_json),
                tags=sorted(set(_json_loads_list(matched_task.tags_json)) | set(tags)),
                source_excerpt=cleaned[:280],
                chat_task_id=matched_task.chat_task_id,
            )
            event_name = {
                "completion": "task.completed",
                "blocked": "task.blocked",
                "progress": "task.progress.signal",
                "approval_granted": "task.approval.granted",
                "approval_denied": "task.approval.denied",
            }.get(signal, "task.updated")
            _emit_event(
                conn,
                event_type=event_name,
                room_id=room_id,
                subsystem="guardian_spine",
                actor_kind=actor_kind,
                actor_id=actor_id,
                source_kind=source_kind,
                source_ref=source_ref,
                correlation_id=correlation_id,
                payload={"message": cleaned[:400], "status": next_status},
                task_id=matched_task.task_id,
                project_id=project_id,
            )
            if signal in {"approval_granted", "approval_denied"}:
                _record_approval(
                    conn,
                    task_id=matched_task.task_id,
                    requester_id=matched_task.owner_id,
                    approver_id=actor_id,
                    approval_method="chat",
                    state="granted" if signal == "approval_granted" else "denied",
                    scope=["vault", "service_control"] if signal == "approval_granted" else [],
                )
            _record_handoff(
                conn,
                task_id=matched_task.task_id,
                room_id=matched_task.room_id,
                summary=cleaned[:800],
                source_ref=source_ref,
            )
            task_refs.append(matched_task.task_id)
        else:
            task_id = _generate_task_id(conn)
            status = "awaiting_approval" if approval_required else "open"
            approval_state = "required" if approval_required else "not_required"
            if signal == "blocked":
                status = "blocked"
            elif signal == "completion":
                status = "done"
            elif signal == "progress":
                status = "in_progress"
            elif signal == "approval_granted":
                status = "in_progress"
                approval_state = "granted"
                approval_required = True
            elif signal == "approval_denied":
                status = "blocked"
                approval_state = "denied"
                approval_required = True

            _upsert_task(
                conn,
                task_id=task_id,
                room_id=room_id,
                title=title,
                summary=summary,
                project_id=project_id,
                task_type=task_type,
                priority=priority,
                status=status,
                owner_kind=owner_kind,
                owner_id=owner_id,
                source_kind=source_kind,
                source_ref=source_ref,
                created_by_guardian="guardian_spine",
                created_by_subsystem="guardian_spine",
                updated_by_subsystem="guardian_spine",
                approval_required=approval_required,
                approval_state=approval_state,
                confidence=confidence,
                parent_task_id=None,
                depends_on=[],
                tags=tags,
                source_excerpt=cleaned[:280],
            )
            _record_assignment(conn, task_id=task_id, owner_kind=owner_kind, owner_id=owner_id, assigned_by=actor_id)
            if approval_required:
                _record_approval(
                    conn,
                    task_id=task_id,
                    requester_id=actor_id,
                    approver_id=None,
                    approval_method="chat",
                    state=approval_state,
                    scope=["breakglass"],
                )
                _emit_event(
                    conn,
                    event_type="task.approval.required",
                    room_id=room_id,
                    subsystem="guardian_spine",
                    actor_kind=actor_kind,
                    actor_id=actor_id,
                    source_kind=source_kind,
                    source_ref=source_ref,
                    correlation_id=correlation_id,
                    payload={"message": cleaned[:400], "status": status},
                    task_id=task_id,
                    project_id=project_id,
                )
            _emit_event(
                conn,
                event_type="task.created",
                room_id=room_id,
                subsystem="guardian_spine",
                actor_kind=actor_kind,
                actor_id=actor_id,
                source_kind=source_kind,
                source_ref=source_ref,
                correlation_id=correlation_id,
                payload={"summary": summary, "status": status},
                task_id=task_id,
                project_id=project_id,
            )
            _record_handoff(
                conn,
                task_id=task_id,
                room_id=room_id,
                summary=cleaned[:800],
                source_ref=source_ref,
            )
            task_refs.append(task_id)

        conn.commit()

    room_map = {room_id: room_name}
    for task_id in task_refs:
        task = _render_task(task_id)
        if not task:
            continue
        chat_task_id = _sync_chat_task_mirror(session, spine_task=task)
        if chat_task_id and chat_task_id != task.chat_task_id:
            with _conn() as conn:
                _upsert_task(
                    conn,
                    task_id=task.task_id,
                    room_id=task.room_id,
                    title=task.title,
                    summary=task.summary or "",
                    project_id=task.project_id or project_id,
                    task_type=task.type,
                    priority=task.priority,
                    status=task.status,
                    owner_kind=task.owner_kind,
                    owner_id=task.owner_id,
                    source_kind=task.source_kind,
                    source_ref=task.source_ref,
                    created_by_guardian=task.created_by_guardian,
                    created_by_subsystem=task.created_by_subsystem or task.created_by_guardian,
                    updated_by_subsystem="guardian_spine",
                    approval_required=bool(task.approval_required),
                    approval_state=task.approval_state,
                    confidence=task.confidence,
                    parent_task_id=task.parent_task_id,
                    depends_on=_json_loads_list(task.depends_on_json),
                    tags=_json_loads_list(task.tags_json),
                    source_excerpt=task.source_excerpt or "",
                    chat_task_id=chat_task_id,
                )
                _add_link(conn, task_id=task.task_id, related_task_id=chat_task_id, link_type="mirror")
                conn.commit()
                task = _render_task(task_id)
        if task:
            _write_task_markdown(task, room_name=room_name)
            _write_project_mirror(project_id=task.project_id or project_id, room_name_map=room_map)
            _write_handoff(task, "task.updated" if task.status != "done" else "task.completed", task.summary or task.title)

    if source_kind == "meeting.note.created":
        _write_meeting_mirror(source_ref=source_ref, room_name=room_name, content=cleaned, task_refs=task_refs)
    return task_refs


def capture_message(
    *,
    session: Session,
    message: ChatMessage,
    room_name: str,
    sender_username: str | None,
) -> list[str]:
    source_kind = "message.created"
    actor_kind = "human"
    actor_id = str(message.sender_id)
    if message.sender_type == UserType.BOT:
        if sender_username == "sparkbot":
            actor_kind = "sparkbot"
            source_kind = "agent.output.created"
            actor_id = "sparkbot"
        elif sender_username and sender_username.startswith("agent_"):
            actor_kind = "agent"
            source_kind = "agent.output.created"
            actor_id = sender_username.removeprefix("agent_")
        else:
            actor_kind = "agent"
            source_kind = "agent.output.created"
            actor_id = sender_username or str(message.sender_id)

    return _capture_source(
        session=session,
        room_id=str(message.room_id),
        room_name=room_name,
        source_kind=source_kind,
        source_ref=f"room-{message.room_id}-msg-{message.id}",
        actor_kind=actor_kind,
        actor_id=actor_id,
        actor_username=sender_username,
        content=message.content,
    )


def capture_meeting_artifact(
    *,
    session: Session,
    artifact: ChatMeetingArtifact,
    room_name: str,
    created_by_username: str | None,
) -> list[str]:
    return _capture_source(
        session=session,
        room_id=str(artifact.room_id),
        room_name=room_name,
        source_kind="meeting.note.created",
        source_ref=f"room-{artifact.room_id}-artifact-{artifact.id}",
        actor_kind="human",
        actor_id=str(artifact.created_by_user_id),
        actor_username=created_by_username,
        content=artifact.content_markdown,
    )


def sync_chat_task_created(*, session: Session, task: ChatTask) -> str | None:
    room = session.get(ChatRoom, task.room_id)
    project_id, project_label = _project_from_room(room.name if room else None)
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM guardian_spine_tasks WHERE chat_task_id = ? LIMIT 1",
            (str(task.id),),
        ).fetchall()
        if rows:
            existing = SpineTask(**dict(rows[0]))
            _upsert_task(
                conn,
                task_id=existing.task_id,
                room_id=str(task.room_id),
                title=task.title,
                summary=task.description or existing.summary or task.title,
                project_id=existing.project_id or project_id,
                task_type=existing.type,
                priority=existing.priority,
                status="done" if task.status == TaskStatus.DONE else existing.status,
                owner_kind="human" if task.assigned_to else existing.owner_kind,
                owner_id=str(task.assigned_to) if task.assigned_to else existing.owner_id,
                source_kind=existing.source_kind,
                source_ref=existing.source_ref,
                created_by_guardian=existing.created_by_guardian,
                created_by_subsystem=existing.created_by_subsystem or existing.created_by_guardian,
                updated_by_subsystem="task_master",
                approval_required=bool(existing.approval_required),
                approval_state=existing.approval_state,
                confidence=existing.confidence,
                parent_task_id=existing.parent_task_id,
                depends_on=_json_loads_list(existing.depends_on_json),
                tags=_json_loads_list(existing.tags_json),
                source_excerpt=existing.source_excerpt or (task.description or task.title),
                chat_task_id=str(task.id),
            )
            _emit_event(
                conn,
                event_type="task.updated",
                room_id=str(task.room_id),
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(task.created_by),
                source_kind="room_task",
                source_ref=f"chat-task-{task.id}",
                correlation_id=f"chat-task-{task.id}",
                payload={"summary": task.description or task.title, "status": task.status.value},
                task_id=existing.task_id,
                project_id=existing.project_id,
            )
            _record_handoff(
                conn,
                task_id=existing.task_id,
                room_id=str(task.room_id),
                summary=task.description or task.title,
                source_ref=f"chat-task-{task.id}",
            )
            conn.commit()
            result_id = existing.task_id
        else:
            task_id = _generate_task_id(conn)
            _record_project(
                conn,
                project_id=project_id,
                room_id=str(task.room_id),
                display_name=project_label,
                summary=f"Auto-cataloged project for room {room.name if room else task.room_id}",
                status="active",
                source_kind="room_task",
                source_ref=f"chat-task-{task.id}",
                created_by_subsystem="task_master",
                updated_by_subsystem="task_master",
                tags=["room-task"],
            )
            _upsert_task(
                conn,
                task_id=task_id,
                room_id=str(task.room_id),
                title=task.title,
                summary=task.description or task.title,
                project_id=project_id,
                task_type="feature",
                priority="normal",
                status="done" if task.status == TaskStatus.DONE else "open",
                owner_kind="human" if task.assigned_to else "unassigned",
                owner_id=str(task.assigned_to) if task.assigned_to else None,
                source_kind="room_task",
                source_ref=f"chat-task-{task.id}",
                created_by_guardian="guardian_spine_sync",
                created_by_subsystem="task_master",
                updated_by_subsystem="task_master",
                approval_required=False,
                approval_state="not_required",
                confidence=1.0,
                parent_task_id=None,
                depends_on=[],
                tags=["room-task"],
                source_excerpt=(task.description or task.title)[:280],
                chat_task_id=str(task.id),
            )
            _emit_event(
                conn,
                event_type="task.created",
                room_id=str(task.room_id),
                subsystem="task_master",
                actor_kind="human",
                actor_id=str(task.created_by),
                source_kind="room_task",
                source_ref=f"chat-task-{task.id}",
                correlation_id=f"chat-task-{task.id}",
                payload={"summary": task.description or task.title, "status": task.status.value},
                task_id=task_id,
                project_id=project_id,
            )
            _record_handoff(
                conn,
                task_id=task_id,
                room_id=str(task.room_id),
                summary=task.description or task.title,
                source_ref=f"chat-task-{task.id}",
            )
            conn.commit()
            result_id = task_id

    task_row = _render_task(result_id)
    if task_row:
        _write_task_markdown(task_row, room_name=room.name if room else None)
        _write_project_mirror(project_id=task_row.project_id or project_id, room_name_map={str(task.room_id): room.name if room else str(task.room_id)})
    return result_id


def sync_chat_task_status(*, session: Session, task: ChatTask, status: str) -> str | None:
    _init_store()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM guardian_spine_tasks WHERE chat_task_id = ? LIMIT 1", (str(task.id),)).fetchone()
        if not row:
            return sync_chat_task_created(session=session, task=task)
        spine_task = SpineTask(**dict(row))
        next_status = status if status in TASK_STATUSES else spine_task.status
        _upsert_task(
            conn,
            task_id=spine_task.task_id,
            room_id=spine_task.room_id,
            title=task.title,
            summary=task.description or spine_task.summary or task.title,
            project_id=spine_task.project_id or "sparkbot",
            task_type=spine_task.type,
            priority=spine_task.priority,
            status=next_status,
            owner_kind="human" if task.assigned_to else spine_task.owner_kind,
            owner_id=str(task.assigned_to) if task.assigned_to else spine_task.owner_id,
            source_kind=spine_task.source_kind,
            source_ref=spine_task.source_ref,
            created_by_guardian=spine_task.created_by_guardian,
            created_by_subsystem=spine_task.created_by_subsystem or spine_task.created_by_guardian,
            updated_by_subsystem="task_master",
            approval_required=bool(spine_task.approval_required),
            approval_state=spine_task.approval_state,
            confidence=spine_task.confidence,
            parent_task_id=spine_task.parent_task_id,
            depends_on=_json_loads_list(spine_task.depends_on_json),
            tags=_json_loads_list(spine_task.tags_json),
            source_excerpt=spine_task.source_excerpt or (task.description or task.title),
            chat_task_id=str(task.id),
        )
        _emit_event(
            conn,
            event_type="task.completed" if next_status == "done" else "task.updated",
            room_id=spine_task.room_id,
            subsystem="task_master",
            actor_kind="human",
            actor_id=str(task.created_by),
            source_kind="room_task",
            source_ref=f"chat-task-{task.id}",
            correlation_id=f"chat-task-{task.id}",
            payload={"status": next_status, "summary": task.description or task.title},
            task_id=spine_task.task_id,
            project_id=spine_task.project_id,
        )
        _record_handoff(
            conn,
            task_id=spine_task.task_id,
            room_id=spine_task.room_id,
            summary=task.description or task.title,
            source_ref=f"chat-task-{task.id}",
        )
        conn.commit()
        return spine_task.task_id


def list_spine_tasks(
    *,
    room_id: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    without_project: bool = False,
    limit: int = 50,
) -> list[SpineTask]:
    _init_store()
    clauses: list[str] = []
    params: list[Any] = []
    if room_id:
        clauses.append("room_id = ?")
        params.append(room_id)
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if without_project:
        clauses.append("(project_id IS NULL OR project_id = '')")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 200)))
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM guardian_spine_tasks {where} ORDER BY updated_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [SpineTask(**dict(row)) for row in rows]


def list_spine_events(
    *,
    room_id: str | None = None,
    task_id: str | None = None,
    subsystem: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
) -> list[SpineEvent]:
    _init_store()
    clauses: list[str] = []
    params: list[Any] = []
    if task_id:
        clauses.append("task_id = ?")
        params.append(task_id)
    if project_id:
        clauses.append("project_id = ?")
        params.append(project_id)
    if room_id:
        clauses.append("room_id = ?")
        params.append(room_id)
    if subsystem:
        clauses.append("subsystem = ?")
        params.append(subsystem)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 500)))
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM guardian_spine_events {where} ORDER BY occurred_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [SpineEvent(**dict(row)) for row in rows]


def get_spine_project(*, project_id: str) -> SpineProject | None:
    _init_store()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM guardian_spine_projects WHERE project_id = ? LIMIT 1",
            (project_id,),
        ).fetchone()
    return SpineProject(**dict(row)) if row else None


def list_spine_projects(*, room_id: str | None = None, limit: int = 100) -> list[SpineProject]:
    _init_store()
    clauses: list[str] = []
    params: list[Any] = []
    if room_id:
        clauses.append("room_id = ?")
        params.append(room_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 200)))
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM guardian_spine_projects {where} ORDER BY updated_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [SpineProject(**dict(row)) for row in rows]


def get_spine_task(*, task_id: str) -> SpineTask | None:
    return _render_task(task_id)


def list_project_tasks(*, project_id: str, status: str | None = None, limit: int = 100) -> list[SpineTask]:
    return list_spine_tasks(project_id=project_id, status=status, limit=limit)


def list_orphan_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    return list_spine_tasks(room_id=room_id, without_project=True, limit=limit)


def list_spine_approvals(*, task_id: str | None = None, room_id: str | None = None, limit: int = 100) -> list[SpineApproval]:
    _init_store()
    clauses: list[str] = []
    params: list[Any] = []
    if task_id:
        clauses.append("a.task_id = ?")
        params.append(task_id)
    if room_id:
        clauses.append("t.room_id = ?")
        params.append(room_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 200)))
    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT a.*
            FROM guardian_spine_approvals a
            JOIN guardian_spine_tasks t ON t.task_id = a.task_id
            {where}
            ORDER BY a.created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    return [SpineApproval(**dict(row)) for row in rows]


def list_spine_links(*, task_id: str, link_type: str | None = None) -> list[SpineLink]:
    _init_store()
    clauses = ["task_id = ?"]
    params: list[Any] = [task_id]
    if link_type:
        clauses.append("link_type = ?")
        params.append(link_type)
    where = " AND ".join(clauses)
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM guardian_spine_links WHERE {where} ORDER BY created_at ASC",
            tuple(params),
        ).fetchall()
    return [SpineLink(**dict(row)) for row in rows]


def list_project_handoffs(*, project_id: str, limit: int = 100) -> list[SpineHandoff]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT h.*
            FROM guardian_spine_handoffs h
            JOIN guardian_spine_tasks t ON t.task_id = h.task_id
            WHERE t.project_id = ?
            ORDER BY h.created_at DESC
            LIMIT ?
            """,
            (project_id, max(1, min(limit, 200))),
        ).fetchall()
    return [SpineHandoff(**dict(row)) for row in rows]


def list_project_events(*, project_id: str, limit: int = 100) -> list[SpineProjectEvent]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM guardian_spine_project_events
            WHERE project_id = ?
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (project_id, max(1, min(limit, 200))),
        ).fetchall()
    return [SpineProjectEvent(**dict(row)) for row in rows]


def get_task_lineage(*, task_id: str) -> dict[str, Any]:
    _init_store()
    task = _render_task(task_id)
    if not task:
        return {}
    with _conn() as conn:
        child_rows = conn.execute(
            "SELECT * FROM guardian_spine_tasks WHERE parent_task_id = ? ORDER BY updated_at DESC",
            (task_id,),
        ).fetchall()
        dependency_links = conn.execute(
            "SELECT * FROM guardian_spine_links WHERE task_id = ? AND link_type = 'dependency' ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        related_links = conn.execute(
            "SELECT * FROM guardian_spine_links WHERE task_id = ? AND link_type IN ('related', 'duplicate', 'mirror') ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
    parent = _render_task(task.parent_task_id) if task.parent_task_id else None
    dependencies = [_render_task(str(row["related_task_id"])) for row in dependency_links]
    related = [_render_task(str(row["related_task_id"])) for row in related_links]
    return {
        "task": task,
        "parent": parent,
        "children": [SpineTask(**dict(row)) for row in child_rows],
        "dependencies": [item for item in dependencies if item],
        "related": [item for item in related if item],
        "approvals": list_spine_approvals(task_id=task_id, limit=50),
        "handoffs": list_spine_handoffs(task_id=task_id, limit=50),
    }


def list_spine_handoffs(*, room_id: str | None = None, task_id: str | None = None, limit: int = 100) -> list[SpineHandoff]:
    _init_store()
    clauses: list[str] = []
    params: list[Any] = []
    if task_id:
        clauses.append("task_id = ?")
        params.append(task_id)
    if room_id:
        clauses.append("room_id = ?")
        params.append(room_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(limit, 500)))
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM guardian_spine_handoffs {where} ORDER BY created_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    return [SpineHandoff(**dict(row)) for row in rows]


def get_spine_overview(*, room_id: str) -> dict[str, Any]:
    _init_store()
    with _conn() as conn:
        task_rows = conn.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM guardian_spine_tasks
            WHERE room_id = ?
            GROUP BY status
            """,
            (room_id,),
        ).fetchall()
        event_count = conn.execute(
            "SELECT COUNT(*) AS count FROM guardian_spine_events WHERE room_id = ?",
            (room_id,),
        ).fetchone()
        approval_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM guardian_spine_tasks
            WHERE room_id = ? AND approval_state IN ('required', 'requested')
            """,
            (room_id,),
        ).fetchone()
        project_rows = conn.execute(
            """
            SELECT project_id, display_name, updated_at
            FROM guardian_spine_projects
            WHERE room_id = ?
            ORDER BY updated_at DESC
            """,
            (room_id,),
        ).fetchall()
        handoff_count = conn.execute(
            "SELECT COUNT(*) AS count FROM guardian_spine_handoffs WHERE room_id = ?",
            (room_id,),
        ).fetchone()
        orphan_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM guardian_spine_tasks
            WHERE room_id = ? AND (project_id IS NULL OR project_id = '')
            """,
            (room_id,),
        ).fetchone()
        unassigned_open_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM guardian_spine_tasks
            WHERE room_id = ? AND status NOT IN ('done', 'canceled') AND owner_kind = 'unassigned'
            """,
            (room_id,),
        ).fetchone()

    status_counts = {str(row["status"]): int(row["count"]) for row in task_rows}
    return {
        "room_id": room_id,
        "task_count": sum(status_counts.values()),
        "status_counts": status_counts,
        "event_count": int(event_count["count"]) if event_count else 0,
        "awaiting_approval_count": int(approval_count["count"]) if approval_count else 0,
        "handoff_count": int(handoff_count["count"]) if handoff_count else 0,
        "orphan_task_count": int(orphan_count["count"]) if orphan_count else 0,
        "unassigned_open_task_count": int(unassigned_open_count["count"]) if unassigned_open_count else 0,
        "project_count": len(project_rows),
        "projects": [
            {
                "project_id": str(row["project_id"]),
                "display_name": str(row["display_name"]),
                "updated_at": str(row["updated_at"]),
            }
            for row in project_rows
        ],
    }


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def _stale_threshold_for_priority(priority: str) -> timedelta:
    thresholds = {
        "critical": timedelta(hours=6),
        "high": timedelta(hours=24),
        "normal": timedelta(hours=72),
        "low": timedelta(days=7),
    }
    return thresholds.get(priority, thresholds["normal"])


def _task_is_stale(task: SpineTask, *, now: datetime | None = None) -> bool:
    now = now or _now()
    last_progress = _parse_iso_datetime(task.last_progress_at) or _parse_iso_datetime(task.updated_at) or _parse_iso_datetime(task.created_at)
    if not last_progress:
        return False
    if task.status in {"done", "canceled", "awaiting_approval"}:
        return False
    return now - last_progress > _stale_threshold_for_priority(task.priority)


def list_open_queue(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    tasks = list_spine_tasks(room_id=room_id, limit=max(limit * 2, 50))
    return [task for task in tasks if task.status in {"open", "triaged", "queued", "in_progress"}][:limit]


def list_blocked_queue(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    return list_spine_tasks(room_id=room_id, status="blocked", limit=limit)


def list_approval_waiting_queue(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    tasks = list_spine_tasks(room_id=room_id, limit=max(limit * 2, 50))
    return [task for task in tasks if task.status == "awaiting_approval" or task.approval_state in {"required", "requested"}][:limit]


def list_stale_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    tasks = list_spine_tasks(room_id=room_id, limit=max(limit * 4, 100))
    stale = [task for task in tasks if _task_is_stale(task)]
    stale.sort(key=lambda task: task.last_progress_at or task.updated_at)
    return stale[:limit]


def list_recently_resurfaced_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    events = list_spine_events(room_id=room_id, subsystem="memory", limit=max(limit * 3, 50))
    task_ids: list[str] = []
    for event in events:
        if event.task_id and event.task_id not in task_ids:
            task_ids.append(event.task_id)
    tasks = [_render_task(task_id) for task_id in task_ids]
    return [task for task in tasks if task][:limit]


def list_assignment_ready_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    candidates = list_open_queue(room_id=room_id, limit=max(limit * 3, 50))
    ready = [
        task for task in candidates
        if task.owner_kind == "unassigned"
        and task.approval_state not in {"required", "requested"}
        and not _task_is_stale(task)
        and bool(task.source_kind and task.source_ref)
    ]
    return ready[:limit]


def list_tasks_missing_source_traceability(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    tasks = list_spine_tasks(room_id=room_id, limit=max(limit * 2, 50))
    return [task for task in tasks if not task.source_kind or not task.source_ref][:limit]


def list_tasks_missing_project_linkage(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    return list_orphan_tasks(room_id=room_id, limit=limit)


def list_executive_directives(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    tasks = list_spine_tasks(room_id=room_id, limit=max(limit * 2, 50))
    directives = [task for task in tasks if task.created_by_subsystem == "executive" or task.updated_by_subsystem == "executive"]
    return directives[:limit]


def list_recent_cross_room_events(*, limit: int = 100) -> list[SpineEvent]:
    events = list_spine_events(limit=max(limit * 2, 100))
    return [event for event in events if event.room_id][:limit]


def list_high_priority_blocked_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    return [task for task in list_blocked_queue(room_id=room_id, limit=max(limit * 2, 50)) if task.priority in {"high", "critical"}][:limit]


def list_high_priority_approval_waiting_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    return [task for task in list_approval_waiting_queue(room_id=room_id, limit=max(limit * 2, 50)) if task.priority in {"high", "critical"}][:limit]


def list_stale_unowned_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    return [task for task in list_stale_tasks(room_id=room_id, limit=max(limit * 2, 50)) if task.owner_kind == "unassigned"][:limit]


def list_unassigned_executive_directives(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    return [task for task in list_executive_directives(room_id=room_id, limit=max(limit * 2, 50)) if task.owner_kind == "unassigned"][:limit]


def list_resurfaced_without_followup_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    resurfaced = list_recently_resurfaced_tasks(room_id=room_id, limit=max(limit * 2, 50))
    result: list[SpineTask] = []
    for task in resurfaced:
        events = list_spine_events(room_id=room_id, task_id=task.task_id, limit=20)
        memory_event = next((event for event in events if event.subsystem == "memory"), None)
        if not memory_event:
            continue
        follow_up = any(
            event.subsystem != "memory"
            and event.occurred_at > memory_event.occurred_at
            and event.event_type not in {"task.updated", "task.created"}
            for event in events
        )
        if not follow_up:
            result.append(task)
    return result[:limit]


def list_tasks_missing_durable_linkage(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    tasks = list_spine_tasks(room_id=room_id, limit=max(limit * 3, 100))
    result: list[SpineTask] = []
    for task in tasks:
        source_missing = not task.source_kind or not task.source_ref
        mirror_missing = not task.chat_task_id and task.source_kind in {"room_task", "message.created", "meeting", "meeting.note.created", "worker"}
        if source_missing or mirror_missing:
            result.append(task)
    return result[:limit]


def list_fragmented_tasks(*, room_id: str | None = None, limit: int = 100) -> list[SpineTask]:
    tasks = list_spine_tasks(room_id=room_id, limit=max(limit * 3, 100))
    fragmented: list[SpineTask] = []
    for task in tasks:
        if task.status in {"done", "canceled"}:
            continue
        has_project = bool(task.project_id)
        has_parent = bool(task.parent_task_id)
        has_deps = bool(list_spine_links(task_id=task.task_id, link_type="dependency"))
        has_related = bool(list_spine_links(task_id=task.task_id))
        if not has_project and not has_parent and not has_deps and not has_related:
            fragmented.append(task)
    return fragmented[:limit]


def get_project_workload_summary(*, room_id: str | None = None) -> list[dict[str, Any]]:
    projects = list_spine_projects(room_id=room_id, limit=500)
    summary: list[dict[str, Any]] = []
    for project in projects:
        tasks = list_project_tasks(project_id=project.project_id, limit=500)
        if room_id:
            tasks = [task for task in tasks if task.room_id == room_id]
        open_count = sum(1 for task in tasks if task.status not in {"done", "canceled"})
        blocked_count = sum(1 for task in tasks if task.status == "blocked")
        approval_count = sum(1 for task in tasks if task.status == "awaiting_approval" or task.approval_state in {"required", "requested"})
        unassigned_count = sum(1 for task in tasks if task.owner_kind == "unassigned" and task.status not in {"done", "canceled"})
        summary.append(
            {
                "project_id": project.project_id,
                "display_name": project.display_name,
                "status": project.status or "active",
                "open_count": open_count,
                "blocked_count": blocked_count,
                "approval_count": approval_count,
                "unassigned_count": unassigned_count,
                "updated_at": project.updated_at,
            }
        )
    summary.sort(key=lambda item: (item["blocked_count"], item["approval_count"], item["open_count"]), reverse=True)
    return summary


def get_task_master_overview(*, room_id: str | None = None, limit_per_queue: int = 25) -> dict[str, Any]:
    return {
        "open_queue": list_open_queue(room_id=room_id, limit=limit_per_queue),
        "blocked_queue": list_blocked_queue(room_id=room_id, limit=limit_per_queue),
        "orphan_queue": list_orphan_tasks(room_id=room_id, limit=limit_per_queue),
        "approval_waiting_queue": list_approval_waiting_queue(room_id=room_id, limit=limit_per_queue),
        "stale_queue": list_stale_tasks(room_id=room_id, limit=limit_per_queue),
        "recently_resurfaced_queue": list_recently_resurfaced_tasks(room_id=room_id, limit=limit_per_queue),
        "assignment_ready_queue": list_assignment_ready_tasks(room_id=room_id, limit=limit_per_queue),
        "project_workload_summary": get_project_workload_summary(room_id=room_id),
    }


def _find_approval_target_task(*, room_id: str | None, tool_name: str, event_type: str) -> SpineTask | None:
    if not room_id:
        return None
    candidates = list_approval_waiting_queue(room_id=room_id, limit=25)
    if not candidates and event_type in {"approval.discarded", "approval.denied"}:
        candidates = list_blocked_queue(room_id=room_id, limit=25)
    tool_hint = _normalize_for_compare(tool_name)
    best: SpineTask | None = None
    best_score = 0.0
    for task in candidates:
        haystacks = [task.title, task.summary or "", task.source_excerpt or ""]
        score = max((_task_similarity(tool_hint, _normalize_for_compare(item)) for item in haystacks if item), default=0.0)
        if score > best_score:
            best = task
            best_score = score
    if best_score >= 0.25:
        return best
    return candidates[0] if candidates else None


def ingest_subsystem_event(*, event: SpineSubsystemEvent, session: Session | None = None) -> dict[str, Any]:
    _init_store()
    room_id = event.room_id or event.source.room_id
    correlation_id = event.correlation_id or event.source.source_ref
    project_id = event.project.project_id if event.project else (event.task.project_id if event.task else None)
    created_task_id: str | None = None

    with _conn() as conn:
        if event.project:
            _create_or_update_project(
                conn,
                project_id=event.project.project_id,
                room_id=event.project.room_id or room_id,
                display_name=event.project.display_name,
                summary=event.project.summary,
                status=event.project.status,
                source_kind=event.source.source_kind,
                source_ref=event.source.source_ref,
                subsystem=event.subsystem,
                tags=event.project.tags,
                parent_project_id=event.project.parent_project_id,
            )
            project_id = event.project.project_id
        elif event.task and event.task.project_id:
            _create_or_update_project(
                conn,
                project_id=event.task.project_id,
                room_id=room_id,
                display_name=event.task.project_id,
                summary=event.content or event.task.summary or event.task.title,
                status="active",
                source_kind=event.source.source_kind,
                source_ref=event.source.source_ref,
                subsystem=event.subsystem,
                tags=event.task.tags,
                parent_project_id=None,
            )
            project_id = event.task.project_id

        if event.task:
            existing = _render_task(event.task.task_id) if event.task.task_id else None
            if existing is None and event.task.task_id is None and room_id:
                candidate, score = _find_candidate_match(
                    conn,
                    room_id=room_id,
                    title=event.task.title,
                    summary=event.task.summary or event.content or event.task.title,
                    project_id=project_id or "",
                    source_ref=event.source.source_ref,
                )
                if candidate and score >= 0.72:
                    existing = candidate

            task_id = existing.task_id if existing else (event.task.task_id or _generate_task_id(conn))
            task_summary = event.task.summary or event.content or event.task.title
            task_project_id = event.task.project_id if event.task.project_id is not None else (existing.project_id if existing else project_id)
            _upsert_task(
                conn,
                task_id=task_id,
                room_id=room_id or (existing.room_id if existing else ""),
                title=event.task.title if event.task.title else (existing.title if existing else "Untitled task"),
                summary=task_summary,
                project_id=task_project_id or "",
                task_type=event.task.type if event.task.type in TASK_TYPES else (existing.type if existing else "feature"),
                priority=event.task.priority if event.task.priority in TASK_PRIORITIES else (existing.priority if existing else "normal"),
                status=event.task.status if event.task.status in TASK_STATUSES else (existing.status if existing else "open"),
                owner_kind=event.task.owner_kind if event.task.owner_kind in OWNER_KINDS else (existing.owner_kind if existing else "unassigned"),
                owner_id=event.task.owner_id if event.task.owner_id is not None else (existing.owner_id if existing else None),
                source_kind=event.source.source_kind,
                source_ref=event.source.source_ref,
                created_by_guardian=(existing.created_by_guardian if existing else event.subsystem),
                created_by_subsystem=(existing.created_by_subsystem if existing else event.subsystem),
                updated_by_subsystem=event.subsystem,
                approval_required=event.task.approval_required,
                approval_state=event.task.approval_state,
                confidence=event.task.confidence,
                parent_task_id=event.task.parent_task_id,
                depends_on=event.task.depends_on,
                tags=event.task.tags,
                source_excerpt=(event.content or task_summary)[:280],
                chat_task_id=existing.chat_task_id if existing else None,
            )
            for related_task_id in event.task.related_task_ids:
                _add_link(conn, task_id=task_id, related_task_id=related_task_id, link_type="related")
            for dependency_id in event.task.depends_on:
                _add_link(conn, task_id=task_id, related_task_id=dependency_id, link_type="dependency")
            if event.task.approval_required or event.event_type.startswith("approval."):
                _record_approval(
                    conn,
                    task_id=task_id,
                    requester_id=event.actor_id,
                    approver_id=event.payload.get("approver_id"),
                    approval_method=str(event.payload.get("approval_method") or "guardian_spine"),
                    state=event.task.approval_state if event.task.approval_state in APPROVAL_STATES else ("required" if event.task.approval_required else "not_required"),
                    scope=list(event.payload.get("scope") or []),
                    expires_at=event.payload.get("expires_at"),
                )
            if event.event_type == "handoff.created" or event.payload.get("handoff_summary"):
                _record_handoff(
                    conn,
                    task_id=task_id,
                    room_id=room_id or (existing.room_id if existing else ""),
                    summary=str(event.payload.get("handoff_summary") or event.content or task_summary),
                    source_ref=event.source.source_ref,
                )
            created_task_id = task_id

        payload = {
            "content": event.content,
            "payload": event.payload,
            "task_id": created_task_id,
            "project_id": project_id,
        }
        _emit_event(
            conn,
            event_type=event.event_type,
            room_id=room_id,
            subsystem=event.subsystem,
            actor_kind=event.actor_kind,
            actor_id=event.actor_id,
            source_kind=event.source.source_kind,
            source_ref=event.source.source_ref,
            correlation_id=correlation_id,
            payload=payload,
            task_id=created_task_id,
            project_id=project_id,
        )
        if project_id:
            _emit_project_event(
                conn,
                project_id=project_id,
                event_type=event.event_type,
                room_id=room_id,
                subsystem=event.subsystem,
                source_kind=event.source.source_kind,
                source_ref=event.source.source_ref,
                payload=payload,
            )
        conn.commit()

    if created_task_id:
        task = _render_task(created_task_id)
        if task:
            if session is not None and room_id:
                chat_task_id = _sync_chat_task_mirror(session, spine_task=task)
                if chat_task_id and chat_task_id != task.chat_task_id:
                    with _conn() as conn:
                        _upsert_task(
                            conn,
                            task_id=task.task_id,
                            room_id=task.room_id,
                            title=task.title,
                            summary=task.summary or "",
                            project_id=task.project_id or "",
                            task_type=task.type,
                            priority=task.priority,
                            status=task.status,
                            owner_kind=task.owner_kind,
                            owner_id=task.owner_id,
                            source_kind=task.source_kind,
                            source_ref=task.source_ref,
                            created_by_guardian=task.created_by_guardian,
                            created_by_subsystem=task.created_by_subsystem or task.created_by_guardian,
                            updated_by_subsystem=event.subsystem,
                            approval_required=bool(task.approval_required),
                            approval_state=task.approval_state,
                            confidence=task.confidence,
                            parent_task_id=task.parent_task_id,
                            depends_on=_json_loads_list(task.depends_on_json),
                            tags=_json_loads_list(task.tags_json),
                            source_excerpt=task.source_excerpt or "",
                            chat_task_id=chat_task_id,
                        )
                        conn.commit()
                        task = _render_task(created_task_id)
            if task:
                _write_task_markdown(task, room_name=room_id)
                if task.project_id:
                    _write_project_mirror(project_id=task.project_id, room_name_map={task.room_id: room_id or task.room_id})
                _write_handoff(task, event.event_type, event.content or task.summary or task.title)

    return {"task_id": created_task_id, "project_id": project_id, "event_type": event.event_type}


def ingest_memory_signal(
    *,
    room_id: str | None,
    source_ref: str,
    signal_text: str,
    project: SpineProjectInput | None = None,
    task: SpineTaskInput | None = None,
    reopen_task_id: str | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    memory_task = task
    if reopen_task_id and memory_task is None:
        existing = _render_task(reopen_task_id)
        if existing:
            memory_task = SpineTaskInput(
                task_id=reopen_task_id,
                title=existing.title,
                summary=signal_text,
                project_id=existing.project_id,
                type=existing.type,
                priority=existing.priority,
                status="open" if existing.status == "done" else existing.status,
                owner_kind=existing.owner_kind,
                owner_id=existing.owner_id,
                parent_task_id=existing.parent_task_id,
                depends_on=_json_loads_list(existing.depends_on_json),
                related_task_ids=[],
                approval_required=bool(existing.approval_required),
                approval_state=existing.approval_state,
                confidence=max(existing.confidence, 0.9),
                tags=sorted(set(_json_loads_list(existing.tags_json)) | {"memory"}),
            )
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type="memory.signal",
            subsystem="memory",
            actor_kind="system",
            room_id=room_id,
            source=SpineSourceReference(source_kind="memory", source_ref=source_ref, room_id=room_id),
            content=signal_text,
            project=project,
            task=memory_task,
            payload={"reopen_task_id": reopen_task_id} if reopen_task_id else {},
        ),
        session=session,
    )


def ingest_executive_decision(
    *,
    room_id: str | None,
    source_ref: str,
    decision_summary: str,
    task: SpineTaskInput | None = None,
    project: SpineProjectInput | None = None,
    metadata: dict[str, Any] | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type="executive.decision",
            subsystem="executive",
            actor_kind="system",
            room_id=room_id,
            source=SpineSourceReference(source_kind="executive", source_ref=source_ref, room_id=room_id),
            content=decision_summary,
            project=project,
            task=task,
            payload=metadata or {},
        ),
        session=session,
    )


def get_spine_task_by_chat_task_id(*, chat_task_id: str) -> SpineTask | None:
    _init_store()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM guardian_spine_tasks WHERE chat_task_id = ? LIMIT 1",
            (chat_task_id,),
        ).fetchone()
    return SpineTask(**dict(row)) if row else None


def emit_task_master_action(
    *,
    session: Session | None,
    task: ChatTask,
    action: str,
    actor_id: str | None = None,
    summary: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing = get_spine_task_by_chat_task_id(chat_task_id=str(task.id))
    event_map = {
        "queued": ("task.queued", "queued"),
        "assigned": ("task.assigned", "in_progress" if task.assigned_to else "open"),
        "status_changed": ("task.status.changed", task.status.value if hasattr(task.status, "value") else str(task.status)),
        "blocked": ("task.blocked", "blocked"),
        "completed": ("task.completed", "done"),
        "reopened": ("task.reopened", "open"),
        "canceled": ("task.canceled", "canceled"),
    }
    event_type, status = event_map.get(action, ("task.updated", task.status.value if hasattr(task.status, "value") else str(task.status)))
    related_task_ids = []
    if existing:
        related_task_ids = [link.related_task_id for link in list_spine_links(task_id=existing.task_id, link_type="related")]
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type=event_type,
            subsystem="task_master",
            actor_kind="human",
            actor_id=actor_id or str(task.created_by),
            room_id=str(task.room_id),
            source=SpineSourceReference(source_kind="room_task", source_ref=f"chat-task-{task.id}", room_id=str(task.room_id)),
            content=summary or task.description or task.title,
            task=SpineTaskInput(
                task_id=existing.task_id if existing else None,
                title=task.title,
                summary=task.description or summary or task.title,
                project_id=existing.project_id if existing else None,
                type=existing.type if existing else "feature",
                priority=existing.priority if existing else "normal",
                status=status,
                owner_kind="human" if task.assigned_to else (existing.owner_kind if existing else "unassigned"),
                owner_id=str(task.assigned_to) if task.assigned_to else (existing.owner_id if existing else None),
                parent_task_id=existing.parent_task_id if existing else None,
                depends_on=_json_loads_list(existing.depends_on_json) if existing else [],
                related_task_ids=related_task_ids,
                approval_required=bool(existing.approval_required) if existing else False,
                approval_state=existing.approval_state if existing else "not_required",
                confidence=existing.confidence if existing else 1.0,
                tags=_json_loads_list(existing.tags_json) if existing else ["room-task"],
            ),
            payload={"action": action, **(payload or {})},
        ),
        session=session,
    )


def emit_approval_event(
    *,
    room_id: str | None,
    source_ref: str,
    event_type: str,
    tool_name: str,
    confirm_id: str,
    user_id: str | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = dict(payload or {})
    target = _find_approval_target_task(room_id=room_id, tool_name=tool_name, event_type=event_type)
    task_input: SpineTaskInput | None = None
    if target:
        next_status = target.status
        next_approval_state = target.approval_state
        if event_type == "approval.required":
            next_status = "awaiting_approval"
            next_approval_state = "required"
        elif event_type == "approval.granted":
            next_status = "in_progress" if target.status == "awaiting_approval" else target.status
            next_approval_state = "granted"
            data.setdefault("resume_ready", True)
        elif event_type in {"approval.discarded", "approval.denied"}:
            next_status = "blocked"
            next_approval_state = "denied"
        task_input = SpineTaskInput(
            task_id=target.task_id,
            title=target.title,
            summary=target.summary or f"{event_type} for {tool_name}",
            project_id=target.project_id,
            type=target.type,
            priority=target.priority,
            status=next_status,
            owner_kind=target.owner_kind,
            owner_id=target.owner_id,
            parent_task_id=target.parent_task_id,
            depends_on=_json_loads_list(target.depends_on_json),
            related_task_ids=[],
            approval_required=event_type == "approval.required" or bool(target.approval_required),
            approval_state=next_approval_state,
            confidence=target.confidence,
            tags=_json_loads_list(target.tags_json),
        )
        data.setdefault("task_id", target.task_id)
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type=event_type,
            subsystem="approval",
            actor_kind="system",
            actor_id=user_id,
            room_id=room_id,
            source=SpineSourceReference(source_kind="approval", source_ref=source_ref, room_id=room_id),
            content=f"{event_type} for {tool_name}",
            task=task_input,
            payload={"tool_name": tool_name, "confirm_id": confirm_id, **data},
        ),
        session=None,
    )


def emit_breakglass_event(
    *,
    room_id: str,
    user_id: str,
    event_type: str,
    confirm_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_ref = confirm_id or f"{event_type}:{user_id}:{room_id}"
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type=event_type,
            subsystem="approval",
            actor_kind="human",
            actor_id=user_id,
            room_id=room_id,
            source=SpineSourceReference(source_kind="breakglass", source_ref=source_ref, room_id=room_id),
            content=event_type,
            payload=payload or {},
        ),
        session=None,
    )


def ingest_task_guardian_result(
    *,
    room_id: str,
    guardian_task_id: str,
    task_name: str,
    tool_name: str,
    verification_status: str,
    summary: str,
    recommended_next_action: str | None,
    output_excerpt: str,
    user_id: str | None,
    escalated: bool = False,
) -> dict[str, Any]:
    status_map = {
        "verified": "done",
        "blocked": "blocked",
        "failed": "blocked",
        "unverified": "in_progress",
    }
    event_type = {
        "verified": "task.completed",
        "blocked": "task.blocked",
        "failed": "task.blocked",
        "unverified": "task.progress",
    }.get(verification_status, "task.progress")
    result = ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type=event_type,
            subsystem="task_guardian",
            actor_kind="system",
            actor_id=user_id,
            room_id=room_id,
            source=SpineSourceReference(source_kind="task_guardian", source_ref=f"guardian-task-{guardian_task_id}", room_id=room_id),
            content=summary,
            task=SpineTaskInput(
                title=f"Task Guardian: {task_name}",
                summary=summary,
                type="maintenance",
                priority="normal",
                status=status_map.get(verification_status, "in_progress"),
                owner_kind="sparkbot",
                owner_id="sparkbot",
                tags=["task-guardian", tool_name],
            ),
            payload={
                "guardian_task_id": guardian_task_id,
                "tool_name": tool_name,
                "verification_status": verification_status,
                "recommended_next_action": recommended_next_action,
                "output_excerpt": output_excerpt[:500],
                "escalated": escalated,
                "handoff_summary": recommended_next_action if escalated else None,
            },
        ),
        session=None,
    )
    return result


def emit_room_lifecycle_event(
    *,
    room_id: str,
    actor_id: str,
    event_type: str,
    room_name: str,
    description: str | None = None,
) -> dict[str, Any]:
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type=event_type,
            subsystem="room_lifecycle",
            actor_kind="human",
            actor_id=actor_id,
            room_id=room_id,
            source=SpineSourceReference(source_kind="room", source_ref=f"room-{room_id}", room_id=room_id),
            content=description or room_name,
            payload={"room_name": room_name, "description": description},
        ),
        session=None,
    )


def emit_project_lifecycle_event(
    *,
    room_id: str | None,
    actor_id: str | None,
    event_type: str,
    project: SpineProjectInput,
    payload: dict[str, Any] | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type=event_type,
            subsystem="project_lifecycle",
            actor_kind="human" if actor_id else "system",
            actor_id=actor_id,
            room_id=room_id or project.room_id,
            source=SpineSourceReference(
                source_kind="project",
                source_ref=project.project_id,
                room_id=room_id or project.room_id,
            ),
            content=project.summary or project.display_name,
            project=project,
            payload=payload or {},
        ),
        session=session,
    )


def emit_handoff_event(
    *,
    room_id: str,
    task_id: str,
    summary: str,
    source_ref: str,
    subsystem: str = "handoff",
    actor_id: str | None = None,
    session: Session | None = None,
) -> dict[str, Any]:
    task = get_spine_task(task_id=task_id)
    if not task:
        return {}
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type="handoff.created",
            subsystem=subsystem,
            actor_kind="human" if actor_id else "system",
            actor_id=actor_id,
            room_id=room_id,
            source=SpineSourceReference(source_kind="handoff", source_ref=source_ref, room_id=room_id),
            content=summary,
            task=SpineTaskInput(
                task_id=task.task_id,
                title=task.title,
                summary=summary,
                project_id=task.project_id,
                type=task.type,
                priority=task.priority,
                status=task.status,
                owner_kind=task.owner_kind,
                owner_id=task.owner_id,
                parent_task_id=task.parent_task_id,
                depends_on=_json_loads_list(task.depends_on_json),
                related_task_ids=[],
                approval_required=bool(task.approval_required),
                approval_state=task.approval_state,
                confidence=task.confidence,
                tags=_json_loads_list(task.tags_json),
            ),
            payload={"handoff_summary": summary},
        ),
        session=session,
    )


def emit_meeting_output_event(
    *,
    room_id: str,
    actor_id: str | None,
    artifact_type: str,
    artifact_id: str,
    content_markdown: str,
    session: Session | None = None,
) -> dict[str, Any]:
    event_type = {
        "notes": "meeting.summary.created",
        "decisions": "meeting.decisions.created",
        "action_items": "meeting.action_items.created",
    }.get(artifact_type, "meeting.output.created")
    task_input: SpineTaskInput | None = None
    cleaned_lines = [line.strip(" -*\t") for line in (content_markdown or "").splitlines() if line.strip()]
    if artifact_type in {"action_items", "decisions"} and cleaned_lines:
        title = _first_sentence(cleaned_lines[0]) or cleaned_lines[0]
        task_input = SpineTaskInput(
            title=title[:160],
            summary=content_markdown[:1200],
            type="meeting_followup",
            priority="normal",
            status="open",
            owner_kind="unassigned",
            tags=["meeting", artifact_type],
        )
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type=event_type,
            subsystem="meeting",
            actor_kind="human" if actor_id else "system",
            actor_id=actor_id,
            room_id=room_id,
            source=SpineSourceReference(
                source_kind="meeting",
                source_ref=f"meeting-artifact-{artifact_id}",
                room_id=room_id,
            ),
            content=content_markdown[:1200],
            task=task_input,
            payload={"artifact_type": artifact_type, "artifact_id": artifact_id},
        ),
        session=session,
    )


def emit_worker_status_event(
    *,
    room_id: str,
    actor_id: str | None,
    worker_name: str,
    source_ref: str,
    status_text: str,
    session: Session | None = None,
) -> dict[str, Any]:
    return ingest_subsystem_event(
        event=SpineSubsystemEvent(
            event_type="worker.status",
            subsystem="worker",
            actor_kind="agent",
            actor_id=actor_id or worker_name,
            room_id=room_id,
            source=SpineSourceReference(source_kind="worker", source_ref=source_ref, room_id=room_id),
            content=status_text,
            payload={"worker_name": worker_name},
        ),
        session=session,
    )
