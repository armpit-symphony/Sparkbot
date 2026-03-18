"""Terminal HTTP + WebSocket endpoints.

Routes (mounted at /api/v1/terminal):
  POST   /sessions              — create a new PTY session
  GET    /sessions              — list caller's active sessions
  DELETE /sessions/{session_id} — close a session
  WS     /ws/{session_id}       — stream input/output for a session

WebSocket message protocol (all JSON):

  Client → Server
  ───────────────
  {"type": "auth",   "token": "<JWT>"}          # first msg if no cookie
  {"type": "input",  "data": "<base64-bytes>"}  # user keystroke(s)
  {"type": "resize", "cols": N, "rows": N}      # terminal size change
  {"type": "close"}                              # client-requested close

  Server → Client
  ───────────────
  {"type": "connected", "session_id": "...", "host": "...", "shell": "...", "started_at": N}
  {"type": "output",    "data": "<base64-bytes>"}  # PTY output
  {"type": "status",    "session_id": "...", "status": "..."}
  {"type": "error",     "message": "..."}
  {"type": "closed",    "reason": "..."}

Security notes (Phase 3):
  - All HTTP endpoints require a valid chat session cookie or Bearer token.
  - WS auth uses the same cookie-first / first-message-auth pattern as
    the main chat WebSocket.
  - User can only access sessions they own (user_id check).
  - Only localhost shell sessions are permitted in this phase.
  - No terminal output is written to logs by this module.
  - Command-level filtering is NOT enforced — this is a raw shell.
    Suitable for self-hosted, operator-controlled deployments only.
    Document this clearly; add command policy in a future phase.
"""
import asyncio
import base64
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.api.deps import CurrentChatUser, get_db
from app.core.config import settings
try:
    from app.services.terminal_service import terminal_manager
except ImportError:
    terminal_manager = None  # type: ignore[assignment]  # unavailable on Windows

logger = logging.getLogger(__name__)

terminal_router = APIRouter(tags=["terminal"])


# ─── Feature gate ─────────────────────────────────────────────────────────────

def _gate() -> None:
    if not settings.WORKSTATION_LIVE_TERMINAL_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Live terminal is not enabled on this instance. "
                   "Set WORKSTATION_LIVE_TERMINAL_ENABLED=true to enable.",
        )


# ─── HTTP endpoints ───────────────────────────────────────────────────────────

class SessionCreateRequest(BaseModel):
    host: str = "localhost"
    shell: str = "/bin/bash"
    station_id: Optional[str] = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    host: str
    shell: str
    status: str
    started_at: float
    last_activity_at: float
    station_id: Optional[str] = None


