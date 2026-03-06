"""Sparkbot adapter for vendored Memory Guardian modules."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .memory_os.api import MemoryGuardian
from .memory_os.config import Config
from .memory_os.schemas import Event, EventType

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "memory_guardian"
_NO_CONTEXT_MARKER = "<!-- No relevant context found -->"


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

    text = _safe_text(content)
    if not text:
        return False

    event = Event(
        type=event_type,
        role=role,
        content=text,
        session_id=session_id,
        metadata=metadata or {},
    )
    guardian = _guardian()
    guardian.ledger.append(event)
    guardian.fts.index_event(event)
    return True


def remember_chat_message(*, user_id: str, room_id: str, role: str, content: str) -> bool:
    return _append_event(
        event_type=EventType.MESSAGE,
        role=role,
        content=content,
        session_id=_room_session(user_id, room_id),
        metadata={"user_id": user_id, "room_id": room_id},
    )


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
        "args": args,
        "result": _safe_text(result, limit=1500),
    }
    return _append_event(
        event_type=EventType.TOOL_CALL,
        role="system",
        content=f"{tool_name}({json.dumps(args, sort_keys=True)})",
        session_id=_room_session(user_id, room_id),
        metadata=payload,
    )


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

    guardian = _guardian()
    limit = _retrieve_limit()

    blocks: list[str] = []
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
