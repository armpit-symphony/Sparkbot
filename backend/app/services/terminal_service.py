"""Terminal session service.

Manages PTY-backed shell sessions for the Workstation live terminal.
Each session owns one PTY pair + subprocess. All sessions are tracked
by session_id and owned by a user_id.

Design notes:
- Uses stdlib pty/fcntl/termios — no extra pip installs required.
- Output is read in a background asyncio task using run_in_executor +
  select so the event loop stays unblocked.
- Callbacks are called from the event loop after the executor returns,
  so asyncio.Queue.put_nowait() is safe.
- Max sessions per user: MAX_SESSIONS_PER_USER.
- Idle sessions with no active WS subscriber are closed after
  SESSION_IDLE_TIMEOUT seconds.
"""
import sys
if sys.platform == "win32":
    raise ImportError("terminal_service requires Linux/Unix (fcntl/termios unavailable on Windows)")

import asyncio
import fcntl
import logging
import os
import select
import struct
import subprocess
import termios
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

MAX_SESSIONS_PER_USER = 4
SESSION_IDLE_TIMEOUT = 30 * 60  # 30 minutes
DEFAULT_SHELL = "/bin/bash"
ALLOWED_SHELLS = {"/bin/bash", "/bin/sh", "/usr/bin/bash", "/usr/bin/zsh", "/bin/zsh"}
READ_CHUNK = 4096
SELECT_TIMEOUT = 0.5  # seconds for blocking select in executor


# ─── Session model ────────────────────────────────────────────────────────────

@dataclass
class TerminalSession:
    session_id: str
    user_id: str
    host: str
    shell: str
    station_id: Optional[str]
    started_at: float
    last_activity_at: float
    status: str  # "idle" | "connected" | "closed" | "error"
    master_fd: int = field(repr=False, default=-1)
    proc: Optional[subprocess.Popen] = field(repr=False, default=None)
    _output_callbacks: List[Callable[[bytes], None]] = field(
        default_factory=list, repr=False
    )

    def touch(self) -> None:
        self.last_activity_at = time.time()

    def add_output_callback(self, cb: Callable[[bytes], None]) -> None:
        if cb not in self._output_callbacks:
            self._output_callbacks.append(cb)

    def remove_output_callback(self, cb: Callable[[bytes], None]) -> None:
        try:
            self._output_callbacks.remove(cb)
        except ValueError:
            pass

    def deliver_output(self, data: bytes) -> None:
        """Deliver bytes to all registered callbacks. Called from event loop."""
        for cb in list(self._output_callbacks):
            try:
                cb(data)
            except Exception:
                pass


# ─── Session manager ──────────────────────────────────────────────────────────

