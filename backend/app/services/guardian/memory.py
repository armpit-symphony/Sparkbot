"""Sparkbot adapter for vendored Memory Guardian modules."""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .memory_os.api import MemoryGuardian
from .memory_os.config import Config
from .memory_os.schemas import Event, EventType

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "memory_guardian"
_NO_CONTEXT_MARKER = "<!-- No relevant context found -->"
_SNAPSHOT_DIRNAME = "snapshots"
_MAX_LEARNED_FACTS = 8
_MAX_RECENT_FOCUS = 3
_MAX_ACTIVE_TOOLS = 4

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|access_key|credential|auth_token|passphrase|private_key)",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?){2}\d{4}(?!\d)")
_LONG_NUMBER_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_TOKEN_RE = re.compile(r"\b(?:sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|xoxb-[A-Za-z0-9\-]{10,}|secret_[A-Za-z0-9]{16,})\b")
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----")
_SECRET_PAIR_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|auth[_-]?token|passphrase|private[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)
_NAME_PATTERNS: tuple[tuple[str, float, re.Pattern[str]], ...] = (
    ("identity", 2.2, re.compile(r"\bcall me ([A-Za-z][A-Za-z0-9' -]{1,40})\b", re.IGNORECASE)),
    ("identity", 2.0, re.compile(r"\bmy name is ([A-Za-z][A-Za-z0-9' -]{1,40})\b", re.IGNORECASE)),
)
_FACT_PATTERNS: tuple[tuple[str, float, re.Pattern[str], str], ...] = (
    ("preference", 1.8, re.compile(r"\bi prefer ([^.!,;\n]{2,90})", re.IGNORECASE), "User prefers {value}"),
    ("timezone", 1.7, re.compile(r"\bmy timezone is ([A-Za-z0-9_/\-+]{2,60})\b", re.IGNORECASE), "User timezone is {value}"),
    ("project", 1.6, re.compile(r"\bi(?: am|'m)? working on ([^.!,;\n]{2,100})", re.IGNORECASE), "User is working on {value}"),
    ("focus", 1.5, re.compile(r"\bi(?: am|'m)? focused on ([^.!,;\n]{2,100})", re.IGNORECASE), "User is focused on {value}"),
    ("workflow", 1.4, re.compile(r"\bi use ([^.!,;\n]{2,80}) for work\b", re.IGNORECASE), "User uses {value} for work"),
)
_TOOL_LABELS = {
    "web_search": "web research",
    "github_get_pr": "GitHub PR review",
    "github_list_prs": "GitHub PR triage",
    "calendar_list_events": "calendar review",
    "calendar_create_event": "calendar scheduling",
    "gmail_fetch_inbox": "Gmail triage",
    "gmail_search": "Gmail search",
    "list_tasks": "task review",
    "create_task": "task capture",
    "complete_task": "task completion",
}


