"""
Sparkbot skill: time_tracking

Track time spent on projects and tasks. Start/stop timers, log sessions manually,
and generate reports by project or date range.

Tools:
  time_start(project, task="")          — start a timer
  time_stop(note="")                    — stop the running timer and save the session
  time_log(project, minutes, task="", date="") — manually log time
  time_report(project="", days=7)       — report total time by project
  time_status()                         — show currently running timer

Storage: data/timetracking/time.db
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _db_path() -> Path:
    root = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    base = Path(root).expanduser() if root else Path(__file__).resolve().parents[1] / "data"
    d = base / "timetracking"
    d.mkdir(parents=True, exist_ok=True)
    return d / "time.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS time_sessions (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL DEFAULT '',
            project     TEXT NOT NULL,
            task        TEXT NOT NULL DEFAULT '',
            started_at  TEXT,
            stopped_at  TEXT,
            minutes     REAL,
            note        TEXT NOT NULL DEFAULT '',
            manual      INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ts_user ON time_sessions(user_id, project);
    """)
    c.commit()
    return c


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _time_start_sync(args: dict, user_id: str) -> str:
    project = (args.get("project") or "").strip()
    task = (args.get("task") or "").strip()
    if not project:
        return "Error: project name is required."
    conn = _conn()
    # Check for already-running timer
    running = conn.execute(
        "SELECT id, project, started_at FROM time_sessions WHERE user_id=? AND stopped_at IS NULL AND manual=0",
        (user_id,),
    ).fetchone()
    if running:
        return (
            f"Timer already running on **{running['project']}** since {running['started_at'][:16]}. "
            "Stop it first with `time_stop`."
        )
    sid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO time_sessions(id,user_id,project,task,started_at,manual) VALUES(?,?,?,?,?,0)",
        (sid, user_id, project, task, _now_iso()),
    )
    conn.commit()
    label = f" — {task}" if task else ""
    return f"⏱ Timer started: **{project}**{label}"


def _time_stop_sync(args: dict, user_id: str) -> str:
    note = (args.get("note") or "").strip()
    conn = _conn()
    running = conn.execute(
        "SELECT id, project, task, started_at FROM time_sessions WHERE user_id=? AND stopped_at IS NULL AND manual=0",
        (user_id,),
    ).fetchone()
    if not running:
        return "No timer is currently running."
    stopped = _now_iso()
    started_dt = datetime.fromisoformat(running["started_at"].replace("Z", "+00:00"))
    stopped_dt = datetime.fromisoformat(stopped.replace("Z", "+00:00"))
    minutes = (stopped_dt - started_dt).total_seconds() / 60
    conn.execute(
        "UPDATE time_sessions SET stopped_at=?, minutes=?, note=? WHERE id=?",
        (stopped, minutes, note, running["id"]),
    )
    conn.commit()
    h, m = divmod(int(minutes), 60)
    duration = f"{h}h {m}m" if h else f"{m}m"
    return f"⏹ Timer stopped: **{running['project']}** — {duration} logged."


def _time_log_sync(args: dict, user_id: str) -> str:
    project = (args.get("project") or "").strip()
    minutes_raw = args.get("minutes")
    task = (args.get("task") or "").strip()
    note = (args.get("note") or "").strip()
    date_str = (args.get("date") or "").strip()
    if not project or minutes_raw is None:
        return "Error: project and minutes are required."
    try:
        minutes = float(minutes_raw)
    except (TypeError, ValueError):
        return "Error: minutes must be a number."
    ts = _now_iso() if not date_str else f"{date_str}T00:00:00+00:00"
    conn = _conn()
    conn.execute(
        "INSERT INTO time_sessions(id,user_id,project,task,started_at,stopped_at,minutes,note,manual) VALUES(?,?,?,?,?,?,?,?,1)",
        (str(uuid.uuid4()), user_id, project, task, ts, ts, minutes, note),
    )
    conn.commit()
    h, m = divmod(int(minutes), 60)
    return f"✅ Logged {h}h {m}m on **{project}**" + (f" — {task}" if task else "")


