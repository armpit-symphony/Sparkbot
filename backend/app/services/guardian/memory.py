"""Sparkbot adapter for vendored Memory Guardian modules."""

from __future__ import annotations

import json
import os
import re
import threading
import time
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
_VALID_RETRIEVER_MODES = {"fts", "embed", "hybrid"}

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


def _embeddings_enabled() -> bool:
    """Hybrid retrieval embedding writes are on by default — the in-process
    hashing-trick index has no external deps. Set to false to fall back to
    pure FTS."""
    raw = os.getenv("SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _retriever_mode() -> str:
    raw = (os.getenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVER", "hybrid") or "hybrid").strip().lower()
    if raw not in _VALID_RETRIEVER_MODES:
        return "hybrid"
    return raw


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
            enable_embeddings=_embeddings_enabled(),
        )
    )


# ── Telemetry --------------------------------------------------------------

class _RetrievalStats:
    """In-process counters for memory recall observability.

    Numbers are best-effort and reset when the backend restarts. Use
    ``memory_retrieval_stats()`` to inspect them or expose via a tool.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.writes = 0
        self.write_failures = 0
        self.recalls = 0
        self.empty_recalls = 0
        self.total_latency_ms = 0.0
        self.last_latency_ms = 0.0
        self.recalls_by_mode: dict[str, int] = {}
        self.last_query: str = ""
        self.last_mode: str = ""
        self.last_event_count: int = 0
        self.last_top_score: float = 0.0
        self.started_at = datetime.now(timezone.utc).isoformat()

    def record_write(self, *, ok: bool) -> None:
        with self._lock:
            if ok:
                self.writes += 1
            else:
                self.write_failures += 1

    def record_recall(
        self,
        *,
        mode: str,
        latency_ms: float,
        event_count: int,
        top_score: float,
        query: str,
    ) -> None:
        with self._lock:
            self.recalls += 1
            self.total_latency_ms += latency_ms
            self.last_latency_ms = latency_ms
            self.recalls_by_mode[mode] = self.recalls_by_mode.get(mode, 0) + 1
            self.last_query = query[:140]
            self.last_mode = mode
            self.last_event_count = event_count
            self.last_top_score = round(top_score, 4)
            if event_count == 0:
                self.empty_recalls += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            avg = (self.total_latency_ms / self.recalls) if self.recalls else 0.0
            hit = ((self.recalls - self.empty_recalls) / self.recalls) if self.recalls else 0.0
            return {
                "started_at": self.started_at,
                "writes": self.writes,
                "write_failures": self.write_failures,
                "recalls": self.recalls,
                "empty_recalls": self.empty_recalls,
                "memory_hit_rate": round(hit, 4),
                "avg_latency_ms": round(avg, 2),
                "last_latency_ms": round(self.last_latency_ms, 2),
                "recalls_by_mode": dict(self.recalls_by_mode),
                "last_query": self.last_query,
                "last_mode": self.last_mode,
                "last_event_count": self.last_event_count,
                "last_top_score": self.last_top_score,
            }

    def reset(self) -> None:
        with self._lock:
            self._reset()


_STATS = _RetrievalStats()


def memory_retrieval_stats() -> dict[str, Any]:
    """Return a JSON-friendly snapshot of memory recall telemetry."""
    snap = _STATS.snapshot()
    snap["embeddings_enabled"] = _embeddings_enabled()
    snap["retriever_mode"] = _retriever_mode()
    try:
        snap["embed_index_size"] = _guardian().embed.size()
    except Exception:
        snap["embed_index_size"] = 0
    return snap


def reset_memory_retrieval_stats() -> None:
    _STATS.reset()


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
    source: str = "chat",
    confidence: float | None = None,
) -> bool:
    if not memory_guardian_enabled():
        return False

    text = _safe_text(_redact_sensitive_text(content))
    if not text:
        return False

    sanitized = _sanitize_metadata(metadata or {})
    sanitized.setdefault("source", source)
    if confidence is not None:
        sanitized["confidence"] = round(float(confidence), 4)
    sanitized.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())

    event = Event(
        type=event_type,
        role=role,
        content=text,
        session_id=session_id,
        metadata=sanitized,
    )
    guardian = _guardian()
    try:
        guardian.ledger.append(event)
        guardian.fts.index_event(event)
        if _embeddings_enabled():
            try:
                guardian.embed.index_event(event)
            except Exception:
                # Hybrid retrieval is best-effort; never block on it.
                pass
        _STATS.record_write(ok=True)
        return True
    except Exception:
        _STATS.record_write(ok=False)
        return False


def remember_chat_message(*, user_id: str, room_id: str, role: str, content: str) -> bool:
    stored = _append_event(
        event_type=EventType.MESSAGE,
        role=role,
        content=content,
        session_id=_room_session(user_id, room_id),
        metadata={"user_id": user_id, "room_id": room_id},
        source=f"chat.{role}",
        confidence=0.9 if role == "user" else 0.7,
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
        source=f"tool.{tool_name}",
        confidence=0.85,
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


def _emit_memory_event(event_type: str, content: str, payload: dict) -> None:
    """Emit a spine event for a memory action. Non-blocking — never raises."""
    try:
        from app.services.guardian import spine
        spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type=event_type,
                subsystem="memory",
                actor_kind="system",
                source=spine.SpineSourceReference(
                    source_kind="memory",
                    source_ref=event_type,
                ),
                content=content,
                payload=payload,
            ),
        )
    except Exception:
        pass


def remember_fact(*, user_id: str, fact: str, memory_id: str = "") -> bool:
    metadata = {"user_id": user_id}
    if memory_id:
        metadata["memory_id"] = memory_id
    stored = _append_event(
        event_type=EventType.SYSTEM,
        role="system",
        content=f"FACT: {_safe_text(fact, limit=500)}",
        session_id=_user_session(user_id),
        metadata=metadata,
        source="fact.user_authored",
        confidence=0.95,
    )
    if stored:
        _emit_memory_event(
            "memory.fact_stored",
            _safe_text(fact, limit=120),
            {"user_id": user_id, "memory_id": memory_id},
        )
    return stored


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
    try:
        from . import improvement

        promoted_block = improvement.build_promoted_workflow_context(
            user_id=user_id,
            room_id=room_id,
            query=prompt_query,
        ).strip()
    except Exception:
        promoted_block = ""
    if promoted_block:
        blocks.append(promoted_block)

    guardian = _guardian()
    limit = _retrieve_limit()
    mode = _retriever_mode()

    user_block = ""
    room_block = ""
    user_count = 0
    room_count = 0
    user_top = 0.0
    room_top = 0.0

    started = time.perf_counter()
    try:
        user_scored = guardian.retriever.retrieve_scored(
            prompt_query, limit=limit, session_id=_user_session(user_id), mode=mode
        )
        user_count = len(user_scored)
        user_top = user_scored[0][1] if user_scored else 0.0
        if user_scored:
            user_block = guardian.packer.pack([e for e, _ in user_scored]).strip()

        room_scored = guardian.retriever.retrieve_scored(
            prompt_query, limit=limit, session_id=_room_session(user_id, room_id), mode=mode
        )
        room_count = len(room_scored)
        room_top = room_scored[0][1] if room_scored else 0.0
        if room_scored:
            room_block = guardian.packer.pack([e for e, _ in room_scored]).strip()
    except Exception:
        # Fall back to the legacy packer path if the scored API fails for any reason.
        user_block = guardian.get_context(
            prompt_query, limit=limit, session_id=_user_session(user_id), mode=mode
        ).strip()
        room_block = guardian.get_context(
            prompt_query, limit=limit, session_id=_room_session(user_id, room_id), mode=mode
        ).strip()
    finally:
        latency_ms = (time.perf_counter() - started) * 1000.0
        _STATS.record_recall(
            mode=mode,
            latency_ms=latency_ms,
            event_count=user_count + room_count,
            top_score=max(user_top, room_top),
            query=prompt_query,
        )

    if user_block and user_block != _NO_CONTEXT_MARKER:
        blocks.append("## Durable Memory\n" + user_block)
    if room_block and room_block != _NO_CONTEXT_MARKER:
        blocks.append("## Relevant Room Memory\n" + room_block)
    return "\n\n".join(blocks)


def recall_relevant_events(
    *,
    user_id: str,
    room_id: str | None,
    query: str,
    limit: int | None = None,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    """Hybrid recall returning structured event records with provenance + score.

    Used by the ``memory_recall`` tool and any caller that needs
    machine-readable recall results rather than a packed prompt block.
    """
    if not memory_guardian_enabled():
        return []

    prompt_query = _safe_text(query, limit=500)
    if not prompt_query:
        return []

    guardian = _guardian()
    effective_limit = max(1, min(int(limit or _retrieve_limit()), 25))
    effective_mode = (mode or _retriever_mode()).strip().lower()
    if effective_mode not in _VALID_RETRIEVER_MODES:
        effective_mode = "hybrid"

    sessions: list[str] = [_user_session(user_id)]
    if room_id:
        sessions.append(_room_session(user_id, room_id))

    started = time.perf_counter()
    aggregated: list[tuple[Event, float, str]] = []
    try:
        for sess in sessions:
            scored = guardian.retriever.retrieve_scored(
                prompt_query, limit=effective_limit, session_id=sess, mode=effective_mode
            )
            for event, score in scored:
                aggregated.append((event, float(score), sess))
    finally:
        latency_ms = (time.perf_counter() - started) * 1000.0
        top = max((s for _, s, _ in aggregated), default=0.0)
        _STATS.record_recall(
            mode=effective_mode,
            latency_ms=latency_ms,
            event_count=len(aggregated),
            top_score=top,
            query=prompt_query,
        )

    aggregated.sort(key=lambda triple: triple[1], reverse=True)
    aggregated = aggregated[:effective_limit]

    out: list[dict[str, Any]] = []
    for event, score, sess in aggregated:
        meta = dict(event.metadata or {})
        out.append(
            {
                "id": event.id,
                "session_id": sess,
                "type": event.type.value if hasattr(event.type, "value") else str(event.type),
                "role": event.role,
                "content": _safe_text(event.content, limit=500),
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "score": round(score, 4),
                "source": meta.get("source"),
                "confidence": meta.get("confidence"),
            }
        )
    return out


def reindex_memory_indexes() -> dict[str, Any]:
    """Rebuild FTS + embedding indexes from the ledger.

    Returns a small summary suitable for a Task Guardian run record.
    """
    guardian = _guardian()
    fts_count = 0
    embed_count = 0
    try:
        guardian.fts.rebuild_from_ledger(guardian.ledger.ledger_path)
        fts_count = sum(1 for _ in guardian.ledger.iter_events())
    except Exception:
        pass
    if _embeddings_enabled():
        try:
            embed_count = guardian.embed.rebuild_from_ledger(guardian.ledger.ledger_path)
        except Exception:
            embed_count = 0
    return {
        "fts_indexed": fts_count,
        "embed_indexed": embed_count,
        "embeddings_enabled": _embeddings_enabled(),
        "retriever_mode": _retriever_mode(),
    }


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
    if _embeddings_enabled():
        try:
            guardian.embed.rebuild_from_ledger(guardian.ledger.ledger_path)
        except Exception:
            pass
