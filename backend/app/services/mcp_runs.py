from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

McpRunStatus = Literal["planned", "awaiting_approval", "ready", "blocked", "completed", "failed"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mcp_runs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  room_id TEXT,
  manifest_id TEXT NOT NULL,
  manifest_name TEXT NOT NULL,
  runtime TEXT NOT NULL,
  policy_tool_name TEXT NOT NULL,
  policy_action TEXT NOT NULL,
  status TEXT NOT NULL,
  approval_required INTEGER NOT NULL DEFAULT 0,
  dry_run_required INTEGER NOT NULL DEFAULT 0,
  can_execute_now INTEGER NOT NULL DEFAULT 0,
  approval_id TEXT,
  approval_requested_at TEXT,
  approved_by TEXT,
  approved_at TEXT,
  denied_by TEXT,
  denied_at TEXT,
  status_message TEXT,
  user_request TEXT NOT NULL,
  next_action TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mcp_runs_user_created ON mcp_runs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_runs_room_created ON mcp_runs(room_id, created_at DESC);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_root() -> Path:
    root = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    if root:
        return Path(root).expanduser()
    app_root = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    if app_root:
        return Path(app_root).expanduser() / "guardian"
    return Path(__file__).resolve().parents[3] / "data" / "guardian"


def _db_path() -> Path:
    path = _data_root() / "mcp_runs.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_store() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)
        _ensure_column(conn, "mcp_runs", "approval_id", "TEXT")
        _ensure_column(conn, "mcp_runs", "approval_requested_at", "TEXT")
        _ensure_column(conn, "mcp_runs", "approved_by", "TEXT")
        _ensure_column(conn, "mcp_runs", "approved_at", "TEXT")
        _ensure_column(conn, "mcp_runs", "denied_by", "TEXT")
        _ensure_column(conn, "mcp_runs", "denied_at", "TEXT")
        _ensure_column(conn, "mcp_runs", "status_message", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, column_def: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column in existing:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")


def _status_for_plan(plan: dict[str, Any]) -> McpRunStatus:
    action = str(plan.get("policy", {}).get("decision", {}).get("action") or "")
    if action == "deny":
        return "blocked"
    if action in {"confirm", "privileged", "privileged_reveal"} or plan.get("approvalRequired"):
        return "awaiting_approval"
    if plan.get("canExecuteNow"):
        return "ready"
    return "planned"


def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
    plan = json.loads(str(row["plan_json"] or "{}"))
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "roomId": row["room_id"],
        "manifestId": row["manifest_id"],
        "manifestName": row["manifest_name"],
        "runtime": row["runtime"],
        "policyToolName": row["policy_tool_name"],
        "policyAction": row["policy_action"],
        "status": row["status"],
        "approvalRequired": bool(row["approval_required"]),
        "dryRunRequired": bool(row["dry_run_required"]),
        "canExecuteNow": bool(row["can_execute_now"]),
        "approvalId": row["approval_id"],
        "approvalRequestedAt": row["approval_requested_at"],
        "approvedBy": row["approved_by"],
        "approvedAt": row["approved_at"],
        "deniedBy": row["denied_by"],
        "deniedAt": row["denied_at"],
        "statusMessage": row["status_message"],
        "userRequest": row["user_request"],
        "nextAction": row["next_action"],
        "plan": plan,
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def create_mcp_run(
    *,
    user_id: str,
    room_id: str | None,
    manifest_id: str,
    user_request: str,
    plan: dict[str, Any],
) -> dict[str, Any]:
    _init_store()
    run_id = str(uuid.uuid4())
    now = _now_iso()
    manifest = plan.get("manifest", {})
    decision = plan.get("policy", {}).get("decision", {})
    status = _status_for_plan(plan)
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO mcp_runs (
              id, user_id, room_id, manifest_id, manifest_name, runtime, policy_tool_name,
              policy_action, status, approval_required, dry_run_required, can_execute_now,
              user_request, next_action, plan_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                user_id,
                room_id,
                manifest_id,
                str(manifest.get("name") or manifest_id),
                str(manifest.get("runtime") or ""),
                str(plan.get("policyToolName") or manifest_id),
                str(decision.get("action") or ""),
                status,
                1 if plan.get("approvalRequired") else 0,
                1 if plan.get("dryRunRequired") else 0,
                1 if plan.get("canExecuteNow") else 0,
                user_request,
                str(plan.get("nextAction") or ""),
                json.dumps(plan, sort_keys=True),
                now,
                now,
            ),
        )
    run = get_mcp_run(run_id, user_id=user_id)
    if run is None:
        raise RuntimeError("MCP run was not persisted")
    return run


def get_mcp_run(run_id: str, *, user_id: str | None = None) -> dict[str, Any] | None:
    _init_store()
    query = "SELECT * FROM mcp_runs WHERE id = ?"
    params: list[Any] = [run_id]
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    with _conn() as conn:
        row = conn.execute(query, params).fetchone()
    return _row_to_run(row) if row else None


def list_mcp_runs(*, user_id: str, room_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    _init_store()
    safe_limit = max(1, min(int(limit), 100))
    query = "SELECT * FROM mcp_runs WHERE user_id = ?"
    params: list[Any] = [user_id]
    if room_id:
        query += " AND room_id = ?"
        params.append(room_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(safe_limit)
    with _conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [_row_to_run(row) for row in rows]


def request_mcp_run_approval(run_id: str, *, user_id: str) -> dict[str, Any] | None:
    _init_store()
    approval_id = str(uuid.uuid4())
    now = _now_iso()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM mcp_runs WHERE id = ? AND user_id = ?",
            (run_id, user_id),
        ).fetchone()
        if not row:
            return None
        if row["status"] == "awaiting_approval":
            return _row_to_run(row)
        if row["status"] not in {"planned", "ready"}:
            raise ValueError(f"Cannot request approval for MCP run in {row['status']} state.")
        conn.execute(
            """
            UPDATE mcp_runs
            SET status = ?, approval_id = ?, approval_requested_at = ?, status_message = ?,
                updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                "awaiting_approval",
                approval_id,
                now,
                "Approval requested. Execution remains disabled until an operator approves and a runner is wired.",
                now,
                run_id,
                user_id,
            ),
        )
    return get_mcp_run(run_id, user_id=user_id)


def approve_mcp_run(run_id: str, *, user_id: str, approver_id: str) -> dict[str, Any] | None:
    _init_store()
    now = _now_iso()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM mcp_runs WHERE id = ? AND user_id = ?",
            (run_id, user_id),
        ).fetchone()
        if not row:
            return None
        if row["status"] != "awaiting_approval":
            raise ValueError(f"Cannot approve MCP run in {row['status']} state.")
        conn.execute(
            """
            UPDATE mcp_runs
            SET status = ?, approved_by = ?, approved_at = ?, denied_by = NULL, denied_at = NULL,
                status_message = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                "ready",
                approver_id,
                now,
                "Approved for execution handoff. No tool has been executed by MCP run history.",
                now,
                run_id,
                user_id,
            ),
        )
    return get_mcp_run(run_id, user_id=user_id)


def deny_mcp_run(run_id: str, *, user_id: str, denier_id: str, reason: str = "") -> dict[str, Any] | None:
    _init_store()
    now = _now_iso()
    message = reason.strip() or "Denied by operator."
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM mcp_runs WHERE id = ? AND user_id = ?",
            (run_id, user_id),
        ).fetchone()
        if not row:
            return None
        if row["status"] != "awaiting_approval":
            raise ValueError(f"Cannot deny MCP run in {row['status']} state.")
        conn.execute(
            """
            UPDATE mcp_runs
            SET status = ?, denied_by = ?, denied_at = ?, status_message = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            ("blocked", denier_id, now, message[:500], now, run_id, user_id),
        )
    return get_mcp_run(run_id, user_id=user_id)
