"""
Guardian Vault — Encrypted SQLite-backed secrets store.

Encryption: cryptography.fernet.Fernet
Key source:  SPARKBOT_VAULT_KEY env var
Storage:     data/guardian/vault.db

Access policies:
  use_only         — value passed to tools internally; never revealed in chat
  privileged_reveal — can be revealed to operator in privileged mode
  admin_reveal     — reserved for future admin-tier reveal
  disabled         — cannot be used or revealed
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alias TEXT UNIQUE NOT NULL,
  category TEXT NOT NULL DEFAULT 'general',
  encrypted_value BLOB NOT NULL,
  access_policy TEXT NOT NULL DEFAULT 'use_only',
  notes TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  last_used_at TEXT,
  rotation_due TEXT
);

CREATE TABLE IF NOT EXISTS vault_audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alias TEXT NOT NULL,
  action TEXT NOT NULL,
  operator TEXT NOT NULL,
  session_id TEXT,
  outcome TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vault_entries_alias ON vault_entries(alias);
CREATE INDEX IF NOT EXISTS idx_vault_audit_alias ON vault_audit(alias);
"""

_VALID_POLICIES = {"use_only", "privileged_reveal", "admin_reveal", "disabled"}


def _data_root() -> Path:
    root = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    if root:
        return Path(root).expanduser()
    app_root = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    if app_root:
        return Path(app_root).expanduser() / "guardian"
    return Path(__file__).resolve().parents[3] / "data" / "guardian"


def _db_path() -> Path:
    path = _data_root() / "vault.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_vault_db() -> None:
    """Create vault tables if they don't exist. Called at startup."""
    with _conn() as conn:
        conn.executescript(_SCHEMA)
    log.info("[vault] Vault DB initialized at %s", _db_path())