class TerminalSessionManager:
    """Process-level singleton managing all terminal sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, TerminalSession] = {}
        self._read_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the idle-session cleanup loop."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._idle_cleanup_loop(), name="terminal-idle-cleanup"
            )

    async def stop(self) -> None:
        """Shutdown: cancel cleanup task and close all sessions."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        await self._close_all()

    # ── Session creation ──────────────────────────────────────────────────────

    async def create_session(
        self,
        user_id: str,
        host: str = "localhost",
        shell: str = DEFAULT_SHELL,
        station_id: Optional[str] = None,
    ) -> TerminalSession:
        """Spawn a PTY-backed shell and return the new session."""
        if shell not in ALLOWED_SHELLS:
            raise ValueError(f"Shell not permitted: {shell}")
        if host != "localhost":
            raise ValueError("Only localhost is supported in Phase 3")

        async with self._lock:
            active = sum(
                1
                for s in self._sessions.values()
                if s.user_id == user_id and s.status not in ("closed", "error")
            )
            if active >= MAX_SESSIONS_PER_USER:
                raise RuntimeError(
                    f"Session limit reached ({MAX_SESSIONS_PER_USER} per user)"
                )

            master_fd, slave_fd = os.openpty()
            # Make master non-blocking so reads in the executor use select
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

            # Get the slave terminal device name before forking.
            # We need it in preexec_fn to acquire a controlling terminal.
            slave_name = os.ttyname(slave_fd)

            env = {
                "TERM": "xterm-256color",
                "LANG": "en_US.UTF-8",
                "HOME": os.path.expanduser("~"),
                "USER": os.environ.get("USER", "sparky"),
                "SHELL": shell,
                "PATH": os.environ.get(
                    "PATH",
                    "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                ),
            }

            def _acquire_ctty() -> None:
                # Runs in child process after setsid() (from start_new_session=True).
                # Opening the slave terminal after setsid() automatically acquires it
                # as the controlling terminal of the new session on Linux.
                # Without this, bash starts without a controlling terminal and
                # disables interactive mode (no prompt, no command output).
                try:
                    fd = os.open(slave_name, os.O_RDWR)
                    os.close(fd)
                except OSError:
                    pass  # best-effort; shell may still work in non-interactive mode

            # Shell args: --norc avoids loading ~/.bashrc which may contain slow
            # or blocking startup commands (e.g. `$(npm root -g)` in PATH exports).
            # This is intentional for embedded/headless terminal sessions.
            # Users can source their rc file manually: source ~/.bashrc
            shell_args = [shell]
            if shell in ("/bin/bash", "/usr/bin/bash"):
                shell_args = [shell, "--norc"]

            try:
                proc = subprocess.Popen(
                    shell_args,
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    start_new_session=True,   # setsid() — new session, no ctty yet
                    preexec_fn=_acquire_ctty, # acquire slave as ctty after setsid
                    env=env,
                )
            except Exception as exc:
                os.close(master_fd)
                os.close(slave_fd)
                raise RuntimeError(f"Failed to spawn shell: {exc}") from exc

            os.close(slave_fd)  # parent doesn't need the slave end

            now = time.time()
            session_id = str(uuid.uuid4())
            session = TerminalSession(
                session_id=session_id,
                user_id=user_id,
                host=host,
                shell=shell,
                station_id=station_id,
                started_at=now,
                last_activity_at=now,
                status="idle",
                master_fd=master_fd,
                proc=proc,
            )
            self._sessions[session_id] = session

        # Start reader outside the lock (avoids holding lock across task creation)
        self._read_tasks[session_id] = asyncio.create_task(
            self._read_loop(session), name=f"terminal-read-{session_id[:8]}"
        )
        logger.info("Terminal session created: %s (user=%s)", session_id, user_id)
        return session

    # ── Session access ────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    def list_user_sessions(self, user_id: str) -> List[TerminalSession]:
        return [
            s
            for s in self._sessions.values()
            if s.user_id == user_id and s.status not in ("closed", "error")
        ]

    # ── I/O ──────────────────────────────────────────────────────────────────

    async def write_input(self, session_id: str, data: bytes) -> bool:
        session = self._sessions.get(session_id)
        if not session or session.master_fd == -1 or session.status in ("closed", "error"):
            return False
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, os.write, session.master_fd, data)
            session.touch()
            return True
        except OSError as exc:
            logger.warning("Write to session %s failed: %s", session_id, exc)
            return False

    async def resize(self, session_id: str, cols: int, rows: int) -> bool:
        session = self._sessions.get(session_id)
        if not session or session.master_fd == -1 or session.status in ("closed", "error"):
            return False
        cols = max(20, min(cols, 500))
        rows = max(5, min(rows, 200))
        try:
            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(session.master_fd, termios.TIOCSWINSZ, winsize)
            return True
        except OSError as exc:
            logger.warning("Resize session %s failed: %s", session_id, exc)
            return False

    # ── Close ─────────────────────────────────────────────────────────────────

    async def close_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return

        session.status = "closed"

        task = self._read_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

        if session.proc:
            try:
                session.proc.terminate()
                try:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, session.proc.wait
                        ),
                        timeout=2.0,
                    )
                except asyncio.TimeoutError:
                    session.proc.kill()
            except Exception:
                pass

        if session.master_fd != -1:
            try:
                os.close(session.master_fd)
            except OSError:
                pass
            session.master_fd = -1

        logger.info("Terminal session closed: %s", session_id)

    async def _close_all(self) -> None:
        for sid in list(self._sessions):
            await self.close_session(sid)

    # ── Read loop ─────────────────────────────────────────────────────────────

    async def _read_loop(self, session: TerminalSession) -> None:
        """Read PTY output and deliver to callbacks. Runs until session closes."""
        loop = asyncio.get_event_loop()
        try:
            while session.status not in ("closed", "error"):
                data = await loop.run_in_executor(
                    None, self._blocking_read, session.master_fd
                )
                if data is None:
                    # EOF / shell exited
                    break
                if data:
                    session.touch()
                    session.deliver_output(data)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.debug("Read loop for %s ended: %s", session.session_id, exc)
        finally:
            if session.status not in ("closed", "error"):
                session.status = "closed"
                logger.info("Terminal session %s: shell exited", session.session_id)

    @staticmethod
    def _blocking_read(master_fd: int) -> Optional[bytes]:
        """Blocking select+read from PTY master — runs in executor thread."""
        try:
            rlist, _, _ = select.select([master_fd], [], [], SELECT_TIMEOUT)
            if not rlist:
                return b""  # timeout, no data — caller checks status
            data = os.read(master_fd, READ_CHUNK)
            return data if data else None  # None signals EOF
        except OSError:
            return None  # fd closed / shell gone

    # ── Idle cleanup ──────────────────────────────────────────────────────────

    async def _idle_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                now = time.time()
                to_close = [
                    sid
                    for sid, s in self._sessions.items()
                    if s.status not in ("closed", "error")
                    and not s._output_callbacks  # no active WS subscriber
                    and s.last_activity_at < now - SESSION_IDLE_TIMEOUT
                ]
                for sid in to_close:
                    logger.info("Closing idle terminal session %s", sid)
                    await self.close_session(sid)
            except Exception as exc:
                logger.warning("Terminal idle cleanup error: %s", exc)


# ─── Singleton ────────────────────────────────────────────────────────────────

terminal_manager = TerminalSessionManager()
