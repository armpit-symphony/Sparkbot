"""
Sparkbot skill: nl_sql

Natural language → SQL. The LLM writes SQL; this skill executes it safely.

Tools:
  execute_sql(sql, database="")         — run a SELECT query against a SQLite database
  list_databases()                      — list known SQLite databases in the data dir
  describe_table(table, database="")    — show schema for a table

By default only SELECT is allowed. Write operations require the user to set
SPARKBOT_SQL_ALLOW_WRITE=true in the environment (disabled by default).

Env vars:
  SPARKBOT_SQL_DEFAULT_DB   — default database path (relative to data dir)
  SPARKBOT_SQL_ALLOW_WRITE  — set to "true" to allow INSERT/UPDATE/DELETE
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
from pathlib import Path

_ALLOW_WRITE = os.getenv("SPARKBOT_SQL_ALLOW_WRITE", "").strip().lower() == "true"
_DEFAULT_DB  = os.getenv("SPARKBOT_SQL_DEFAULT_DB", "").strip()


def _data_dir() -> Path:
    root = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    return Path(root).expanduser() if root else Path(__file__).resolve().parents[1] / "data"


def _resolve_db(database: str) -> str | None:
    if database:
        p = Path(database)
        if p.is_absolute() and p.exists():
            return str(p)
        # Relative to data dir
        p2 = _data_dir() / database
        if p2.exists():
            return str(p2)
        return None
    if _DEFAULT_DB:
        p = Path(_DEFAULT_DB)
        if not p.is_absolute():
            p = _data_dir() / _DEFAULT_DB
        return str(p) if p.exists() else None
    return None


def _execute_sql_sync(args: dict) -> str:
    sql = (args.get("sql") or "").strip()
    database = (args.get("database") or "").strip()
    if not sql:
        return "Error: sql is required."

    # Safety check — block write ops unless explicitly enabled
    sql_upper = sql.upper().lstrip()
    is_write = any(sql_upper.startswith(kw) for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "REPLACE"))
    if is_write and not _ALLOW_WRITE:
        return "Write SQL blocked. Only SELECT queries are allowed by default. Set SPARKBOT_SQL_ALLOW_WRITE=true to enable writes."

    db_path = _resolve_db(database)
    if not db_path:
        return (
            "No database found. Specify a path in the `database` argument or set SPARKBOT_SQL_DEFAULT_DB. "
            "Use `list_databases` to see available databases."
        )

    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if not _ALLOW_WRITE:
            conn.execute("PRAGMA query_only = ON")
        cur = conn.execute(sql)
        rows = cur.fetchmany(200)
        if not rows:
            return "_Query returned no rows._"
        cols = [d[0] for d in cur.description]
        lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
        for row in rows:
            lines.append("| " + " | ".join(str(v) if v is not None else "NULL" for v in row) + " |")
        suffix = f"\n_({len(rows)} rows shown" + (", truncated at 200)" if len(rows) == 200 else ")_")
        return "\n".join(lines) + suffix
    except sqlite3.Error as e:
        return f"SQL error: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _list_databases_sync(args: dict) -> str:
    data = _data_dir()
    dbs = list(data.rglob("*.db"))
    if not dbs:
        return "No SQLite databases found in the data directory."
    lines = [f"• `{db.relative_to(data)}` ({db.stat().st_size // 1024} KB)" for db in sorted(dbs)]
    return f"**SQLite databases in data dir:**\n" + "\n".join(lines)


def _describe_table_sync(args: dict) -> str:
    table    = (args.get("table") or "").strip()
    database = (args.get("database") or "").strip()
    if not table:
        return "Error: table name is required."
    db_path = _resolve_db(database)
    if not db_path:
        return "Database not found. Use `list_databases` to see available databases."
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not rows:
            # List available tables
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            names = [r[0] for r in tables]
            return f"Table '{table}' not found. Available tables: {', '.join(names) or 'none'}"
        lines = [f"**{table}** schema:", "| col | type | notnull | default | pk |",
                 "| --- | --- | --- | --- | --- |"]
        for r in rows:
            lines.append(f"| {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")
        return "\n".join(lines)
    except sqlite3.Error as e:
        return f"Error: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "execute_sql",
            "description": (
                "Execute a SQL query against a local SQLite database. "
                "Use this when the user asks questions about their data in natural language — "
                "write the appropriate SELECT query and call this tool. "
                "Only SELECT is allowed by default (safe read-only mode)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "The SQL query to execute"},
                    "database": {"type": "string", "description": "Database filename or path. Omit to use the default."},
                },
                "required": ["sql"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_databases",
            "description": "List all SQLite database files available in the Sparkbot data directory.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Show the schema (columns, types) of a table in a SQLite database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table": {"type": "string"},
                    "database": {"type": "string"},
                },
                "required": ["table"],
            },
        },
    },
]

POLICIES = {
    "execute_sql":     {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "list_databases":  {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "describe_table":  {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
}

_SYNC_FNS = {
    "execute_sql":    _execute_sql_sync,
    "list_databases": _list_databases_sync,
    "describe_table": _describe_table_sync,
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["execute_sql"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await asyncio.to_thread(_execute_sql_sync, args)


def _make_executor(fn):
    async def _exec(args: dict, *, user_id=None, room_id=None, session=None) -> str:
        return await asyncio.to_thread(fn, args)
    return _exec


def _register_extra(registry) -> None:
    for defn in DEFINITIONS:
        name = defn["function"]["name"]
        if name not in registry.executors:
            registry.definitions.append(defn)
            registry.policies[name] = POLICIES[name]
            registry.executors[name] = _make_executor(_SYNC_FNS[name])
