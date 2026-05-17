"""
Desktop launcher for Sparkbot backend.
Bundled by PyInstaller and sideloaded by the Tauri shell.
Starts a local uvicorn server on 127.0.0.1:8765.
"""
import json
import os
import shutil
import sys
from pathlib import Path


# ── Guardian sidecar migration ────────────────────────────────────────────────
# Both improvement_loop and correction_lock store JSON in
# Path(__file__).resolve().parents[3] / "data" / <feature> by default. Under a
# PyInstaller frozen build that path resolves into sys._MEIPASS, which gets
# recreated on every launch — so proposals and correction locks would be wiped
# on every desktop restart unless we redirect the data dir. This helper runs
# once at launch, before app modules are imported.
_GUARDIAN_SIDECAR_FEATURES = (
    ("improvement_loop", "outcomes.json"),
    ("correction_locks", "locks.json"),
)


def _migrate_guardian_sidecar_data(umbrella_dir: str) -> None:
    """Seed the umbrella data dir from any non-empty pre-umbrella source.

    Sources are checked in this order; the freshest non-empty one wins:
      1. <DATA_DIR>/<feature>/<file>  — the legacy pre-umbrella stable path
         (used briefly during v1.6.71 testing before this fix landed).
      2. <APPDATA>/Sparkbot/pyi-runtime/_MEI*/data/<feature>/<file>  — the
         transient PyInstaller default that we are migrating away from.

    Idempotent: if the umbrella file already exists with content, nothing is
    copied. We keep this purely additive so it cannot lose data.
    """
    umbrella = Path(umbrella_dir).expanduser()
    appdata = Path(os.environ.get("APPDATA") or os.path.expanduser("~"))
    legacy_root = Path(os.environ.get("SPARKBOT_DATA_DIR") or umbrella.parent)
    pyi_runtime = appdata / "Sparkbot" / "pyi-runtime"

    for feature, filename in _GUARDIAN_SIDECAR_FEATURES:
        target = umbrella / feature / filename
        if target.exists() and target.stat().st_size > 0:
            continue

        candidates: list[Path] = []
        legacy = legacy_root / feature / filename
        if legacy.exists() and legacy.stat().st_size > 0 and legacy.resolve() != target.resolve():
            candidates.append(legacy)
        if pyi_runtime.exists():
            for mei in pyi_runtime.glob("_MEI*"):
                candidate = mei / "data" / feature / filename
                if candidate.exists() and candidate.stat().st_size > 0:
                    candidates.append(candidate)
        if not candidates:
            continue

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for source in candidates:
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            break


def _rotate_oversized_backend_log(log_path: str, max_bytes: int = 50 * 1024 * 1024) -> None:
    """Rename `sparkbot-backend.log` to `.1` if it has grown past `max_bytes`.

    Pre-v1.6.80 builds wrote httpcore/httpx DEBUG to the log, which produced
    ~600 MB files on busy installs. v1.6.80 lowered the level, but existing
    installs would still carry the legacy file forward. Rotating on launch
    gives upgraders a clean slate while preserving the prior log for one
    cycle of triage.
    """
    try:
        path = Path(log_path)
        if not path.exists() or path.stat().st_size <= max_bytes:
            return
        rotated = path.with_suffix(path.suffix + ".1")
        if rotated.exists():
            try:
                rotated.unlink()
            except Exception:
                pass
        path.rename(rotated)
    except Exception:
        # Never block startup over log housekeeping.
        pass


def _prune_stale_pyinstaller_temp_dirs(pyi_runtime_root: Path, keep_latest: int = 2) -> None:
    """Remove old `_MEI*` PyInstaller temp dirs from `pyi-runtime/`.

    PyInstaller is supposed to delete these on graceful exit, but desktop
    builds frequently terminate abruptly (Tauri close, user logout, crash)
    and leave the directories behind. Each is ~50 MB; observed installs
    accumulated 30+ dirs (~1.5 GB) over the v1.6.6x → v1.6.8x line. We keep
    the newest `keep_latest` as a safety margin in case the current process
    still references one — the active `sys._MEIPASS` is always among them.
    """
    try:
        if not pyi_runtime_root.exists():
            return
        candidates = [p for p in pyi_runtime_root.glob("_MEI*") if p.is_dir()]
        if len(candidates) <= keep_latest:
            return
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        active = getattr(sys, "_MEIPASS", "")
        active_path = Path(active).resolve() if active else None
        for stale in candidates[keep_latest:]:
            try:
                if active_path and stale.resolve() == active_path:
                    continue
                shutil.rmtree(stale, ignore_errors=True)
            except Exception:
                # One bad dir shouldn't stop the rest.
                continue
    except Exception:
        # Never block startup over disk housekeeping.
        pass


