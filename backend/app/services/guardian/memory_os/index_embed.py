"""Lightweight embedding index for hybrid retrieval.

This module replaces the original sentence-transformers placeholder with a
zero-dependency hashing-trick TF-IDF embedding stored in SQLite. It runs inside
the PyInstaller-frozen Sparkbot binary without pulling in 300+ MB of ML
dependencies, while still providing a real cosine-similarity rerank signal on
top of the FTS5 lexical index.

The index can be promoted to a real semantic embedder later (sentence
transformers, OpenAI embeddings, etc.) by swapping `_compute_vector`. The
public surface is intentionally small:

    EmbedIndex.is_available() -> bool
    EmbedIndex.index_event(event)
    EmbedIndex.bulk_index_events(events)
    EmbedIndex.search(query, limit, session_id=None) -> list[dict]
    EmbedIndex.rebuild_from_ledger(ledger_path)
    EmbedIndex.size() -> int
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Iterable

from .schemas import Event


# Number of hash buckets used by the hashing trick. 256 keeps the per-row
# storage small (~2 KB JSON encoded) while still giving useful cosine signal.
_VECTOR_DIM = 256

_TOKEN_RE = re.compile(r"[A-Za-z0-9]{2,}")
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "but", "not", "you", "your", "with",
        "this", "that", "from", "have", "has", "had", "was", "were", "will",
        "can", "could", "should", "would", "into", "out", "about", "what",
        "when", "where", "why", "how", "who", "any", "all", "some", "very",
        "just", "than", "then", "there", "here", "they", "them", "their",
    }
)


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for token in _TOKEN_RE.findall(text.lower()):
        if len(token) < 2 or token in _STOPWORDS:
            continue
        out.append(token)
    return out


def _hash_bucket(token: str) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % _VECTOR_DIM


def _compute_vector(text: str) -> list[float]:
    tokens = _tokenize(text)
    if not tokens:
        return [0.0] * _VECTOR_DIM
    vec = [0.0] * _VECTOR_DIM
    for token in tokens:
        vec[_hash_bucket(token)] += 1.0
    # log-tf damping
    for i, v in enumerate(vec):
        if v > 0.0:
            vec[i] = 1.0 + math.log(v)
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _serialize(vec: list[float]) -> bytes:
    # 4-byte little-endian floats — compact and faster than JSON.
    import struct

    return struct.pack(f"<{len(vec)}f", *vec)


def _deserialize(blob: bytes) -> list[float]:
    import struct

    if not blob:
        return [0.0] * _VECTOR_DIM
    count = len(blob) // 4
    return list(struct.unpack(f"<{count}f", blob))


class EmbedIndex:
    """SQLite-backed hashing-trick embedding index."""

    def __init__(self, data_dir: str | Path | None = None):
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "indexes"
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "embed.sqlite"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS event_embeddings (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    event_type TEXT,
                    role TEXT,
                    content TEXT,
                    timestamp TEXT,
                    vector BLOB NOT NULL,
                    dim INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_event_embeddings_session "
                "ON event_embeddings(session_id)"
            )
            conn.commit()
        finally:
            conn.close()

    # ── Availability -----------------------------------------------------

    def is_available(self) -> bool:
        """Hash-based embedder has no external deps and is always available."""
        flag = os.getenv("SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS", "true").strip().lower()
        return flag not in {"0", "false", "no", "off"}

    # ── Writes -----------------------------------------------------------

    def index_event(self, event: Event) -> None:
        if not self.is_available():
            return
        vec = _compute_vector(event.content or "")
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO event_embeddings
                  (id, session_id, event_type, role, content, timestamp, vector, dim)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.id,
                    event.session_id,
                    event.type.value if hasattr(event.type, "value") else str(event.type),
                    event.role,
                    (event.content or "")[:4000],
                    event.timestamp.isoformat() if event.timestamp else None,
                    _serialize(vec),
                    _VECTOR_DIM,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def bulk_index_events(self, events: Iterable[Event]) -> int:
        if not self.is_available():
            return 0
        conn = sqlite3.connect(str(self.db_path))
        count = 0
        try:
            for event in events:
                vec = _compute_vector(event.content or "")
                conn.execute(
                    """
                    INSERT OR REPLACE INTO event_embeddings
                      (id, session_id, event_type, role, content, timestamp, vector, dim)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.session_id,
                        event.type.value if hasattr(event.type, "value") else str(event.type),
                        event.role,
                        (event.content or "")[:4000],
                        event.timestamp.isoformat() if event.timestamp else None,
                        _serialize(vec),
                        _VECTOR_DIM,
                    ),
                )
                count += 1
            conn.commit()
        finally:
            conn.close()
        return count

    # ── Reads ------------------------------------------------------------

    def search(
        self,
        query: str,
        limit: int = 10,
        session_id: str | None = None,
        candidate_pool: int = 200,
    ) -> list[dict]:
        if not self.is_available():
            return []
        query_vec = _compute_vector(query or "")
        if not any(query_vec):
            return []

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            params: list[object] = []
            sql = "SELECT id, session_id, event_type, role, content, timestamp, vector FROM event_embeddings"
            if session_id:
                sql += " WHERE session_id = ?"
                params.append(session_id)
            sql += " ORDER BY rowid DESC LIMIT ?"
            params.append(int(candidate_pool))

            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        scored: list[dict] = []
        for row in rows:
            vec = _deserialize(row["vector"])
            score = _cosine(query_vec, vec)
            if score <= 0.0:
                continue
            scored.append(
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "event_type": row["event_type"],
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["timestamp"],
                    "score": float(score),
                }
            )
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:limit]

    # ── Maintenance ------------------------------------------------------

    def delete_event(self, event_id: str) -> int:
        conn = sqlite3.connect(str(self.db_path))
        try:
            cur = conn.execute("DELETE FROM event_embeddings WHERE id = ?", (event_id,))
            conn.commit()
            return cur.rowcount or 0
        finally:
            conn.close()

    def clear(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("DELETE FROM event_embeddings")
            conn.commit()
        finally:
            conn.close()

    def size(self) -> int:
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT COUNT(*) FROM event_embeddings").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()

    def rebuild_from_ledger(self, ledger_path: Path) -> int:
        """Rebuild the embedding index from a JSONL ledger file."""
        if not Path(ledger_path).exists():
            return 0
        self.clear()
        from .schemas import Event as _Event

        count = 0
        conn = sqlite3.connect(str(self.db_path))
        try:
            with open(ledger_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = _Event.model_validate_json(line)
                    except Exception:
                        continue
                    vec = _compute_vector(event.content or "")
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO event_embeddings
                          (id, session_id, event_type, role, content, timestamp, vector, dim)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.id,
                            event.session_id,
                            event.type.value if hasattr(event.type, "value") else str(event.type),
                            event.role,
                            (event.content or "")[:4000],
                            event.timestamp.isoformat() if event.timestamp else None,
                            _serialize(vec),
                            _VECTOR_DIM,
                        ),
                    )
                    count += 1
            conn.commit()
        finally:
            conn.close()
        return count

    # ── Compat -----------------------------------------------------------

    def index_events(self, events: Iterable[Event]) -> None:
        """Backward-compat shim for the old API."""
        self.bulk_index_events(events)
