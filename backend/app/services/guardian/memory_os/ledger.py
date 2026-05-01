"""Append-only event ledger - stores hot events and searchable cold archives."""

import gzip
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

    @property
    def archive_dir(self) -> Path:
        path = self.data_dir / "archive"
        path.mkdir(parents=True, exist_ok=True)
        return path

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

    def _iter_jsonl_path(self, path: Path) -> Iterator[Event]:
        opener = gzip.open if path.suffix == ".gz" else open
        mode = "rt" if path.suffix == ".gz" else "r"
        with opener(path, mode, encoding="utf-8") as f:  # type: ignore[arg-type]
            for line in f:
                if line.strip():
                    yield Event.model_validate_json(line)

    def iter_archived_events(
        self,
        *,
        limit: int | None = None,
        session_id: str | None = None,
    ) -> Iterator[Event]:
        """Iterate cold archived events, newest archive file first."""
        count = 0
        paths = sorted(
            [*self.archive_dir.glob("ledger-*.jsonl"), *self.archive_dir.glob("ledger-*.jsonl.gz")],
            reverse=True,
        )
        for path in paths:
            for event in self._iter_jsonl_path(path):
                if session_id is not None and event.session_id != session_id:
                    continue
                yield event
                count += 1
                if limit and count >= limit:
                    return

    def iter_events(
        self,
        limit: int | None = None,
        session_id: str | None = None,
        *,
        include_archives: bool = False,
    ) -> Iterator[Event]:
        """Iterate over hot events, optionally followed by cold archives."""
        count = 0
        for event in self._iter_jsonl_path(self.ledger_path):
            if limit and count >= limit:
                break
            if session_id is None or event.session_id == session_id:
                yield event
                count += 1
        if include_archives and (not limit or count < limit):
            remaining = None if limit is None else limit - count
            yield from self.iter_archived_events(limit=remaining, session_id=session_id)

    def get_recent(
        self,
        n: int = 10,
        session_id: str | None = None,
        *,
        include_archives: bool = False,
    ) -> list[Event]:
        """Get the N most recent events."""
        events = list(self.iter_events(session_id=session_id, include_archives=include_archives))
        return events[-n:] if len(events) > n else events