# Inject required env vars before any app module is imported.
# Settings() runs at module-level in app.core.config, so these must be set first.
os.environ.setdefault("PROJECT_NAME", "Sparkbot")
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("WORKSTATION_LIVE_TERMINAL_ENABLED", "false")
os.environ.setdefault("SPARKBOT_BROWSER_HEADLESS", "false")  # show browser window on desktop
os.environ.setdefault("SPARKBOT_DM_EXECUTION_DEFAULT", "true")  # enable shell/terminal/browser in DM

# Point Playwright at a stable persistent directory so Chromium survives app restarts.
# Without this, Playwright installs browsers relative to the PyInstaller temp dir
# which gets a new random path (_MEIxxxxxx) on every launch, losing Chromium each time.
_pw_browsers_dir = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "Sparkbot", "playwright-browsers"
)
os.makedirs(_pw_browsers_dir, exist_ok=True)
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _pw_browsers_dir)
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
    # Guardian sidecar stores (improvement loop, correction lock, future
    # autonomous-turn pacing) need a writable location that survives across
    # desktop restarts. The module defaults resolve into sys._MEIPASS, which
    # PyInstaller wipes on every launch, so route them through the data dir.
    os.environ.setdefault(
        "SPARKBOT_GUARDIAN_DATA_DIR",
        os.path.join(os.environ["SPARKBOT_DATA_DIR"], "guardian-data"),
    )
    _migrate_guardian_sidecar_data(os.environ["SPARKBOT_GUARDIAN_DATA_DIR"])
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
    # Persist vault encryption key — generated once, reused forever.
    _vault_key_path = os.path.join(exe_dir, "vault.key")
    if os.path.exists(_vault_key_path):
        with open(_vault_key_path) as _vkf:
            _vk = _vkf.read().strip()
            if _vk:
                os.environ.setdefault("SPARKBOT_VAULT_KEY", _vk)
    if not os.environ.get("SPARKBOT_VAULT_KEY"):
        from cryptography.fernet import Fernet as _Fernet
        _vk = _Fernet.generate_key().decode()
        with open(_vault_key_path, "w") as _vkf:
            _vkf.write(_vk)
        os.environ["SPARKBOT_VAULT_KEY"] = _vk
    # Point the skill loader at the bundled skills directory inside sys._MEIPASS.
    # Without this, skills.py falls back to "skills" relative to __file__ which
    # does not exist in a frozen binary — all skills return "Unknown tool".
    os.environ.setdefault("SPARKBOT_SKILLS_DIR", os.path.join(sys._MEIPASS, "skills"))  # noqa: SLF001
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
    # ── Playwright browser auto-install ───────────────────────────────────────
    # The Playwright Python package is bundled in the frozen binary, but the
    # Chromium browser binary lives outside the bundle (~150 MB; downloaded once
    # to %LOCALAPPDATA%\ms-playwright on Windows).  We download it on first
    # launch so browser_open / browser_fill_field work without manual setup.
    # Check both the marker AND that Chromium actually exists at the stable path.
    # If the marker exists but no chrome.exe is found, re-run the install.
    _playwright_marker = os.path.join(exe_dir, ".playwright_ready")
    _chromium_found = any(
        True for _, _, files in os.walk(_pw_browsers_dir)
        if any(f in ("chrome.exe", "chrome") for f in files)
    ) if os.path.isdir(_pw_browsers_dir) else False
    if not os.path.exists(_playwright_marker) or not _chromium_found:
        try:
            import subprocess as _pw_subprocess
            _pw_log = _root_logging.getLogger("sparkbot.playwright_install")

            # Locate the Playwright Node driver.  In a frozen PyInstaller binary
            # the playwright package lives inside sys._MEIPASS, so we search
            # there first, then fall back to compute_driver_executable().
            _driver_exe = None
            _meipass = getattr(sys, "_MEIPASS", None)
            if _meipass:
                import pathlib as _pathlib
                for _candidate in (
                    _pathlib.Path(_meipass) / "playwright" / "driver" / "playwright.cmd",
                    _pathlib.Path(_meipass) / "playwright" / "driver" / "playwright",
                ):
                    if _candidate.exists():
                        _driver_exe = str(_candidate)
                        break

            if _driver_exe is None:
                try:
                    from playwright._impl._driver import compute_driver_executable as _cde
                    _p, _ = _cde()
                    if _p.exists():
                        _driver_exe = str(_p)
                except Exception as _e:
                    _pw_log.warning("compute_driver_executable failed: %s", _e)

            if _driver_exe:
                _pw_log.info("Installing Playwright Chromium via driver: %s", _driver_exe)
                _result = _pw_subprocess.run(
                    [_driver_exe, "install", "chromium"],
                    capture_output=True, timeout=600,
                )
                _pw_log.info(
                    "playwright install chromium exit=%s stdout=%s stderr=%s",
                    _result.returncode,
                    (_result.stdout or b"")[:500],
                    (_result.stderr or b"")[:500],
                )
                if _result.returncode == 0:
                    with open(_playwright_marker, "w") as _pmf:
                        _pmf.write("ok")
            else:
                _pw_log.warning("Playwright driver not found — browser tools will not work")
        except Exception as _pw_err:
            try:
                _root_logging.getLogger("sparkbot.playwright_install").warning(
                    "Playwright install failed: %s", _pw_err
                )
            except Exception:
                pass

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
import logging as _root_logging  # noqa: E402
import traceback as _traceback  # noqa: E402
import uvicorn  # noqa: E402 (import after path fixup)

