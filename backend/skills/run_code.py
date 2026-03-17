"""
Sparkbot skill: run_code

Execute Python, JavaScript (Node.js), or Bash code in a sandboxed subprocess.
Returns stdout + stderr. Useful for calculations, data transforms, scripting,
and logic testing without leaving the chat.

Security model:
  - Runs in the same OS process tree as the backend (self-hosted operator use)
  - Timeout: default 30s, max 120s (configurable via SPARKBOT_CODE_TIMEOUT)
  - Output: capped at 8 KB stdout + 2 KB stderr
  - No extra sandbox (nsjail/docker) — acceptable for single-operator installs.
    Set SPARKBOT_CODE_DISABLE=true to disable entirely if running multi-tenant.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile

DEFINITION = {
    "type": "function",
    "function": {
        "name": "run_code",
        "description": (
            "Execute Python 3, JavaScript (Node.js), or Bash code and return the output. "
            "Use for calculations, data transforms, scripting, testing logic, or any task "
            "where running code produces a more accurate answer than reasoning alone."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["python", "javascript", "bash"],
                    "description": "Language: python (Python 3), javascript (Node.js), or bash",
                },
                "code": {
                    "type": "string",
                    "description": "The code to execute",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max execution time in seconds (default 30, max 120)",
                    "default": 30,
                },
            },
            "required": ["language", "code"],
        },
    },
}

POLICY = {
    "category": "write",
    "default_action": "allow",
    "high_risk": False,
    "description": "Execute code in a subprocess",
}

_MAX_STDOUT = 8192
_MAX_STDERR = 2048
_DEFAULT_TIMEOUT = int(os.getenv("SPARKBOT_CODE_TIMEOUT", "30"))
_DISABLED = os.getenv("SPARKBOT_CODE_DISABLE", "").strip().lower() in ("1", "true", "yes")

_LANG_CONFIG = {
    "python":     {"interp": "python3",  "suffix": ".py"},
    "javascript": {"interp": "node",     "suffix": ".js"},
    "bash":       {"interp": "bash",     "suffix": ".sh"},
}


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    if _DISABLED:
        return "Code execution is disabled on this instance (SPARKBOT_CODE_DISABLE=true)."

    language = (args.get("language") or "python").lower().strip()
    if language == "js":
        language = "javascript"
    code = (args.get("code") or "").strip()
    timeout = min(max(int(args.get("timeout") or _DEFAULT_TIMEOUT), 1), 120)

    if not code:
        return "Error: No code provided."

    cfg = _LANG_CONFIG.get(language)
    if cfg is None:
        return f"Error: Unsupported language '{language}'. Use python, javascript, or bash."

    interp = cfg["interp"]
    if not shutil.which(interp):
        return f"Error: '{interp}' is not installed on this server."

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=cfg["suffix"], delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        loop = asyncio.get_event_loop()
        proc_result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [interp, tmp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            ),
        )
        stdout = proc_result.stdout or ""
        stderr = proc_result.stderr or ""
        exit_code = proc_result.returncode

    except subprocess.TimeoutExpired:
        return f"Error: Execution timed out after {timeout} seconds."
    except Exception as exc:
        return f"Error running code: {exc}"
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    parts: list[str] = []
    if stdout:
        out = stdout[:_MAX_STDOUT]
        if len(stdout) > _MAX_STDOUT:
            out += f"\n... (truncated — {len(stdout)} chars total)"
        parts.append(f"stdout:\n{out}")
    if stderr:
        err = stderr[:_MAX_STDERR]
        if len(stderr) > _MAX_STDERR:
            err += f"\n... (truncated)"
        parts.append(f"stderr:\n{err}")
    if not parts:
        parts.append("(no output)")
    parts.append(f"exit code: {exit_code}")

    return "\n\n".join(parts)
