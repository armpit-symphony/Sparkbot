from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlmodel import Session

from app.crud import create_audit_log, create_chat_message
from app.models import ChatRoom, ChatUser, UserType
from app.services.guardian.executive import exec_with_guard
from app.services.guardian.memory import remember_tool_event
from app.services.guardian.policy import decide_tool_use


TASK_GUARDIAN_ENABLED = os.getenv("SPARKBOT_TASK_GUARDIAN_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
TASK_GUARDIAN_POLL_SECONDS = max(
    15,
    min(int(os.getenv("SPARKBOT_TASK_GUARDIAN_POLL_SECONDS", "60")), 3600),
)
TASK_GUARDIAN_MAX_OUTPUT = max(
    300,
    min(int(os.getenv("SPARKBOT_TASK_GUARDIAN_MAX_OUTPUT", "2000")), 12000),
)

ALLOWED_TASK_TOOLS = {
    "web_search",
    "github_list_prs",
    "github_get_ci_status",
    "slack_get_channel_history",
    "notion_search",
    "confluence_search",
    "gmail_fetch_inbox",
    "gmail_search",
    "drive_search",
    "calendar_list_events",
    "server_read_command",
    "ssh_read_command",
    "list_tasks",
    "list_reminders",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guardian_tasks (
  id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  tool_args_json TEXT NOT NULL,
  schedule TEXT NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_run_at TEXT,
  next_run_at TEXT,
  last_status TEXT,
  last_message TEXT
);

CREATE TABLE IF NOT EXISTS guardian_task_runs (
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  room_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL,
  message TEXT NOT NULL,
  output_excerpt TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(task_id) REFERENCES guardian_tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_guardian_tasks_room_id ON guardian_tasks(room_id);
CREATE INDEX IF NOT EXISTS idx_guardian_tasks_next_run_at ON guardian_tasks(next_run_at);
CREATE INDEX IF NOT EXISTS idx_guardian_task_runs_task_id ON guardian_task_runs(task_id);
"""


@dataclass(frozen=True)
class GuardianTask:
    id: str
    room_id: str
    user_id: str
    name: str
    tool_name: str
    tool_args_json: str
    schedule: str
    enabled: int
    created_at: str
    updated_at: str
    last_run_at: Optional[str]
    next_run_at: Optional[str]
    last_status: Optional[str]
    last_message: Optional[str]


@dataclass(frozen=True)
class GuardianTaskRun:
    run_id: str
    task_id: str
    room_id: str
    user_id: str
    status: str
    message: str
    output_excerpt: str
    created_at: str


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
    path = _data_root() / "task_guardian.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_store() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def _parse_schedule(schedule: str) -> tuple[str, str]:
    if ":" not in schedule:
        raise ValueError("schedule must be every:<seconds> or at:<ISO-8601 datetime>")
    kind, raw_value = schedule.split(":", 1)
    kind = kind.strip().lower()
    value = raw_value.strip()
    if kind not in {"every", "at"}:
        raise ValueError("schedule must start with every: or at:")
    return kind, value


def _next_run_at(schedule: str, *, base: Optional[datetime] = None) -> str:
    base = base or _now()
    kind, value = _parse_schedule(schedule)
    if kind == "every":
        seconds = max(60, int(value))
        return (base + timedelta(seconds=seconds)).isoformat()
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _safe_excerpt(text: str) -> str:
    text = (text or "").strip()
    if len(text) <= TASK_GUARDIAN_MAX_OUTPUT:
        return text
    return text[:TASK_GUARDIAN_MAX_OUTPUT] + "\n...[truncated]"


def _allowed_task_tool(tool_name: str) -> bool:
    return tool_name in ALLOWED_TASK_TOOLS


def schedule_task(
    *,
    name: str,
    tool_name: str,
    tool_args: dict[str, Any],
    schedule: str,
    room_id: str,
    user_id: str,
) -> dict[str, Any]:
    if not _allowed_task_tool(tool_name):
        raise ValueError(
            "Task Guardian only allows approved read-only tools. "
            f"Allowed: {', '.join(sorted(ALLOWED_TASK_TOOLS))}"
        )
    next_run_at = _next_run_at(schedule)
    task_id = str(uuid.uuid4())
    now = _now_iso()
    payload = json.dumps(tool_args or {}, ensure_ascii=False)
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO guardian_tasks
            (id, room_id, user_id, name, tool_name, tool_args_json, schedule, enabled, created_at, updated_at, next_run_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (task_id, room_id, user_id, name.strip(), tool_name, payload, schedule.strip(), now, now, next_run_at),
        )
    return {
        "id": task_id,
        "name": name.strip(),
        "tool_name": tool_name,
        "schedule": schedule.strip(),
        "next_run_at": next_run_at,
    }


def list_tasks(*, room_id: str, limit: int = 25) -> list[GuardianTask]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM guardian_tasks
            WHERE room_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (room_id, max(1, min(limit, 100))),
        ).fetchall()
    return [GuardianTask(**dict(row)) for row in rows]


def list_runs(*, room_id: str, limit: int = 25) -> list[GuardianTaskRun]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM guardian_task_runs
            WHERE room_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (room_id, max(1, min(limit, 100))),
        ).fetchall()
    return [GuardianTaskRun(**dict(row)) for row in rows]


def get_task(task_id: str) -> Optional[GuardianTask]:
    _init_store()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM guardian_tasks WHERE id = ?", (task_id,)).fetchone()
    if not row:
        return None
    return GuardianTask(**dict(row))


def set_task_enabled(task_id: str, enabled: bool) -> bool:
    _init_store()
    with _conn() as conn:
        cursor = conn.execute(
            "UPDATE guardian_tasks SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if enabled else 0, _now_iso(), task_id),
        )
    return cursor.rowcount > 0


def _record_run(
    *,
    task_id: str,
    room_id: str,
    user_id: str,
    status: str,
    message: str,
    output_excerpt: str,
) -> str:
    _init_store()
    run_id = str(uuid.uuid4())
    now = _now_iso()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO guardian_task_runs
            (run_id, task_id, room_id, user_id, status, message, output_excerpt, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (run_id, task_id, room_id, user_id, status, message[:400], output_excerpt[:TASK_GUARDIAN_MAX_OUTPUT], now),
        )
        conn.execute(
            """
            UPDATE guardian_tasks
            SET last_run_at = ?, updated_at = ?, last_status = ?, last_message = ?
            WHERE id = ?
            """,
            (now, now, status, message[:400], task_id),
        )
    return run_id


def _set_followup_schedule(task: GuardianTask) -> None:
    kind, _ = _parse_schedule(task.schedule)
    next_value = None if kind == "at" else _next_run_at(task.schedule)
    enabled = 0 if kind == "at" else task.enabled
    with _conn() as conn:
        conn.execute(
            "UPDATE guardian_tasks SET next_run_at = ?, enabled = ?, updated_at = ? WHERE id = ?",
            (next_value, enabled, _now_iso(), task.id),
        )


def _find_or_create_bot_user(session: Session) -> ChatUser:
    bot_user = session.exec(select(ChatUser).where(ChatUser.username == "sparkbot")).scalar_one_or_none()
    if bot_user:
        return bot_user
    bot_user = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
    session.add(bot_user)
    session.commit()
    session.refresh(bot_user)
    return bot_user


async def _broadcast_task_message(room_id: str, message_id: str, content: str) -> None:
    try:
        from app.api.routes.chat.websocket import ws_manager

        await ws_manager.broadcast(
            room_id,
            {
                "type": "message",
                "payload": {
                    "id": message_id,
                    "room_id": room_id,
                    "content": content,
                    "sender_type": "BOT",
                    "sender": {"username": "sparkbot"},
                    "created_at": _now_iso(),
                },
            },
        )
    except Exception:
        pass


async def _execute_internal_tool(task: GuardianTask, session: Session) -> tuple[str, str]:
    from app.api.routes.chat.tools import execute_tool

    room = session.get(ChatRoom, uuid.UUID(task.room_id))
    execution_allowed = bool(room.execution_allowed) if room else False
    tool_args = json.loads(task.tool_args_json or "{}")
    decision = decide_tool_use(
        task.tool_name,
        tool_args if isinstance(tool_args, dict) else {},
        room_execution_allowed=execution_allowed,
    )
    if decision.action == "deny":
        return "denied", decision.reason
    if decision.action == "confirm":
        return "denied", "Scheduled tasks cannot run confirm-required tools."

    def perform() -> Any:
        return execute_tool(
            task.tool_name,
            tool_args if isinstance(tool_args, dict) else {},
            user_id=task.user_id,
            session=session,
            room_id=task.room_id,
        )

    result = await exec_with_guard(
        tool_name=task.tool_name,
        action_type=decision.action_type,
        expected_outcome=f"Task Guardian run for {task.name}",
        perform_fn=perform,
        metadata={"task_id": task.id, "room_id": task.room_id, "user_id": task.user_id},
    )
    return "success", str(result)


async def run_task_once(task: GuardianTask, session: Session) -> dict[str, Any]:
    status, output = await _execute_internal_tool(task, session)
    excerpt = _safe_excerpt(output)
    message = f"{status.upper()}: {task.name} via {task.tool_name}"
    run_id = _record_run(
        task_id=task.id,
        room_id=task.room_id,
        user_id=task.user_id,
        status=status,
        message=message,
        output_excerpt=excerpt,
    )
    _set_followup_schedule(task)

    create_audit_log(
        session=session,
        tool_name="guardian_task_run",
        tool_input=json.dumps(
            {
                "task_id": task.id,
                "task_name": task.name,
                "tool_name": task.tool_name,
            }
        ),
        tool_result=json.dumps({"status": status, "output_excerpt": excerpt[:600]}),
        user_id=uuid.UUID(task.user_id),
        room_id=uuid.UUID(task.room_id),
        agent_name="task_guardian",
    )
    try:
        remember_tool_event(
            user_id=task.user_id,
            room_id=task.room_id,
            tool_name="guardian_task_run",
            args={"task_id": task.id, "tool_name": task.tool_name},
            result=f"{status}: {excerpt}",
        )
    except Exception:
        pass

    bot_user = _find_or_create_bot_user(session)
    content = (
        f"🛡️ Scheduled task `{task.name}` ran via `{task.tool_name}`.\n\n"
        f"{excerpt}"
    )
    msg = create_chat_message(
        session=session,
        room_id=uuid.UUID(task.room_id),
        sender_id=bot_user.id,
        content=content,
        sender_type="BOT",
    )
    await _broadcast_task_message(task.room_id, str(msg.id), content)

    return {"run_id": run_id, "status": status, "output": excerpt}


def due_tasks(limit: int = 10) -> list[GuardianTask]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM guardian_tasks
            WHERE enabled = 1
              AND next_run_at IS NOT NULL
              AND next_run_at <= ?
            ORDER BY next_run_at ASC
            LIMIT ?
            """,
            (_now_iso(), max(1, min(limit, 25))),
        ).fetchall()
    return [GuardianTask(**dict(row)) for row in rows]


async def task_guardian_scheduler(get_db_session: Callable[[], Any]) -> None:
    if not TASK_GUARDIAN_ENABLED:
        return
    _init_store()
    while True:
        try:
            await asyncio.sleep(TASK_GUARDIAN_POLL_SECONDS)
            for task in due_tasks():
                db = next(get_db_session())
                try:
                    await run_task_once(task, db)
                finally:
                    db.close()
        except asyncio.CancelledError:
            return
        except Exception:
            await asyncio.sleep(5)