@terminal_router.post("/sessions", response_model=SessionResponse)
async def create_terminal_session(
    body: SessionCreateRequest,
    current_user: CurrentChatUser,
) -> SessionResponse:
    """Spawn a new PTY-backed shell session."""
    _gate()
    try:
        session = await terminal_manager.create_session(
            user_id=str(current_user.id),
            host=body.host,
            shell=body.shell,
            station_id=body.station_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    return SessionResponse(
        session_id=session.session_id,
        user_id=session.user_id,
        host=session.host,
        shell=session.shell,
        status=session.status,
        started_at=session.started_at,
        last_activity_at=session.last_activity_at,
        station_id=session.station_id,
    )


@terminal_router.get("/sessions", response_model=list[SessionResponse])
async def list_terminal_sessions(
    current_user: CurrentChatUser,
) -> list[SessionResponse]:
    """List the caller's active sessions."""
    _gate()
    sessions = terminal_manager.list_user_sessions(str(current_user.id))
    return [
        SessionResponse(
            session_id=s.session_id,
            user_id=s.user_id,
            host=s.host,
            shell=s.shell,
            status=s.status,
            started_at=s.started_at,
            last_activity_at=s.last_activity_at,
            station_id=s.station_id,
        )
        for s in sessions
    ]


@terminal_router.delete("/sessions/{session_id}")
async def close_terminal_session(
    session_id: str,
    current_user: CurrentChatUser,
) -> dict:
    """Close a terminal session."""
    _gate()
    session = terminal_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    await terminal_manager.close_session(session_id)
    return {"status": "closed", "session_id": session_id}


# ─── WebSocket ────────────────────────────────────────────────────────────────

@terminal_router.websocket("/ws/{session_id}")
async def terminal_websocket(websocket: WebSocket, session_id: str) -> None:
    """
    WebSocket stream for a terminal session.

    Auth: cookie-first (chat_token), then first-message auth if no cookie.
    User can only connect to their own sessions.
    """
    if not settings.WORKSTATION_LIVE_TERMINAL_ENABLED:
        await websocket.close(code=4403, reason="Terminal not enabled")
        return

    await websocket.accept()

    # ── Auth ──────────────────────────────────────────────────────────────────
    from app.api.routes.chat.websocket import get_current_chat_user_from_token

    token = websocket.cookies.get("chat_token")
    if not token:
        try:
            auth_msg = await asyncio.wait_for(
                websocket.receive_json(), timeout=10.0
            )
        except (asyncio.TimeoutError, Exception):
            await websocket.close(code=4001, reason="Authentication timeout")
            return
        if auth_msg.get("type") != "auth" or not auth_msg.get("token"):
            await websocket.close(
                code=4001,
                reason="First message must be {type: 'auth', token: '...'}",
            )
            return
        token = auth_msg["token"]

    db = next(get_db())
    user = await get_current_chat_user_from_token(token, db)
    if not user:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # ── Session auth ──────────────────────────────────────────────────────────
    session = terminal_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4404, reason="Session not found")
        return
    if session.user_id != str(user.id):
        await websocket.close(code=4403, reason="Access denied")
        return
    if session.status in ("closed", "error"):
        await websocket.close(code=4410, reason="Session already closed")
        return

    session.status = "connected"

    # ── Send initial connected event ──────────────────────────────────────────
    await websocket.send_json(
        {
            "type": "connected",
            "session_id": session_id,
            "host": session.host,
            "shell": session.shell,
            "started_at": session.started_at,
        }
    )

    # ── Output queue (PTY → WS) ───────────────────────────────────────────────
    output_queue: asyncio.Queue = asyncio.Queue(maxsize=512)

    def on_output(data: bytes) -> None:
        try:
            output_queue.put_nowait(
                {"type": "output", "data": base64.b64encode(data).decode()}
            )
        except asyncio.QueueFull:
            pass  # drop on back-pressure; terminal keeps rendering from PTY buffer

    session.add_output_callback(on_output)

    # ── Run send + recv tasks concurrently ────────────────────────────────────
    send_task = asyncio.create_task(
        _drain_output(websocket, output_queue),
        name=f"terminal-send-{session_id[:8]}",
    )
    recv_task = asyncio.create_task(
        _handle_input(websocket, session_id),
        name=f"terminal-recv-{session_id[:8]}",
    )

    try:
        done, pending = await asyncio.wait(
            [send_task, recv_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
    except Exception as exc:
        logger.debug("Terminal WS error for %s: %s", session_id, exc)
    finally:
        session.remove_output_callback(on_output)
        if session.status == "connected":
            session.status = "idle"
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info("Terminal WS disconnected for session %s", session_id)


async def _drain_output(websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Forward PTY output from queue to the WebSocket."""
    try:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except (WebSocketDisconnect, Exception):
        pass


async def _handle_input(websocket: WebSocket, session_id: str) -> None:
    """Receive input/resize/close messages from the WebSocket."""
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "input":
                raw_b64 = data.get("data", "")
                try:
                    raw = base64.b64decode(raw_b64)
                except Exception:
                    continue
                if raw:
                    await terminal_manager.write_input(session_id, raw)

            elif msg_type == "resize":
                cols = int(data.get("cols", 80))
                rows = int(data.get("rows", 24))
                await terminal_manager.resize(session_id, cols, rows)

            elif msg_type == "close":
                await terminal_manager.close_session(session_id)
                break

    except (WebSocketDisconnect, Exception):
        pass