def _time_report_sync(args: dict, user_id: str) -> str:
    project_filter = (args.get("project") or "").strip()
    days = max(1, min(int(args.get("days") or 7), 365))
    conn = _conn()
    cutoff = f"datetime('now', '-{days} days')"
    if project_filter:
        rows = conn.execute(
            f"SELECT project, task, minutes, started_at, note FROM time_sessions "
            f"WHERE user_id=? AND project LIKE ? AND minutes IS NOT NULL AND started_at >= {cutoff} "
            f"ORDER BY started_at DESC",
            (user_id, f"%{project_filter}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT project, task, minutes, started_at, note FROM time_sessions "
            f"WHERE user_id=? AND minutes IS NOT NULL AND started_at >= {cutoff} "
            f"ORDER BY started_at DESC",
            (user_id,),
        ).fetchall()
    if not rows:
        scope = f"'{project_filter}'" if project_filter else "any project"
        return f"No time logged for {scope} in the last {days} days."
    totals: dict[str, float] = {}
    for r in rows:
        totals[r["project"]] = totals.get(r["project"], 0.0) + (r["minutes"] or 0)
    lines = [f"**Time report — last {days} days**", ""]
    for proj, mins in sorted(totals.items(), key=lambda x: -x[1]):
        h, m = divmod(int(mins), 60)
        lines.append(f"• **{proj}**: {h}h {m}m")
    grand = sum(totals.values())
    gh, gm = divmod(int(grand), 60)
    lines += ["", f"**Total: {gh}h {gm}m**"]
    return "\n".join(lines)


def _time_status_sync(args: dict, user_id: str) -> str:
    conn = _conn()
    running = conn.execute(
        "SELECT project, task, started_at FROM time_sessions WHERE user_id=? AND stopped_at IS NULL AND manual=0",
        (user_id,),
    ).fetchone()
    if not running:
        return "No timer running."
    started_dt = datetime.fromisoformat(running["started_at"].replace("Z", "+00:00"))
    elapsed = (datetime.now(timezone.utc) - started_dt).total_seconds() / 60
    h, m = divmod(int(elapsed), 60)
    label = f" — {running['task']}" if running["task"] else ""
    return f"⏱ **{running['project']}**{label} running for {h}h {m}m"


DEFINITIONS = [
    {"type": "function", "function": {"name": "time_start", "description": "Start a timer for a project/task. Only one timer can run at a time.", "parameters": {"type": "object", "properties": {"project": {"type": "string"}, "task": {"type": "string", "description": "Optional task description"}}, "required": ["project"]}}},
    {"type": "function", "function": {"name": "time_stop", "description": "Stop the running timer and save the session.", "parameters": {"type": "object", "properties": {"note": {"type": "string", "description": "Optional note about what was accomplished"}}, "required": []}}},
    {"type": "function", "function": {"name": "time_log", "description": "Manually log time for a project without using start/stop.", "parameters": {"type": "object", "properties": {"project": {"type": "string"}, "minutes": {"type": "number"}, "task": {"type": "string"}, "note": {"type": "string"}, "date": {"type": "string", "description": "YYYY-MM-DD, defaults to today"}}, "required": ["project", "minutes"]}}},
    {"type": "function", "function": {"name": "time_report", "description": "Show time logged by project for the last N days.", "parameters": {"type": "object", "properties": {"project": {"type": "string", "description": "Optional project filter"}, "days": {"type": "integer", "description": "Look-back window in days (default 7)"}}, "required": []}}},
    {"type": "function", "function": {"name": "time_status", "description": "Show the currently running timer if any.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]

POLICIES = {
    "time_start":  {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "time_stop":   {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "time_log":    {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "time_report": {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "time_status": {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
}

_SYNC_FNS = {
    "time_start":  _time_start_sync,
    "time_stop":   _time_stop_sync,
    "time_log":    _time_log_sync,
    "time_report": _time_report_sync,
    "time_status": _time_status_sync,
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["time_start"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await asyncio.to_thread(_time_start_sync, args, user_id or "")


def _make_executor(fn):
    async def _exec(args: dict, *, user_id=None, room_id=None, session=None) -> str:
        return await asyncio.to_thread(fn, args, user_id or "")
    return _exec


def _register_extra(registry) -> None:
    for defn in DEFINITIONS:
        name = defn["function"]["name"]
        if name not in registry.executors:
            registry.definitions.append(defn)
            registry.policies[name] = POLICIES[name]
            registry.executors[name] = _make_executor(_SYNC_FNS[name])
