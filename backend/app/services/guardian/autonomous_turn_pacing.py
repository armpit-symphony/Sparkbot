"""Pacing layer for autonomous agent turns.

Provider failures (especially 4xx — provider-config or tool-incompat issues
like the MiniMax error 2013) used to send the autonomous-meeting dispatcher
into a tight retry loop, holding SQLite write locks long enough that
unrelated chat writes timed out and the user saw "Connection error" in the
desktop UI. This module gives the dispatcher a place to record outcomes and
ask "should I skip this agent's turn right now?" before each LLM call.

Behaviour summary:
  * On success → counter resets, any sleep is cleared.
  * On 4xx failure → counter increments and ``next_attempt_at`` is scheduled
    ``2 ** min(counter, 6)`` seconds in the future (1, 2, 4, 8, 16, 32, 64,
    capped at 64). After ``_FAIL_PAUSE_THRESHOLD`` consecutive 4xx failures
    within ``_FAIL_WINDOW_SECONDS``, the (room, agent) pair is marked paused
    and ``should_skip`` returns True until an operator resumes via the
    Guardian API.
  * On 5xx, network, or unknown errors → counter increments but no pause
    threshold (those are transient infra). The dispatcher's existing
    immediate-retry path keeps handling them.

The state lives in a sidecar JSON store under
``SPARKBOT_GUARDIAN_DATA_DIR/autonomous_turn_pacing/state.json`` (same
umbrella convention as ``improvement.py`` and ``correction_lock.py``). Per-
feature override is ``SPARKBOT_AUTONOMOUS_TURN_PACING_DATA_DIR``; the whole
module can be disabled with ``SPARKBOT_AUTONOMOUS_TURN_PACING_ENABLED=false``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "autonomous_turn_pacing"
_STORE_FILENAME = "state.json"
_MAX_TRACKED_PAIRS = 500

_FAIL_PAUSE_THRESHOLD = 8           # consecutive 4xx failures
_FAIL_WINDOW_SECONDS = 300          # within 5 minutes
_BACKOFF_MAX_EXPONENT = 6           # 2^6 = 64 seconds max sleep
_BACKOFF_MAX_SECONDS = 1 << _BACKOFF_MAX_EXPONENT


def pacing_enabled() -> bool:
    return os.getenv("SPARKBOT_AUTONOMOUS_TURN_PACING_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _data_dir() -> Path:
    configured = os.getenv("SPARKBOT_AUTONOMOUS_TURN_PACING_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    umbrella = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    if umbrella:
        return Path(umbrella).expanduser() / "autonomous_turn_pacing"
    return _DEFAULT_DATA_DIR


def _store_path() -> Path:
    path = _data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / _STORE_FILENAME


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _load_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"pairs": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"pairs": []}
    if not isinstance(payload, dict):
        return {"pairs": []}
    payload.setdefault("pairs", [])
    if not isinstance(payload["pairs"], list):
        payload["pairs"] = []
    return payload


def _save_store(store: dict[str, Any]) -> None:
    path = _store_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _find_pair(pairs: list[dict[str, Any]], room_id: str, agent_handle: str) -> dict[str, Any] | None:
    for item in pairs:
        if not isinstance(item, dict):
            continue
        if _norm(item.get("room_id")) == room_id and _norm(item.get("agent_handle")) == agent_handle:
            return item
    return None


def _new_pair(room_id: str, agent_handle: str) -> dict[str, Any]:
    return {
        "room_id": room_id,
        "agent_handle": agent_handle,
        "consecutive_failures": 0,
        "first_failure_at": "",
        "last_failure_at": "",
        "last_failure_status": None,
        "last_failure_error": "",
        "next_attempt_at": "",
        "paused": False,
        "paused_at": "",
        "paused_reason": "",
        "resumed_at": "",
        "resumed_by": "",
    }


def should_skip(*, room_id: str, agent_handle: str) -> tuple[bool, str | None]:
    """Return (skip, reason). ``reason`` is None when not skipping.

    Skips when the pair is paused, or when the backoff sleep window has not
    yet elapsed.
    """
    if not pacing_enabled():
        return False, None
    room = _norm(room_id)
    agent = _norm(agent_handle)
    if not room or not agent:
        return False, None
    store = _load_store()
    pair = _find_pair(store.get("pairs", []), room, agent)
    if pair is None:
        return False, None
    if bool(pair.get("paused")):
        reason = _norm(pair.get("paused_reason")) or "paused"
        return True, f"paused: {reason}"
    next_at = _parse_utc(pair.get("next_attempt_at"))
    if next_at is not None and next_at > _utc_now():
        wait_seconds = int((next_at - _utc_now()).total_seconds()) + 1
        return True, f"backoff: retry in {wait_seconds}s"
    return False, None


def record_success(*, room_id: str, agent_handle: str) -> None:
    if not pacing_enabled():
        return
    room = _norm(room_id)
    agent = _norm(agent_handle)
    if not room or not agent:
        return
    store = _load_store()
    pairs = store.setdefault("pairs", [])
    pair = _find_pair(pairs, room, agent)
    if pair is None or pair.get("consecutive_failures", 0) == 0 and not pair.get("next_attempt_at"):
        # Nothing to clear; avoid an unnecessary disk write.
        return
    if pair is None:
        return
    pair["consecutive_failures"] = 0
    pair["first_failure_at"] = ""
    pair["last_failure_at"] = ""
    pair["last_failure_status"] = None
    pair["last_failure_error"] = ""
    pair["next_attempt_at"] = ""
    _save_store(store)


def _is_4xx(status_code: int | None) -> bool:
    if status_code is None:
        return False
    try:
        return 400 <= int(status_code) < 500
    except Exception:
        return False


def record_failure(
    *,
    room_id: str,
    agent_handle: str,
    status_code: int | None = None,
    error: str = "",
) -> dict[str, Any] | None:
    """Record a failure. Returns the updated pair record, or None if disabled."""
    if not pacing_enabled():
        return None
    room = _norm(room_id)
    agent = _norm(agent_handle)
    if not room or not agent:
        return None

    store = _load_store()
    pairs = store.setdefault("pairs", [])
    pair = _find_pair(pairs, room, agent)
    now = _utc_now()
    if pair is None:
        pair = _new_pair(room, agent)
        pairs.insert(0, pair)
        del pairs[_MAX_TRACKED_PAIRS:]

    # If this failure is outside the sliding window, reset the streak so a
    # genuinely transient blip a long time later does not accumulate toward
    # a pause.
    last_failure = _parse_utc(pair.get("last_failure_at"))
    if last_failure is not None and (now - last_failure).total_seconds() > _FAIL_WINDOW_SECONDS:
        pair["consecutive_failures"] = 0
        pair["first_failure_at"] = ""

    pair["consecutive_failures"] = int(pair.get("consecutive_failures") or 0) + 1
    if not pair.get("first_failure_at"):
        pair["first_failure_at"] = now.isoformat()
    pair["last_failure_at"] = now.isoformat()
    pair["last_failure_status"] = int(status_code) if status_code is not None else None
    pair["last_failure_error"] = _norm(error)[:600]

    is_4xx = _is_4xx(status_code)
    if is_4xx:
        # Schedule the next attempt with exponential backoff. 2^0 = 1 sec on
        # the first failure, doubling each subsequent failure up to 64 sec.
        exponent = min(max(pair["consecutive_failures"] - 1, 0), _BACKOFF_MAX_EXPONENT)
        sleep_seconds = min(1 << exponent, _BACKOFF_MAX_SECONDS)
        pair["next_attempt_at"] = (now + timedelta(seconds=sleep_seconds)).isoformat()

        if pair["consecutive_failures"] >= _FAIL_PAUSE_THRESHOLD and not pair.get("paused"):
            pair["paused"] = True
            pair["paused_at"] = now.isoformat()
            pair["paused_reason"] = (
                f"{_FAIL_PAUSE_THRESHOLD} consecutive 4xx failures within "
                f"{_FAIL_WINDOW_SECONDS}s. Last status {pair['last_failure_status']}."
            )
    else:
        # Non-4xx (5xx, connection, unknown) clears any pending sleep — those
        # are transient infra and the existing immediate-retry path handles
        # them. We still record the failure for visibility but do not pause.
        pair["next_attempt_at"] = ""

    _save_store(store)
    return dict(pair)


def pause(*, room_id: str, agent_handle: str, reason: str = "operator_pause") -> dict[str, Any] | None:
    if not pacing_enabled():
        return None
    room = _norm(room_id)
    agent = _norm(agent_handle)
    if not room or not agent:
        return None
    store = _load_store()
    pairs = store.setdefault("pairs", [])
    pair = _find_pair(pairs, room, agent)
    if pair is None:
        pair = _new_pair(room, agent)
        pairs.insert(0, pair)
    pair["paused"] = True
    pair["paused_at"] = _utc_now_iso()
    pair["paused_reason"] = _norm(reason)[:200] or "operator_pause"
    _save_store(store)
    return dict(pair)


def resume(*, room_id: str, agent_handle: str, operator_id: str = "") -> dict[str, Any] | None:
    """Clear pause + counters for a (room, agent) pair. Returns updated record."""
    if not pacing_enabled():
        return None
    room = _norm(room_id)
    agent = _norm(agent_handle)
    if not room or not agent:
        return None
    store = _load_store()
    pair = _find_pair(store.get("pairs", []), room, agent)
    if pair is None:
        return None
    pair["paused"] = False
    pair["resumed_at"] = _utc_now_iso()
    pair["resumed_by"] = _norm(operator_id)[:80]
    pair["consecutive_failures"] = 0
    pair["first_failure_at"] = ""
    pair["last_failure_at"] = ""
    pair["last_failure_status"] = None
    pair["next_attempt_at"] = ""
    pair["paused_reason"] = ""
    _save_store(store)
    return dict(pair)


def list_paused() -> list[dict[str, Any]]:
    if not pacing_enabled():
        return []
    store = _load_store()
    return [
        dict(item)
        for item in store.get("pairs", [])
        if isinstance(item, dict) and bool(item.get("paused"))
    ]


def list_state() -> list[dict[str, Any]]:
    """Full state dump (paused + currently-backing-off + recently-failing)."""
    if not pacing_enabled():
        return []
    store = _load_store()
    return [dict(item) for item in store.get("pairs", []) if isinstance(item, dict)]
