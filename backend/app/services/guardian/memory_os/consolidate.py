"""Consolidation job - extracts durable facts and rolling summaries."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .index_embed import text_similarity
from .ledger import Ledger
from .schemas import Event, EventType

_FACT_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("identity", "User goes by {value}", re.compile(r"\b(?:call me|my name is)\s+([A-Za-z][A-Za-z0-9' -]{1,40})\b", re.IGNORECASE)),
    ("employment", "User works at {value}", re.compile(r"\b(?:i work at|i work for|my company is)\s+([A-Za-z0-9 ._-]{2,80}?)(?=\s+(?:and|but)\b|[.;,\n]|$)", re.IGNORECASE)),
    ("preference", "User prefers {value}", re.compile(r"\b(?:i prefer|my preference is)\s+([^.;,\n]{2,100})", re.IGNORECASE)),
    ("timezone", "User timezone is {value}", re.compile(r"\bmy timezone is\s+([A-Za-z0-9_/\-+]{2,60})\b", re.IGNORECASE)),
    ("project", "User is working on {value}", re.compile(r"\bi(?: am|'m)? working on\s+([^.!,;\n]{2,100})", re.IGNORECASE)),
    ("focus", "User is focused on {value}", re.compile(r"\bi(?: am|'m)? focused on\s+([^.!,;\n]{2,100})", re.IGNORECASE)),
    ("workflow", "User uses {value} for work", re.compile(r"\bi use\s+([^.!,;\n]{2,80})\s+for work\b", re.IGNORECASE)),
)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _clean_text(value: str, *, limit: int = 220) -> str:
    text = " ".join((value or "").split()).strip(" .,:;")
    return text[:limit].rstrip() if len(text) > limit else text


def _fact_key(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _safe_fact(value: str) -> str:
    fact = _clean_text(value)
    if not fact:
        return ""
    return fact[0].upper() + fact[1:]


def _event_user_id(event: Event) -> str:
    return str((event.metadata or {}).get("user_id") or "")


def _user_session(user_id: str) -> str:
    return f"user:{user_id}"


def _extract_message_facts(event: Event) -> list[dict[str, str]]:
    content = event.content or ""
    user_id = _event_user_id(event)
    if not user_id:
        return []
    facts: list[dict[str, str]] = []
    for category, template, pattern in _FACT_PATTERNS:
        for match in pattern.finditer(content):
            value = _clean_text(match.group(1), limit=120)
            fact = _safe_fact(template.format(value=value))
            if fact and len(fact) <= 220:
                facts.append({"fact": fact, "category": category, "user_id": user_id})
    return facts


def _existing_fact_text(event: Event) -> str:
    if event.type == EventType.SYSTEM and event.content.startswith("FACT:"):
        return _safe_fact(event.content.removeprefix("FACT:").strip())
    return ""


def _is_duplicate_fact(candidate: str, existing: list[str], threshold: float) -> bool:
    candidate_key = _fact_key(candidate)
    for fact in existing:
        if _fact_key(fact) == candidate_key:
            return True
        if text_similarity(candidate, fact) >= threshold:
            return True
    return False


def _summary_line(event: Event) -> str:
    content = _clean_text(event.content, limit=140)
    role = event.role or event.type.value
    return f"- {role}: {content}" if content else ""


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
            date = datetime.now(timezone.utc)
        return self.daily_dir / f"{date.strftime('%Y-%m-%d')}.md"

    def extract_facts(self, events: list[Event]) -> list[str]:
        """Extract durable facts from events."""
        facts = []
        for event in events:
            facts.extend(item["fact"] for item in _extract_message_facts(event))
            if event.type == EventType.DECISION:
                facts.append(f"Decision: {_clean_text(event.content, limit=180)}")
        return facts

    def create_summary(self, events: list[Event]) -> str:
        """Create a rolling summary of recent events."""
        if not events:
            return "No events to summarize."

        user_msgs = [e for e in events if e.role == "user"]
        assistant_msgs = [e for e in events if e.role == "assistant"]
        tool_calls = [e for e in events if e.type == EventType.TOOL_CALL]

        summary = f"""## Session Summary - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}

