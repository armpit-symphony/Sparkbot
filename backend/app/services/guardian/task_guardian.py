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
from app.services.guardian.verifier import VerificationResult, verify_task_run


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
TASK_GUARDIAN_DEFAULT_RETRY_BUDGET = max(
    1,
    min(int(os.getenv("SPARKBOT_TASK_GUARDIAN_MAX_RETRIES", "3")), 10),
)
TASK_GUARDIAN_RETRY_BASE_SECONDS = max(
    60,
    min(int(os.getenv("SPARKBOT_TASK_GUARDIAN_RETRY_BASE_SECONDS", "300")), 86400),
)
TASK_GUARDIAN_RETRY_MAX_SECONDS = max(
    TASK_GUARDIAN_RETRY_BASE_SECONDS,
    min(int(os.getenv("SPARKBOT_TASK_GUARDIAN_RETRY_MAX_SECONDS", "3600")), 172800),
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
    "morning_briefing",      # compound read skill: gmail + calendar + reminders digest
}

# Write tools allowed in scheduled context when SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true.
# These require __pre_authorized=True embedded in tool_args at scheduling time,
# which the guardian_schedule_task confirmation modal provides.
WRITE_TASK_TOOLS: frozenset[str] = frozenset({
    "gmail_send",
    "slack_send_message",
    "calendar_create_event",
})

