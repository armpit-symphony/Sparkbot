"""Retrieval and context packing.

The retriever has three retrieval modes:

- ``"fts"``     — pure SQLite FTS5 (BM25) search.  Default; cheap, keyword based.
- ``"embed"``   — hashing-trick cosine similarity over stored embeddings.
- ``"hybrid"``  — pull a candidate pool from FTS + embeddings, rerank by a
                  weighted sum of normalised scores.  This is the recommended
                  mode for self-learning Sparkbot recall.

The mode can be overridden per-call, or globally via the
``SPARKBOT_MEMORY_GUARDIAN_RETRIEVER`` env var (read by the Sparkbot adapter).
"""

from __future__ import annotations

from typing import Iterable

from .index_embed import EmbedIndex
from .index_fts import FTSIndex
from .ledger import Ledger
from .schemas import Event


_VALID_MODES = {"fts", "embed", "hybrid"}


def _normalise(scores: list[float]) -> list[float]:
    if not scores:
        return scores
    lo = min(scores)
    hi = max(scores)
    if hi - lo < 1e-9:
        return [1.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


class Retriever:
    """Retrieves relevant context from memory."""

    def __init__(self, data_dir: str | None = None):
        self.ledger = Ledger(data_dir)
        self.fts = FTSIndex(data_dir)
        self.embed = EmbedIndex(data_dir)
        self._event_cache: dict[str, Event] = {}
        self._cache_loaded = False

    # ── Cache helpers ----------------------------------------------------

    def _load_cache(self) -> None:
        if self._cache_loaded:
            return
        for event in self.ledger.iter_events():
            self._event_cache[event.id] = event
        self._cache_loaded = True

    def _reload_cache(self) -> None:
        self._cache_loaded = False
        self._event_cache.clear()
        self._load_cache()

    def _load_event(self, event_id: str) -> Event | None:
        self._load_cache()
        return self._event_cache.get(event_id)

    # ── Public API -------------------------------------------------------

    def retrieve(
        self,
        query: str,
        limit: int = 10,
        hybrid: bool = True,
        session_id: str | None = None,
        mode: str | None = None,
    ) -> list[Event]:
        """Retrieve up to ``limit`` events matching ``query``.

        ``mode`` overrides the legacy ``hybrid`` flag when supplied.
        """
        if mode is None:
            mode = "hybrid" if hybrid else "fts"
        if mode not in _VALID_MODES:
            mode = "hybrid"

        if mode == "fts":
            return self._fts_only(query, limit, session_id)
        if mode == "embed":
            return self._embed_only(query, limit, session_id)
        return self._hybrid(query, limit, session_id)

    def retrieve_scored(
        self,
        query: str,
        limit: int = 10,
        session_id: str | None = None,
        mode: str = "hybrid",
    ) -> list[tuple[Event, float]]:
        """Same as :meth:`retrieve` but also returns the rerank score."""
        if mode == "fts":
            results = self.fts.search(query, limit=limit, session_id=session_id)
            scored: list[tuple[Event, float]] = []
            # bm25 scores are negative — smaller = more relevant.  Flip + normalise.
            raw = [-float(r.get("score") or 0.0) for r in results]
            norm = _normalise(raw)
            for r, n in zip(results, norm):
                event = self._load_event(r["id"])
                if event is not None:
                    scored.append((event, float(n)))
            return scored

        if mode == "embed":
            results = self.embed.search(query, limit=limit, session_id=session_id)
            scored = []
            for r in results:
                event = self._load_event(r["id"])
                if event is not None:
                    scored.append((event, float(r["score"])))
            return scored

        # hybrid
        return self._hybrid_scored(query, limit, session_id)

    # ── Mode implementations --------------------------------------------

    def _fts_only(self, query: str, limit: int, session_id: str | None) -> list[Event]:
        results = self.fts.search(query, limit=limit, session_id=session_id)
        events: list[Event] = []
        for r in results:
            event = self._load_event(r["id"])
            if event is not None:
                events.append(event)
        return events

    def _embed_only(self, query: str, limit: int, session_id: str | None) -> list[Event]:
        results = self.embed.search(query, limit=limit, session_id=session_id)
        events: list[Event] = []
        for r in results:
            event = self._load_event(r["id"])
            if event is not None:
                events.append(event)
        return events

    def _hybrid(self, query: str, limit: int, session_id: str | None) -> list[Event]:
        return [event for event, _ in self._hybrid_scored(query, limit, session_id)]

    def _hybrid_scored(
        self, query: str, limit: int, session_id: str | None
    ) -> list[tuple[Event, float]]:
        pool = max(limit * 4, 25)

        fts_results = self.fts.search(query, limit=pool, session_id=session_id)
        fts_raw = [-float(r.get("score") or 0.0) for r in fts_results]
        fts_norm = _normalise(fts_raw)

        scores: dict[str, float] = {}
        for r, n in zip(fts_results, fts_norm):
            scores[r["id"]] = scores.get(r["id"], 0.0) + 0.55 * n

        if self.embed.is_available():
            embed_results = self.embed.search(query, limit=pool, session_id=session_id)
            embed_raw = [float(r["score"]) for r in embed_results]
            embed_norm = _normalise(embed_raw)
            for r, n in zip(embed_results, embed_norm):
                scores[r["id"]] = scores.get(r["id"], 0.0) + 0.45 * n

        if not scores:
            return []

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        out: list[tuple[Event, float]] = []
        for event_id, score in ranked:
            event = self._load_event(event_id)
            if event is None:
                continue
            out.append((event, float(score)))
            if len(out) >= limit:
                break
        return out

    # ── Recent / convenience --------------------------------------------

    def get_recent(self, n: int = 10, session_id: str | None = None) -> list[Event]:
        return self.ledger.get_recent(n=n, session_id=session_id)


class ContextPacker:
    """Packs retrieved context into a bounded prompt block."""

    def __init__(self, max_tokens: int = 4000):
        self.max_tokens = max_tokens
        # Rough estimate: 1 token ≈ 4 characters
        self.char_budget = max_tokens * 4

    def pack(self, events: list[Event], include_metadata: bool = False) -> str:
        if not events:
            return "<!-- No relevant context found -->"

        context = "<!-- MEMORY_CONTEXT_START -->\n"
        context += f"<!-- {len(events)} events retrieved -->\n\n"

        for i, event in enumerate(events):
            timestamp = event.timestamp.strftime("%H:%M")
            role = event.role or event.type.value

            context += f"[{timestamp}] {role}: {event.content}\n"

            if include_metadata and event.metadata:
                context += f"  <!-- metadata: {event.metadata} -->\n"

            if len(context) > self.char_budget:
                context += f"\n<!-- ... {len(events) - i - 1} more events truncated -->\n"
                break

        context += "\n<!-- MEMORY_CONTEXT_END -->\n"
        return context

    def pack_query(
        self,
        query: str,
        retriever: Retriever,
        limit: int = 10,
        session_id: str | None = None,
        mode: str | None = None,
    ) -> str:
        events = retriever.retrieve(query, limit=limit, session_id=session_id, mode=mode)
        return self.pack(events)
