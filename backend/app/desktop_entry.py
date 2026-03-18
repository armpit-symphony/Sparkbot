"""Sparkbot v1 Local desktop backend entrypoint.

This module is the sidecar target for the Windows desktop shell. It mirrors the
current start-local backend scripts, but packages the backend as a single
PyInstaller executable that Tauri can launch.
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import sys
from pathlib import Path


logger = logging.getLogger(__name__)


def _load_or_create_secret_key(data_dir: Path) -> str:
    """Persist SECRET_KEY across restarts so sessions survive app relaunches."""
    key_file = data_dir / "secret.key"
    if key_file.exists():
        key = key_file.read_text().strip()
        if key:
            return key
    key = secrets.token_urlsafe(32)
    key_file.write_text(key)
    return key


def _default_data_dir() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / "Sparkbot"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Sparkbot"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "sparkbot"


def _configure_environment(args: argparse.Namespace) -> tuple[Path, Path]:
    data_dir = Path(args.data_dir).expanduser() if args.data_dir else _default_data_dir()
    guardian_dir = data_dir / "guardian"

    os.environ.setdefault("V1_LOCAL_MODE", "true")
    os.environ.setdefault("DATABASE_TYPE", "sqlite")
    os.environ.setdefault("WORKSTATION_LIVE_TERMINAL_ENABLED", "false")
    os.environ.setdefault("ENVIRONMENT", "local")
    os.environ.setdefault("PROJECT_NAME", "Sparkbot")
    os.environ.setdefault("FIRST_SUPERUSER", "admin@example.com")
    os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "sparkbot-local")
    os.environ.setdefault(
        "BACKEND_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
        ",tauri://localhost,https://tauri.localhost",
    )
    os.environ.setdefault("FRONTEND_HOST", "http://127.0.0.1:5173")
    os.environ.setdefault("SPARKBOT_PASSPHRASE", args.passphrase or "sparkbot-local")
    os.environ["SPARKBOT_DATA_DIR"] = str(data_dir)
    os.environ["SPARKBOT_GUARDIAN_DATA_DIR"] = str(guardian_dir)

    data_dir.mkdir(parents=True, exist_ok=True)
    guardian_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, guardian_dir


def _initialize_local_state() -> None:
    from app.initial_data import init as seed_initial_data
    from app.local_db_init import init_sqlite_schema

    init_sqlite_schema()
    seed_initial_data()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sparkbot v1 Local desktop backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--passphrase", default="")
    parser.add_argument("--log-level", default="info")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()
    data_dir, guardian_dir = _configure_environment(args)
    logger.info("Sparkbot desktop backend starting")
    logger.info("Data dir: %s", data_dir)
    logger.info("Guardian dir: %s", guardian_dir)

    # Persist SECRET_KEY so sessions survive app restarts
    os.environ.setdefault("SECRET_KEY", _load_or_create_secret_key(data_dir))

    _initialize_local_state()

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        reload=False,
    )


if __name__ == "__main__":
    main()