**Events:** {len(events)}
- User messages: {len(user_msgs)}
- Assistant messages: {len(assistant_msgs)}
- Tool calls: {len(tool_calls)}

**Recent context:**
"""
        for msg in user_msgs[-3:]:
            line = _summary_line(msg)
            if line:
                summary += f"{line}\n"

        return summary

    def consolidate_recent(
        self,
        ledger: Ledger,
        *,
        lookback_hours: int = 24,
        window_size: int = 10,
        facts_per_window: int = 3,
        similarity_threshold: float = 0.85,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Consolidate the last day into durable facts and a daily markdown summary."""
        now = _aware(now or datetime.now(timezone.utc))
        cutoff = now - timedelta(hours=max(1, min(int(lookback_hours), 24 * 14)))
        messages = [
            event
            for event in ledger.iter_events()
            if event.type == EventType.MESSAGE
            and event.role == "user"
            and event.timestamp
            and _aware(event.timestamp) >= cutoff
        ]
        existing_facts = [
            fact
            for event in ledger.iter_events(include_archives=True)
            if (fact := _existing_fact_text(event))
        ]

        emitted: list[dict[str, str]] = []
        windows_processed = 0
        effective_window = max(1, int(window_size))
        for start in range(0, len(messages), effective_window):
            window = messages[start:start + effective_window]
            if not window:
                continue
            windows_processed += 1
            window_facts: list[dict[str, str]] = []
            for event in window:
                window_facts.extend(_extract_message_facts(event))
            for item in window_facts[:max(1, min(int(facts_per_window), 5))]:
                fact = item["fact"]
                if _is_duplicate_fact(fact, existing_facts, similarity_threshold):
                    continue
                user_id = item["user_id"]
                ledger.append(
                    Event(
                        type=EventType.SYSTEM,
                        role="system",
                        content=f"FACT: {fact}",
                        session_id=_user_session(user_id),
                        metadata={
                            "user_id": user_id,
                            "source": "memory.consolidation",
                            "memory_type": item["category"],
                            "scope_type": "user",
                            "lifecycle_state": "active",
                            "verification_state": "recorded",
                            "confidence": 0.78,
                            "recorded_at": now.isoformat(),
                        },
                    )
                )
                existing_facts.append(fact)
                emitted.append(item)

        daily_path = self._get_daily_path(now)
        with daily_path.open("a", encoding="utf-8") as f:
            f.write(f"\n## Memory Consolidation - {now.strftime('%Y-%m-%d %H:%M UTC')}\n\n")
            f.write(f"- Messages scanned: {len(messages)}\n")
            f.write(f"- Windows processed: {windows_processed}\n")
            f.write(f"- Durable facts written: {len(emitted)}\n")
            if messages:
                f.write("\n### Recent Conversation\n")
                for event in messages[-10:]:
                    line = _summary_line(event)
                    if line:
                        f.write(f"{line}\n")
            if emitted:
                f.write("\n### Durable Facts\n")
                for item in emitted:
                    f.write(f"- {item['fact']}\n")

        return {
            "status": "success",
            "lookback_hours": lookback_hours,
            "messages_scanned": len(messages),
            "windows_processed": windows_processed,
            "facts_extracted": len(emitted),
            "daily_file": str(daily_path),
        }

    def consolidate(self, ledger: Ledger, session_id: str | None = None) -> dict:
        """Run consolidation job on the ledger."""
        events = list(ledger.iter_events(session_id=session_id))

        if not events:
            return {"status": "no_events", "facts": [], "summary": ""}

        facts = self.extract_facts(events)
        summary = self.create_summary(events)

        daily_path = self._get_daily_path()
        with open(daily_path, "a", encoding="utf-8") as f:
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
            "daily_file": str(daily_path),
        }

    def get_daily_summary(self, date: datetime | None = None) -> str | None:
        """Get the daily summary for a specific date."""
        daily_path = self._get_daily_path(date)
        if daily_path.exists():
            return daily_path.read_text(encoding="utf-8")
        return None
