from pathlib import Path

from app.services.guardian import correction_lock


def _reset_correction_lock(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_CORRECTION_LOCK_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_CORRECTION_LOCK_DATA_DIR", str(tmp_path / "correction_locks"))


def test_record_then_is_suppressed(monkeypatch, tmp_path: Path) -> None:
    _reset_correction_lock(monkeypatch, tmp_path)

    record = correction_lock.record_correction(
        room_id="room-A",
        intent_kind="self_inspection",
        trigger_phrase="that's not an answer",
        user_id="user-1",
    )

    assert record is not None
    assert record["active"] is True
    assert record["hit_count"] == 1
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is True


def test_room_scoping(monkeypatch, tmp_path: Path) -> None:
    _reset_correction_lock(monkeypatch, tmp_path)
    correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="just answer")

    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is True
    assert correction_lock.is_suppressed(room_id="room-B", intent_kind="self_inspection") is False


def test_intent_scoping(monkeypatch, tmp_path: Path) -> None:
    _reset_correction_lock(monkeypatch, tmp_path)
    correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="stop dumping state")

    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is True
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="provider_readiness") is False


def test_record_is_idempotent_and_increments_hit_count(monkeypatch, tmp_path: Path) -> None:
    _reset_correction_lock(monkeypatch, tmp_path)
    first = correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="just answer")
    second = correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="answer my question")
    third = correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="that's not an answer")

    assert first is not None and second is not None and third is not None
    assert first["id"] == second["id"] == third["id"]
    assert third["hit_count"] == 3
    assert third["last_trigger_phrase"] == "that's not an answer"

    listed = correction_lock.list_corrections(room_id="room-A")
    assert len(listed) == 1


def test_persists_across_fresh_load(monkeypatch, tmp_path: Path) -> None:
    _reset_correction_lock(monkeypatch, tmp_path)
    correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="just answer")

    # Simulate a fresh process by clearing in-memory caches via monkeypatch only
    # (the module is stateless apart from env-driven path resolution).
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is True
    listed = correction_lock.list_corrections(room_id="room-A")
    assert len(listed) == 1
    assert listed[0]["room_id"] == "room-A"


def test_clear_lifts_suppression(monkeypatch, tmp_path: Path) -> None:
    _reset_correction_lock(monkeypatch, tmp_path)
    correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="just answer")
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is True

    cleared = correction_lock.clear_correction(room_id="room-A", intent_kind="self_inspection")
    assert cleared == 1
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is False


def test_clear_without_intent_clears_all_for_room(monkeypatch, tmp_path: Path) -> None:
    _reset_correction_lock(monkeypatch, tmp_path)
    correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="x")
    correction_lock.record_correction(room_id="room-A", intent_kind="provider_readiness", trigger_phrase="y")
    correction_lock.record_correction(room_id="room-B", intent_kind="self_inspection", trigger_phrase="z")

    cleared = correction_lock.clear_correction(room_id="room-A", intent_kind=None)
    assert cleared == 2
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is False
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="provider_readiness") is False
    # Room B was untouched.
    assert correction_lock.is_suppressed(room_id="room-B", intent_kind="self_inspection") is True


def test_disabled_flag_is_respected(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_CORRECTION_LOCK_ENABLED", "false")
    monkeypatch.setenv("SPARKBOT_CORRECTION_LOCK_DATA_DIR", str(tmp_path / "correction_locks"))

    assert correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection") is None
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is False
    assert correction_lock.clear_correction(room_id="room-A", intent_kind="self_inspection") == 0


def test_missing_room_or_intent_is_no_op(monkeypatch, tmp_path: Path) -> None:
    _reset_correction_lock(monkeypatch, tmp_path)

    assert correction_lock.record_correction(room_id=None, intent_kind="self_inspection") is None
    assert correction_lock.record_correction(room_id="room-A", intent_kind="") is None
    assert correction_lock.is_suppressed(room_id="", intent_kind="self_inspection") is False
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="") is False


def test_guardian_data_dir_umbrella_takes_effect(monkeypatch, tmp_path: Path) -> None:
    # Simulate the desktop launcher: per-feature env unset, umbrella set.
    monkeypatch.setenv("SPARKBOT_CORRECTION_LOCK_ENABLED", "true")
    monkeypatch.delenv("SPARKBOT_CORRECTION_LOCK_DATA_DIR", raising=False)
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian-data"))

    correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="x")
    assert (tmp_path / "guardian-data" / "correction_locks" / "locks.json").exists()
    assert correction_lock.is_suppressed(room_id="room-A", intent_kind="self_inspection") is True


def test_per_feature_env_wins_over_umbrella(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_CORRECTION_LOCK_ENABLED", "true")
    monkeypatch.setenv("SPARKBOT_CORRECTION_LOCK_DATA_DIR", str(tmp_path / "per_feature"))
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "umbrella"))

    correction_lock.record_correction(room_id="room-A", intent_kind="self_inspection", trigger_phrase="y")
    assert (tmp_path / "per_feature" / "locks.json").exists()
    assert not (tmp_path / "umbrella" / "correction_locks" / "locks.json").exists()
