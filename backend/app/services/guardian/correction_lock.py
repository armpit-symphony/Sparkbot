"""Durable per-room correction lock.

When a user corrects Sparkbot for misrouting an intent (for example saying
"that's not an answer" or "stop dumping runtime state"), the correction needs
to outlive the immediate 6-message conversation window so the same misroute
does not repeat in the next turn or the next session.

This module persists those corrections in a sidecar JSON store and exposes
``is_suppressed`` so intent matchers can ask "should I skip this short-circuit
because the user already pushed back on it?". The store is intentionally
narrow — it records intent-suppression flags only, never conversation
content — so it does not duplicate the Memory Guardian content path.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "correction_locks"
_STORE_FILENAME = "locks.json"
_MAX_LOCKS = 200


def correction_lock_enabled() -> bool:
    return os.getenv("SPARKBOT_CORRECTION_LOCK_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _data_dir() -> Path:
    configured = os.getenv("SPARKBOT_CORRECTION_LOCK_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_DATA_DIR


def _store_path() -> Path:
    path = _data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / _STORE_FILENAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"locks": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"locks": []}
    if not isinstance(payload, dict):
        return {"locks": []}
    payload.setdefault("locks", [])
    if not isinstance(payload["locks"], list):
        payload["locks"] = []
    return payload


def _save_store(store: dict[str, Any]) -> None:
    path = _store_path()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _normalize(value: str | None) -> str:
    return str(value or "").strip()


def record_correction(
    *,
    room_id: str | None,
    intent_kind: str,
    trigger_phrase: str = "",
    user_id: str | None = None,
) -> dict[str, Any] | None:
    """Persist that the user has pushed back on a particular intent in this room.

    Idempotent: if an active lock already exists for the (room_id, intent_kind)
    pair, the existing record's ``last_seen_at`` is bumped and ``hit_count``
    incremented rather than creating a duplicate.
    """
    if not correction_lock_enabled():
        return None

    room = _normalize(room_id)
    intent = _normalize(intent_kind)
    if not room or not intent:
        return None

    store = _load_store()
    locks = store.setdefault("locks", [])
    now_iso = _utc_now_iso()

    for existing in locks:
        if (
            isinstance(existing, dict)
            and bool(existing.get("active"))
            and _normalize(existing.get("room_id")) == room
            and _normalize(existing.get("intent_kind")) == intent
        ):
            existing["last_seen_at"] = now_iso
            existing["hit_count"] = int(existing.get("hit_count") or 1) + 1
            if trigger_phrase:
                existing["last_trigger_phrase"] = _normalize(trigger_phrase)[:200]
            _save_store(store)
            return dict(existing)

    record = {
        "id": f"corrlock-{uuid.uuid4().hex[:12]}",
        "room_id": room,
        "intent_kind": intent,
        "user_id": _normalize(user_id),
        "trigger_phrase": _normalize(trigger_phrase)[:200],
        "last_trigger_phrase": _normalize(trigger_phrase)[:200],
        "created_at": now_iso,
        "last_seen_at": now_iso,
        "hit_count": 1,
        "active": True,
    }
    locks.insert(0, record)
    del locks[_MAX_LOCKS:]
    _save_store(store)
    return dict(record)


def is_suppressed(*, room_id: str | None, intent_kind: str) -> bool:
    """Return True when the room has an active correction lock for this intent."""
    if not correction_lock_enabled():
        return False
    room = _normalize(room_id)
    intent = _normalize(intent_kind)
    if not room or not intent:
        return False
    store = _load_store()
    for item in store.get("locks", []):
        if not isinstance(item, dict):
            continue
        if not bool(item.get("active")):
            continue
        if _normalize(item.get("room_id")) != room:
            continue
        if _normalize(item.get("intent_kind")) != intent:
            continue
        return True
    return False


def clear_correction(*, room_id: str | None, intent_kind: str | None = None) -> int:
    """Mark matching locks inactive. Returns the number of locks cleared.

    If ``intent_kind`` is None, clears every active lock for the room.
    """
    if not correction_lock_enabled():
        return 0
    room = _normalize(room_id)
    if not room:
        return 0
    intent = _normalize(intent_kind) if intent_kind is not None else ""

    store = _load_store()
    cleared = 0
    now_iso = _utc_now_iso()
    for item in store.get("locks", []):
        if not isinstance(item, dict):
            continue
        if not bool(item.get("active")):
            continue
        if _normalize(item.get("room_id")) != room:
            continue
        if intent and _normalize(item.get("intent_kind")) != intent:
            continue
        item["active"] = False
        item["cleared_at"] = now_iso
        cleared += 1
    if cleared:
        _save_store(store)
    return cleared


def list_corrections(*, room_id: str | None = None, active_only: bool = True) -> list[dict[str, Any]]:
    if not correction_lock_enabled():
        return []
    room_filter = _normalize(room_id)
    store = _load_store()
    rows: list[dict[str, Any]] = []
    for item in store.get("locks", []):
        if not isinstance(item, dict):
            continue
        if active_only and not bool(item.get("active")):
            continue
        if room_filter and _normalize(item.get("room_id")) != room_filter:
            continue
        rows.append(dict(item))
    return rows
