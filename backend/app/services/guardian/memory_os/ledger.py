"""Append-only event ledger - stores every message and tool action as an event."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .schemas import Event, EventType


class Ledger:
    """Append-only event ledger stored as JSONL."""

    def __init__(self, data_dir: str | Path | None = None):
        """Initialize ledger with data directory."""
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data" / "memory"
        self.data_dir = Path(data_dir)
        self.ledger_path = self.data_dir / "ledger.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.ledger_path.exists():
            self.ledger_path.touch()

    def append(self, event: Event) -> None:
        """Append an event to the ledger."""
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(event.model_dump_json() + "\n")

    def log_message(self, role: str, content: str, session_id: str | None = None, turn: int | None = None) -> Event:
        """Log a message event."""
        event = Event(
            type=EventType.MESSAGE,
            role=role,
            content=content,
            session_id=session_id,
            turn=turn
        )
        self.append(event)
        return event

    def log_tool(self, tool_name: str, args: dict, result: str | None = None, session_id: str | None = None) -> Event:
        """Log a tool call event."""
        event = Event(
            type=EventType.TOOL_CALL,
            content=f"{tool_name}({args})",
            metadata={"tool_name": tool_name, "args": args, "result": result},
            session_id=session_id
        )
        self.append(event)
        return event

    def log_thought(self, thought: str, session_id: str | None = None, turn: int | None = None) -> Event:
        """Log an internal thought."""
        event = Event(
            type=EventType.THOUGHT,
            content=thought,
            session_id=session_id,
            turn=turn
        )
        self.append(event)
        return event

    def iter_events(self, limit: int | None = None, session_id: str | None = None) -> Iterator[Event]:
        """Iterate over events, optionally filtered by session."""
        count = 0
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                if limit and count >= limit:
                    break
                if line.strip():
                    event = Event.model_validate_json(line)
                    if session_id is None or event.session_id == session_id:
                        yield event
                        count += 1

    def get_recent(self, n: int = 10, session_id: str | None = None) -> list[Event]:
        """Get the N most recent events."""
        events = list(self.iter_events(session_id=session_id))
        return events[-n:] if len(events) > n else events
