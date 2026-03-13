from pathlib import Path

from app.services.guardian import vault


def test_vault_uses_app_data_dir_when_guardian_dir_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SPARKBOT_GUARDIAN_DATA_DIR", raising=False)
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path / "sparkbot-data"))

    assert vault._db_path() == tmp_path / "sparkbot-data" / "guardian" / "vault.db"


def test_vault_prefers_explicit_guardian_data_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path / "sparkbot-data"))
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(tmp_path / "guardian-explicit"))

    assert vault._db_path() == tmp_path / "guardian-explicit" / "vault.db"
