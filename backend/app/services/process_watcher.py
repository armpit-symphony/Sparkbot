"""
Process watcher — background service that monitors system load and
automatically lowers the OS priority of heavy local model processes
(Ollama, LM Studio, llama.cpp) when they threaten interactive latency.

Behaviour
---------
- Polls every POLL_INTERVAL seconds (default 30).
- If a watched process is consuming > CPU_THRESHOLD % CPU it is moved
  to BelowNormal (Windows) / nice=10 (Unix) priority.
- Once CPU drops back below RESTORE_THRESHOLD the priority is restored.
- All actions are logged; no process is ever killed or paused.

Configuration (env vars)
------------------------
SPARKBOT_PROCESS_WATCHER_ENABLED   true | false  (default true in V1_LOCAL_MODE)
SPARKBOT_PROCESS_WATCHER_INTERVAL  poll seconds  (default 30)
SPARKBOT_CPU_THRESHOLD             % above which priority is lowered (default 70)
SPARKBOT_CPU_RESTORE_THRESHOLD     % below which priority is restored (default 40)
SPARKBOT_WATCHED_PROCESSES         comma-separated names (default: ollama,ollama_llama_server,
                                   lmstudio,llama-server,llama.cpp)
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

log = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

_ENABLED = os.getenv("SPARKBOT_PROCESS_WATCHER_ENABLED", "").strip().lower()
_POLL_INTERVAL = int(os.getenv("SPARKBOT_PROCESS_WATCHER_INTERVAL", "30"))
_CPU_THRESHOLD = float(os.getenv("SPARKBOT_CPU_THRESHOLD", "70"))
_RESTORE_THRESHOLD = float(os.getenv("SPARKBOT_CPU_RESTORE_THRESHOLD", "40"))
_WATCHED_NAMES_RAW = os.getenv(
    "SPARKBOT_WATCHED_PROCESSES",
    "ollama,ollama_llama_server,lmstudio,llama-server,llama.cpp,llama-cpp",
)
_WATCHED_NAMES: set[str] = {n.strip().lower() for n in _WATCHED_NAMES_RAW.split(",") if n.strip()}

# Track which PIDs we've already lowered so we only log once per transition
_lowered: dict[int, str] = {}   # pid → process name


def _is_enabled() -> bool:
    """Return True if the watcher should run."""
    if _ENABLED in ("false", "0", "no"):
        return False
    if _ENABLED in ("true", "1", "yes"):
        return True
    # Default: on in V1_LOCAL_MODE (desktop app), off on servers
    from app.core.config import settings
    return bool(getattr(settings, "V1_LOCAL_MODE", False))


# ── Priority helpers ───────────────────────────────────────────────────────────

def _lower_priority(proc) -> bool:  # type: ignore[return]
    """Lower process priority. Returns True on success."""
    try:
        if sys.platform == "win32":
            import ctypes
            BELOW_NORMAL = 0x4000
            handle = ctypes.windll.kernel32.OpenProcess(0x0200, False, proc.pid)
            if handle:
                ctypes.windll.kernel32.SetPriorityClass(handle, BELOW_NORMAL)
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            # Fallback via psutil
            proc.nice(1)  # BELOW_NORMAL_PRIORITY_CLASS equivalent via psutil
            return True
        else:
            current = proc.nice()
            if current < 10:
                proc.nice(10)
            return True
    except Exception as exc:
        log.debug("Could not lower priority for PID %s: %s", proc.pid, exc)
        return False


def _restore_priority(proc) -> bool:
    """Restore process to normal priority. Returns True on success."""
    try:
        if sys.platform == "win32":
            import ctypes
            NORMAL = 0x0020
            handle = ctypes.windll.kernel32.OpenProcess(0x0200, False, proc.pid)
            if handle:
                ctypes.windll.kernel32.SetPriorityClass(handle, NORMAL)
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            proc.nice(0)
            return True
        else:
            proc.nice(0)
            return True
    except Exception as exc:
        log.debug("Could not restore priority for PID %s: %s", proc.pid, exc)
        return False


# ── Watcher loop ───────────────────────────────────────────────────────────────

async def process_watcher_loop() -> None:
    """
    Async loop — runs as a background asyncio task.
    Safely no-ops if psutil is unavailable or watcher is disabled.
    """
    if not _is_enabled():
        log.debug("Process watcher disabled.")
        return

    try:
        import psutil
    except ImportError:
        log.warning("process_watcher: psutil not installed — watcher inactive.")
        return

    log.info(
        "Process watcher started: interval=%ss cpu_threshold=%.0f%% restore=%.0f%% watching=%s",
        _POLL_INTERVAL, _CPU_THRESHOLD, _RESTORE_THRESHOLD, sorted(_WATCHED_NAMES),
    )

    while True:
        try:
            await _tick(psutil)
        except asyncio.CancelledError:
            log.info("Process watcher stopped.")
            return
        except Exception as exc:
            log.warning("Process watcher tick error: %s", exc)

        await asyncio.sleep(_POLL_INTERVAL)


async def _tick(psutil) -> None:  # noqa: ANN001
    """Single poll iteration — called from the loop."""
    alive_pids: set[int] = set()

    for proc in psutil.process_iter(["pid", "name", "cpu_percent", "status"]):
        try:
            info = proc.info
            name = (info.get("name") or "").lower()
            # Strip .exe suffix for cross-platform name matching
            base_name = name.removesuffix(".exe")

            if base_name not in _WATCHED_NAMES and name not in _WATCHED_NAMES:
                continue

            alive_pids.add(info["pid"])
            cpu = info.get("cpu_percent") or 0.0

            if cpu > _CPU_THRESHOLD and info["pid"] not in _lowered:
                if _lower_priority(proc):
                    _lowered[info["pid"]] = info.get("name") or base_name
                    log.warning(
                        "process_watcher: %s (PID %s) CPU=%.1f%% > threshold=%.0f%% — "
                        "priority lowered to BelowNormal. "
                        "To prevent this set SPARKBOT_CPU_THRESHOLD=100 or move Ollama "
                        "to Backup position in your model stack.",
                        info.get("name"), info["pid"], cpu, _CPU_THRESHOLD,
                    )

            elif cpu < _RESTORE_THRESHOLD and info["pid"] in _lowered:
                if _restore_priority(proc):
                    pname = _lowered.pop(info["pid"])
                    log.info(
                        "process_watcher: %s (PID %s) CPU=%.1f%% < restore=%.0f%% — "
                        "priority restored to Normal.",
                        pname, info["pid"], cpu, _RESTORE_THRESHOLD,
                    )

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Clean up _lowered entries for processes that no longer exist
    gone = set(_lowered) - alive_pids
    for pid in gone:
        name = _lowered.pop(pid)
        log.info("process_watcher: %s (PID %s) no longer running — removed from tracking.", name, pid)


# ── Public API ─────────────────────────────────────────────────────────────────

def get_watcher_status() -> dict:
    """Return current watcher state — used by diagnostics and /models endpoint."""
    return {
        "enabled": _is_enabled(),
        "poll_interval_seconds": _POLL_INTERVAL,
        "cpu_threshold_pct": _CPU_THRESHOLD,
        "restore_threshold_pct": _RESTORE_THRESHOLD,
        "watched_process_names": sorted(_WATCHED_NAMES),
        "currently_throttled": [
            {"pid": pid, "name": name} for pid, name in _lowered.items()
        ],
    }
