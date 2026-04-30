"""
Sparkbot skill: system_diagnostics

Reports the current health of the local machine:
  - CPU usage (overall + per-core)
  - RAM usage
  - Disk usage (all mounted drives)
  - Top 10 processes by CPU consumption
  - Model endpoint reachability (Ollama, OpenAI, Anthropic, Google)
  - Recent backend log tail (last 20 lines)

No API keys required. Uses psutil (bundled with Sparkbot).

Perfect as a scheduled Task Guardian job:
  guardian_schedule_task(
      name="System Health Check",
      tool_name="system_diagnostics",
      schedule="every:900",   # every 15 minutes
      tool_args={}
  )

Or run on demand:
  "Run a system diagnostics check"
  "How is the system performing right now?"
  "Check CPU and memory usage"
"""
from __future__ import annotations

import os
import sys
import socket
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

# ── Tool definition ────────────────────────────────────────────────────────────

DEFINITION = {
    "type": "function",
    "function": {
        "name": "system_diagnostics",
        "description": (
            "Run a full system health check on the local machine. "
            "Reports CPU usage, RAM, disk space, top processes by CPU, "
            "model endpoint reachability, and recent backend log lines. "
            "Use this to diagnose slow responses, high CPU, or connectivity issues."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "include_log_tail": {
                    "type": "boolean",
                    "description": "Include the last 20 lines of the backend log (default true)",
                },
                "top_processes": {
                    "type": "integer",
                    "description": "Number of top CPU processes to list (default 10, max 20)",
                },
            },
            "required": [],
        },
    },
}

POLICY = {
    "scope": "read",
    "resource": "local_machine",
    "default_action": "allow",
    "action_type": "data_read",
    "high_risk": False,
    "requires_execution_gate": False,
}

# ── Model endpoints to probe ────────────────────────────────────────────────────

_ENDPOINTS = [
    ("Ollama (local)", "localhost", 11434),
    ("OpenAI", "api.openai.com", 443),
    ("Anthropic", "api.anthropic.com", 443),
    ("Google AI", "generativelanguage.googleapis.com", 443),
    ("Groq", "api.groq.com", 443),
    ("OpenRouter", "openrouter.ai", 443),
]

_TIMEOUT = 3.0  # seconds per probe


def _probe_endpoint(host: str, port: int) -> str:
    try:
        sock = socket.create_connection((host, port), timeout=_TIMEOUT)
        sock.close()
        return "reachable"
    except OSError:
        return "unreachable"


def _tail_log(n: int = 20) -> str:
    candidates = []

    # Desktop app: log beside the executable
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(os.path.join(exe_dir, "sparkbot-backend.log"))

    # Windows AppData location (Tauri sets this)
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        candidates.append(os.path.join(appdata, "Sparkbot Local", "sparkbot-backend.log"))

    # SPARKBOT_DATA_DIR
    data_dir = os.environ.get("SPARKBOT_DATA_DIR", "")
    if data_dir:
        candidates.append(os.path.join(data_dir, "sparkbot-backend.log"))

    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                tail = "".join(lines[-n:]).strip()
                return f"Log: {path}\n{tail}" if tail else f"Log: {path} — (empty)"
            except OSError as e:
                return f"Could not read log at {path}: {e}"

    return "Backend log not found (checked: " + ", ".join(candidates) + ")"


# ── Main executor ──────────────────────────────────────────────────────────────

async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    include_log = args.get("include_log_tail", True)
    top_n = min(int(args.get("top_processes", 10)), 20)

    lines: list[str] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines.append(f"## System Diagnostics — {now}\n")

    # ── psutil availability check ──────────────────────────────────────────────
    try:
        import psutil
    except ImportError:
        lines.append(
            "psutil is not installed. Install it to enable full diagnostics:\n"
            "  pip install psutil\n\n"
            "Falling back to endpoint reachability check only.\n"
        )
        psutil = None  # type: ignore[assignment]

    # ── CPU ────────────────────────────────────────────────────────────────────
    if psutil:
        cpu_overall = psutil.cpu_percent(interval=1.0)
        cpu_per_core = psutil.cpu_percent(interval=None, percpu=True)
        core_str = "  ".join(f"C{i}:{v:.0f}%" for i, v in enumerate(cpu_per_core))
        lines.append(f"### CPU\n- Overall: **{cpu_overall:.1f}%**\n- Per core: {core_str}\n")

    # ── RAM ────────────────────────────────────────────────────────────────────
    if psutil:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        lines.append(
            f"### Memory\n"
            f"- RAM: **{mem.percent:.1f}% used** "
            f"({mem.used / 1e9:.1f} GB / {mem.total / 1e9:.1f} GB)\n"
            f"- Swap: {swap.percent:.1f}% used "
            f"({swap.used / 1e9:.1f} GB / {swap.total / 1e9:.1f} GB)\n"
        )

    # ── Disk ───────────────────────────────────────────────────────────────────
    if psutil:
        disk_lines = []
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                disk_lines.append(
                    f"  - {part.mountpoint}: **{usage.percent:.1f}% used** "
                    f"({usage.used / 1e9:.1f} GB / {usage.total / 1e9:.1f} GB free: {usage.free / 1e9:.1f} GB)"
                )
            except (PermissionError, OSError):
                pass
        lines.append("### Disk\n" + "\n".join(disk_lines) + "\n")

    # ── Top processes ──────────────────────────────────────────────────────────
    if psutil:
        try:
            procs = []
            for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
                try:
                    procs.append(p.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            # Second pass — cpu_percent needs a first call to calibrate; sort by it
            procs.sort(key=lambda x: x.get("cpu_percent") or 0, reverse=True)
            top = procs[:top_n]
            proc_lines = [
                f"  - {p['name']} (PID {p['pid']}): "
                f"CPU {p.get('cpu_percent', 0):.1f}%  MEM {p.get('memory_percent', 0):.1f}%"
                for p in top
            ]
            lines.append(f"### Top {top_n} Processes (by CPU)\n" + "\n".join(proc_lines) + "\n")
        except Exception as e:
            lines.append(f"### Top Processes\nCould not retrieve process list: {e}\n")

    # ── Model endpoint reachability ────────────────────────────────────────────
    reach_lines = []
    for label, host, port in _ENDPOINTS:
        status = _probe_endpoint(host, port)
        icon = "✅" if status == "reachable" else "❌"
        reach_lines.append(f"  - {icon} {label} ({host}:{port}): {status}")
    lines.append("### Model Endpoint Reachability\n" + "\n".join(reach_lines) + "\n")

    # ── Log tail ───────────────────────────────────────────────────────────────
    if include_log:
        log_tail = _tail_log(20)
        lines.append(f"### Recent Backend Log (last 20 lines)\n```\n{log_tail}\n```\n")

    # ── Summary / alerts ──────────────────────────────────────────────────────
    alerts = []
    if psutil:
        if cpu_overall > 80:
            alerts.append(f"⚠️ CPU is at {cpu_overall:.0f}% — consider pausing heavy local models (Ollama)")
        if mem.percent > 85:
            alerts.append(f"⚠️ RAM is at {mem.percent:.0f}% — system may swap; close unused applications")
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                if usage.percent > 90:
                    alerts.append(f"⚠️ Disk {part.mountpoint} is {usage.percent:.0f}% full")
            except (PermissionError, OSError):
                pass

    if alerts:
        lines.append("### ⚠️ Alerts\n" + "\n".join(alerts) + "\n")
    else:
        lines.append("### Status\n✅ All checks within normal range.\n")

    return "\n".join(lines)
