from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.guardian import autonomous_turn_pacing as pacing


def _reset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_AUTONOMOUS_TURN_PACING_ENABLED", "true")
    monkeypatch.setenv(
        "SPARKBOT_AUTONOMOUS_TURN_PACING_DATA_DIR",
        str(tmp_path / "autonomous_turn_pacing"),
    )


def test_clean_state_does_not_skip(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    skip, reason = pacing.should_skip(room_id="room-A", agent_handle="minimax")
    assert skip is False
    assert reason is None


def test_4xx_failure_schedules_backoff(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    record = pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="invalid chat setting")
    assert record is not None
    assert record["consecutive_failures"] == 1
    assert record["next_attempt_at"]  # backoff scheduled
    skip, reason = pacing.should_skip(room_id="room-A", agent_handle="minimax")
    assert skip is True
    assert reason is not None and reason.startswith("backoff")


def test_5xx_failure_does_not_schedule_backoff(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    record = pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=503, error="upstream")
    assert record is not None
    assert record["consecutive_failures"] == 1
    assert not record["next_attempt_at"]
    skip, _ = pacing.should_skip(room_id="room-A", agent_handle="minimax")
    assert skip is False


def test_threshold_reached_paused(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    # Drive 8 consecutive 4xx failures within the window.
    last = None
    for _ in range(pacing._FAIL_PAUSE_THRESHOLD):
        last = pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
    assert last is not None
    assert last["paused"] is True
    skip, reason = pacing.should_skip(room_id="room-A", agent_handle="minimax")
    assert skip is True
    assert reason is not None and reason.startswith("paused")


def test_below_threshold_not_paused(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    last = None
    for _ in range(pacing._FAIL_PAUSE_THRESHOLD - 1):
        last = pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
    assert last is not None
    assert last["paused"] is False


def test_success_clears_counters(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
    pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
    pacing.record_success(room_id="room-A", agent_handle="minimax")
    skip, _ = pacing.should_skip(room_id="room-A", agent_handle="minimax")
    assert skip is False
    state = pacing.list_state()
    assert state[0]["consecutive_failures"] == 0
    assert state[0]["next_attempt_at"] == ""


def test_resume_clears_pause(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    for _ in range(pacing._FAIL_PAUSE_THRESHOLD):
        pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
    paused_list = pacing.list_paused()
    assert len(paused_list) == 1

    resumed = pacing.resume(room_id="room-A", agent_handle="minimax", operator_id="op-1")
    assert resumed is not None
    assert resumed["paused"] is False
    assert resumed["resumed_by"] == "op-1"
    assert pacing.list_paused() == []
    skip, _ = pacing.should_skip(room_id="room-A", agent_handle="minimax")
    assert skip is False


def test_pair_scoping(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
    skip_a, _ = pacing.should_skip(room_id="room-A", agent_handle="minimax")
    skip_b, _ = pacing.should_skip(room_id="room-A", agent_handle="meetings_manager")
    skip_c, _ = pacing.should_skip(room_id="room-B", agent_handle="minimax")
    assert skip_a is True
    assert skip_b is False
    assert skip_c is False


def test_failure_outside_window_resets_counter(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    # Manually seed a stale failure timestamp older than the window.
    pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
    store = pacing._load_store()
    pair = pacing._find_pair(store["pairs"], "room-A", "minimax")
    assert pair is not None
    stale = (datetime.now(timezone.utc) - timedelta(seconds=pacing._FAIL_WINDOW_SECONDS + 60)).isoformat()
    pair["last_failure_at"] = stale
    pair["consecutive_failures"] = 7
    pacing._save_store(store)

    new_record = pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="y")
    assert new_record is not None
    # The stale streak was reset, so this becomes consecutive #1, not #8.
    assert new_record["consecutive_failures"] == 1
    assert new_record["paused"] is False


def test_disabled_flag_is_a_no_op(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_AUTONOMOUS_TURN_PACING_ENABLED", "false")
    monkeypatch.setenv(
        "SPARKBOT_AUTONOMOUS_TURN_PACING_DATA_DIR",
        str(tmp_path / "autonomous_turn_pacing"),
    )
    skip, _ = pacing.should_skip(room_id="room-A", agent_handle="minimax")
    assert skip is False
    assert pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400) is None
    assert pacing.list_paused() == []


def test_guardian_data_dir_umbrella_routes_pacing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_AUTONOMOUS_TURN_PACING_ENABLED", "true")
    monkeypatch.delenv("SPARKBOT_AUTONOMOUS_TURN_PACING_DATA_DIR", raising=False)
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian-data"))

    pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
    target = tmp_path / "guardian-data" / "autonomous_turn_pacing" / "state.json"
    assert target.exists()


def test_backoff_grows_exponentially_then_caps(monkeypatch, tmp_path: Path) -> None:
    _reset(monkeypatch, tmp_path)
    waits: list[int] = []
    for _ in range(8):
        record = pacing.record_failure(room_id="room-A", agent_handle="minimax", status_code=400, error="x")
        assert record is not None
        last_failure = datetime.fromisoformat(record["last_failure_at"])
        next_attempt = datetime.fromisoformat(record["next_attempt_at"])
        waits.append(int(round((next_attempt - last_failure).total_seconds())))
    # Powers of 2 capped at 64: failure 1=1, 2=2, 3=4, 4=8, 5=16, 6=32, 7=64, 8=64.
    assert waits == [1, 2, 4, 8, 16, 32, 64, 64]
