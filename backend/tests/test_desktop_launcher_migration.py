"""Tests for the guardian-sidecar migration helper in desktop_launcher.

The migration runs once on launch to seed the umbrella data dir from any
non-empty pre-umbrella source (legacy stable path or transient PyInstaller
_MEI*/data/<feature> path), so v1.6.71 proposals and correction locks do
not vanish when the user upgrades to v1.6.72.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_BACKEND = Path(__file__).resolve().parents[1]
LAUNCHER_PATH = REPO_BACKEND / "desktop_launcher.py"


def _load_launcher_module():
    # The launcher sets default env vars at import time. Load it as a sandboxed
    # module so the migration helper can be tested without side-effecting real
    # process env or importing the FastAPI app.
    spec = importlib.util.spec_from_file_location("desktop_launcher_for_test", LAUNCHER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["desktop_launcher_for_test"] = module
    spec.loader.exec_module(module)
    return module


def _seed(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_migration_pulls_in_proposals_from_legacy_stable_path(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path / "data"))

    legacy = tmp_path / "data" / "improvement_loop" / "outcomes.json"
    _seed(legacy, {"improvement_proposals": [{"id": "improve-legacy", "summary": "from legacy", "status": "proposed"}]})

    launcher = _load_launcher_module()
    umbrella = tmp_path / "data" / "guardian-data"
    launcher._migrate_guardian_sidecar_data(str(umbrella))

    target = umbrella / "improvement_loop" / "outcomes.json"
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    summaries = [p["summary"] for p in payload["improvement_proposals"]]
    assert "from legacy" in summaries


def test_migration_picks_freshest_mei_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path / "data"))

    appdata_sb = tmp_path / "appdata" / "Sparkbot" / "pyi-runtime"
    older = appdata_sb / "_MEI100" / "data" / "improvement_loop" / "outcomes.json"
    _seed(older, {"improvement_proposals": [{"id": "improve-old", "summary": "from older MEI", "status": "proposed"}]})
    newer = appdata_sb / "_MEI200" / "data" / "improvement_loop" / "outcomes.json"
    _seed(newer, {"improvement_proposals": [{"id": "improve-new", "summary": "from newer MEI", "status": "proposed"}]})

    # Bump newer's mtime explicitly.
    older_mtime = older.stat().st_mtime
    import os
    os.utime(newer, (older_mtime + 100, older_mtime + 100))

    launcher = _load_launcher_module()
    umbrella = tmp_path / "data" / "guardian-data"
    launcher._migrate_guardian_sidecar_data(str(umbrella))

    target = umbrella / "improvement_loop" / "outcomes.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    summaries = [p["summary"] for p in payload["improvement_proposals"]]
    assert "from newer MEI" in summaries
    assert "from older MEI" not in summaries


def test_migration_is_idempotent_when_target_exists(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path / "data"))

    target = tmp_path / "data" / "guardian-data" / "improvement_loop" / "outcomes.json"
    _seed(target, {"improvement_proposals": [{"id": "improve-existing", "summary": "already there", "status": "proposed"}]})

    legacy = tmp_path / "data" / "improvement_loop" / "outcomes.json"
    _seed(legacy, {"improvement_proposals": [{"id": "improve-legacy", "summary": "should not overwrite", "status": "proposed"}]})

    launcher = _load_launcher_module()
    launcher._migrate_guardian_sidecar_data(str(target.parent.parent))

    payload = json.loads(target.read_text(encoding="utf-8"))
    summaries = [p["summary"] for p in payload["improvement_proposals"]]
    assert "already there" in summaries
    assert "should not overwrite" not in summaries


def test_migration_handles_missing_sources(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path / "data"))

    launcher = _load_launcher_module()
    # No sources, no legacy, no MEI. Should be a no-op without raising.
    launcher._migrate_guardian_sidecar_data(str(tmp_path / "data" / "guardian-data"))
    assert not (tmp_path / "data" / "guardian-data" / "improvement_loop" / "outcomes.json").exists()


def test_migration_covers_correction_locks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path / "data"))

    legacy = tmp_path / "data" / "correction_locks" / "locks.json"
    _seed(legacy, {"locks": [{"id": "lock-1", "room_id": "room-A", "intent_kind": "self_inspection", "active": True}]})

    launcher = _load_launcher_module()
    umbrella = tmp_path / "data" / "guardian-data"
    launcher._migrate_guardian_sidecar_data(str(umbrella))

    target = umbrella / "correction_locks" / "locks.json"
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert any(item["room_id"] == "room-A" for item in payload["locks"])
