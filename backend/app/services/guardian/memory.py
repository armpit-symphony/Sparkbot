"""Sparkbot adapter for vendored Memory Guardian modules."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from .memory_os.api import MemoryGuardian
from .memory_os.config import Config
from .memory_os.index_embed import text_similarity
from .memory_os.schemas import Event, EventType
from .memory_taxonomy import (
    classify_memory_type,
    is_secret_like,
    should_index_memory_candidate,
)
from .retrievers import build_retriever
from .verifier import verify_fact

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "memory_guardian"
_NO_CONTEXT_MARKER = "<!-- No relevant context found -->"
_SNAPSHOT_DIRNAME = "snapshots"
_MAX_LEARNED_FACTS = 8
_MAX_RECENT_FOCUS = 3
_MAX_ACTIVE_TOOLS = 4
_VALID_RETRIEVER_MODES = {"fts", "embed", "hybrid"}
_SNAPSHOT_STATE_LOCK = threading.Lock()
_SNAPSHOT_STATE: dict[str, dict[str, Any]] = {}

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
    ("employment", 1.8, re.compile(r"\b(?:i work at|i work for|my company is)\s+([A-Za-z0-9 ._-]{2,80}?)(?=\s+(?:and|but)\b|[.;,\n]|$)", re.IGNORECASE), "User works at {value}"),
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


def _snapshot_rebuild_every_n() -> int:
    raw = os.getenv("SPARKBOT_MEMORY_SNAPSHOT_REBUILD_EVERY_N", "10").strip()
    try:
        return max(1, min(int(raw), 500))
    except ValueError:
        return 10


def _snapshot_rebuild_min_seconds() -> int:
    raw = os.getenv("SPARKBOT_MEMORY_SNAPSHOT_REBUILD_MIN_SECONDS", "300").strip()
    try:
        return max(0, min(int(raw), 86400))
    except ValueError:
        return 300


def _chat_memory_min_chars() -> int:
    raw = os.getenv("SPARKBOT_MEMORY_CHAT_MIN_CHARS", "20").strip()
    try:
        return max(1, min(int(raw), 500))
    except ValueError:
        return 20


def _embeddings_enabled() -> bool:
    """Embedding writes are opt-in. Default retrieval is BM25/FTS only."""
    raw = os.getenv("SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS", "false").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _retriever_mode() -> str:
    default = "hybrid" if _embeddings_enabled() else "fts"
    raw = (os.getenv("SPARKBOT_MEMORY_GUARDIAN_RETRIEVER", default) or default).strip().lower()
    if raw not in _VALID_RETRIEVER_MODES:
        return default
    if raw in {"embed", "hybrid"} and not _embeddings_enabled():
        return "fts"
    return raw


def _data_dir() -> Path:
    configured = os.getenv("SPARKBOT_MEMORY_GUARDIAN_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    desktop_data_dir = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    if desktop_data_dir:
        return Path(desktop_data_dir).expanduser() / "memory_guardian"
    return _DEFAULT_DATA_DIR


def _snapshot_dir() -> Path:
    path = _data_dir() / _SNAPSHOT_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_path(user_id: str, room_id: str) -> Path:
    return _snapshot_dir() / f"user_{user_id}__room_{room_id}.json"


def _snapshot_state_key(user_id: str, room_id: str) -> str:
    return f"{user_id}:{room_id}"


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
        self.guardian_jobs = 0
        self.guardian_job_failures = 0
        self.pending_approvals_created = 0
        self.recent_memory_events_checked = 0
        self.recall_precision_at_5 = 0.0
        self.last_guardian_job: dict[str, Any] = {}
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
            job_success = (
                (self.guardian_jobs - self.guardian_job_failures) / self.guardian_jobs
                if self.guardian_jobs
                else 0.0
            )
            pending_rate = (
                self.pending_approvals_created / self.recent_memory_events_checked
                if self.recent_memory_events_checked
                else 0.0
            )
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
                "recall_precision@5": round(self.recall_precision_at_5, 4),
                "avg_retrieval_latency": round(avg, 2),
                "guardian_job_success_rate": round(job_success, 4),
                "pending_approvals_rate": round(pending_rate, 4),
                "guardian_jobs": self.guardian_jobs,
                "guardian_job_failures": self.guardian_job_failures,
                "pending_approvals_created": self.pending_approvals_created,
                "recent_memory_events_checked": self.recent_memory_events_checked,
                "last_guardian_job": dict(self.last_guardian_job),
            }

    def reset(self) -> None:
        with self._lock:
            self._reset()

    def record_guardian_job(
        self,
        *,
        ok: bool,
        checked: int,
        pending_created: int,
        recall_precision_at_5: float | None,
        summary: dict[str, Any],
    ) -> None:
        with self._lock:
            self.guardian_jobs += 1
            if not ok:
                self.guardian_job_failures += 1
            self.recent_memory_events_checked += max(0, int(checked))
            self.pending_approvals_created += max(0, int(pending_created))
            if recall_precision_at_5 is not None:
                self.recall_precision_at_5 = round(float(recall_precision_at_5), 4)
            self.last_guardian_job = dict(summary)


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


def memory_metrics() -> dict[str, Any]:
    """Return the five high-level memory quality metrics."""
    snap = memory_retrieval_stats()
    return {
        "memory_hit_rate": snap.get("memory_hit_rate", 0.0),
        "recall_precision@5": snap.get("recall_precision@5", 0.0),
        "avg_retrieval_latency": snap.get("avg_retrieval_latency", snap.get("avg_latency_ms", 0.0)),
        "guardian_job_success_rate": snap.get("guardian_job_success_rate", 0.0),
        "pending_approvals_rate": snap.get("pending_approvals_rate", 0.0),
    }


def reset_memory_retrieval_stats() -> None:
    _STATS.reset()


def _user_session(user_id: str) -> str:
    return f"user:{user_id}"


def _room_session(user_id: str, room_id: str) -> str:
    return f"room:{room_id}:user:{user_id}"


def _shared_work_session(user_id: str) -> str:
    return f"work:user:{user_id}"


def unified_chat_memory_enabled() -> bool:
    return os.getenv("SPARKBOT_UNIFIED_CHAT_MEMORY_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _safe_text(value: str, limit: int = 4000) -> str:
    text = " ".join((value or "").split()).strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


_CHAT_NOISE_RE = re.compile(
    r"^(?:ok|okay|k|yes|no|yep|nope|thanks|thank you|thx|lol|haha|done|got it|sounds good|"
    r"error|system error|internal server error|traceback|failed|retry)$",
    re.IGNORECASE,
)


def _should_store_chat_message(*, role: str, content: str) -> tuple[bool, str]:
    text = _safe_text(content, limit=4000)
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in {"user", "assistant"}:
        return False, "system_noise"
    if normalized_role == "user" and _extract_fact_candidates(text):
        return True, "durable_fact_candidate"
    if len(text) < _chat_memory_min_chars():
        return False, "too_short"
    if _CHAT_NOISE_RE.match(text):
        return False, "chat_noise"
    return True, "stored"


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


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _is_event_expired(event: Event) -> bool:
    expires_at = _parse_iso_datetime((event.metadata or {}).get("expires_at"))
    return bool(expires_at and expires_at <= datetime.now(timezone.utc))


def _ledger_inactive_refs() -> tuple[set[str], set[str], set[str], set[str]]:
    deleted_memory_ids: set[str] = set()
    deleted_event_ids: set[str] = set()
    cleared_user_ids: set[str] = set()
    cleared_session_ids: set[str] = set()
    try:
        for event in _guardian().ledger.iter_events():
            meta = dict(event.metadata or {})
            action = str(meta.get("lifecycle_action") or "")
            target_event = str(meta.get("target_event_id") or "")
            if target_event:
                deleted_event_ids.add(target_event)
            for event_id in meta.get("target_event_ids") or []:
                if event_id:
                    deleted_event_ids.add(str(event_id))
            if action in {"soft_delete", "approve_delete"}:
                target = str(meta.get("target_memory_id") or "")
                if target:
                    deleted_memory_ids.add(target)
            elif action == "clear_user_memory":
                target_user = str(meta.get("target_user_id") or "")
                if target_user:
                    cleared_user_ids.add(target_user)
                    cleared_session_ids.add(_user_session(target_user))
    except Exception:
        pass
    return deleted_memory_ids, deleted_event_ids, cleared_user_ids, cleared_session_ids


def _is_event_active_for_prompt(
    event: Event,
    *,
    include_archived: bool = False,
    deep_recall: bool = False,
    inactive_refs: tuple[set[str], set[str], set[str], set[str]] | None = None,
) -> bool:
    meta = dict(event.metadata or {})
    deleted_memory_ids, deleted_event_ids, cleared_user_ids, cleared_session_ids = inactive_refs or _ledger_inactive_refs()
    if event.id in deleted_event_ids:
        return False
    memory_id = str(meta.get("memory_id") or "")
    user_id = str(meta.get("user_id") or "")
    session_id = str(event.session_id or "")
    if bool(meta.get("deleted")):
        return False
    if memory_id and memory_id in deleted_memory_ids:
        return False
    if user_id and user_id in cleared_user_ids:
        return False
    if session_id in cleared_session_ids or any(session_id.endswith(f":user:{uid}") for uid in cleared_user_ids):
        return False
    memory_type = str(meta.get("memory_type") or "unknown")
    if memory_type == "secret_blocked":
        return False
    state = str(meta.get("lifecycle_state") or "active")
    if state == "archived" and (include_archived or deep_recall):
        return not _is_event_expired(event)
    if state != "active":
        return False
    if bool(meta.get("soft_deleted")) or meta.get("soft_deleted_at"):
        return False
    if bool(meta.get("deprecated")) or meta.get("deprecated_by"):
        return False
    if str(meta.get("verification_state") or "recorded") in {"blocked", "failed", "rejected"}:
        return False
    return not _is_event_expired(event)


def _filter_prompt_events(
    events: list[Event],
    *,
    include_archived: bool = False,
    deep_recall: bool = False,
) -> list[Event]:
    inactive_refs = _ledger_inactive_refs()
    return [
        event
        for event in events
        if _is_event_active_for_prompt(
            event,
            include_archived=include_archived,
            deep_recall=deep_recall,
            inactive_refs=inactive_refs,
        )
    ]


def _score_fact(*, mentions: int, weight: float, last_seen: datetime) -> float:
    now = datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    age_days = max((now - last_seen).total_seconds() / 86400.0, 0.0)
    recency_penalty = min(age_days * 0.15, 1.5)
    return round(weight + (mentions * 0.7) - recency_penalty, 2)


def _merge_semantic_fact_state(fact_state: dict[str, dict[str, Any]], *, threshold: float = 0.85) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for state in fact_state.values():
        target: dict[str, Any] | None = None
        for cluster in clusters:
            if text_similarity(str(state["fact"]), str(cluster["fact"])) >= threshold:
                target = cluster
                break
        if target is None:
            clusters.append(dict(state))
            continue
        target["mentions"] = int(target.get("mentions") or 0) + int(state.get("mentions") or 0)
        target["weight"] = max(float(target.get("weight") or 0.0), float(state.get("weight") or 0.0))
        target["last_seen"] = max(target["last_seen"], state["last_seen"])
        target.setdefault("aliases", [])
        if state["fact"] != target["fact"]:
            target["aliases"].append(state["fact"])
    return clusters


def _build_profile_snapshot(*, user_id: str, room_id: str) -> dict[str, Any]:
    guardian = _guardian()
    user_events = _filter_prompt_events(list(guardian.ledger.iter_events(session_id=_user_session(user_id))))
    room_events = _filter_prompt_events(list(guardian.ledger.iter_events(session_id=_room_session(user_id, room_id))))

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
    for state in _merge_semantic_fact_state(fact_state):
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


def _load_profile_snapshot(*, user_id: str, room_id: str) -> dict[str, Any]:
    try:
        path = _snapshot_path(user_id, room_id)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _remember_snapshot_candidate(*, user_id: str, room_id: str, indexed: bool) -> None:
    if not indexed:
        return
    key = _snapshot_state_key(user_id, room_id)
    with _SNAPSHOT_STATE_LOCK:
        state = _SNAPSHOT_STATE.setdefault(
            key,
            {"candidate_count": 0, "last_rebuild_monotonic": time.monotonic()},
        )
        state["candidate_count"] = int(state.get("candidate_count") or 0) + 1


def _snapshot_rebuild_due(*, user_id: str, room_id: str, force: bool = False) -> bool:
    if force:
        return True
    path = _snapshot_path(user_id, room_id)
    if not path.exists():
        return True
    key = _snapshot_state_key(user_id, room_id)
    with _SNAPSHOT_STATE_LOCK:
        state = _SNAPSHOT_STATE.setdefault(
            key,
            {"candidate_count": 0, "last_rebuild_monotonic": time.monotonic()},
        )
        candidate_count = int(state.get("candidate_count") or 0)
        elapsed = time.monotonic() - float(state.get("last_rebuild_monotonic") or 0.0)
    return candidate_count >= _snapshot_rebuild_every_n() or elapsed >= _snapshot_rebuild_min_seconds()


def _build_and_persist_profile_snapshot(
    *,
    user_id: str,
    room_id: str,
    force: bool = False,
) -> dict[str, Any]:
    if not _snapshot_rebuild_due(user_id=user_id, room_id=room_id, force=force):
        return _load_profile_snapshot(user_id=user_id, room_id=room_id)
    snapshot = _build_profile_snapshot(user_id=user_id, room_id=room_id)
    _persist_profile_snapshot(user_id=user_id, room_id=room_id, snapshot=snapshot)
    key = _snapshot_state_key(user_id, room_id)
    with _SNAPSHOT_STATE_LOCK:
        _SNAPSHOT_STATE[key] = {"candidate_count": 0, "last_rebuild_monotonic": time.monotonic()}
    return snapshot


def _maybe_persist_profile_snapshot(*, user_id: str, room_id: str) -> None:
    key = _snapshot_state_key(user_id, room_id)
    with _SNAPSHOT_STATE_LOCK:
        state = _SNAPSHOT_STATE.setdefault(
            key,
            {"candidate_count": 0, "last_rebuild_monotonic": time.monotonic()},
        )
        candidate_count = int(state.get("candidate_count") or 0)
        elapsed = time.monotonic() - float(state.get("last_rebuild_monotonic") or time.monotonic())
    if candidate_count < _snapshot_rebuild_every_n() and elapsed < _snapshot_rebuild_min_seconds():
        return
    _build_and_persist_profile_snapshot(user_id=user_id, room_id=room_id, force=True)


def force_profile_snapshot_refresh(*, user_id: str, room_id: str) -> dict[str, Any]:
    """Explicit memory refresh hook for commands/API callers."""
    return _build_and_persist_profile_snapshot(user_id=user_id, room_id=room_id, force=True)


def mark_profile_snapshot_dirty(*, user_id: str | None = None, room_id: str | None = None) -> None:
    """Force the next profile snapshot read to rebuild after lifecycle changes."""
    with _SNAPSHOT_STATE_LOCK:
        if user_id and room_id:
            _SNAPSHOT_STATE[_snapshot_state_key(user_id, room_id)] = {
                "candidate_count": _snapshot_rebuild_every_n(),
                "last_rebuild_monotonic": 0.0,
            }
        else:
            for key in list(_SNAPSHOT_STATE):
                _SNAPSHOT_STATE[key]["candidate_count"] = _snapshot_rebuild_every_n()
                _SNAPSHOT_STATE[key]["last_rebuild_monotonic"] = 0.0


def _append_event(
    *,
    event_type: EventType,
    content: str,
    session_id: str,
    role: str | None = None,
    metadata: dict[str, Any] | None = None,
    source: str = "chat",
    confidence: float | None = None,
    verification_state: str | None = None,
) -> bool:
    if not memory_guardian_enabled():
        return False

    raw_text = _safe_text(content)
    redacted_text = _redact_sensitive_text(raw_text)
    redacted = redacted_text != raw_text
    text = _safe_text(redacted_text)
    if not text:
        return False

    sanitized = _sanitize_metadata(metadata or {})
    sanitized.setdefault("source", source)
    memory_type = classify_memory_type(raw_text, sanitized)
    sanitized.setdefault("memory_type", memory_type)
    sanitized.setdefault("lifecycle_state", "active")
    if confidence is not None:
        sanitized["confidence"] = round(float(confidence), 4)
    sanitized.setdefault("verification_state", verification_state or "recorded")
    sanitized.setdefault("redacted", redacted)
    sanitized.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())

    event = Event(
        type=event_type,
        role=role,
        content=text,
        session_id=session_id,
        metadata=sanitized,
    )
    should_index, index_reason = should_index_memory_candidate(
        {
            "type": event_type.value if hasattr(event_type, "value") else str(event_type),
            "role": role,
            "content": raw_text,
            "metadata": sanitized,
        }
    )
    event.metadata["candidate_indexed"] = should_index
    event.metadata["candidate_reason"] = index_reason
    guardian = _guardian()
    try:
        guardian.ledger.append(event)
        if should_index:
            guardian.fts.index_event(event)
            if _embeddings_enabled():
                try:
                    guardian.embed.index_event(event)
                except Exception:
                    # Hybrid retrieval is best-effort; never block on it.
                    pass
        try:
            if getattr(guardian.retriever, "_cache_loaded", False):
                guardian.retriever._event_cache[event.id] = event
        except Exception:
            pass
        _STATS.record_write(ok=True)
        return True
    except Exception:
        _STATS.record_write(ok=False)
        return False


def remember_chat_message(*, user_id: str, room_id: str, role: str, content: str) -> bool:
    should_store, _reason = _should_store_chat_message(role=role, content=content)
    if not should_store:
        return False
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
            last_event = _guardian().ledger.get_recent(n=1, session_id=_room_session(user_id, room_id))[0]
            _remember_snapshot_candidate(
                user_id=user_id,
                room_id=room_id,
                indexed=bool(last_event.metadata.get("candidate_indexed")),
            )
            _maybe_persist_profile_snapshot(user_id=user_id, room_id=room_id)
        except Exception:
            pass
    if stored and unified_chat_memory_enabled():
        try:
            shared_content = _safe_text(content, limit=1200)
            if shared_content:
                fingerprint = hashlib.sha256(
                    "\n".join([user_id, room_id, role, shared_content]).encode("utf-8")
                ).hexdigest()
                duplicate = False
                for event in _guardian().ledger.iter_events(session_id=_shared_work_session(user_id)):
                    meta = dict(event.metadata or {})
                    if meta.get("chat_fingerprint") == fingerprint and _is_event_active_for_prompt(event):
                        duplicate = True
                        break
                if not duplicate:
                    _append_event(
                        event_type=EventType.MESSAGE,
                        role=role,
                        content=f"Chat from room {room_id} ({role}): {shared_content}",
                        session_id=_shared_work_session(user_id),
                        metadata={
                            "user_id": user_id,
                            "room_id": room_id,
                            "scope_type": "shared_chat",
                            "chat_fingerprint": fingerprint,
                        },
                        source=f"chat.{role}.shared",
                        confidence=0.82 if role == "user" else 0.68,
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
            last_event = _guardian().ledger.get_recent(n=1, session_id=_room_session(user_id, room_id))[0]
            _remember_snapshot_candidate(
                user_id=user_id,
                room_id=room_id,
                indexed=bool(last_event.metadata.get("candidate_indexed")),
            )
            _maybe_persist_profile_snapshot(user_id=user_id, room_id=room_id)
        except Exception:
            pass
    return stored


def _artifact_rollup_lines(content: str, *, max_lines: int = 14) -> list[str]:
    selected: list[str] = []
    current_heading = ""
    allowed_headings = {
        "key decisions",
        "action items",
        "next steps",
        "open questions",
        "discussion summary",
    }
    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("## "):
            current_heading = line[3:].strip().lower()
            continue
        if line.startswith("#"):
            continue
        if current_heading and current_heading not in allowed_headings:
            continue
        if line.lower() in {"(none noted)", "- (none noted)", "none noted", "n/a"}:
            continue
        if line.startswith(("-", "*")) or current_heading in {"key decisions", "action items", "next steps", "open questions"}:
            selected.append(line[:500])
        elif current_heading == "discussion summary" and len(line) >= 20:
            selected.append(line[:500])
        if len(selected) >= max_lines:
            break
    return selected


def remember_meeting_artifact(
    *,
    user_id: str,
    room_id: str,
    artifact_id: str,
    artifact_type: str,
    content_markdown: str,
    room_name: str = "",
    project_id: str | None = None,
) -> bool:
    """Roll important meeting outputs into shared work memory.

    Room transcripts remain room-scoped. Summaries, decisions, action items,
    next steps, and open questions are copied into a user-wide work session so
    main Sparkbot chat can retrieve meeting outcomes without pretending the
    meeting happened in the current room.
    """
    normalized_type = (artifact_type or "").strip().lower()
    if normalized_type not in {"notes", "action_items", "decisions", "agenda"}:
        return False
    lines = _artifact_rollup_lines(content_markdown)
    if not lines:
        return False
    title = room_name.strip() or f"room {room_id}"
    content = "\n".join(
        [
            f"Meeting rollup from {title} ({normalized_type}):",
            *lines,
        ]
    )
    fingerprint = hashlib.sha256(
        "\n".join([user_id, room_id, normalized_type, *lines]).encode("utf-8")
    ).hexdigest()
    try:
        for event in _guardian().ledger.iter_events(session_id=_shared_work_session(user_id)):
            meta = dict(event.metadata or {})
            if meta.get("rollup_fingerprint") == fingerprint and _is_event_active_for_prompt(event):
                return False
    except Exception:
        pass
    return _append_event(
        event_type=EventType.SYSTEM,
        role="system",
        content=content,
        session_id=_shared_work_session(user_id),
        metadata={
            "user_id": user_id,
            "room_id": room_id,
            "artifact_id": artifact_id,
            "artifact_type": normalized_type,
            "scope_type": "shared_work",
            "project_id": project_id or "",
            "rollup_fingerprint": fingerprint,
        },
        source=f"meeting.{normalized_type}.rollup",
        confidence=0.86,
        verification_state="recorded",
    )


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


def _store_pending_memory_approval(
    *,
    user_id: str,
    fact: str,
    source: str,
    confidence: float,
    verification_state: str,
    summary: str,
    memory_id: str = "",
    confirm_id: str | None = None,
) -> str | None:
    try:
        from app.services.guardian.pending_approvals import store_pending_approval

        confirm_id = confirm_id or f"memory_fact:{uuid.uuid4()}"
        store_pending_approval(
            confirm_id=confirm_id,
            tool_name="memory_fact_promotion",
            tool_args={
                "fact": _safe_text(_redact_sensitive_text(fact), limit=500),
                "source": source,
                "confidence": round(float(confidence), 4),
                "verification_state": verification_state,
                "verification_summary": summary,
                "memory_id": memory_id,
            },
            user_id=user_id,
            room_id=None,
        )
        return confirm_id
    except Exception:
        return None


def remember_fact(
    *,
    user_id: str,
    fact: str,
    memory_id: str = "",
    source: str = "fact.user_authored",
    confidence: float = 0.95,
) -> bool:
    safe_fact = _safe_text(fact, limit=500)
    memory_type = classify_memory_type(safe_fact, {"source": source})
    if memory_type == "secret_blocked" or is_secret_like(safe_fact):
        _emit_memory_event(
            "memory.fact_blocked",
            "Secret-like fact promotion blocked",
            {
                "user_id": user_id,
                "memory_id": memory_id,
                "memory_type": "secret_blocked",
                "source": source,
            },
        )
        return False
    verification = verify_fact(fact=safe_fact, source=source, confidence=confidence)
    if verification.status != "verified":
        confirm_id = _store_pending_memory_approval(
            user_id=user_id,
            fact=safe_fact,
            source=source,
            confidence=verification.confidence,
            verification_state=verification.status,
            summary=verification.summary,
            memory_id=memory_id,
        )
        _emit_memory_event(
            "memory.fact_pending_approval",
            _safe_text(safe_fact, limit=120),
            {
                "user_id": user_id,
                "memory_id": memory_id,
                "confirm_id": confirm_id,
                "verification_state": verification.status,
                "confidence": verification.confidence,
            },
        )
        return False

    metadata = {
        "user_id": user_id,
        "verification_state": verification.status,
        "verification_summary": verification.summary,
        "memory_type": memory_type,
        "scope_type": "user",
    }
    if memory_id:
        metadata["memory_id"] = memory_id
    stored = _append_event(
        event_type=EventType.SYSTEM,
        role="system",
        content=f"FACT: {safe_fact}",
        session_id=_user_session(user_id),
        metadata=metadata,
        source=source,
        confidence=verification.confidence,
        verification_state=verification.status,
    )
    if stored:
        _emit_memory_event(
            "memory.fact_stored",
            _safe_text(safe_fact, limit=120),
            {
                "user_id": user_id,
                "memory_id": memory_id,
                "verification_state": verification.status,
                "confidence": verification.confidence,
            },
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
        snapshot = _build_and_persist_profile_snapshot(user_id=user_id, room_id=room_id)
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
    work_block = ""
    room_block = ""
    user_count = 0
    work_count = 0
    room_count = 0
    user_top = 0.0
    work_top = 0.0
    room_top = 0.0

    started = time.perf_counter()
    try:
        retriever = build_retriever(
            guardian,
            requested_mode=mode,
            embeddings_enabled=_embeddings_enabled(),
        )
        inactive_refs = _ledger_inactive_refs()
        user_hits = retriever.retrieve_scored(
            prompt_query, limit=limit, session_id=_user_session(user_id)
        )
        user_hits = [
            hit for hit in user_hits
            if _is_event_active_for_prompt(hit.event, inactive_refs=inactive_refs)
        ]
        user_count = len(user_hits)
        user_top = user_hits[0].score if user_hits else 0.0
        if user_hits:
            user_block = guardian.packer.pack([hit.event for hit in user_hits]).strip()

        work_hits = retriever.retrieve_scored(
            prompt_query, limit=limit, session_id=_shared_work_session(user_id)
        )
        work_hits = [
            hit for hit in work_hits
            if _is_event_active_for_prompt(hit.event, inactive_refs=inactive_refs)
        ]
        work_count = len(work_hits)
        work_top = work_hits[0].score if work_hits else 0.0
        if work_hits:
            work_block = guardian.packer.pack([hit.event for hit in work_hits]).strip()

        room_hits = retriever.retrieve_scored(
            prompt_query, limit=limit, session_id=_room_session(user_id, room_id)
        )
        room_hits = [
            hit for hit in room_hits
            if _is_event_active_for_prompt(hit.event, inactive_refs=inactive_refs)
        ]
        room_count = len(room_hits)
        room_top = room_hits[0].score if room_hits else 0.0
        if room_hits:
            room_block = guardian.packer.pack([hit.event for hit in room_hits]).strip()
    except Exception:
        # Fall back to the legacy packer path if the scored API fails for any reason.
        user_events = _filter_prompt_events(
            guardian.retriever.retrieve(
                prompt_query,
                limit=limit,
                session_id=_user_session(user_id),
                mode="fts",
            )
        )
        room_events = _filter_prompt_events(
            guardian.retriever.retrieve(
                prompt_query,
                limit=limit,
                session_id=_room_session(user_id, room_id),
                mode="fts",
            )
        )
        user_count = len(user_events)
        work_events = _filter_prompt_events(
            guardian.retriever.retrieve(
                prompt_query,
                limit=limit,
                session_id=_shared_work_session(user_id),
                mode="fts",
            )
        )
        work_count = len(work_events)
        room_count = len(room_events)
        user_block = guardian.packer.pack(user_events).strip()
        work_block = guardian.packer.pack(work_events).strip()
        room_block = guardian.packer.pack(room_events).strip()
    finally:
        latency_ms = (time.perf_counter() - started) * 1000.0
        _STATS.record_recall(
            mode=mode,
            latency_ms=latency_ms,
            event_count=user_count + work_count + room_count,
            top_score=max(user_top, work_top, room_top),
            query=prompt_query,
        )

    if user_block and user_block != _NO_CONTEXT_MARKER:
        blocks.append("## Durable Memory\n" + user_block)
    if work_block and work_block != _NO_CONTEXT_MARKER:
        blocks.append("## Shared Work Memory\n" + work_block)
    if room_block and room_block != _NO_CONTEXT_MARKER:
        blocks.append("## Relevant Room Memory\n" + room_block)
    return "\n\n".join(blocks)


def _archive_recall_events(
    *,
    query: str,
    sessions: list[str],
    limit: int,
    include_archived: bool,
    deep_recall: bool,
) -> list[tuple[Event, float, str]]:
    if not (include_archived or deep_recall):
        return []
    terms = {term.lower() for term in re.findall(r"[A-Za-z0-9_]{3,}", query or "")}
    if not terms:
        return []
    out: list[tuple[Event, float, str]] = []
    inactive_refs = _ledger_inactive_refs()
    for session_id in sessions:
        for event in _guardian().ledger.iter_archived_events(session_id=session_id, limit=1000):
            if not _is_event_active_for_prompt(
                event,
                include_archived=include_archived,
                deep_recall=deep_recall,
                inactive_refs=inactive_refs,
            ):
                continue
            content = (event.content or "").lower()
            overlap = sum(1 for term in terms if term in content)
            if overlap <= 0:
                continue
            score = min(0.99, overlap / max(len(terms), 1))
            out.append((event, float(score), session_id))
            if len(out) >= limit:
                return out
    return out


def recall_relevant_events(
    *,
    user_id: str,
    room_id: str | None,
    query: str,
    limit: int | None = None,
    mode: str | None = None,
    include_archived: bool = False,
    deep_recall: bool = False,
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
        effective_mode = _retriever_mode()
    if effective_mode in {"embed", "hybrid"} and not _embeddings_enabled():
        effective_mode = "fts"

    sessions: list[str] = [_user_session(user_id), _shared_work_session(user_id)]
    if room_id:
        sessions.append(_room_session(user_id, room_id))

    started = time.perf_counter()
    aggregated: list[tuple[Event, float, str]] = []
    try:
        inactive_refs = _ledger_inactive_refs()
        retriever = build_retriever(
            guardian,
            requested_mode=effective_mode,
            embeddings_enabled=_embeddings_enabled(),
        )
        for sess in sessions:
            hits = retriever.retrieve_scored(prompt_query, limit=effective_limit, session_id=sess)
            for hit in hits:
                if not _is_event_active_for_prompt(
                    hit.event,
                    include_archived=include_archived,
                    deep_recall=deep_recall,
                    inactive_refs=inactive_refs,
                ):
                    continue
                aggregated.append((hit.event, float(hit.score), sess))
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

    if include_archived or deep_recall:
        aggregated.extend(
            _archive_recall_events(
                query=prompt_query,
                sessions=sessions,
                limit=effective_limit,
                include_archived=include_archived,
                deep_recall=deep_recall,
            )
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
                "memory_type": meta.get("memory_type"),
                "lifecycle_state": meta.get("lifecycle_state", "active"),
                "why_selected": {
                    "lexical_score": round(score, 4) if effective_mode == "fts" else None,
                    "semantic_score": round(score, 4) if effective_mode in {"embed", "hybrid"} else None,
                    "scope_match": sess,
                    "confidence": meta.get("confidence"),
                    "lifecycle_state": meta.get("lifecycle_state", "active"),
                },
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
        guardian.fts.clear()
        inactive_refs = _ledger_inactive_refs()
        for event in guardian.ledger.iter_events():
            meta = dict(event.metadata or {})
            should_index, _reason = should_index_memory_candidate(
                {
                    "type": event.type.value if hasattr(event.type, "value") else str(event.type),
                    "role": event.role,
                    "content": event.content,
                    "metadata": meta,
                }
            )
            if should_index and _is_event_active_for_prompt(event, inactive_refs=inactive_refs):
                guardian.fts.index_event(event)
                fts_count += 1
    except Exception:
        pass
    if _embeddings_enabled():
        try:
            guardian.embed.clear()
            embed_count = 0
            inactive_refs = _ledger_inactive_refs()
            for event in guardian.ledger.iter_events():
                meta = dict(event.metadata or {})
                should_index, _reason = should_index_memory_candidate(
                    {
                        "type": event.type.value if hasattr(event.type, "value") else str(event.type),
                        "role": event.role,
                        "content": event.content,
                        "metadata": meta,
                    }
                )
                if should_index and _is_event_active_for_prompt(event, inactive_refs=inactive_refs):
                    guardian.embed.index_event(event)
                    embed_count += 1
        except Exception:
            embed_count = 0
    try:
        guardian.retriever._reload_cache()
    except Exception:
        pass
    return {
        "fts_indexed": fts_count,
        "embed_indexed": embed_count,
        "embeddings_enabled": _embeddings_enabled(),
        "retriever_mode": _retriever_mode(),
    }


def _delete_event_from_indexes(event_id: str) -> dict[str, int]:
    guardian = _guardian()
    fts_deleted = 0
    embed_deleted = 0
    try:
        fts_deleted = int(guardian.fts.delete_event(event_id) or 0)
    except Exception:
        fts_deleted = 0
    if _embeddings_enabled():
        try:
            embed_deleted = int(guardian.embed.delete_event(event_id) or 0)
        except Exception:
            embed_deleted = 0
    try:
        guardian.retriever._event_cache.pop(event_id, None)
    except Exception:
        pass
    return {"fts_deleted": fts_deleted, "embed_deleted": embed_deleted}


def _delete_events_from_indexes(event_ids: list[str]) -> dict[str, int]:
    summary = {"events": 0, "fts_deleted": 0, "embed_deleted": 0}
    for event_id in event_ids:
        if not event_id:
            continue
        deleted = _delete_event_from_indexes(event_id)
        summary["events"] += 1
        summary["fts_deleted"] += deleted["fts_deleted"]
        summary["embed_deleted"] += deleted["embed_deleted"]
    return summary


def compact_deleted_memory_events(*, dry_run: bool = False) -> dict[str, Any]:
    """Physically remove tombstoned hot-ledger events; cold archives stay governed by tombstones."""
    if not memory_guardian_enabled():
        return {"compacted": False, "reason": "disabled"}
    guardian = _guardian()
    inactive_refs = _ledger_inactive_refs()
    deleted_memory_ids, deleted_event_ids, cleared_user_ids, cleared_session_ids = inactive_refs
    if not (deleted_memory_ids or deleted_event_ids or cleared_user_ids or cleared_session_ids):
        return {"compacted": False, "reason": "no_tombstones"}
    kept: list[Event] = []
    removed = 0
    for event in guardian.ledger.iter_events():
        meta = dict(event.metadata or {})
        session_id = str(event.session_id or "")
        memory_id = str(meta.get("memory_id") or "")
        user_id = str(meta.get("user_id") or "")
        remove = (
            event.id in deleted_event_ids
            or (memory_id and memory_id in deleted_memory_ids)
            or (user_id and user_id in cleared_user_ids and str(meta.get("lifecycle_action") or "") != "clear_user_memory")
            or (
                session_id
                and session_id in cleared_session_ids
                and str(meta.get("lifecycle_action") or "") != "clear_user_memory"
            )
            or (
                session_id
                and any(session_id.endswith(f":user:{uid}") for uid in cleared_user_ids)
                and str(meta.get("lifecycle_action") or "") != "clear_user_memory"
            )
        )
        if remove:
            removed += 1
            continue
        kept.append(event)
    if dry_run:
        return {"compacted": False, "dry_run": True, "events_removed": removed, "events_kept": len(kept)}
    if removed:
        _rewrite_events(kept)
    return {"compacted": bool(removed), "events_removed": removed, "events_kept": len(kept)}


def _guardian_job_log_path() -> Path:
    path = _data_dir() / "memory_guardian_jobs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_guardian_job_log(payload: dict[str, Any]) -> None:
    try:
        with _guardian_job_log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception:
        pass


def _env_int(name: str, default: int, *, minimum: int = 1, maximum: int = 100000) -> int:
    try:
        return max(minimum, min(int(os.getenv(name, str(default))), maximum))
    except ValueError:
        return default


def _ledger_compression_enabled() -> bool:
    return os.getenv("SPARKBOT_MEMORY_LEDGER_COMPRESSION", "false").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _archive_manifest_path() -> Path:
    archive_dir = _data_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir / "manifest.json"


def _read_archive_manifest() -> list[dict[str, Any]]:
    path = _archive_manifest_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data if isinstance(data, list) else data.get("archives", []))
    except Exception:
        return []


def _write_archive_manifest(entries: list[dict[str, Any]]) -> None:
    _archive_manifest_path().write_text(
        json.dumps({"archives": entries}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _event_timestamp_utc(event: Event) -> datetime:
    if event.timestamp.tzinfo is None:
        return event.timestamp.replace(tzinfo=timezone.utc)
    return event.timestamp.astimezone(timezone.utc)


def rotate_memory_ledger_if_needed(*, now: datetime | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Move events older than the hot window into month-named cold archives."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    guardian = _guardian()
    ledger_path = guardian.ledger.ledger_path
    if not ledger_path.exists():
        return {"rotated": False, "reason": "missing_ledger"}

    max_active_mb = _env_int("SPARKBOT_MEMORY_MAX_ACTIVE_MB", 256, minimum=1, maximum=102400)
    hot_ledger_days = _env_int("SPARKBOT_MEMORY_HOT_LEDGER_DAYS", 30, minimum=1, maximum=3650)
    stat = ledger_path.stat()
    size_mb = stat.st_size / (1024 * 1024)
    cutoff = now - timedelta(days=hot_ledger_days)
    events = list(guardian.ledger.iter_events())
    hot_events: list[Event] = []
    archive_groups: dict[str, list[Event]] = {}
    for event in events:
        event_ts = _event_timestamp_utc(event)
        if event_ts < cutoff:
            archive_groups.setdefault(event_ts.strftime("%Y-%m"), []).append(event)
        else:
            hot_events.append(event)
    if not archive_groups:
        return {
            "rotated": False,
            "reason": "no_cold_events",
            "size_mb": round(size_mb, 3),
            "hot_ledger_days": hot_ledger_days,
            "active_events": len(events),
        }
    if size_mb < max_active_mb and len(hot_events) == len(events):
        return {"rotated": False, "reason": "below_threshold", "size_mb": round(size_mb, 3)}

    archive_dir = _data_dir() / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for month, group in sorted(archive_groups.items()):
        archive_path = archive_dir / f"ledger-{month}.jsonl"
        final_path = archive_path.with_suffix(".jsonl.gz") if _ledger_compression_enabled() else archive_path
        oldest = min((_event_timestamp_utc(event) for event in group), default=None)
        newest = max((_event_timestamp_utc(event) for event in group), default=None)
        entries.append(
            {
                "archive_id": f"ledger-{month}",
                "path": str(final_path.relative_to(_data_dir())),
                "event_count": len(group),
                "oldest_event": oldest.isoformat() if oldest else None,
                "newest_event": newest.isoformat() if newest else None,
                "contains_approved_memory_sources": any(
                    str((event.metadata or {}).get("verification_state")) == "verified" for event in group
                ),
                "contains_tool_approvals": any(event.type == EventType.TOOL_CALL for event in group),
                "lifecycle_state": "archived",
                "delete_proposed_at": None,
                "delete_approved_at": None,
                "updated_at": now.isoformat(),
            }
        )
    if dry_run:
        return {
            "rotated": False,
            "dry_run": True,
            "archive_entries": entries,
            "active_events_after": len(hot_events),
        }

    for month, group in sorted(archive_groups.items()):
        archive_path = archive_dir / f"ledger-{month}.jsonl"
        final_path = archive_path.with_suffix(".jsonl.gz") if _ledger_compression_enabled() else archive_path
        if _ledger_compression_enabled():
            with gzip.open(final_path, "at", encoding="utf-8") as dst:
                for event in group:
                    dst.write(event.model_dump_json() + "\n")
        else:
            with final_path.open("a", encoding="utf-8") as dst:
                for event in group:
                    dst.write(event.model_dump_json() + "\n")
    ledger_path.write_text("", encoding="utf-8")
    for event in hot_events:
        guardian.ledger.append(event)
    manifest_by_path = {entry.get("path"): entry for entry in _read_archive_manifest()}
    for entry in entries:
        existing = manifest_by_path.get(entry["path"])
        if existing:
            existing["event_count"] = int(existing.get("event_count") or 0) + int(entry["event_count"])
            existing["newest_event"] = max(str(existing.get("newest_event") or ""), str(entry.get("newest_event") or ""))
            existing["oldest_event"] = min(str(existing.get("oldest_event") or entry["oldest_event"]), str(entry.get("oldest_event") or ""))
            existing["updated_at"] = now.isoformat()
            existing["contains_approved_memory_sources"] = bool(existing.get("contains_approved_memory_sources")) or bool(entry.get("contains_approved_memory_sources"))
            existing["contains_tool_approvals"] = bool(existing.get("contains_tool_approvals")) or bool(entry.get("contains_tool_approvals"))
        else:
            manifest_by_path[entry["path"]] = entry
    manifest = sorted(manifest_by_path.values(), key=lambda item: str(item.get("path") or ""))
    _write_archive_manifest(manifest)
    _append_event(
        event_type=EventType.SYSTEM,
        role="system",
        content=f"MEMORY_LEDGER_ARCHIVED: {sum(len(group) for group in archive_groups.values())} events",
        session_id=None,
        metadata={"lifecycle_action": "ledger_archived", "archive_entries": entries},
        source="memory.ledger",
        confidence=1.0,
        verification_state="verified",
    )
    reindex_memory_indexes()
    return {
        "rotated": True,
        "archive_entries": entries,
        "archived_events": sum(len(group) for group in archive_groups.values()),
        "active_events_after": len(hot_events),
    }


def verify_recent_memory_events(
    *,
    lookback_hours: int = 24,
    limit: int = 200,
) -> dict[str, Any]:
    """Verify recent memory events and queue approvals for weak fact promotions."""
    guardian = _guardian()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, min(int(lookback_hours), 24 * 30)))
    events = list(guardian.ledger.iter_events())[-max(1, min(int(limit), 1000)):]
    checked = 0
    verified_promotions = 0
    pending_created = 0
    blocked = 0
    verification_states: dict[str, int] = {}

    for event in events:
        event_ts = event.timestamp
        if event_ts and event_ts.tzinfo is None:
            event_ts = event_ts.replace(tzinfo=timezone.utc)
        if event_ts and event_ts < cutoff:
            continue
        checked += 1
        meta = dict(event.metadata or {})
        state = str(meta.get("verification_state") or "recorded")
        verification_states[state] = verification_states.get(state, 0) + 1
        if event.type != EventType.SYSTEM or not event.content.startswith("FACT:"):
            continue
        fact = _normalize_fact_text(event.content.removeprefix("FACT:").strip())
        confidence = float(meta.get("confidence") or 0.5)
        source = str(meta.get("source") or "memory")
        verification = verify_fact(fact=fact, source=source, confidence=confidence)
        verification_states[verification.status] = verification_states.get(verification.status, 0) + 1
        if verification.status == "verified":
            verified_promotions += 1
            continue
        if verification.status == "blocked":
            blocked += 1
        confirm_id = _store_pending_memory_approval(
            user_id=str(meta.get("user_id") or ""),
            fact=fact,
            source=source,
            confidence=verification.confidence,
            verification_state=verification.status,
            summary=verification.summary,
            memory_id=str(meta.get("memory_id") or ""),
            confirm_id=f"memory_fact:{event.id}",
        )
        if confirm_id:
            pending_created += 1

    return {
        "checked": checked,
        "verified_promotions": verified_promotions,
        "pending_approvals_created": pending_created,
        "blocked": blocked,
        "verification_states": verification_states,
    }


def run_nightly_memory_guardian_job(*, session: Any | None = None) -> dict[str, Any]:
    """Run the nightly memory verification/evaluation pass and update metrics."""
    ok = True
    error = ""
    verification_summary: dict[str, Any] = {}
    eval_summary: dict[str, Any] = {}
    hygiene_summary: dict[str, Any] = {}
    cleanup_summary: dict[str, Any] = {}
    consolidation_summary: dict[str, Any] = {}
    rotation_summary: dict[str, Any] = {}
    compaction_summary: dict[str, Any] = {}
    try:
        verification_summary = verify_recent_memory_events()
        try:
            consolidation_summary = _guardian().consolidator.consolidate_recent(_guardian().ledger)
        except Exception as exc:
            consolidation_summary = {"error": str(exc)}
        try:
            from .retrieval_eval import run_retrieval_eval

            eval_summary = run_retrieval_eval(session=session)
        except Exception as exc:
            eval_summary = {"error": str(exc), "cases": 0}
        if session is not None:
            now = datetime.now(timezone.utc)
            try:
                if now.weekday() == 0:
                    from .memory_hygiene import run_weekly_memory_hygiene_job

                    hygiene_summary = run_weekly_memory_hygiene_job(session=session, now=now)
                    compaction_summary = compact_deleted_memory_events()
                if now.day == 1:
                    from .memory_hygiene import run_monthly_memory_cleanup_proposal_job

                    cleanup_summary = run_monthly_memory_cleanup_proposal_job(session=session, now=now)
            except Exception as exc:
                hygiene_summary = {"error": str(exc)}
        try:
            rotation_summary = rotate_memory_ledger_if_needed()
        except Exception as exc:
            rotation_summary = {"error": str(exc)}
        try:
            reindex_memory_indexes()
        except Exception:
            pass
    except Exception as exc:
        ok = False
        error = str(exc)

    precision = None
    try:
        modes = eval_summary.get("modes") or {}
        preferred = eval_summary.get("preferred_mode") or _retriever_mode()
        if preferred in modes:
            precision = float(modes[preferred].get("precision@5") or 0.0)
        elif "fts" in modes:
            precision = float(modes["fts"].get("precision@5") or 0.0)
    except Exception:
        precision = None

    summary = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "error": error,
        "verification": verification_summary,
        "consolidation": consolidation_summary,
        "ledger_rotation": rotation_summary,
        "ledger_compaction": compaction_summary,
        "retrieval_eval": eval_summary,
        "weekly_hygiene": hygiene_summary,
        "monthly_cleanup": cleanup_summary,
        "metrics": memory_metrics(),
    }
    _STATS.record_guardian_job(
        ok=ok,
        checked=int(verification_summary.get("checked") or 0),
        pending_created=int(verification_summary.get("pending_approvals_created") or 0),
        recall_precision_at_5=precision,
        summary=summary,
    )
    summary["metrics"] = memory_metrics()
    _append_guardian_job_log(summary)
    return summary


def delete_fact_memory(*, user_id: str, memory_id: str) -> int:
    if not memory_guardian_enabled():
        return 0

    target_user_session = _user_session(user_id)
    guardian = _guardian()
    matched = 0
    matched_event_ids: list[str] = []
    for event in guardian.ledger.iter_events():
        if (
            event.session_id == target_user_session
            and str(event.metadata.get("memory_id", "")) == memory_id
        ):
            matched += 1
            matched_event_ids.append(event.id)
    if matched:
        _append_event(
            event_type=EventType.SYSTEM,
            role="system",
            content=f"MEMORY_LIFECYCLE: soft_deleted memory {memory_id}",
            session_id=target_user_session,
            metadata={
                "user_id": user_id,
                "target_memory_id": memory_id,
                "target_event_ids": matched_event_ids,
                "lifecycle_action": "soft_delete",
                "lifecycle_state": "soft_deleted",
                "soft_delete_reason": "explicit user memory delete",
                "deleted": True,
            },
            source="memory.lifecycle",
            confidence=1.0,
            verification_state="verified",
        )
        _delete_events_from_indexes(matched_event_ids)
        mark_profile_snapshot_dirty()
    return matched


def forget_fact_by_query(*, user_id: str, query: str, threshold: float = 0.62) -> dict[str, Any]:
    """Semantically match a user's durable fact and retire the best candidate."""
    if not memory_guardian_enabled():
        return {"deleted": False, "reason": "disabled"}
    cleaned = _safe_text(query, limit=500)
    if not cleaned:
        return {"deleted": False, "reason": "empty_query"}
    target_session = _user_session(user_id)
    inactive_refs = _ledger_inactive_refs()
    candidates: list[tuple[Event, str, float]] = []
    for event in _guardian().ledger.iter_events(session_id=target_session, include_archives=True):
        if not _is_event_active_for_prompt(event, include_archived=True, deep_recall=True, inactive_refs=inactive_refs):
            continue
        if event.type != EventType.SYSTEM or not event.content.startswith("FACT:"):
            continue
        fact = _normalize_fact_text(event.content.removeprefix("FACT:").strip())
        score = max(text_similarity(cleaned, fact), text_similarity(f"User {cleaned}", fact))
        candidates.append((event, fact, score))
    candidates.sort(key=lambda item: item[2], reverse=True)
    if not candidates or candidates[0][2] < threshold:
        return {
            "deleted": False,
            "reason": "no_match",
            "best_score": round(candidates[0][2], 4) if candidates else 0.0,
        }
    event, fact, score = candidates[0]
    memory_id = str(event.metadata.get("memory_id") or "")
    if memory_id:
        matched = delete_fact_memory(user_id=user_id, memory_id=memory_id)
    else:
        matched = 0
    if not memory_id or matched <= 0:
        _append_event(
            event_type=EventType.SYSTEM,
            role="system",
            content=f"MEMORY_LIFECYCLE: soft_deleted event {event.id}",
            session_id=target_session,
            metadata={
                "user_id": user_id,
                "target_event_id": event.id,
                "lifecycle_action": "soft_delete",
                "lifecycle_state": "soft_deleted",
                "soft_delete_reason": f"semantic forget query: {cleaned[:160]}",
                "deleted": True,
            },
            source="memory.lifecycle",
            confidence=1.0,
            verification_state="verified",
        )
        _delete_event_from_indexes(event.id)
        mark_profile_snapshot_dirty()
        matched = 1
    return {
        "deleted": bool(matched),
        "memory_id": memory_id,
        "fact": fact,
        "score": round(score, 4),
        "events_retired": matched,
    }


