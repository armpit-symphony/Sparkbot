"""Terminal session service — cross-platform PTY backend.

Manages interactive shell sessions for the Workstation live terminal panel.

Platform backends
─────────────────
• Windows  — ConPTY via pywinpty (PtyProcess)
• Linux/macOS — stdlib pty + fcntl + termios (original approach)

Both backends expose the same TerminalSession / TerminalSessionManager API
so the HTTP + WebSocket router (terminal.py) is unchanged.

WebSocket protocol (handled by terminal.py):
  input  → write_input(session_id, bytes)
  resize → resize(session_id, cols, rows)
  output ← output callbacks (bytes)
"""
import asyncio
import logging
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_SESSIONS_PER_USER = 4
SESSION_IDLE_TIMEOUT = 30 * 60  # 30 min
READ_CHUNK = 4096

_IS_WINDOWS = sys.platform == "win32"


# ─── Shared session model ─────────────────────────────────────────────────────

@dataclass
class TerminalSession:
    session_id: str
    user_id: str
    host: str
    shell: str
    station_id: Optional[str]
    started_at: float
    last_activity_at: float
    status: str          # "idle" | "connected" | "closed" | "error"
    _backend: object = field(repr=False, default=None)   # platform handle
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
        for cb in list(self._output_callbacks):
            try:
                cb(data)
            except Exception:
                pass


# ─── Windows backend (pywinpty / ConPTY) ─────────────────────────────────────

if _IS_WINDOWS:
    import subprocess as _subprocess

    _DEFAULT_SHELL_WIN = "powershell.exe"
    _ALLOWED_SHELLS_WIN = {"powershell.exe", "pwsh.exe", "cmd.exe"}

    # Normalize shell names: if the user passes a bare name we resolve it
    def _resolve_shell_win(shell: str) -> str:
        base = os.path.basename(shell).lower()
        for allowed in _ALLOWED_SHELLS_WIN:
            if base == allowed or base == allowed.replace(".exe", ""):
                found = shutil.which(allowed)
                if found:
                    return found
        # Default
        return shutil.which("powershell.exe") or "powershell.exe"

    class _WinPtyHandle:
        """Thin wrapper around a pywinpty PtyProcess."""

        def __init__(self, proc, rows: int = 24, cols: int = 220) -> None:
            self.proc = proc
            self.rows = rows
            self.cols = cols

        @classmethod
        def spawn(cls, shell: str, rows: int = 24, cols: int = 220) -> "_WinPtyHandle":
            from winpty import PtyProcess  # type: ignore[import]
            proc = PtyProcess.spawn(
                shell,
                dimensions=(rows, cols),
                env=dict(os.environ, TERM="xterm-256color"),
            )
            return cls(proc, rows=rows, cols=cols)

        def read(self) -> bytes:
            """Blocking read — run in executor thread."""
            try:
                data = self.proc.read(READ_CHUNK)
                return data if isinstance(data, bytes) else data.encode("utf-8", errors="replace")
            except EOFError:
                return b""
            except Exception:
                return b""

        def write(self, data: bytes) -> None:
            try:
                self.proc.write(data.decode("utf-8", errors="replace"))
            except Exception:
                pass

        def setwinsize(self, rows: int, cols: int) -> None:
            try:
                self.proc.setwinsize(rows, cols)
                self.rows, self.cols = rows, cols
            except Exception:
                pass

        def is_alive(self) -> bool:
            try:
                return self.proc.isalive()
            except Exception:
                return False

        def terminate(self) -> None:
            try:
                self.proc.terminate()
            except Exception:
                pass


# ─── Unix backend (pty / fcntl / termios) ─────────────────────────────────────

else:
    import fcntl
    import select
    import struct
    import subprocess as _subprocess
    import termios

    SELECT_TIMEOUT = 0.5
    _DEFAULT_SHELL_UNIX = "/bin/bash"
    _ALLOWED_SHELLS_UNIX = {
        "/bin/bash", "/bin/sh", "/usr/bin/bash", "/usr/bin/zsh", "/bin/zsh",
    }

    def _resolve_shell_unix(shell: str) -> str:
        if shell in _ALLOWED_SHELLS_UNIX and os.path.exists(shell):
            return shell
        return _DEFAULT_SHELL_UNIX

    class _UnixPtyHandle:
        """Thin wrapper around a POSIX PTY + subprocess."""

        def __init__(self, master_fd: int, proc: "_subprocess.Popen") -> None:  # type: ignore
            self.master_fd = master_fd
            self.proc = proc

        @classmethod
        def spawn(cls, shell: str, rows: int = 24, cols: int = 220) -> "_UnixPtyHandle":
            import pty as _pty
            master_fd, slave_fd = os.openpty()
            flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
            fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            slave_name = os.ttyname(slave_fd)

            winsize = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

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
                try:
                    fd = os.open(slave_name, os.O_RDWR)
                    os.close(fd)
                except OSError:
                    pass

            shell_args = [shell, "--norc"] if "bash" in shell else [shell]
            proc = _subprocess.Popen(
                shell_args,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                preexec_fn=_acquire_ctty,
                env=env,
            )
            os.close(slave_fd)
            return cls(master_fd, proc)

        def read(self) -> bytes:
            """Blocking select+read — run in executor thread."""
            try:
                rlist, _, _ = select.select([self.master_fd], [], [], SELECT_TIMEOUT)
                if not rlist:
                    return b""
                data = os.read(self.master_fd, READ_CHUNK)
                return data if data else b""
            except OSError:
                return b""

        def write(self, data: bytes) -> None:
            try:
                os.write(self.master_fd, data)
            except OSError:
                pass

        def setwinsize(self, rows: int, cols: int) -> None:
            rows = max(5, min(rows, 200))
            cols = max(20, min(cols, 500))
            try:
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            except OSError:
                pass

        def is_alive(self) -> bool:
            return self.proc is not None and self.proc.poll() is None

        def terminate(self) -> None:
            if self.proc:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
            if self.master_fd != -1:
                try:
                    os.close(self.master_fd)
                except OSError:
                    pass
                self.master_fd = -1


