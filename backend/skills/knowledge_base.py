"""
Sparkbot skill: knowledge_base

Operator-owned document store with full-text search (SQLite FTS5 / BM25).
Feed it text, URLs, or any content — then query it by topic.

No extra dependencies beyond Python stdlib + httpx (already in pyproject).

Tools exposed:
  ingest_document(text, name, source="")    — add or update a document
  search_knowledge(query, top_k=5)         — BM25 full-text search
  list_knowledge()                          — list all ingested documents
  delete_knowledge(name)                    — remove by name

Storage: data/knowledge/knowledge.db  (respects SPARKBOT_DATA_DIR)
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import textwrap
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ─── Storage path ─────────────────────────────────────────────────────────────

def _kb_db_path() -> Path:
    data_root = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    if data_root:
        base = Path(data_root).expanduser()
    else:
        base = Path(__file__).resolve().parents[1] / "data"
    kb_dir = base / "knowledge"
    kb_dir.mkdir(parents=True, exist_ok=True)
    return kb_dir / "knowledge.db"


# ─── DB bootstrap ─────────────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_kb_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kb_documents (
            id       TEXT PRIMARY KEY,
            name     TEXT NOT NULL UNIQUE,
            source   TEXT NOT NULL DEFAULT '',
            content  TEXT NOT NULL,
            added_at TEXT NOT NULL,
            user_id  TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts
        USING fts5(id UNINDEXED, name, content, content=kb_documents, content_rowid=rowid)
    """)
    # Trigger to keep FTS in sync
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_fts_insert AFTER INSERT ON kb_documents BEGIN
            INSERT INTO kb_fts(rowid, id, name, content) VALUES (new.rowid, new.id, new.name, new.content);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_fts_delete AFTER DELETE ON kb_documents BEGIN
            INSERT INTO kb_fts(kb_fts, rowid, id, name, content)
                VALUES ('delete', old.rowid, old.id, old.name, old.content);
        END
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS kb_fts_update AFTER UPDATE ON kb_documents BEGIN
            INSERT INTO kb_fts(kb_fts, rowid, id, name, content)
                VALUES ('delete', old.rowid, old.id, old.name, old.content);
            INSERT INTO kb_fts(rowid, id, name, content) VALUES (new.rowid, new.id, new.name, new.content);
        END
    """)
    conn.commit()
    return conn


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _fetch_url_text(url: str) -> str:
    """Fetch URL and return plain text. Requires httpx."""
    import httpx
    headers = {"User-Agent": "Sparkbot/2.0 (knowledge base ingestor)"}
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "html" in ct:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)
            except ImportError:
                pass
        return resp.text


def _chunk_text(text: str, chunk_size: int = 1500, overlap: int = 150) -> list[str]:
    """Split text into overlapping chunks for better search coverage."""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


# ─── Core operations (sync, run in executor) ──────────────────────────────────

def _ingest_sync(name: str, content: str, source: str, user_id: str) -> str:
    conn = _get_conn()
    try:
        # Check if exists
        existing = conn.execute("SELECT id FROM kb_documents WHERE name = ?", (name,)).fetchone()
        now = datetime.now(timezone.utc).isoformat()
        chunks = _chunk_text(content)

        if existing:
            # Update: delete all chunks for this name then re-insert
            conn.execute("DELETE FROM kb_documents WHERE name LIKE ?", (f"{name}%",))
            conn.commit()

        if len(chunks) == 1:
            doc_id = str(_uuid.uuid4())[:8]
            conn.execute(
                "INSERT INTO kb_documents (id, name, source, content, added_at, user_id) VALUES (?,?,?,?,?,?)",
                (doc_id, name, source, content, now, user_id),
            )
        else:
            for i, chunk in enumerate(chunks):
                doc_id = str(_uuid.uuid4())[:8]
                chunk_name = f"{name} [chunk {i+1}/{len(chunks)}]"
                conn.execute(
                    "INSERT INTO kb_documents (id, name, source, content, added_at, user_id) VALUES (?,?,?,?,?,?)",
                    (doc_id, chunk_name, source, chunk, now, user_id),
                )
        conn.commit()
        return f"Ingested '{name}' — {len(chunks)} chunk(s), {len(content)} chars."
    finally:
        conn.close()


def _search_sync(query: str, top_k: int) -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT d.name, d.source, d.content, d.added_at,
                   bm25(kb_fts) AS score
            FROM kb_fts
            JOIN kb_documents d ON kb_fts.id = d.id
            WHERE kb_fts MATCH ?
            ORDER BY score
            LIMIT ?
            """,
            (query, top_k),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _list_sync() -> list[dict[str, Any]]:
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT name, source, length(content) as chars, added_at FROM kb_documents ORDER BY added_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _delete_sync(name: str) -> int:
    conn = _get_conn()
    try:
        cur = conn.execute("DELETE FROM kb_documents WHERE name = ? OR name LIKE ?", (name, f"{name} [chunk%]"))
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


# ─── Skill tool implementations ───────────────────────────────────────────────

