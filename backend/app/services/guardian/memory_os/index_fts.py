"""FTS (Full-Text Search) index using SQLite FTS5."""

import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .schemas import Event


class FTSIndex:
    """Full-text search index using SQLite FTS5."""

    def __init__(self, data_dir: str | Path | None = None):
        """Initialize FTS index."""
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "indexes"
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "fts.sqlite"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the FTS database."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
                id,
                timestamp,
                event_type,
                role,
                content,
                session_id,
                tokenize='porter unicode61'
            )
        """)
        conn.commit()
        conn.close()

    def index_event(self, event: Event) -> None:
        """Index a single event."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO events_fts (id, timestamp, event_type, role, content, session_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                event.id,
                event.timestamp.isoformat(),
                event.type.value,
                event.role,
                event.content,
                event.session_id,
            ),
        )
        conn.commit()
        conn.close()

    def index_events(self, events: Iterator[Event]) -> None:
        """Bulk index multiple events."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        data = [
            (
                e.id,
                e.timestamp.isoformat(),
                e.type.value,
                e.role,
                e.content,
                e.session_id,
            )
            for e in events
        ]
        cursor.executemany(
            """INSERT INTO events_fts (id, timestamp, event_type, role, content, session_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            data,
        )
        conn.commit()
        conn.close()

    def delete_event(self, event_id: str) -> int:
        """Remove one event from the FTS index."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events_fts WHERE id = ?", (event_id,))
        count = cursor.rowcount or 0
        conn.commit()
        conn.close()
        return count

    def search(
        self, query: str, limit: int = 10, session_id: str | None = None
    ) -> list[dict]:
        """Search the FTS index."""
        normalized = self._normalize_query(query)
        if not normalized:
            return []

        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        sql = """
            SELECT id, timestamp, event_type, role, content, session_id,
                   bm25(events_fts) as score
            FROM events_fts
            WHERE events_fts MATCH ?
        """

        params: list[object] = [normalized, limit]
        if session_id:
            sql += " AND session_id = ?"
            params = [normalized, session_id, limit]

        sql += " ORDER BY score LIMIT ?"

        cursor.execute(sql, params)
        results = [dict(row) for row in cursor.fetchall()]
        results = self._fill_lexical_matches(
            cursor,
            results,
            query=query,
            limit=limit,
            session_id=session_id,
        )
        conn.close()
        return results

    def _fill_lexical_matches(
        self,
        cursor: sqlite3.Cursor,
        results: list[dict],
        *,
        query: str,
        limit: int,
        session_id: str | None,
    ) -> list[dict]:
        terms = set(self._query_terms(query))
        if not terms:
            return results
        seen = {str(row.get("id")) for row in results}
        sql = "SELECT id, timestamp, event_type, role, content, session_id FROM events_fts"
        params: list[object] = []
        if session_id:
            sql += " WHERE session_id = ?"
            params.append(session_id)
        candidates: list[dict] = []
        for row in cursor.execute(sql, params).fetchall():
            item = dict(row)
            if str(item.get("id")) in seen:
                continue
            content_terms = set(self._query_terms(str(item.get("content") or "")))
            overlap = len(terms & content_terms)
            if overlap <= 0:
                continue
            item["score"] = -float(overlap)
            candidates.append(item)
        merged = [*results, *candidates]
        merged.sort(key=lambda item: float(item.get("score") or 0.0))
        return merged[:limit]

    @staticmethod
    def _query_terms(query: str) -> list[str]:
        return re.findall(r"[A-Za-z0-9_]+", query.lower())

    @staticmethod
    def _normalize_query(query: str) -> str:
        terms = FTSIndex._query_terms(query)
        if not terms:
            return ""
        return " OR ".join(f'"{term}"' for term in terms[:12])

    def rebuild_from_ledger(self, ledger_path: Path) -> None:
        """Rebuild the entire FTS index from the ledger."""
        self.clear()

        # Re-index all events
        with open(ledger_path) as f:
            for line in f:
                if line.strip():
                    event = Event.model_validate_json(line)
                    self.index_event(event)

    def clear(self) -> None:
        """Clear the FTS index without touching the append-only ledger."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("DELETE FROM events_fts")
        conn.commit()
        conn.close()
