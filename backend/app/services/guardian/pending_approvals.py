from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


_PENDING_TTL_SECONDS = 600

_SECRET_KEY_RE = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|"
    r"auth[_-]?token|passphrase|private[_-]?key|vault[_-]?key)",
)


def _redact_tool_args_for_event(tool_args: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of tool_args with secret-like values replaced by [REDACTED]."""
    if not tool_args:
        return {}
    safe = {}
    for key, value in tool_args.items():
        if _SECRET_KEY_RE.search(str(key)):
            safe[key] = "[REDACTED]"
        else:
            safe[key] = value
    return safe

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_approvals (
  confirm_id TEXT PRIMARY KEY,
  tool_name TEXT NOT NULL,
  tool_args_json TEXT NOT NULL,
  user_id TEXT,
  room_id TEXT,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pending_approvals_room_id ON pending_approvals(room_id);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_user_id ON pending_approvals(user_id);
CREATE INDEX IF NOT EXISTS idx_pending_approvals_expires_at ON pending_approvals(expires_at);
"""


@dataclass(frozen=True)
class PendingApproval:
    confirm_id: str
    tool_name: str
    tool_args_json: str
    user_id: Optional[str]
    room_id: Optional[str]
    created_at: float
    expires_at: float


def _data_root() -> Path:
    root_env = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    root = Path(root_env).expanduser() if root_env else Path(__file__).resolve().parents[4] / "data" / "guardian"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _db_path() -> Path:
    return _data_root() / "pending_approvals.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_store() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def _prune_expired(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM pending_approvals WHERE expires_at <= ?", (time.time(),))


def store_pending_approval(
    *,
    confirm_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    user_id: str | None,
    room_id: str | None,
) -> None:
    _init_store()
    now = time.time()
    expires_at = now + _PENDING_TTL_SECONDS
    payload = json.dumps(tool_args or {}, ensure_ascii=False)
    with _conn() as conn:
        _prune_expired(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO pending_approvals
            (confirm_id, tool_name, tool_args_json, user_id, room_id, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (confirm_id, tool_name, payload, user_id, room_id, now, expires_at),
        )
    try:
        from app.services.guardian.spine import emit_approval_event

        emit_approval_event(
            room_id=room_id,
            source_ref=confirm_id,
            event_type="approval.required",
            tool_name=tool_name,
            confirm_id=confirm_id,
            user_id=user_id,
            payload={"expires_at": expires_at, "approval_state": "required", "tool_args": _redact_tool_args_for_event(tool_args)},
        )
    except Exception:
        pass


def consume_pending_approval(confirm_id: str) -> dict[str, Any] | None:
    _init_store()
    with _conn() as conn:
        _prune_expired(conn)
        row = conn.execute(
            "SELECT * FROM pending_approvals WHERE confirm_id = ?",
            (confirm_id,),
        ).fetchone()
        if not row:
            return None
        conn.execute("DELETE FROM pending_approvals WHERE confirm_id = ?", (confirm_id,))

    tool_args: dict[str, Any]
    try:
        tool_args = json.loads(str(row["tool_args_json"]) or "{}")
        if not isinstance(tool_args, dict):
            tool_args = {}
    except Exception:
        tool_args = {}

    payload = {
        "tool": str(row["tool_name"]),
        "args": tool_args,
        "user_id": row["user_id"],
        "room_id": row["room_id"],
        "created_at": float(row["created_at"]),
    }
    try:
        from app.services.guardian.spine import emit_approval_event

        emit_approval_event(
            room_id=payload["room_id"],
            source_ref=confirm_id,
            event_type="approval.granted",
            tool_name=payload["tool"],
            confirm_id=confirm_id,
            user_id=payload["user_id"],
            payload={"created_at": payload["created_at"], "tool_args": _redact_tool_args_for_event(tool_args)},
        )
    except Exception:
        pass
    return payload


def get_pending_approval(confirm_id: str) -> PendingApproval | None:
    _init_store()
    with _conn() as conn:
        _prune_expired(conn)
        row = conn.execute(
            "SELECT * FROM pending_approvals WHERE confirm_id = ?",
            (confirm_id,),
        ).fetchone()
    if not row:
        return None
    return PendingApproval(**dict(row))


def discard_pending_approval(confirm_id: str) -> bool:
    _init_store()
    with _conn() as conn:
        _prune_expired(conn)
        row = conn.execute(
            "SELECT * FROM pending_approvals WHERE confirm_id = ?",
            (confirm_id,),
        ).fetchone()
        result = conn.execute(
            "DELETE FROM pending_approvals WHERE confirm_id = ?",
            (confirm_id,),
        )
        deleted = result.rowcount > 0
    if deleted and row:
        tool_args: dict[str, Any]
        try:
            tool_args = json.loads(str(row["tool_args_json"]) or "{}")
            if not isinstance(tool_args, dict):
                tool_args = {}
        except Exception:
            tool_args = {}
        try:
            from app.services.guardian.spine import emit_approval_event

            emit_approval_event(
                room_id=row["room_id"],
                source_ref=confirm_id,
                event_type="approval.discarded",
                tool_name=str(row["tool_name"]),
                confirm_id=confirm_id,
                user_id=row["user_id"],
                payload={"tool_args": _redact_tool_args_for_event(tool_args)},
            )
        except Exception:
            pass
    return deleted


def list_pending_approvals(
    *,
    room_ids: list[str] | None = None,
    user_id: str | None = None,
    limit: int = 25,
) -> list[PendingApproval]:
    _init_store()
    clauses = []
    params: list[Any] = []
    if room_ids:
        placeholders = ", ".join("?" for _ in room_ids)
        clauses.append(f"room_id IN ({placeholders})")
        params.extend(room_ids)
    if user_id:
        clauses.append("user_id = ?")
        params.append(user_id)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(max(1, min(limit, 100)))

    with _conn() as conn:
        _prune_expired(conn)
        rows = conn.execute(
            f"""
            SELECT * FROM pending_approvals
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
    return [PendingApproval(**dict(row)) for row in rows]
