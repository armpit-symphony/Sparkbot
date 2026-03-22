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

# When running as a PyInstaller frozen bundle, ensure the bundle dir is on sys.path
if getattr(sys, "frozen", False):
    bundle_dir = sys._MEIPASS  # noqa: SLF001
    sys.path.insert(0, bundle_dir)
    # Point Python's ssl module to the certifi CA bundle bundled by PyInstaller.
    # Build the path directly from _MEIPASS instead of calling certifi.where()
    # because importlib.resources resolution is unreliable in frozen environments.
    # ssl.create_default_context() (used in the backend httpx calls) honours
    # SSL_CERT_FILE automatically; REQUESTS_CA_BUNDLE covers requests/urllib3.
    _ca_bundle = os.path.join(bundle_dir, "certifi", "cacert.pem")
    if os.path.exists(_ca_bundle):
        os.environ["SSL_CERT_FILE"] = _ca_bundle
        os.environ["REQUESTS_CA_BUNDLE"] = _ca_bundle
    # Point alembic / SQLite to a writable location beside the exe
    exe_dir = os.path.dirname(sys.executable)
    os.environ.setdefault("SPARKBOT_DATA_DIR", exe_dir)
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

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        log_level="info",
    )