def _get_fernet():
    """Return a Fernet instance. Raises RuntimeError if key not configured."""
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise RuntimeError(
            "Guardian Vault requires the 'cryptography' package. "
            "Install it with: pip install cryptography"
        )
    key = os.getenv("SPARKBOT_VAULT_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "SPARKBOT_VAULT_KEY is not configured. "
            "Generate a key: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(alias: str, action: str, operator: str, session_id: Optional[str], outcome: str) -> None:
    try:
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO vault_audit (alias, action, operator, session_id, outcome, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (alias, action, operator, session_id, outcome, _now_iso()),
            )
    except Exception as exc:
        log.warning("[vault] Failed to write audit entry for %s/%s: %s", alias, action, exc)


def vault_add(
    alias: str,
    value: str,
    category: str = "general",
    notes: Optional[str] = None,
    policy: str = "use_only",
    operator: str = "system",
    session_id: Optional[str] = None,
) -> dict:
    """Encrypt and store a new secret. Raises ValueError on duplicate alias."""
    if policy not in _VALID_POLICIES:
        raise ValueError(f"Invalid access_policy '{policy}'. Must be one of: {', '.join(sorted(_VALID_POLICIES))}")
    f = _get_fernet()
    encrypted = f.encrypt(value.encode("utf-8"))
    now = _now_iso()
    try:
        with _conn() as conn:
            conn.execute(
                """
                INSERT INTO vault_entries
                  (alias, category, encrypted_value, access_policy, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (alias, category, encrypted, policy, notes, now, now),
            )
    except sqlite3.IntegrityError:
        _audit(alias, "add", operator, session_id, "error:duplicate")
        raise ValueError(f"A secret with alias '{alias}' already exists. Use vault_update to change it.")
    _audit(alias, "add", operator, session_id, "ok")
    log.info("[vault] Secret added alias=%s category=%s policy=%s operator=%s", alias, category, policy, operator)
    return {"alias": alias, "category": category, "access_policy": policy, "notes": notes, "created_at": now}


def vault_get_metadata(alias: str) -> Optional[dict]:
    """Return metadata for an alias (no decrypted value). Returns None if not found."""
    with _conn() as conn:
        row = conn.execute(
            "SELECT alias, category, access_policy, notes, created_at, updated_at, last_used_at, rotation_due "
            "FROM vault_entries WHERE alias = ?",
            (alias,),
        ).fetchone()
    if not row:
        return None
    return dict(row)


def vault_list() -> list[dict]:
    """List all secret aliases with metadata. No plaintext values returned."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT alias, category, access_policy, notes, created_at, updated_at, last_used_at, rotation_due "
            "FROM vault_entries ORDER BY alias"
        ).fetchall()
    return [dict(row) for row in rows]


def vault_use(alias: str, user_id: str, operator: str, session_id: Optional[str] = None) -> str:
    """
    Decrypt and return a secret value for internal tool use.
    Allowed for use_only and privileged_reveal policies.
    The value is passed to tools but not directly echoed in chat.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT encrypted_value, access_policy FROM vault_entries WHERE alias = ?",
            (alias,),
        ).fetchone()
    if not row:
        _audit(alias, "use", operator, session_id, "error:not_found")
        raise ValueError(f"No secret found with alias '{alias}'.")
    policy = str(row["access_policy"])
    if policy == "disabled":
        _audit(alias, "use", operator, session_id, "error:disabled")
        raise ValueError(f"Secret '{alias}' is disabled and cannot be used.")
    f = _get_fernet()
    plaintext = f.decrypt(bytes(row["encrypted_value"])).decode("utf-8")
    with _conn() as conn:
        conn.execute(
            "UPDATE vault_entries SET last_used_at = ? WHERE alias = ?",
            (_now_iso(), alias),
        )
    _audit(alias, "use", operator, session_id, "ok")
    return plaintext


def vault_reveal(alias: str, user_id: str, operator: str, session_id: Optional[str] = None) -> str:
    """
    Decrypt and return a secret value for explicit reveal to the operator.
    Requires policy 'privileged_reveal' or 'admin_reveal'. Only called in privileged mode.
    """
    with _conn() as conn:
        row = conn.execute(
            "SELECT encrypted_value, access_policy FROM vault_entries WHERE alias = ?",
            (alias,),
        ).fetchone()
    if not row:
        _audit(alias, "reveal", operator, session_id, "error:not_found")
        raise ValueError(f"No secret found with alias '{alias}'.")
    policy = str(row["access_policy"])
    if policy == "use_only":
        _audit(alias, "reveal", operator, session_id, "error:policy_blocked")
        raise ValueError(
            f"Secret '{alias}' has policy 'use_only' — it can be used by tools but not revealed in plaintext. "
            "Change the policy to 'privileged_reveal' if you need to view it."
        )
    if policy == "disabled":
        _audit(alias, "reveal", operator, session_id, "error:disabled")
        raise ValueError(f"Secret '{alias}' is disabled.")
    f = _get_fernet()
    plaintext = f.decrypt(bytes(row["encrypted_value"])).decode("utf-8")
    with _conn() as conn:
        conn.execute(
            "UPDATE vault_entries SET last_used_at = ? WHERE alias = ?",
            (_now_iso(), alias),
        )
    _audit(alias, "reveal", operator, session_id, "ok")
    return plaintext


def vault_update(
    alias: str,
    value: str,
    operator: str = "system",
    session_id: Optional[str] = None,
    notes: Optional[str] = None,
    policy: Optional[str] = None,
) -> dict:
    """Update an existing secret's value and optionally notes/policy."""
    if policy is not None and policy not in _VALID_POLICIES:
        raise ValueError(f"Invalid access_policy '{policy}'.")
    with _conn() as conn:
        row = conn.execute("SELECT alias FROM vault_entries WHERE alias = ?", (alias,)).fetchone()
    if not row:
        _audit(alias, "update", operator, session_id, "error:not_found")
        raise ValueError(f"No secret found with alias '{alias}'.")
    f = _get_fernet()
    encrypted = f.encrypt(value.encode("utf-8"))
    now = _now_iso()
    if policy is not None and notes is not None:
        with _conn() as conn:
            conn.execute(
                "UPDATE vault_entries SET encrypted_value = ?, notes = ?, access_policy = ?, updated_at = ? WHERE alias = ?",
                (encrypted, notes, policy, now, alias),
            )
    elif policy is not None:
        with _conn() as conn:
            conn.execute(
                "UPDATE vault_entries SET encrypted_value = ?, access_policy = ?, updated_at = ? WHERE alias = ?",
                (encrypted, policy, now, alias),
            )
    elif notes is not None:
        with _conn() as conn:
            conn.execute(
                "UPDATE vault_entries SET encrypted_value = ?, notes = ?, updated_at = ? WHERE alias = ?",
                (encrypted, notes, now, alias),
            )
    else:
        with _conn() as conn:
            conn.execute(
                "UPDATE vault_entries SET encrypted_value = ?, updated_at = ? WHERE alias = ?",
                (encrypted, now, alias),
            )
    _audit(alias, "update", operator, session_id, "ok")
    log.info("[vault] Secret updated alias=%s operator=%s", alias, operator)
    return vault_get_metadata(alias) or {"alias": alias, "updated_at": now}


def vault_delete(alias: str, operator: str = "system", session_id: Optional[str] = None) -> bool:
    """Delete a secret. Returns True if deleted, False if not found."""
    with _conn() as conn:
        row = conn.execute("SELECT alias FROM vault_entries WHERE alias = ?", (alias,)).fetchone()
    if not row:
        _audit(alias, "delete", operator, session_id, "error:not_found")
        return False
    with _conn() as conn:
        conn.execute("DELETE FROM vault_entries WHERE alias = ?", (alias,))
    _audit(alias, "delete", operator, session_id, "ok")
    log.info("[vault] Secret deleted alias=%s operator=%s", alias, operator)
    return True
