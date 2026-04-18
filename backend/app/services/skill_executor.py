"""
Skill execution sandbox.

Wraps every skill plugin call with:
  - Wall-clock timeout (asyncio.wait_for)
  - Memory headroom check before execution (psutil, optional)
  - Memory growth monitoring during execution (psutil, optional)
  - Structured error reporting (timeout / OOM / exception / success)

Configuration (env vars)
------------------------
SPARKBOT_SKILL_TIMEOUT_SECONDS    default wall-clock limit per skill (default 60)
SPARKBOT_SKILL_MAX_MEMORY_MB      abort if process RSS exceeds this during execution
                                   0 = disabled (default 0)

Skills that define TIMEOUT in their module can override the global default.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = float(os.getenv("SPARKBOT_SKILL_TIMEOUT_SECONDS", "60"))
_MAX_MEMORY_MB = float(os.getenv("SPARKBOT_SKILL_MAX_MEMORY_MB", "0"))


def _rss_mb() -> float | None:
    """Return current process RSS in MB, or None if psutil unavailable."""
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1_048_576
    except Exception:
        return None


async def run_skill(
    name: str,
    executor: Callable[..., Coroutine[Any, Any, str]],
    args: dict,
    *,
    timeout: float | None = None,
    user_id: str | None = None,
    room_id: str | None = None,
    session: Any = None,
) -> str:
    """
    Execute a skill with timeout and optional memory guardrails.

    Returns the skill's string output, or a structured error string on failure.
    Never raises — callers can treat the return value as the tool result.
    """
    effective_timeout = timeout if timeout is not None else _DEFAULT_TIMEOUT

    # Pre-execution memory baseline
    rss_before = _rss_mb()
    if _MAX_MEMORY_MB > 0 and rss_before is not None and rss_before > _MAX_MEMORY_MB:
        msg = (
            f"Skill [{name}] not started: process memory {rss_before:.0f} MB "
            f"already exceeds limit {_MAX_MEMORY_MB:.0f} MB."
        )
        log.warning(msg)
        return msg

    t0 = time.perf_counter()

    try:
        result = await asyncio.wait_for(
            executor(args, user_id=user_id, room_id=room_id, session=session),
            timeout=effective_timeout,
        )
        elapsed = time.perf_counter() - t0

        # Post-execution memory check
        rss_after = _rss_mb()
        if _MAX_MEMORY_MB > 0 and rss_after is not None and rss_after > _MAX_MEMORY_MB:
            log.warning(
                "Skill [%s] completed but process memory %s MB exceeds limit %s MB "
                "(growth: +%s MB). Consider restarting Sparkbot if memory stays high.",
                name,
                f"{rss_after:.0f}",
                f"{_MAX_MEMORY_MB:.0f}",
                f"{(rss_after - (rss_before or 0)):.0f}",
            )

        log.debug("Skill [%s] completed in %.2fs", name, elapsed)
        return result if isinstance(result, str) else str(result)

    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - t0
        msg = (
            f"Skill [{name}] timed out after {elapsed:.1f}s "
            f"(limit: {effective_timeout:.0f}s). "
            f"The operation may still be running in the background. "
            f"To increase the limit set SPARKBOT_SKILL_TIMEOUT_SECONDS."
        )
        log.warning(msg)
        return msg

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        log.exception("Skill [%s] raised after %.2fs: %s", name, elapsed, exc)
        return f"Skill error [{name}]: {type(exc).__name__}: {exc}"
