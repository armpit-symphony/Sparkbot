"""
Desktop launcher for Sparkbot backend.
Bundled by PyInstaller and sideloaded by the Tauri shell.
Starts a local uvicorn server on 127.0.0.1:8765.
"""
import os
import sys

# Inject required env vars before any app module is imported.
# Settings() runs at module-level in app.core.config, so these must be set first.
os.environ.setdefault("PROJECT_NAME", "Sparkbot")
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("WORKSTATION_LIVE_TERMINAL_ENABLED", "false")
os.environ.setdefault("V1_LOCAL_MODE", "true")
os.environ.setdefault("SPARKBOT_PASSPHRASE", "sparkbot-local")
os.environ.setdefault("FIRST_SUPERUSER", "admin@example.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "sparkbot-local")
os.environ.setdefault(
    "BACKEND_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173"
    ",tauri://localhost,https://tauri.localhost",
)
os.environ.setdefault("FRONTEND_HOST", "http://127.0.0.1:5173")

# When running as a PyInstaller frozen bundle, ensure the bundle dir is on sys.path
if getattr(sys, "frozen", False):
    bundle_dir = sys._MEIPASS  # noqa: SLF001
    sys.path.insert(0, bundle_dir)
    # Fix SSL certificate verification inside the frozen bundle.
    # httpx (used by litellm) cannot find the system CA bundle when running from
    # sys._MEIPASS.  Point it at the certifi bundle that PyInstaller collected.
    import certifi  # noqa: E402 (must be after sys.path fixup)
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    # Point alembic / SQLite to a writable location beside the exe
    exe_dir = os.path.dirname(sys.executable)
    os.environ.setdefault("SPARKBOT_DATA_DIR", exe_dir)
    # Persist SECRET_KEY so JWT sessions survive app restarts.
    # Without this, every restart generates a new secret and all existing
    # login cookies become invalid, forcing re-login every session.
    _secret_key_path = os.path.join(exe_dir, "secret.key")
    if os.path.exists(_secret_key_path):
        with open(_secret_key_path) as _skf:
            _sk = _skf.read().strip()
            if _sk:
                os.environ.setdefault("SECRET_KEY", _sk)
    if not os.environ.get("SECRET_KEY"):
        import secrets as _secrets_mod
        _sk = _secrets_mod.token_urlsafe(32)
        with open(_secret_key_path, "w") as _skf:
            _skf.write(_sk)
        os.environ["SECRET_KEY"] = _sk
    # Ensure a .env file exists beside the exe for pydantic-settings and key storage
    env_path = os.path.join(exe_dir, ".env")
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write("PROJECT_NAME=Sparkbot\nDATABASE_TYPE=sqlite\nENVIRONMENT=local\n")
    # Load saved keys (e.g. OPENROUTER_API_KEY) from the .env into the current process.
    # setdefault is intentional: os.environ values set above take precedence.
    with open(env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())
    # Also load from SPARKBOT_DATA_DIR/.env (where model.py writes user keys).
    # Tauri sets SPARKBOT_DATA_DIR to %APPDATA%\Sparkbot, which differs from exe_dir.
    _data_dir = os.environ.get("SPARKBOT_DATA_DIR", "")
    if _data_dir and _data_dir != exe_dir:
        _data_env_path = os.path.join(_data_dir, ".env")
        if os.path.exists(_data_env_path):
            with open(_data_env_path) as _f2:
                for _line2 in _f2:
                    _line2 = _line2.strip()
                    if _line2 and not _line2.startswith("#") and "=" in _line2:
                        _k2, _, _v2 = _line2.partition("=")
                        os.environ.setdefault(_k2.strip(), _v2.strip())

import argparse  # noqa: E402
import uvicorn  # noqa: E402 (import after path fixup)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=None)  # consumed by Tauri; ignored here
    args, _ = parser.parse_known_args()

    # Initialize SQLite schema and seed initial superuser on fresh installs.
    # Safe to run on every startup — create_all uses checkfirst=True.
    try:
        from app.local_db_init import init_sqlite_schema
        from app.initial_data import init as _seed_initial_data
        init_sqlite_schema()
        _seed_initial_data()
    except Exception as _init_err:
        import logging as _logging
        _logging.getLogger(__name__).warning("DB init warning (non-fatal): %s", _init_err)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