TASK_GUARDIAN_WRITE_ENABLED: bool = (
    os.getenv("SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)

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
  last_message TEXT,
  last_verification_status TEXT,
  last_evidence_json TEXT,
  last_confidence REAL,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  retry_budget INTEGER NOT NULL DEFAULT 3,
  last_blocked_reason TEXT,
  escalated_at TEXT
);

CREATE TABLE IF NOT EXISTS guardian_task_runs (
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  room_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  status TEXT NOT NULL,
  verification_status TEXT,
  confidence REAL,
  message TEXT NOT NULL,
  output_excerpt TEXT NOT NULL,
  evidence_json TEXT,
  recommended_next_action TEXT,
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
    last_verification_status: Optional[str] = None
    last_evidence_json: Optional[str] = None
    last_confidence: Optional[float] = None
    consecutive_failures: Optional[int] = None
    retry_budget: Optional[int] = None
    last_blocked_reason: Optional[str] = None
    escalated_at: Optional[str] = None


@dataclass(frozen=True)
class GuardianTaskRun:
    run_id: str
    task_id: str
    room_id: str
    user_id: str
    status: str
    verification_status: Optional[str]
    confidence: Optional[float]
    message: str
    output_excerpt: str
    evidence_json: Optional[str]
    recommended_next_action: Optional[str]
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
        _ensure_column(conn, "guardian_tasks", "last_verification_status", "TEXT")
        _ensure_column(conn, "guardian_tasks", "last_evidence_json", "TEXT")
        _ensure_column(conn, "guardian_tasks", "last_confidence", "REAL")
        _ensure_column(conn, "guardian_tasks", "consecutive_failures", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(
            conn,
            "guardian_tasks",
            "retry_budget",
            f"INTEGER NOT NULL DEFAULT {TASK_GUARDIAN_DEFAULT_RETRY_BUDGET}",
        )
        _ensure_column(conn, "guardian_tasks", "last_blocked_reason", "TEXT")
        _ensure_column(conn, "guardian_tasks", "escalated_at", "TEXT")
        _ensure_column(conn, "guardian_task_runs", "verification_status", "TEXT")
        _ensure_column(conn, "guardian_task_runs", "confidence", "REAL")
        _ensure_column(conn, "guardian_task_runs", "evidence_json", "TEXT")
        _ensure_column(conn, "guardian_task_runs", "recommended_next_action", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_def: str) -> None:
    existing = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")


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
    if tool_name in ALLOWED_TASK_TOOLS:
        return True
    if TASK_GUARDIAN_WRITE_ENABLED and tool_name in WRITE_TASK_TOOLS:
        return True
    return False


def _is_pre_authorized(tool_args: dict) -> bool:
    """Return True when the task was explicitly pre-authorized at scheduling time."""
    return bool(tool_args.get("__pre_authorized"))


def _strip_meta_keys(tool_args: dict) -> dict:
    """Strip internal __ meta keys before passing args to the actual tool."""
    return {k: v for k, v in tool_args.items() if not k.startswith("__")}


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
        all_allowed = sorted(ALLOWED_TASK_TOOLS | (WRITE_TASK_TOOLS if TASK_GUARDIAN_WRITE_ENABLED else set()))
        raise ValueError(
            f"Task Guardian does not allow '{tool_name}'. "
            f"Allowed tools: {', '.join(all_allowed)}"
        )
    if tool_name in WRITE_TASK_TOOLS:
        if not TASK_GUARDIAN_WRITE_ENABLED:
            raise ValueError(
                f"'{tool_name}' is a write-action tool. "
                "Set SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true to allow scheduled write tasks."
            )
        # Embed pre-authorization so the executor knows this was confirmed at scheduling time.
        tool_args = dict(tool_args or {})
        tool_args["__pre_authorized"] = True
    next_run_at = _next_run_at(schedule)
    task_id = str(uuid.uuid4())
    now = _now_iso()
    payload = json.dumps(tool_args or {}, ensure_ascii=False)
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO guardian_tasks
            (id, room_id, user_id, name, tool_name, tool_args_json, schedule, enabled, created_at, updated_at, next_run_at, consecutive_failures, retry_budget)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, 0, ?)
            """,
            (
                task_id,
                room_id,
                user_id,
                name.strip(),
                tool_name,
                payload,
                schedule.strip(),
                now,
                now,
                next_run_at,
                TASK_GUARDIAN_DEFAULT_RETRY_BUDGET,
            ),
        )
    return {
        "id": task_id,
        "name": name.strip(),
        "tool_name": tool_name,
        "schedule": schedule.strip(),
        "next_run_at": next_run_at,
        "retry_budget": TASK_GUARDIAN_DEFAULT_RETRY_BUDGET,
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
    verification: VerificationResult,
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
            (run_id, task_id, room_id, user_id, status, verification_status, confidence, message, output_excerpt, evidence_json, recommended_next_action, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                task_id,
                room_id,
                user_id,
                status,
                verification.status,
                verification.confidence,
                message[:400],
                output_excerpt[:TASK_GUARDIAN_MAX_OUTPUT],
                json.dumps(verification.evidence, ensure_ascii=False),
                verification.recommended_next_action,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE guardian_tasks
            SET last_run_at = ?, updated_at = ?, last_status = ?, last_message = ?, last_verification_status = ?, last_evidence_json = ?, last_confidence = ?
            WHERE id = ?
            """,
            (
                now,
                now,
                status,
                message[:400],
                verification.status,
                json.dumps(verification.evidence, ensure_ascii=False),
                verification.confidence,
                task_id,
            ),
        )
    return run_id


def _task_failure_count(task: GuardianTask) -> int:
    return max(0, int(task.consecutive_failures or 0))


def _task_retry_budget(task: GuardianTask) -> int:
    return max(1, int(task.retry_budget or TASK_GUARDIAN_DEFAULT_RETRY_BUDGET))


def _retry_delay_seconds(task: GuardianTask, failure_count: int) -> int:
    delay = min(
        TASK_GUARDIAN_RETRY_BASE_SECONDS * (2 ** max(0, failure_count - 1)),
        TASK_GUARDIAN_RETRY_MAX_SECONDS,
    )
    kind, value = _parse_schedule(task.schedule)
    if kind == "every":
        delay = min(delay, max(60, int(value)))
    return max(60, int(delay))


def _apply_followup_state(task: GuardianTask, verification: VerificationResult) -> dict[str, Any]:
    now = _now()
    now_iso = now.isoformat()
    failure_count = _task_failure_count(task)
    retry_budget = _task_retry_budget(task)
    kind, _ = _parse_schedule(task.schedule)
    enabled = int(task.enabled)
    escalated = False
    next_value: Optional[str]
    blocked_reason: Optional[str] = None

    if verification.status == "verified":
        failure_count = 0
        blocked_reason = None
        next_value = None if kind == "at" else _next_run_at(task.schedule, base=now)
        enabled = 0 if kind == "at" else int(task.enabled)
    elif verification.status == "blocked":
        failure_count += 1
        blocked_reason = verification.recommended_next_action or verification.summary
        next_value = None
        enabled = 0
        escalated = True
    else:
        failure_count += 1
        blocked_reason = verification.recommended_next_action or verification.summary
        if failure_count >= retry_budget:
            next_value = None
            enabled = 0
            escalated = True
        else:
            next_value = (now + timedelta(seconds=_retry_delay_seconds(task, failure_count))).isoformat()

    with _conn() as conn:
        conn.execute(
            """
            UPDATE guardian_tasks
            SET next_run_at = ?, enabled = ?, updated_at = ?, consecutive_failures = ?, last_blocked_reason = ?, escalated_at = ?
            WHERE id = ?
            """,
            (
                next_value,
                enabled,
                now_iso,
                failure_count,
                blocked_reason,
                now_iso if escalated else None,
                task.id,
            ),
        )
    return {
        "next_run_at": next_value,
        "enabled": bool(enabled),
        "consecutive_failures": failure_count,
        "retry_budget": retry_budget,
        "escalated": escalated,
        "last_blocked_reason": blocked_reason,
    }


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
    from app.api.routes.chat.llm import mask_tool_result_for_external
    from app.api.routes.chat.tools import execute_tool
    from app.services.guardian.auth import is_operator_user_id

    room = session.get(ChatRoom, uuid.UUID(task.room_id))
    execution_allowed = bool(room.execution_allowed) if room else False
    tool_args = json.loads(task.tool_args_json or "{}")
    decision = decide_tool_use(
        task.tool_name,
        tool_args if isinstance(tool_args, dict) else {},
        room_execution_allowed=execution_allowed,
        is_operator=is_operator_user_id(session, task.user_id),
    )
    if decision.action == "deny":
        return "denied", decision.reason
    if decision.action == "confirm":
        if not _is_pre_authorized(tool_args if isinstance(tool_args, dict) else {}):
            return (
                "denied",
                "Scheduled tasks cannot run confirm-required tools without pre-authorization. "
                "Re-schedule the task via chat to go through the confirmation modal.",
            )
        # Pre-authorized write task — the user confirmed via guardian_schedule_task modal.
    if decision.action in {"privileged", "privileged_reveal"}:
        return (
            "denied",
            "Scheduled tasks cannot use break-glass or vault reveal actions. Run them interactively as an operator instead.",
        )

    clean_args = _strip_meta_keys(tool_args if isinstance(tool_args, dict) else {})

    def perform() -> Any:
        return execute_tool(
            task.tool_name,
            clean_args,
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
    return "success", mask_tool_result_for_external(task.tool_name, clean_args, result)


async def run_task_once(task: GuardianTask, session: Session) -> dict[str, Any]:
    execution_status, output = await _execute_internal_tool(task, session)
    verification = verify_task_run(
        task_name=task.name,
        tool_name=task.tool_name,
        output=output,
        execution_status=execution_status,
    )
    status = verification.status
    excerpt = _safe_excerpt(output)
    message = verification.summary
    run_id = _record_run(
        task_id=task.id,
        room_id=task.room_id,
        user_id=task.user_id,
        status=status,
        verification=verification,
        message=message,
        output_excerpt=excerpt,
    )
    followup = _apply_followup_state(task, verification)

    create_audit_log(
        session=session,
        tool_name="guardian_task_run",
        tool_input=json.dumps(
            {
                "task_id": task.id,
                "task_name": task.name,
                "tool_name": task.tool_name,
                "execution_status": execution_status,
            }
        ),
        tool_result=json.dumps(
            {
                "status": status,
                "verification_status": verification.status,
                "confidence": verification.confidence,
                "output_excerpt": excerpt[:600],
                "evidence": verification.evidence[:3],
            }
        ),
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
            result=f"{status}: {verification.summary} :: {excerpt}",
        )
    except Exception:
        pass

    bot_user = _find_or_create_bot_user(session)
    content = (
        f"🛡️ Scheduled task `{task.name}` finished with status `{status}` via `{task.tool_name}`.\n\n"
        f"{verification.summary}\n\n"
        f"{excerpt}"
    )
    if followup["escalated"]:
        content += (
            f"\n\nTask Guardian paused this job after "
            f"{followup['consecutive_failures']} consecutive non-verified runs."
        )
    elif status != "verified" and followup["next_run_at"]:
        content += (
            f"\n\nRetry {followup['consecutive_failures']}/{followup['retry_budget']} "
            f"scheduled for {followup['next_run_at']}."
        )
    if verification.recommended_next_action:
        content += f"\n\nNext action: {verification.recommended_next_action}"
    msg = create_chat_message(
        session=session,
        room_id=uuid.UUID(task.room_id),
        sender_id=bot_user.id,
        content=content,
        sender_type="BOT",
    )
    await _broadcast_task_message(task.room_id, str(msg.id), content)
    for _bridge_module in (
        "app.services.telegram_bridge",
        "app.services.discord_bridge",
        "app.services.whatsapp_bridge",
    ):
        try:
            import importlib as _il
            await _il.import_module(_bridge_module).send_room_notification(task.room_id, content)
        except Exception:
            pass

    return {
        "run_id": run_id,
        "status": status,
        "execution_status": execution_status,
        "verification_status": verification.status,
        "confidence": verification.confidence,
        "evidence": verification.evidence,
        "recommended_next_action": verification.recommended_next_action,
        "output": excerpt,
        "next_run_at": followup["next_run_at"],
        "enabled": followup["enabled"],
        "consecutive_failures": followup["consecutive_failures"],
        "retry_budget": followup["retry_budget"],
        "escalated": followup["escalated"],
    }


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
