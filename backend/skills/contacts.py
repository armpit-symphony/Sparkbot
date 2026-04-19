"""
Sparkbot skill: contacts

Personal contacts manager with Google Contacts sync.

Tools:
  contacts_search(query)                        — search contacts by name/email/phone
  contacts_add(name, email="", phone="", notes="") — add a contact
  contacts_update(contact_id, **fields)         — update a contact
  contacts_delete(contact_id)                   — remove a contact
  contacts_sync_google()                        — import contacts from Google People API

Google sync requires: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

Storage: data/contacts/contacts.db
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

_GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "").strip()
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
_GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
_TOKEN_CACHE: dict = {}


def _db_path() -> Path:
    root = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    base = Path(root).expanduser() if root else Path(__file__).resolve().parents[1] / "data"
    d = base / "contacts"
    d.mkdir(parents=True, exist_ok=True)
    return d / "contacts.db"


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript("""
        CREATE TABLE IF NOT EXISTS contacts (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL DEFAULT '',
            name        TEXT NOT NULL,
            email       TEXT NOT NULL DEFAULT '',
            phone       TEXT NOT NULL DEFAULT '',
            company     TEXT NOT NULL DEFAULT '',
            notes       TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT 'manual',
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_contacts_user ON contacts(user_id);
        CREATE VIRTUAL TABLE IF NOT EXISTS contacts_fts USING fts5(
            id UNINDEXED, name, email, phone, company, notes,
            content=contacts, content_rowid=rowid
        );
        CREATE TRIGGER IF NOT EXISTS contacts_fts_insert AFTER INSERT ON contacts BEGIN
            INSERT INTO contacts_fts(rowid,id,name,email,phone,company,notes)
            VALUES(new.rowid,new.id,new.name,new.email,new.phone,new.company,new.notes);
        END;
        CREATE TRIGGER IF NOT EXISTS contacts_fts_delete AFTER DELETE ON contacts BEGIN
            INSERT INTO contacts_fts(contacts_fts,rowid,id,name,email,phone,company,notes)
            VALUES('delete',old.rowid,old.id,old.name,old.email,old.phone,old.company,old.notes);
        END;
        CREATE TRIGGER IF NOT EXISTS contacts_fts_update AFTER UPDATE ON contacts BEGIN
            INSERT INTO contacts_fts(contacts_fts,rowid,id,name,email,phone,company,notes)
            VALUES('delete',old.rowid,old.id,old.name,old.email,old.phone,old.company,old.notes);
            INSERT INTO contacts_fts(rowid,id,name,email,phone,company,notes)
            VALUES(new.rowid,new.id,new.name,new.email,new.phone,new.company,new.notes);
        END;
    """)
    c.commit()
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_contact(row) -> str:
    parts = [f"**{row['name']}** _(id: {row['id'][:8]})_"]
    if row["email"]:  parts.append(f"  Email: {row['email']}")
    if row["phone"]:  parts.append(f"  Phone: {row['phone']}")
    if row["company"]: parts.append(f"  Company: {row['company']}")
    if row["notes"]:  parts.append(f"  Notes: {row['notes']}")
    return "\n".join(parts)


def _contacts_search_sync(args: dict, user_id: str) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "Error: query is required."
    conn = _conn()
    rows = conn.execute(
        "SELECT c.* FROM contacts c JOIN contacts_fts f ON c.rowid=f.rowid "
        "WHERE c.user_id=? AND contacts_fts MATCH ? ORDER BY rank LIMIT 10",
        (user_id, query),
    ).fetchall()
    if not rows:
        # Fallback to LIKE
        rows = conn.execute(
            "SELECT * FROM contacts WHERE user_id=? AND (name LIKE ? OR email LIKE ? OR phone LIKE ?) LIMIT 10",
            (user_id, f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    if not rows:
        return f"No contacts matching '{query}'."
    return f"**{len(rows)} contact(s) found:**\n\n" + "\n\n".join(_format_contact(r) for r in rows)


def _contacts_add_sync(args: dict, user_id: str) -> str:
    name = (args.get("name") or "").strip()
    if not name:
        return "Error: name is required."
    conn = _conn()
    cid = str(uuid.uuid4())
    now = _now()
    conn.execute(
        "INSERT INTO contacts(id,user_id,name,email,phone,company,notes,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
        (cid, user_id, name, args.get("email",""), args.get("phone",""), args.get("company",""), args.get("notes",""), "manual", now, now),
    )
    conn.commit()
    return f"✅ Contact added: **{name}** (id: {cid[:8]})"


def _contacts_update_sync(args: dict, user_id: str) -> str:
    cid = (args.get("contact_id") or "").strip()
    if not cid:
        return "Error: contact_id is required."
    conn = _conn()
    contact = conn.execute("SELECT id FROM contacts WHERE user_id=? AND id LIKE ?", (user_id, f"{cid}%")).fetchone()
    if not contact:
        return f"Contact not found: {cid}"
    fields = {k: v for k, v in args.items() if k in ("name","email","phone","company","notes") and v}
    if not fields:
        return "No fields to update."
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [_now(), contact["id"]]
    conn.execute(f"UPDATE contacts SET {sets}, updated_at=? WHERE id=?", vals)
    conn.commit()
    return f"✅ Contact updated."


def _contacts_delete_sync(args: dict, user_id: str) -> str:
    cid = (args.get("contact_id") or "").strip()
    if not cid:
        return "Error: contact_id is required."
    conn = _conn()
    conn.execute("DELETE FROM contacts WHERE user_id=? AND id LIKE ?", (user_id, f"{cid}%"))
    conn.commit()
    return "Contact deleted."


async def _get_google_token() -> str | None:
    if not (_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET and _GOOGLE_REFRESH_TOKEN):
        return None
    if _TOKEN_CACHE.get("token") and time.time() < _TOKEN_CACHE.get("expires", 0) - 60:
        return _TOKEN_CACHE["token"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post("https://oauth2.googleapis.com/token", data={
            "client_id": _GOOGLE_CLIENT_ID, "client_secret": _GOOGLE_CLIENT_SECRET,
            "refresh_token": _GOOGLE_REFRESH_TOKEN, "grant_type": "refresh_token",
        })
    if r.status_code != 200:
        return None
    d = r.json()
    _TOKEN_CACHE["token"] = d.get("access_token")
    _TOKEN_CACHE["expires"] = time.time() + int(d.get("expires_in", 3600))
    return _TOKEN_CACHE["token"]


async def _contacts_sync_google(args: dict, user_id: str) -> str:
    token = await _get_google_token()
    if not token:
        return "Google not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN."
    imported = 0
    skipped = 0
    page_token = None
    conn = _conn()
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            params: dict = {"personFields": "names,emailAddresses,phoneNumbers,organizations", "pageSize": 100}
            if page_token:
                params["pageToken"] = page_token
            r = await client.get(
                "https://people.googleapis.com/v1/people/me/connections",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            if r.status_code != 200:
                return f"Google People API error {r.status_code}: {r.text[:200]}"
            data = r.json()
            for person in data.get("connections", []):
                names = person.get("names", [])
                name = names[0].get("displayName", "") if names else ""
                if not name:
                    skipped += 1
                    continue
                emails = person.get("emailAddresses", [])
                email = emails[0].get("value", "") if emails else ""
                phones = person.get("phoneNumbers", [])
                phone = phones[0].get("value", "") if phones else ""
                orgs = person.get("organizations", [])
                company = orgs[0].get("name", "") if orgs else ""
                # Check if exists
                existing = conn.execute("SELECT id FROM contacts WHERE user_id=? AND name=?", (user_id, name)).fetchone()
                now = _now()
                if existing:
                    conn.execute("UPDATE contacts SET email=?,phone=?,company=?,source=?,updated_at=? WHERE id=?",
                                 (email, phone, company, "google", now, existing["id"]))
                else:
                    conn.execute("INSERT INTO contacts(id,user_id,name,email,phone,company,notes,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                 (str(uuid.uuid4()), user_id, name, email, phone, company, "", "google", now, now))
                imported += 1
            conn.commit()
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return f"✅ Google Contacts synced: {imported} imported/updated, {skipped} skipped (no name)."


DEFINITIONS = [
    {"type": "function", "function": {"name": "contacts_search", "description": "Search contacts by name, email, or phone number.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "contacts_add", "description": "Add a new contact.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}, "company": {"type": "string"}, "notes": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "contacts_update", "description": "Update an existing contact by id (first 8 chars from contacts_search).", "parameters": {"type": "object", "properties": {"contact_id": {"type": "string"}, "name": {"type": "string"}, "email": {"type": "string"}, "phone": {"type": "string"}, "company": {"type": "string"}, "notes": {"type": "string"}}, "required": ["contact_id"]}}},
    {"type": "function", "function": {"name": "contacts_delete", "description": "Delete a contact by id.", "parameters": {"type": "object", "properties": {"contact_id": {"type": "string"}}, "required": ["contact_id"]}}},
    {"type": "function", "function": {"name": "contacts_sync_google", "description": "Import/sync contacts from Google Contacts. Requires Google OAuth configured.", "parameters": {"type": "object", "properties": {}, "required": []}}},
]

POLICIES = {
    "contacts_search":      {"scope": "read",  "resource": "local_machine", "default_action": "allow",   "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "contacts_add":         {"scope": "write", "resource": "local_machine", "default_action": "allow",   "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "contacts_update":      {"scope": "write", "resource": "local_machine", "default_action": "allow",   "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "contacts_delete":      {"scope": "write", "resource": "local_machine", "default_action": "allow",   "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "contacts_sync_google": {"scope": "read",  "resource": "web",           "default_action": "allow",   "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
}

_SYNC_FNS = {
    "contacts_search": _contacts_search_sync,
    "contacts_add":    _contacts_add_sync,
    "contacts_update": _contacts_update_sync,
    "contacts_delete": _contacts_delete_sync,
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["contacts_search"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await asyncio.to_thread(_contacts_search_sync, args, user_id or "")


def _make_executor(fn, is_async=False):
    if is_async:
        async def _ea(args: dict, *, user_id=None, room_id=None, session=None) -> str:
            return await fn(args, user_id or "")
        return _ea
    async def _es(args: dict, *, user_id=None, room_id=None, session=None) -> str:
        return await asyncio.to_thread(fn, args, user_id or "")
    return _es


def _register_extra(registry) -> None:
    for defn in DEFINITIONS:
        name = defn["function"]["name"]
        if name not in registry.executors:
            registry.definitions.append(defn)
            registry.policies[name] = POLICIES[name]
            if name == "contacts_sync_google":
                registry.executors[name] = _make_executor(_contacts_sync_google, is_async=True)
            else:
                registry.executors[name] = _make_executor(_SYNC_FNS[name])