async def _ingest_document(args: dict, *, user_id: str = "", **_) -> str:
    text = (args.get("text") or "").strip()
    name = (args.get("name") or "").strip()
    source = (args.get("source") or "").strip()

    if not name:
        return "Error: 'name' is required."

    # URL ingestion
    if not text and source and source.startswith(("http://", "https://")):
        try:
            text = await _fetch_url_text(source)
        except Exception as exc:
            return f"Error fetching URL '{source}': {exc}"

    if not text:
        return "Error: 'text' is required (or provide a URL in 'source')."

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _ingest_sync, name, text, source, user_id or ""
    )


async def _search_knowledge(args: dict, **_) -> str:
    query = (args.get("query") or "").strip()
    top_k = min(max(int(args.get("top_k") or 5), 1), 20)

    if not query:
        return "Error: 'query' is required."

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, _search_sync, query, top_k)

    if not results:
        return f"No results found for '{query}'. Try ingesting relevant documents with ingest_document()."

    parts = [f"## Knowledge base results for: {query}\n"]
    for i, r in enumerate(results, 1):
        snippet = textwrap.shorten(r["content"], width=400, placeholder="…")
        src = f" (source: {r['source']})" if r.get("source") else ""
        parts.append(f"### {i}. {r['name']}{src}\n{snippet}\n")
    return "\n".join(parts)


async def _list_knowledge(args: dict, **_) -> str:
    loop = asyncio.get_event_loop()
    docs = await loop.run_in_executor(None, _list_sync)
    if not docs:
        return "Knowledge base is empty. Use ingest_document() to add content."
    lines = [f"## Knowledge base ({len(docs)} entries)\n"]
    for d in docs:
        src = f" — {d['source']}" if d.get("source") else ""
        ts = d["added_at"][:10] if d.get("added_at") else "?"
        lines.append(f"- **{d['name']}** ({d['chars']} chars, added {ts}){src}")
    return "\n".join(lines)


async def _delete_knowledge(args: dict, **_) -> str:
    name = (args.get("name") or "").strip()
    if not name:
        return "Error: 'name' is required."
    loop = asyncio.get_event_loop()
    deleted = await loop.run_in_executor(None, _delete_sync, name)
    if deleted == 0:
        return f"No document named '{name}' found."
    return f"Deleted '{name}' ({deleted} row(s) removed)."


# ─── Skill registration ───────────────────────────────────────────────────────

DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "ingest_document",
            "description": (
                "Add text or a URL to Sparkbot's knowledge base for later retrieval. "
                "The content is indexed with full-text search (BM25). "
                "Use this to feed Sparkbot docs, notes, web pages, or any reference material."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Unique name / title for this document",
                    },
                    "text": {
                        "type": "string",
                        "description": "The text content to ingest (optional if source is a URL)",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source URL or reference (optional; if a URL and text is empty, the URL is fetched automatically)",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": (
                "Search the knowledge base using full-text BM25 ranking. "
                "Use this before answering questions that might be covered by ingested documents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query",
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return (default 5, max 20)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_knowledge",
            "description": "List all documents in the knowledge base with their names, sizes, and dates.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_knowledge",
            "description": "Remove a document from the knowledge base by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the document to delete",
                    }
                },
                "required": ["name"],
            },
        },
    },
]

POLICIES = {
    "ingest_document": {
        "scope": "write",
        "resource": "local_machine",
        "default_action": "allow",
        "action_type": "data_write",
        "high_risk": False,
        "requires_execution_gate": False,
    },
    "search_knowledge": {
        "scope": "read",
        "resource": "local_machine",
        "default_action": "allow",
        "action_type": "data_read",
        "high_risk": False,
        "requires_execution_gate": False,
    },
    "list_knowledge": {
        "scope": "read",
        "resource": "local_machine",
        "default_action": "allow",
        "action_type": "data_read",
        "high_risk": False,
        "requires_execution_gate": False,
    },
    "delete_knowledge": {
        "scope": "write",
        "resource": "local_machine",
        "default_action": "allow",
        "action_type": "data_write",
        "high_risk": False,
        "requires_execution_gate": False,
    },
}

_EXECUTORS = {
    "ingest_document": _ingest_document,
    "search_knowledge": _search_knowledge,
    "list_knowledge":   _list_knowledge,
    "delete_knowledge": _delete_knowledge,
}

# Multi-tool skill: skills.py loads DEFINITION (singular) per file.
# We expose a shim DEFINITION + execute for the primary tool,
# and register the rest via the _extra hook below.
DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["ingest_document"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await _ingest_document(args, user_id=user_id or "")


# Called by skills.py to register additional tools from this module
def _register_extra(registry) -> None:
    for i, defn in enumerate(DEFINITIONS):
        tool_name = defn["function"]["name"]
        if tool_name not in registry.executors:
            registry.definitions.append(defn)
            registry.executors[tool_name] = _EXECUTORS[tool_name]
            registry.policies[tool_name] = POLICIES[tool_name]