# Hard startup log: write every log line to a file beside the exe so crashes
# are visible even when the Tauri console is hidden (windows_subsystem = "windows").
#
# Default level is INFO. Previously DEBUG, which produced ~600 MB log files in
# a week (httpcore long-poll spam from the Telegram bridge dominated). Operators
# who need lower-level diagnostics can set SPARKBOT_BACKEND_LOG_LEVEL=debug.
# httpcore/httpx/h2/rustls/openai-base-client/cookie_store are pinned at WARNING
# even when root is INFO — they account for >90% of historic log volume and
# offer almost no actionable signal for end users.
if getattr(sys, "frozen", False):
    _log_path = os.path.join(os.path.dirname(sys.executable), "sparkbot-backend.log")
    # Rotate the prior log file BEFORE basicConfig opens it for writing.
    # Pre-v1.6.80 builds wrote DEBUG-level httpcore spam and could leave behind
    # 600+ MB files; rotating gives upgraders a clean slate while preserving
    # the previous run as `.log.1` for one cycle.
    _rotate_oversized_backend_log(_log_path)
    # Prune stale PyInstaller temp dirs left behind by abrupt exits. Keeps
    # the two newest as a safety margin (current run + previous in case the
    # OS still holds a handle).
    try:
        _appdata = Path(os.environ.get("APPDATA") or os.path.expanduser("~"))
        _prune_stale_pyinstaller_temp_dirs(_appdata / "Sparkbot" / "pyi-runtime")
    except Exception:
        pass
    _level_name = os.environ.get("SPARKBOT_BACKEND_LOG_LEVEL", "info").strip().upper()
    _level = getattr(_root_logging, _level_name, _root_logging.INFO)
    if not isinstance(_level, int):
        _level = _root_logging.INFO
    _root_logging.basicConfig(
        filename=_log_path,
        level=_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )
    for _noisy in (
        "httpcore",
        "httpcore.http11",
        "httpcore.connection",
        "httpx",
        "h2",
        "h2.codec",
        "h2.client",
        "rustls",
        "rustls.client",
        "openai._base_client",
        "cookie_store",
        "primp",
    ):
        _root_logging.getLogger(_noisy).setLevel(_root_logging.WARNING)

if __name__ == "__main__":
    _exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else "."
    try:
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
            _root_logging.getLogger(__name__).warning("DB init warning (non-fatal): %s", _init_err)

        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            log_level="info",
        )
    except Exception:
        # Write crash details beside the exe before exiting so users and devs
        # can find them even when the console window is hidden.
        _crash_path = os.path.join(_exe_dir, "sparkbot-backend-crash.txt")
        try:
            with open(_crash_path, "w") as _cf:
                _cf.write(_traceback.format_exc())
        except Exception:
            pass
        raise
