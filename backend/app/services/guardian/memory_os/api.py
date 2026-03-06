"""Tiny API surface for Memory Guardian - the main interface for bots."""

from .config import Config
from .consolidate import Consolidator
from .index_fts import FTSIndex
from .ledger import Ledger
from .retrieve import ContextPacker, Retriever
from .schemas import Event, EventType


class MemoryGuardian:
    """Main API for Memory Guardian - use this in your bot."""

    def __init__(self, config: Config | None = None):
        """Initialize Memory Guardian with optional config."""
        self.config = config or Config()
        self.ledger = Ledger(self.config.data_dir)
        self.fts = FTSIndex(self.config.data_dir)
        self.consolidator = Consolidator(self.config.data_dir)
        self.retriever = Retriever(self.config.data_dir)
        self.packer = ContextPacker(self.config.max_context_tokens)

    def remember(
        self,
        content: str,
        role: str = "system",
        event_type: EventType = EventType.MESSAGE,
        session_id: str | None = None,
        turn: int | None = None,
    ) -> Event:
        """Store something in memory."""
        event = Event(
            type=event_type,
            role=role,
            content=content,
            session_id=session_id,
            turn=turn
        )
        self.ledger.append(event)
        # Index for search
        self.fts.index_event(event)
        return event

    def remember_message(self, role: str, content: str, session_id: str | None = None, turn: int | None = None) -> Event:
        """Convenience: remember a chat message."""
        return self.remember(content, role, EventType.MESSAGE, session_id, turn)

    def remember_tool(self, tool_name: str, args: dict, result: str | None = None, session_id: str | None = None) -> Event:
        """Convenience: remember a tool call."""
        return self.remember(
            f"{tool_name}({args})",
            event_type=EventType.TOOL_CALL,
            session_id=session_id
        )

    def remember_thought(self, thought: str, session_id: str | None = None, turn: int | None = None) -> Event:
        """Convenience: remember an internal thought."""
        return self.remember(thought, "assistant", EventType.THOUGHT, session_id, turn)

    def recall(self, query: str, limit: int = 10) -> list[Event]:
        """Search memory for relevant context."""
        return self.retriever.retrieve(query, limit=limit)

    def recall_recent(self, n: int = 10, session_id: str | None = None) -> list[Event]:
        """Get the N most recent memories."""
        return self.retriever.get_recent(n=n, session_id=session_id)

    def get_context(self, query: str, limit: int = 10, session_id: str | None = None) -> str:
        """Get packed context block for injection into prompt."""
        return self.packer.pack_query(query, self.retriever, limit=limit, session_id=session_id)

    def consolidate(self, session_id: str | None = None) -> dict:
        """Run consolidation job - extract facts and create summaries."""
        return self.consolidator.consolidate(self.ledger, session_id)

    def status(self) -> dict:
        """Get memory status."""
        events = list(self.ledger.iter_events())
        return {
            "total_events": len(events),
            "data_dir": str(self.config.data_dir),
            "max_tokens": self.config.max_context_tokens,
        }