# ─── Unified session manager ──────────────────────────────────────────────────

class TerminalSessionManager:
    """Process-level singleton managing all terminal sessions."""

    def __init__(self) -> None:
        self._sessions: Dict[str, TerminalSession] = {}
        self._read_tasks: Dict[str, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(
                self._idle_cleanup_loop(), name="terminal-idle-cleanup"
            )

    async def stop(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
        await self._close_all()

    # ── Create ────────────────────────────────────────────────────────────────

    async def create_session(
        self,
        user_id: str,
        host: str = "localhost",
        shell: Optional[str] = None,
        station_id: Optional[str] = None,
    ) -> TerminalSession:
        if host != "localhost":
            raise ValueError("Only localhost is supported")

        async with self._lock:
            active = sum(
                1 for s in self._sessions.values()
                if s.user_id == user_id and s.status not in ("closed", "error")
            )
            if active >= MAX_SESSIONS_PER_USER:
                raise RuntimeError(f"Session limit reached ({MAX_SESSIONS_PER_USER} per user)")

        if _IS_WINDOWS:
            resolved = _resolve_shell_win(shell or _DEFAULT_SHELL_WIN)
            try:
                handle = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _WinPtyHandle.spawn(resolved)
                )
            except ImportError:
                raise RuntimeError(
                    "pywinpty is not installed. Run: pip install pywinpty"
                )
            except Exception as exc:
                raise RuntimeError(f"Failed to spawn shell: {exc}") from exc
        else:
            resolved = _resolve_shell_unix(shell or _DEFAULT_SHELL_UNIX)
            try:
                handle = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _UnixPtyHandle.spawn(resolved)
                )
            except Exception as exc:
                raise RuntimeError(f"Failed to spawn shell: {exc}") from exc

        now = time.time()
        session_id = str(uuid.uuid4())
        session = TerminalSession(
            session_id=session_id,
            user_id=user_id,
            host=host,
            shell=resolved,
            station_id=station_id,
            started_at=now,
            last_activity_at=now,
            status="idle",
            _backend=handle,
        )
        async with self._lock:
            self._sessions[session_id] = session

        self._read_tasks[session_id] = asyncio.create_task(
            self._read_loop(session), name=f"terminal-read-{session_id[:8]}"
        )
        logger.info("Terminal session created: %s (user=%s shell=%s)", session_id, user_id, resolved)
        return session

    # ── Access ────────────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        return self._sessions.get(session_id)

    def list_user_sessions(self, user_id: str) -> List[TerminalSession]:
        return [
            s for s in self._sessions.values()
            if s.user_id == user_id and s.status not in ("closed", "error")
        ]

    # ── I/O ──────────────────────────────────────────────────────────────────

    async def write_input(self, session_id: str, data: bytes) -> bool:
        session = self._sessions.get(session_id)
        if not session or not session._backend or session.status in ("closed", "error"):
            return False
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, session._backend.write, data
            )
            session.touch()
            return True
        except Exception as exc:
            logger.warning("Write to session %s failed: %s", session_id, exc)
            return False

    async def resize(self, session_id: str, cols: int, rows: int) -> bool:
        session = self._sessions.get(session_id)
        if not session or not session._backend or session.status in ("closed", "error"):
            return False
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, session._backend.setwinsize, rows, cols
            )
            return True
        except Exception as exc:
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
        if session._backend:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, session._backend.terminate
                )
            except Exception:
                pass
        logger.info("Terminal session closed: %s", session_id)

    async def _close_all(self) -> None:
        for sid in list(self._sessions):
            await self.close_session(sid)

    # ── Read loop ─────────────────────────────────────────────────────────────

    async def _read_loop(self, session: TerminalSession) -> None:
        loop = asyncio.get_event_loop()
        backend = session._backend
        try:
            while session.status not in ("closed", "error"):
                data: bytes = await loop.run_in_executor(None, backend.read)
                if data is None or (not data and not backend.is_alive()):
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

    # ── Idle cleanup ──────────────────────────────────────────────────────────

    async def _idle_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                now = time.time()
                to_close = [
                    sid for sid, s in self._sessions.items()
                    if s.status not in ("closed", "error")
                    and not s._output_callbacks
                    and s.last_activity_at < now - SESSION_IDLE_TIMEOUT
                ]
                for sid in to_close:
                    logger.info("Closing idle terminal session %s", sid)
                    await self.close_session(sid)
            except Exception as exc:
                logger.warning("Terminal idle cleanup error: %s", exc)


# ─── Singleton ────────────────────────────────────────────────────────────────

terminal_manager = TerminalSessionManager()
