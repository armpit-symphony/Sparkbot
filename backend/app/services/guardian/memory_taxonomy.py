"""Conservative memory typing and candidate filtering.

This module intentionally uses local heuristics only. It must never call an
LLM, because it runs on the hot memory write path.
"""

from __future__ import annotations

import re
from typing import Any

MEMORY_TYPES = {
    "identity",
    "preference",
    "project_context",
    "project_decision",
    "active_task",
    "tool_pattern",
    "meeting_action",
    "relationship_note",
    "debug_state",
    "temporary_context",
    "do_not_store",
    "secret_blocked",
    "unknown",
}

ACTIVE_LIFECYCLE_STATE = "active"
LIFECYCLE_STATES = {
    "active",
    "stale",
    "archived",
    "delete_proposed",
    "soft_deleted",
    "deprecated",
    "rejected",
}

_SECRET_RE = re.compile(
    r"(?i)\b("
    r"password|passwd|secret|token|api[_ -]?key|apikey|access[_ -]?key|"
    r"credential|auth[_ -]?token|passphrase|private[_ -]?key|cookie|sessionid"
    r")\b"
)
_TOKEN_VALUE_RE = re.compile(
    r"(?i)\b("
    r"sk-[A-Za-z0-9]{12,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r")\b"
)
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----", re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_ -]?key|access[_ -]?key|credential|"
    r"auth[_ -]?token|passphrase|private[_ -]?key|cookie)\b\s*[:=]\s*\S+"
)
_LOW_VALUE_ACKS = {
    "ok",
    "okay",
    "k",
    "yes",
    "no",
    "thanks",
    "thank you",
    "continue",
    "go ahead",
    "run it",
    "done",
    "cool",
    "nice",
    "great",
    "got it",
    "yep",
    "nope",
}
_ASSISTANT_FILLER_RE = re.compile(
    r"(?i)^(sure|okay|ok|got it|i can help|i'll|i will|let me)\b.{0,80}$"
)
_EXPLICIT_MEMORY_RE = re.compile(
    r"(?i)\b(remember|from now on|going forward|always|my preference|i prefer)\b"
)
_IDENTITY_RE = re.compile(
    r"(?i)\b(i am|i'm|i work|my name|my role|my company|call me)\b"
)
_DECISION_RE = re.compile(
    r"(?i)\b(decision|we decided|final decision|do not|don't|must|should|approved)\b"
)
_DEBUG_RE = re.compile(
    r"(?i)\b(port \d+|stack trace|traceback|failed command|deployment error|"
    r"already in use|exception|segfault|build failed|ci failed|error:|failed:)\b"
)
_ACTION_RE = re.compile(r"(?i)\b(todo|action item|owner|due date|follow[- ]?up|next step)\b")
_TOOL_PATTERN_RE = re.compile(
    r"(?i)\b(model|tool|route|routing|fallback|succeeded|failed|success|provider)\b"
)
_PROJECT_CONTEXT_RE = re.compile(
    r"(?i)\b(project|repo|repository|branch|release|deploy|server|sparkbot|codex)\b"
)


def _clean(content: str) -> str:
    return " ".join((content or "").split()).strip()


def is_secret_like(content: str) -> bool:
    text = content or ""
    return bool(
        _PRIVATE_KEY_RE.search(text)
        or _TOKEN_VALUE_RE.search(text)
        or _SECRET_ASSIGNMENT_RE.search(text)
        or (_SECRET_RE.search(text) and re.search(r"[:=]\s*\S+", text))
    )


def classify_memory_type(content: str, metadata: dict[str, Any] | None = None) -> str:
    """Classify a proposed memory candidate using conservative heuristics."""
    text = _clean(content)
    lowered = text.lower()
    meta = metadata or {}
    source = str(meta.get("source") or "").lower()

    if not text:
        return "do_not_store"
    if is_secret_like(text):
        return "secret_blocked"
    if lowered in _LOW_VALUE_ACKS:
        return "do_not_store"

    meeting_source = any(part in source for part in ("meeting", "transcript", "room"))
    if meeting_source and _DECISION_RE.search(text):
        return "project_decision"
    if meeting_source and _ACTION_RE.search(text):
        return "meeting_action"
    if _IDENTITY_RE.search(text):
        if _DECISION_RE.search(text) and not re.search(r"(?i)\bmy name|call me\b", text):
            return "project_decision"
        return "identity"
    if _EXPLICIT_MEMORY_RE.search(text):
        if _DECISION_RE.search(text):
            return "project_decision"
        return "preference"
    if _DECISION_RE.search(text):
        return "project_decision"
    if _DEBUG_RE.search(text):
        return "debug_state"
    if _ACTION_RE.search(text):
        return "meeting_action" if meeting_source else "active_task"
    if _TOOL_PATTERN_RE.search(text) and ("tool." in source or "model" in lowered or "routing" in lowered):
        return "tool_pattern"
    if _PROJECT_CONTEXT_RE.search(text):
        return "project_context"
    return "temporary_context" if len(text) >= 20 else "unknown"


def should_index_memory_candidate(event: dict[str, Any]) -> tuple[bool, str]:
    """Return whether an append-only ledger event should enter retrieval indexes."""
    content = _clean(str(event.get("content") or ""))
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    role = str(event.get("role") or "").lower()
    source = str(metadata.get("source") or "").lower()
    memory_type = str(metadata.get("memory_type") or classify_memory_type(content, metadata))
    explicit = bool(_EXPLICIT_MEMORY_RE.search(content))

    if not content:
        return False, "empty"
    if memory_type == "secret_blocked":
        return False, "secret_blocked"
    if memory_type == "do_not_store":
        return False, "do_not_store"
    if len(content) < 20 and not explicit:
        return False, "too_short"
    if content.lower() in _LOW_VALUE_ACKS and not explicit:
        return False, "low_value_ack"
    if role == "assistant" and _ASSISTANT_FILLER_RE.search(content):
        return False, "assistant_filler"
    if source.startswith("system.") or source in {"system", "heartbeat"}:
        return False, "system_noise"
    if "tool." in source and re.search(r"(?i)\b(error|failed|traceback|timed out|exception)\b", content):
        return False, "tool_error_noise"
    return True, "indexed"
