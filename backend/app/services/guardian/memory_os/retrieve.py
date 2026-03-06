"""Retrieval and context packing - turns retrieval results into a bounded prompt block."""

from typing import Iterator

from .index_embed import EmbedIndex
from .index_fts import FTSIndex
from .ledger import Ledger
from .schemas import Event


class Retriever:
    """Retrieves relevant context from memory."""

    def __init__(self, data_dir: str | None = None):
        """Initialize retriever with ledger and indexes."""
        self.ledger = Ledger(data_dir)
        self.fts = FTSIndex(data_dir)
        self.embed = EmbedIndex(data_dir)

    def retrieve(self, query: str, limit: int = 10, hybrid: bool = True, session_id: str | None = None) -> list[Event]:
        """Hybrid retrieval: FTS + embeddings."""
        results = []
        
        # FTS results
        fts_results = self.fts.search(query, limit=limit, session_id=session_id)
        fts_ids = {r["id"] for r in fts_results}
        
        # Load full events for FTS results
        for fts_result in fts_results:
            event = self._load_event(fts_result["id"])
            if event:
                results.append(event)
        
        # Embedding results (if available and hybrid)
        if hybrid and self.embed.is_available():
            embed_results = self.embed.search(query, limit=limit)
            embed_ids = {r["id"] for r in embed_results}
            
            # Merge, avoiding duplicates
            for embed_result in embed_results:
                if embed_result["id"] not in fts_ids:
                    event = self._load_event(embed_result["id"])
                    if event:
                        results.append(event)
        
        return results[:limit]

    def _load_event(self, event_id: str) -> Event | None:
        """Load a single event by ID."""
        for event in self.ledger.iter_events():
            if event.id == event_id:
                return event
        return None

    def get_recent(self, n: int = 10, session_id: str | None = None) -> list[Event]:
        """Get N most recent events."""
        return self.ledger.get_recent(n=n, session_id=session_id)


class ContextPacker:
    """Packs retrieved context into a bounded prompt block."""

    def __init__(self, max_tokens: int = 4000):
        """Initialize with token budget."""
        self.max_tokens = max_tokens
        # Rough estimate: 1 token ≈ 4 characters
        self.char_budget = max_tokens * 4

    def pack(self, events: list[Event], include_metadata: bool = False) -> str:
        """Pack events into a context block."""
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
            
            # Check budget
            if len(context) > self.char_budget:
                context += f"\n<!-- ... {len(events) - i - 1} more events truncated -->\n"
                break
        
        context += "\n<!-- MEMORY_CONTEXT_END -->\n"
        return context

    def pack_query(self, query: str, retriever: Retriever, limit: int = 10, session_id: str | None = None) -> str:
        """Retrieve and pack in one call."""
        events = retriever.retrieve(query, limit=limit, session_id=session_id)
        return self.pack(events)
