"""
Sparkbot skill: relationship_memory

Tracks people you interact with — facts, notes, last contact, relationship context.
Think of it as a personal CRM built automatically from your conversations.

Tools:
  remember_person(name, fact, category="general") — add a fact about someone
  recall_person(name)                              — get everything remembered about a person
  list_people(query="")                            — list known people
  log_interaction(name, note)                      — log a meeting/call/email with someone
  forget_person_fact(name, fact_id)                — remove one fact by id
  forget_person(name)                              — remove all memory of a person

Storage: data/relationships/people.db
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
    d = base / "relationships"
    d.mkdir(parents=True, exist_ok=True)
    return d / "people.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS people (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            name_lower  TEXT NOT NULL,
            user_id     TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_people_user ON people(user_id, name_lower);
        CREATE TABLE IF NOT EXISTS person_facts (
            id          TEXT PRIMARY KEY,
            person_id   TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
            category    TEXT NOT NULL DEFAULT 'general',
            fact        TEXT NOT NULL,
            added_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_facts_person ON person_facts(person_id);
        CREATE TABLE IF NOT EXISTS interactions (
            id          TEXT PRIMARY KEY,
            person_id   TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
            note        TEXT NOT NULL,
            logged_at   TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_interactions_person ON interactions(person_id);
    """)
    c.commit()
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_or_create_person(conn: sqlite3.Connection, name: str, user_id: str) -> str:
    row = conn.execute(
        "SELECT id FROM people WHERE user_id=? AND name_lower=?",
        (user_id, name.lower()),
    ).fetchone()
    if row:
        return row["id"]
    pid = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO people(id,name,name_lower,user_id,created_at) VALUES(?,?,?,?,?)",
        (pid, name.strip(), name.lower(), user_id, _now()),
    )
    conn.commit()
    return pid


def _remember_person_sync(args: dict, user_id: str) -> str:
    name = (args.get("name") or "").strip()
    fact = (args.get("fact") or "").strip()
    category = (args.get("category") or "general").strip()
    if not name or not fact:
        return "Error: name and fact are required."
    conn = _conn()
    pid = _get_or_create_person(conn, name, user_id)
    conn.execute(
        "INSERT INTO person_facts(id,person_id,category,fact,added_at) VALUES(?,?,?,?,?)",
        (str(uuid.uuid4()), pid, category, fact, _now()),
    )
    conn.commit()
    return f"Remembered about {name} ({category}): {fact}"


def _recall_person_sync(args: dict, user_id: str) -> str:
    name = (args.get("name") or "").strip()
    if not name:
        return "Error: name is required."
    conn = _conn()
    person = conn.execute(
        "SELECT id, name, created_at FROM people WHERE user_id=? AND name_lower=?",
        (user_id, name.lower()),
    ).fetchone()
    if not person:
        return f"No information stored about {name}."
    pid = person["id"]
    facts = conn.execute(
        "SELECT id, category, fact, added_at FROM person_facts WHERE person_id=? ORDER BY added_at",
        (pid,),
    ).fetchall()
    interactions = conn.execute(
        "SELECT note, logged_at FROM interactions WHERE person_id=? ORDER BY logged_at DESC LIMIT 10",
        (pid,),
    ).fetchall()
    lines = [f"## {person['name']}", f"_Known since {person['created_at'][:10]}_", ""]
    if facts:
        by_cat: dict[str, list[str]] = {}
        for f in facts:
            by_cat.setdefault(f["category"], []).append(f"• {f['fact']}  _(id: {f['id'][:8]})_")
        for cat, items in by_cat.items():
            lines.append(f"**{cat.title()}**")
            lines.extend(items)
            lines.append("")
    else:
        lines += ["_No facts stored yet._", ""]
    if interactions:
        lines.append("**Recent interactions**")
        for i in interactions:
            lines.append(f"• {i['logged_at'][:10]} — {i['note']}")
    return "\n".join(lines)


