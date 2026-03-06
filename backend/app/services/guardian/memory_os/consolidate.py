"""Consolidation job - extracts durable facts and rolling summaries."""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

from .ledger import Ledger
from .schemas import Event, EventType


class Consolidator:
    """Extracts durable facts and creates summaries."""

    def __init__(self, data_dir: str | Path | None = None):
        """Initialize consolidator."""
        if data_dir is None:
            data_dir = Path(__file__).parent.parent / "data"
        self.data_dir = Path(data_dir)
        self.daily_dir = self.data_dir / "daily"
        self.daily_dir.mkdir(parents=True, exist_ok=True)

    def _get_daily_path(self, date: datetime | None = None) -> Path:
        """Get the path for a daily summary file."""
        if date is None:
            date = datetime.utcnow()
        return self.daily_dir / f"{date.strftime('%Y-%m-%d')}.md"

    def extract_facts(self, events: list[Event]) -> list[str]:
        """Extract durable facts from events.
        
        Facts are things the agent should remember long-term:
        - User preferences mentioned
        - Important decisions made
        - Key information shared by user
        """
        facts = []
        for event in events:
            if event.type == EventType.MESSAGE and event.role == "user":
                # Simple heuristic: extract sentences with key info
                content = event.content.strip()
                # Placeholder - real implementation would use LLM or patterns
                if len(content) > 10:
                    facts.append(f"User said: {content[:100]}...")
            elif event.type == EventType.DECISION:
                facts.append(f"Decision: {event.content}")
        return facts

    def create_summary(self, events: list[Event]) -> str:
        """Create a rolling summary of recent events."""
        if not events:
            return "No events to summarize."
        
        user_msgs = [e for e in events if e.role == "user"]
        assistant_msgs = [e for e in events if e.role == "assistant"]
        tool_calls = [e for e in events if e.type == EventType.TOOL_CALL]
        
        summary = f"""## Session Summary - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}

**Events:** {len(events)}
- User messages: {len(user_msgs)}
- Assistant messages: {len(assistant_msgs)}
- Tool calls: {len(tool_calls)}

**Recent context:**
"""
        # Add last 3 user messages
        for msg in user_msgs[-3:]:
            summary += f"- User: {msg.content[:80]}...\n"
        
        return summary

    def consolidate(self, ledger: Ledger, session_id: str | None = None) -> dict:
        """Run consolidation job on the ledger."""
        # Get all events (or session-specific)
        events = list(ledger.iter_events(session_id=session_id))
        
        if not events:
            return {"status": "no_events", "facts": [], "summary": ""}
        
        # Extract facts
        facts = self.extract_facts(events)
        
        # Create summary
        summary = self.create_summary(events)
        
        # Save daily summary
        daily_path = self._get_daily_path()
        with open(daily_path, "a") as f:
            f.write(f"\n### Session {session_id or 'default'}\n")
            f.write(summary)
            if facts:
                f.write("\n### Facts Extracted\n")
                for fact in facts:
                    f.write(f"- {fact}\n")
        
        return {
            "status": "success",
            "events_processed": len(events),
            "facts_extracted": len(facts),
            "summary": summary,
            "daily_file": str(daily_path)
        }

    def get_daily_summary(self, date: datetime | None = None) -> str | None:
        """Get the daily summary for a specific date."""
        daily_path = self._get_daily_path(date)
        if daily_path.exists():
            return daily_path.read_text()
        return None
