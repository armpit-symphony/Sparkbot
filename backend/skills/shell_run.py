"""
Sparkbot skill: shell_run

Run a shell command on the local machine and return its output.
  - Windows  → PowerShell (pwsh.exe then powershell.exe)
  - Linux/macOS → bash (or sh if bash unavailable)

Working directory persists across calls within the same room session so
`cd` commands carry forward just like a real interactive shell.

Security model
──────────────
Single-operator / self-hosted desktop install only.
No extra sandboxing — disable with SPARKBOT_SHELL_DISABLE=true.
Output capped at 16 KB stdout + 4 KB stderr.
Timeout: default 30 s, max 300 s.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import time
from typing import Optional

DEFINITION = {
    "type": "function",
    "function": {
        "name": "shell_run",
        "description": (
            "Run a shell command on the local machine and return the output. "
            "Uses PowerShell on Windows, bash on Linux/macOS. "
            "Working directory persists between calls in the same conversation. "
            "Use for file operations, git, npm, pip, opening apps, system tasks, "
            "or anything you would type in a terminal."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max seconds to wait (default 30, max 300).",
                    "default": 30,
                },
                "cwd": {
                    "type": "string",
                    "description": (
                        "Optional working directory override for this single call. "
                        "Leave blank to use the persisted session directory."
                    ),
                },
            },
            "required": ["command"],
        },
    },
}

POLICY = {
    "category": "execute",
    "default_action": "allow",
    "high_risk": False,
    "description": "Run a shell command on the local machine",
}

_MAX_STDOUT = 16_384
_MAX_STDERR = 4_096
_DEFAULT_TIMEOUT = int(os.getenv("SPARKBOT_SHELL_TIMEOUT", "30"))
_DISABLED = os.getenv("SPARKBOT_SHELL_DISABLE", "").strip().lower() in ("1", "true", "yes")

# Per-room working directory table.
_session_cwd: dict[str, str] = {}

# ── Platform detection ────────────────────────────────────────────────────────

_IS_WINDOWS = sys.platform == "win32"


def _shell_exe() -> Optional[str]:
    """Return the preferred shell executable for this platform."""
    if _IS_WINDOWS:
        for exe in ("pwsh.exe", "powershell.exe"):
            if shutil.which(exe):
                return exe
        return None
    for exe in ("/bin/bash", "bash", "/bin/sh", "sh"):
        if shutil.which(exe):
            return exe
    return None


def _build_cmd(shell: str, command: str) -> list[str]:
    """Wrap the user command so we can also capture the new cwd at the end."""
    if _IS_WINDOWS:
        # Append a sentinel that prints the resolved current directory after the command.
        # We handle both single-line and multi-line commands safely via a scriptblock.
        wrapped = (
            f"& {{ {command} }}; "
            f"Write-Output '___SPARKBOT_CWD___:'+((Get-Location).Path)"
        )
        return [shell, "-NonInteractive", "-Command", wrapped]
    else:
        wrapped = f'{command}; echo "___SPARKBOT_CWD___:$(pwd 2>/dev/null || echo .)"'
        return [shell, "-c", wrapped]


def _extract_cwd(output: str) -> tuple[str, str]:
    """Split the cwd sentinel from stdout; return (clean_output, new_cwd_or_empty)."""
    marker = "___SPARKBOT_CWD___:"
    lines = output.splitlines()
    new_cwd = ""
    clean: list[str] = []
    for line in lines:
        if line.startswith(marker):
            new_cwd = line[len(marker):].strip()
        else:
            clean.append(line)
    return "\n".join(clean).rstrip(), new_cwd


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    if _DISABLED:
        return "Shell access is disabled on this instance (SPARKBOT_SHELL_DISABLE=true)."

    command = (args.get("command") or "").strip()
    if not command:
        return "Error: no command provided."

    timeout = min(max(int(args.get("timeout") or _DEFAULT_TIMEOUT), 1), 300)
    cwd_override = (args.get("cwd") or "").strip() or None

    shell = _shell_exe()
    if not shell:
        return "Error: no suitable shell found on this system (tried pwsh, powershell, bash, sh)."

    session_key = str(room_id or user_id or "global")
    current_cwd = cwd_override or _session_cwd.get(session_key) or os.path.expanduser("~")

    # Make sure the cwd actually exists; fall back to home on stale paths.
    if not os.path.isdir(current_cwd):
        current_cwd = os.path.expanduser("~")
        _session_cwd[session_key] = current_cwd

    cmd = _build_cmd(shell, command)

    loop = asyncio.get_event_loop()
    t_start = time.monotonic()
    try:
        proc_result: subprocess.CompletedProcess = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=current_cwd,
                env=os.environ.copy(),
            ),
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout} seconds."
    except FileNotFoundError as exc:
        return f"Error: shell not found — {exc}"
    except Exception as exc:
        return f"Error running command: {exc}"

    elapsed = time.monotonic() - t_start
    stdout_raw = proc_result.stdout or ""
    stderr_raw = proc_result.stderr or ""
    exit_code = proc_result.returncode

    # Extract and update the working directory from the sentinel.
    stdout_clean, new_cwd = _extract_cwd(stdout_raw)
    if new_cwd and os.path.isdir(new_cwd) and not cwd_override:
        _session_cwd[session_key] = new_cwd

    effective_cwd = _session_cwd.get(session_key, current_cwd)

    # Cap output.
    stdout_out = stdout_clean[:_MAX_STDOUT]
    if len(stdout_clean) > _MAX_STDOUT:
        stdout_out += f"\n… (truncated — {len(stdout_clean)} chars total)"
    stderr_out = stderr_raw[:_MAX_STDERR]
    if len(stderr_raw) > _MAX_STDERR:
        stderr_out += "\n… (truncated)"

    parts: list[str] = [f"cwd: {effective_cwd}"]
    if stdout_out:
        parts.append(f"stdout:\n{stdout_out}")
    if stderr_out:
        parts.append(f"stderr:\n{stderr_out}")
    if not stdout_out and not stderr_out:
        parts.append("(no output)")
    parts.append(f"exit code: {exit_code}  ({elapsed:.2f}s)")

    return "\n\n".join(parts)