def clear_user_memory_events(*, user_id: str) -> int:
    if not memory_guardian_enabled():
        return 0

    suffix = f":user:{user_id}"
    target_user_session = _user_session(user_id)
    guardian = _guardian()
    matched = 0
    matched_event_ids: list[str] = []
    for event in guardian.ledger.iter_events():
        session_id = event.session_id or ""
        if session_id == target_user_session or session_id.endswith(suffix):
            matched += 1
            matched_event_ids.append(event.id)
    if matched:
        _append_event(
            event_type=EventType.SYSTEM,
            role="system",
            content=f"MEMORY_LIFECYCLE: cleared user memory for {user_id}",
            session_id=target_user_session,
            metadata={
                "target_user_id": user_id,
                "target_event_ids": matched_event_ids,
                "lifecycle_action": "clear_user_memory",
                "lifecycle_state": "soft_deleted",
                "soft_delete_reason": "explicit user memory clear",
                "deleted": True,
            },
            source="memory.lifecycle",
            confidence=1.0,
            verification_state="verified",
        )
        _delete_events_from_indexes(matched_event_ids)
        mark_profile_snapshot_dirty()
    return matched


def _rewrite_events(events: list[Event]) -> None:
    guardian = _guardian()
    guardian.ledger.ledger_path.write_text("", encoding="utf-8")
    for event in events:
        guardian.ledger.append(event)
    reindex_memory_indexes()