def _list_people_sync(args: dict, user_id: str) -> str:
    query = (args.get("query") or "").strip().lower()
    conn = _conn()
    if query:
        rows = conn.execute(
            "SELECT name, created_at FROM people WHERE user_id=? AND name_lower LIKE ? ORDER BY name_lower",
            (user_id, f"%{query}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name, created_at FROM people WHERE user_id=? ORDER BY name_lower",
            (user_id,),
        ).fetchall()
    if not rows:
        return "No people in relationship memory yet." if not query else f"No matches for '{query}'."
    lines = [f"• **{r['name']}** — known since {r['created_at'][:10]}" for r in rows]
    return f"**{len(rows)} people in memory:**\n" + "\n".join(lines)


def _log_interaction_sync(args: dict, user_id: str) -> str:
    name = (args.get("name") or "").strip()
    note = (args.get("note") or "").strip()
    if not name or not note:
        return "Error: name and note are required."
    conn = _conn()
    pid = _get_or_create_person(conn, name, user_id)
    conn.execute(
        "INSERT INTO interactions(id,person_id,note,logged_at) VALUES(?,?,?,?)",
        (str(uuid.uuid4()), pid, note, _now()),
    )
    conn.commit()
    return f"Interaction logged with {name}: {note}"


def _forget_person_fact_sync(args: dict, user_id: str) -> str:
    name = (args.get("name") or "").strip()
    fact_id = (args.get("fact_id") or "").strip()
    if not name or not fact_id:
        return "Error: name and fact_id are required."
    conn = _conn()
    person = conn.execute(
        "SELECT id FROM people WHERE user_id=? AND name_lower=?", (user_id, name.lower())
    ).fetchone()
    if not person:
        return f"No person named {name} found."
    conn.execute(
        "DELETE FROM person_facts WHERE person_id=? AND id LIKE ?",
        (person["id"], f"{fact_id}%"),
    )
    conn.commit()
    return f"Fact removed for {name}."


def _forget_person_sync(args: dict, user_id: str) -> str:
    name = (args.get("name") or "").strip()
    if not name:
        return "Error: name is required."
    conn = _conn()
    conn.execute("DELETE FROM people WHERE user_id=? AND name_lower=?", (user_id, name.lower()))
    conn.commit()
    return f"All memory of {name} has been removed."


DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "remember_person",
            "description": (
                "Store a fact about a person — colleague, friend, family, client. "
                "Use when the user mentions something about someone: job, preferences, birthday, "
                "opinions, contact info, relationship context. "
                "Examples: 'Sarah works at Stripe', 'John prefers morning calls', 'Maria's dog is Biscuit'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Person's name"},
                    "fact": {"type": "string", "description": "The fact to remember"},
                    "category": {"type": "string", "description": "'work', 'personal', 'contact', 'preferences', or 'general'"},
                },
                "required": ["name", "fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_person",
            "description": "Retrieve everything remembered about a specific person including facts and interaction history.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_people",
            "description": "List all people in relationship memory with an optional name search filter.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Optional name filter"}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_interaction",
            "description": "Log an interaction with someone — a meeting, call, email, or any contact event.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "note": {"type": "string", "description": "What happened or was discussed"},
                },
                "required": ["name", "note"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_person_fact",
            "description": "Remove one specific fact about a person using the id from recall_person output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "fact_id": {"type": "string", "description": "First 8 chars of the fact id"},
                },
                "required": ["name", "fact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_person",
            "description": "Remove all memory of a person entirely.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
]

POLICIES = {
    "remember_person":    {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "recall_person":      {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "list_people":        {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "log_interaction":    {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "forget_person_fact": {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "forget_person":      {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
}

_SYNC_FNS = {
    "remember_person":    _remember_person_sync,
    "recall_person":      _recall_person_sync,
    "list_people":        _list_people_sync,
    "log_interaction":    _log_interaction_sync,
    "forget_person_fact": _forget_person_fact_sync,
    "forget_person":      _forget_person_sync,
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["remember_person"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await asyncio.to_thread(_remember_person_sync, args, user_id or "")


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