def memory_guardian_enabled() -> bool:
    return os.getenv("SPARKBOT_MEMORY_GUARDIAN_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _max_context_tokens() -> int:
    raw = os.getenv("SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS", "1200").strip()
    try:
        return max(256, min(int(raw), 8000))
    except ValueError:
        return 1200


def _retrieve_limit() -> int:
    raw = os.getenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT", "6").strip()
    try:
        return max(1, min(int(raw), 25))
    except ValueError:
        return 6


def _data_dir() -> Path:
    configured = os.getenv("SPARKBOT_MEMORY_GUARDIAN_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_DATA_DIR


def _snapshot_dir() -> Path:
    path = _data_dir() / _SNAPSHOT_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_path(user_id: str, room_id: str) -> Path:
    return _snapshot_dir() / f"user_{user_id}__room_{room_id}.json"


@lru_cache(maxsize=1)
def _guardian() -> MemoryGuardian:
    return MemoryGuardian(
        Config(
            data_dir=str(_data_dir()),
            max_context_tokens=_max_context_tokens(),
            enable_embeddings=False,
        )
    )


def _user_session(user_id: str) -> str:
    return f"user:{user_id}"


def _room_session(user_id: str, room_id: str) -> str:
    return f"room:{room_id}:user:{user_id}"


def _safe_text(value: str, limit: int = 4000) -> str:
    text = " ".join((value or "").split()).strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _redact_sensitive_text(text: str) -> str:
    text = _TOKEN_RE.sub("[REDACTED_TOKEN]", text)
    text = _PRIVATE_KEY_RE.sub("[REDACTED_PRIVATE_KEY]", text)
    text = _SECRET_PAIR_RE.sub(r"\1\2[REDACTED]", text)
    text = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    text = _PHONE_RE.sub("[REDACTED_PHONE]", text)
    text = _LONG_NUMBER_RE.sub("[REDACTED_NUMBER]", text)
    return text


def _contains_sensitive_content(text: str) -> bool:
    return any(
        pattern.search(text)
        for pattern in (
            _EMAIL_RE,
            _PHONE_RE,
            _LONG_NUMBER_RE,
            _TOKEN_RE,
            _PRIVATE_KEY_RE,
            _SECRET_PAIR_RE,
        )
    )


def _sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if _SECRET_KEY_RE.search(str(key)):
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = _sanitize_metadata(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_metadata(item) for item in value]
    if isinstance(value, str):
        return _safe_text(_redact_sensitive_text(value), limit=1500)
    return value


def _normalize_fact_text(text: str) -> str:
    cleaned = _safe_text(text, limit=220)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    if not cleaned:
        return ""
    return cleaned[0].upper() + cleaned[1:]


def _fact_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _is_safe_fact(text: str) -> bool:
    if not text:
        return False
    if _contains_sensitive_content(text):
        return False
    return len(text) <= 220


def _extract_fact_candidates(text: str) -> list[tuple[str, str, float]]:
    candidates: list[tuple[str, str, float]] = []
    for category, weight, pattern in _NAME_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1).strip()
            fact = _normalize_fact_text(f"User goes by {value}")
            if _is_safe_fact(fact):
                candidates.append((fact, category, weight))
    for category, weight, pattern, template in _FACT_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(1).strip(" .,:;")
            fact = _normalize_fact_text(template.format(value=value))
            if _is_safe_fact(fact):
                candidates.append((fact, category, weight))
    return candidates


def _score_fact(*, mentions: int, weight: float, last_seen: datetime) -> float:
    now = datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    age_days = max((now - last_seen).total_seconds() / 86400.0, 0.0)
    recency_penalty = min(age_days * 0.15, 1.5)
    return round(weight + (mentions * 0.7) - recency_penalty, 2)


def _build_profile_snapshot(*, user_id: str, room_id: str) -> dict[str, Any]:
    guardian = _guardian()
    user_events = list(guardian.ledger.iter_events(session_id=_user_session(user_id)))
    room_events = list(guardian.ledger.iter_events(session_id=_room_session(user_id, room_id)))

    fact_state: dict[str, dict[str, Any]] = {}
    for event in user_events:
        if event.type == EventType.SYSTEM and event.content.startswith("FACT:"):
            fact = _normalize_fact_text(event.content.removeprefix("FACT:").strip())
            if not _is_safe_fact(fact):
                continue
            key = _fact_key(fact)
            state = fact_state.setdefault(
                key,
                {"fact": fact, "category": "explicit", "mentions": 0, "weight": 2.6, "last_seen": event.timestamp},
            )
            state["mentions"] += 1
            state["last_seen"] = max(state["last_seen"], event.timestamp)

    for event in room_events:
        if event.type == EventType.MESSAGE and event.role == "user":
            for fact, category, weight in _extract_fact_candidates(event.content):
                key = _fact_key(fact)
                state = fact_state.setdefault(
                    key,
                    {"fact": fact, "category": category, "mentions": 0, "weight": weight, "last_seen": event.timestamp},
                )
                state["mentions"] += 1
                state["weight"] = max(state["weight"], weight)
                state["last_seen"] = max(state["last_seen"], event.timestamp)

    learned_facts: list[dict[str, Any]] = []
    for state in fact_state.values():
        score = _score_fact(
            mentions=state["mentions"],
            weight=state["weight"],
            last_seen=state["last_seen"],
        )
        if score < 1.6:
            continue
        learned_facts.append(
            {
                "fact": state["fact"],
                "category": state["category"],
                "mentions": state["mentions"],
                "score": score,
                "last_seen": state["last_seen"].isoformat(),
            }
        )
    learned_facts.sort(key=lambda item: (-item["score"], item["fact"]))
    learned_facts = learned_facts[:_MAX_LEARNED_FACTS]

    tool_counts: dict[str, int] = {}
    for event in room_events[-20:]:
        if event.type != EventType.TOOL_CALL:
            continue
        tool_name = str(event.metadata.get("tool_name") or "").strip()
        if not tool_name:
            continue
        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
    active_tools = [
        {
            "tool_name": tool_name,
            "label": _TOOL_LABELS.get(tool_name, tool_name.replace("_", " ")),
            "count": count,
        }
        for tool_name, count in sorted(tool_counts.items(), key=lambda item: (-item[1], item[0]))[:_MAX_ACTIVE_TOOLS]
    ]

    recent_focus: list[str] = []
    for event in reversed(room_events):
        if event.type == EventType.MESSAGE and event.role == "user":
            snippet = _safe_text(event.content, limit=140)
            if snippet and snippet not in recent_focus:
                recent_focus.append(snippet)
            if len(recent_focus) >= _MAX_RECENT_FOCUS:
                break

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "room_id": room_id,
        "learned_facts": learned_facts,
        "active_tools": active_tools,
        "recent_focus": recent_focus,
    }


def _persist_profile_snapshot(*, user_id: str, room_id: str, snapshot: dict[str, Any]) -> None:
    _snapshot_path(user_id, room_id).write_text(json.dumps(snapshot, indent=2), encoding="utf-8")


