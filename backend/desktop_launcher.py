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
    # Point alembic / SQLite to a writable location beside the exe
    exe_dir = os.path.dirname(sys.executable)
    os.environ.setdefault("SPARKBOT_DATA_DIR", exe_dir)
    # Also write a minimal .env beside the exe so pydantic-settings finds it
    env_path = os.path.join(exe_dir, ".env")
    if not os.path.exists(env_path):
        with open(env_path, "w") as f:
            f.write("PROJECT_NAME=Sparkbot\nDATABASE_TYPE=sqlite\nENVIRONMENT=local\n")

import uvicorn  # noqa: E402 (import after path fixup)

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
        # reload=False is the default; keep it off for frozen builds
    )