def _append_event(
    *,
    event_type: EventType,
    content: str,
    session_id: str,
    role: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    if not memory_guardian_enabled():
        return False

    text = _safe_text(_redact_sensitive_text(content))
    if not text:
        return False

    event = Event(
        type=event_type,
        role=role,
        content=text,
        session_id=session_id,
        metadata=_sanitize_metadata(metadata or {}),
    )
    guardian = _guardian()
    guardian.ledger.append(event)
    guardian.fts.index_event(event)
    return True


def remember_chat_message(*, user_id: str, room_id: str, role: str, content: str) -> bool:
    stored = _append_event(
        event_type=EventType.MESSAGE,
        role=role,
        content=content,
        session_id=_room_session(user_id, room_id),
        metadata={"user_id": user_id, "room_id": room_id},
    )
    if stored:
        try:
            _persist_profile_snapshot(
                user_id=user_id,
                room_id=room_id,
                snapshot=_build_profile_snapshot(user_id=user_id, room_id=room_id),
            )
        except Exception:
            pass
    return stored


def remember_tool_event(
    *,
    user_id: str,
    room_id: str,
    tool_name: str,
    args: dict[str, Any],
    result: str = "",
) -> bool:
    payload = {
        "tool_name": tool_name,
        "args": _sanitize_metadata(args),
        "result": _safe_text(_redact_sensitive_text(result), limit=1500),
    }
    stored = _append_event(
        event_type=EventType.TOOL_CALL,
        role="system",
        content=f"{tool_name}({json.dumps(_sanitize_metadata(args), sort_keys=True)})",
        session_id=_room_session(user_id, room_id),
        metadata=payload,
    )
    if stored:
        try:
            _persist_profile_snapshot(
                user_id=user_id,
                room_id=room_id,
                snapshot=_build_profile_snapshot(user_id=user_id, room_id=room_id),
            )
        except Exception:
            pass
    return stored


def remember_fact(*, user_id: str, fact: str, memory_id: str = "") -> bool:
    metadata = {"user_id": user_id}
    if memory_id:
        metadata["memory_id"] = memory_id
    return _append_event(
        event_type=EventType.SYSTEM,
        role="system",
        content=f"FACT: {_safe_text(fact, limit=500)}",
        session_id=_user_session(user_id),
        metadata=metadata,
    )


def build_memory_context(*, user_id: str, room_id: str, query: str) -> str:
    if not memory_guardian_enabled():
        return ""

    prompt_query = _safe_text(query, limit=500)
    if not prompt_query:
        return ""

    blocks: list[str] = []
    try:
        snapshot = _build_profile_snapshot(user_id=user_id, room_id=room_id)
        _persist_profile_snapshot(user_id=user_id, room_id=room_id, snapshot=snapshot)
    except Exception:
        snapshot = {}

    learned_facts = snapshot.get("learned_facts") or []
    if learned_facts:
        lines = [f"- {item['fact']}" for item in learned_facts]
        blocks.append("## Learned User Profile\n" + "\n".join(lines))

    active_tools = snapshot.get("active_tools") or []
    recent_focus = snapshot.get("recent_focus") or []
    workflow_lines: list[str] = []
    if active_tools:
        workflow_lines.append(
            "- Recent tools: "
            + ", ".join(f"{item['label']} x{item['count']}" for item in active_tools)
        )
    if recent_focus:
        workflow_lines.extend(f"- Recent focus: {snippet}" for snippet in recent_focus)
    if workflow_lines:
        blocks.append("## Active Workflow Memory\n" + "\n".join(workflow_lines))

    guardian = _guardian()
    limit = _retrieve_limit()
    user_block = guardian.get_context(prompt_query, limit=limit, session_id=_user_session(user_id)).strip()
    room_block = guardian.get_context(prompt_query, limit=limit, session_id=_room_session(user_id, room_id)).strip()

    if user_block and user_block != _NO_CONTEXT_MARKER:
        blocks.append("## Durable Memory\n" + user_block)
    if room_block and room_block != _NO_CONTEXT_MARKER:
        blocks.append("## Relevant Room Memory\n" + room_block)
    return "\n\n".join(blocks)


def delete_fact_memory(*, user_id: str, memory_id: str) -> int:
    if not memory_guardian_enabled():
        return 0

    target_user_session = _user_session(user_id)
    guardian = _guardian()
    kept: list[Event] = []
    removed = 0
    for event in guardian.ledger.iter_events():
        if (
            event.session_id == target_user_session
            and str(event.metadata.get("memory_id", "")) == memory_id
        ):
            removed += 1
            continue
        kept.append(event)
    if removed:
        _rewrite_events(kept)
    return removed


def clear_user_memory_events(*, user_id: str) -> int:
    if not memory_guardian_enabled():
        return 0

    suffix = f":user:{user_id}"
    target_user_session = _user_session(user_id)
    guardian = _guardian()
    kept: list[Event] = []
    removed = 0
    for event in guardian.ledger.iter_events():
        session_id = event.session_id or ""
        if session_id == target_user_session or session_id.endswith(suffix):
            removed += 1
            continue
        kept.append(event)
    if removed:
        _rewrite_events(kept)
    return removed


def _rewrite_events(events: list[Event]) -> None:
    guardian = _guardian()
    guardian.ledger.ledger_path.write_text("", encoding="utf-8")
    for event in events:
        guardian.ledger.append(event)
    guardian.fts.rebuild_from_ledger(guardian.ledger.ledger_path)
