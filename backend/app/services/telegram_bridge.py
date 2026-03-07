from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from sqlalchemy import select
from sqlmodel import Session

from app.crud import (
    create_audit_log,
    create_chat_message,
    create_chat_room,
    create_chat_user,
    get_chat_messages,
    get_chat_room_by_id,
    get_chat_user_by_id,
    get_chat_user_by_username,
    get_user_memories,
)
from app.models import ChatUser, UserType

logger = logging.getLogger(__name__)

_TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
_TELEGRAM_POLL_ENABLED = os.getenv("TELEGRAM_POLL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
_TELEGRAM_ALLOWED_CHAT_IDS = {
    part.strip() for part in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if part.strip()
}
_TELEGRAM_REQUIRE_PRIVATE_CHAT = os.getenv("TELEGRAM_REQUIRE_PRIVATE_CHAT", "true").strip().lower() in {"1", "true", "yes", "on"}
_TELEGRAM_POLL_TIMEOUT_SECONDS = max(10, min(int(os.getenv("TELEGRAM_POLL_TIMEOUT_SECONDS", "45")), 55))
_TELEGRAM_POLL_RETRY_SECONDS = max(3, min(int(os.getenv("TELEGRAM_POLL_RETRY_SECONDS", "5")), 60))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telegram_links (
  chat_id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  tg_user_id TEXT,
  tg_username TEXT,
  tg_display_name TEXT,
  pending_confirm_id TEXT,
  pending_confirm_tool TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_telegram_links_room_id ON telegram_links(room_id);
"""


@dataclass(frozen=True)
class TelegramLink:
    chat_id: str
    room_id: str
    user_id: str
    tg_user_id: Optional[str]
    tg_username: Optional[str]
    tg_display_name: Optional[str]
    pending_confirm_id: Optional[str]
    pending_confirm_tool: Optional[str]
    created_at: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _configured() -> bool:
    return bool(_TELEGRAM_BOT_TOKEN)


def _api_base() -> str:
    return f"https://api.telegram.org/bot{_TELEGRAM_BOT_TOKEN}"


def _data_root() -> Path:
    root = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    if root:
        return Path(root).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "guardian"


def _db_path() -> Path:
    path = _data_root() / "telegram_bridge.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_store() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def _get_state(key: str, default: str = "") -> str:
    _init_store()
    with _conn() as conn:
        row = conn.execute("SELECT value FROM telegram_state WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else default


def _set_state(key: str, value: str) -> None:
    _init_store()
    now = _now_iso()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO telegram_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )


def _get_link(chat_id: str) -> Optional[TelegramLink]:
    _init_store()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM telegram_links WHERE chat_id = ?", (chat_id,)).fetchone()
    if not row:
        return None
    return TelegramLink(**dict(row))


def _linked_chat_ids_for_room(room_id: str) -> list[str]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT chat_id FROM telegram_links WHERE room_id = ? ORDER BY created_at ASC",
            (room_id,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def _upsert_link(
    *,
    chat_id: str,
    room_id: str,
    user_id: str,
    tg_user_id: Optional[str],
    tg_username: Optional[str],
    tg_display_name: Optional[str],
) -> TelegramLink:
    _init_store()
    now = _now_iso()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO telegram_links (
              chat_id, room_id, user_id, tg_user_id, tg_username, tg_display_name,
              pending_confirm_id, pending_confirm_tool, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
              room_id = excluded.room_id,
              user_id = excluded.user_id,
              tg_user_id = excluded.tg_user_id,
              tg_username = excluded.tg_username,
              tg_display_name = excluded.tg_display_name,
              updated_at = excluded.updated_at
            """,
            (
                chat_id,
                room_id,
                user_id,
                tg_user_id,
                tg_username,
                tg_display_name,
                now,
                now,
            ),
        )
    link = _get_link(chat_id)
    if not link:
        raise RuntimeError("Failed to persist Telegram room link")
    return link


def _set_pending_confirmation(chat_id: str, confirm_id: str, tool_name: str) -> None:
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE telegram_links
            SET pending_confirm_id = ?, pending_confirm_tool = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (confirm_id, tool_name, _now_iso(), chat_id),
        )


def _clear_pending_confirmation(chat_id: str) -> None:
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE telegram_links
            SET pending_confirm_id = NULL, pending_confirm_tool = NULL, updated_at = ?
            WHERE chat_id = ?
            """,
            (_now_iso(), chat_id),
        )


def get_status() -> dict[str, Any]:
    _init_store()
    with _conn() as conn:
        count_row = conn.execute("SELECT COUNT(*) FROM telegram_links").fetchone()
    poll_enabled = os.getenv("TELEGRAM_POLL_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    private_only = os.getenv("TELEGRAM_REQUIRE_PRIVATE_CHAT", "true").strip().lower() in {"1", "true", "yes", "on"}
    allowed_chat_ids = {
        part.strip() for part in os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", "").split(",") if part.strip()
    }
    return {
        "configured": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
        "poll_enabled": poll_enabled,
        "private_only": private_only,
        "allowed_chat_ids_count": len(allowed_chat_ids),
        "linked_chats": int(count_row[0]) if count_row else 0,
        "data_path": str(_db_path()),
    }


def _display_name(user: dict[str, Any] | None) -> str:
    user = user or {}
    parts = [str(user.get("first_name", "")).strip(), str(user.get("last_name", "")).strip()]
    full = " ".join(part for part in parts if part).strip()
    if full:
        return full
    username = str(user.get("username", "")).strip()
    if username:
        return f"@{username}"
    return f"Telegram user {user.get('id', 'unknown')}"


def _safe_room_name(display_name: str) -> str:
    return f"Telegram - {display_name}"[:200]


def _chat_allowed(chat_id: str) -> bool:
    if not _TELEGRAM_ALLOWED_CHAT_IDS:
        return True
    return chat_id in _TELEGRAM_ALLOWED_CHAT_IDS


def _chunk_text(text: str, limit: int = 3500) -> list[str]:
    text = (text or "").strip()
    if not text:
        return ["(empty response)"]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < 500:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks or ["(empty response)"]


async def _telegram_api(method: str, payload: dict[str, Any]) -> Any:
    if not _configured():
        raise RuntimeError("Telegram bridge is not configured.")
    timeout = max(_TELEGRAM_POLL_TIMEOUT_SECONDS + 10, 20)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{_api_base()}/{method}", json=payload)
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        description = str(data.get("description", "Unknown Telegram API error"))
        raise RuntimeError(f"Telegram API {method} failed: {description}")
    return data.get("result")


async def _send_text(chat_id: str, text: str) -> None:
    for chunk in _chunk_text(text):
        try:
            await _telegram_api("sendMessage", {"chat_id": chat_id, "text": chunk})
        except Exception as exc:
            logger.warning("[telegram] sendMessage failed for chat %s: %s", chat_id, exc)
            return


async def send_room_notification(room_id: str, text: str) -> None:
    if not _configured():
        return
    for chat_id in _linked_chat_ids_for_room(room_id):
        await _send_text(chat_id, text)


async def _broadcast_room_message(room_id: str, message_id: str, content: str, sender_username: str, sender_type: str) -> None:
    try:
        from app.api.routes.chat.websocket import ws_manager

        await ws_manager.broadcast(
            room_id,
            {
                "type": "message",
                "payload": {
                    "id": message_id,
                    "room_id": room_id,
                    "content": content,
                    "sender_type": sender_type,
                    "sender": {"username": sender_username},
                    "created_at": _now_iso(),
                },
            },
        )
    except Exception:
        pass


def _find_or_create_bot_user(session: Session) -> ChatUser:
    bot_user = session.exec(select(ChatUser).where(ChatUser.username == "sparkbot")).scalar_one_or_none()
    if bot_user:
        return bot_user
    bot_user = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
    session.add(bot_user)
    session.commit()
    session.refresh(bot_user)
    return bot_user


def _ensure_linked_room(session: Session, chat_id: str, tg_user: dict[str, Any]) -> TelegramLink:
    existing = _get_link(chat_id)
    if existing:
        return _upsert_link(
            chat_id=chat_id,
            room_id=existing.room_id,
            user_id=existing.user_id,
            tg_user_id=str(tg_user.get("id", "")) or None,
            tg_username=str(tg_user.get("username", "")).strip() or None,
            tg_display_name=_display_name(tg_user),
        )

    telegram_user_id = str(tg_user.get("id", "")).strip()
    if not telegram_user_id:
        raise RuntimeError("Telegram user id missing")
    username = f"telegram_{telegram_user_id}"[:100]
    chat_user = get_chat_user_by_username(session, username)
    if not chat_user:
        chat_user = create_chat_user(session, username=username, user_type="HUMAN")
    room = create_chat_room(
        session,
        name=_safe_room_name(_display_name(tg_user)),
        created_by=chat_user.id,
        description=f"Private Telegram bridge for chat {chat_id}",
    )
    return _upsert_link(
        chat_id=chat_id,
        room_id=str(room.id),
        user_id=str(chat_user.id),
        tg_user_id=telegram_user_id,
        tg_username=str(tg_user.get("username", "")).strip() or None,
        tg_display_name=_display_name(tg_user),
    )


async def _run_room_prompt(session: Session, room_id: str, user_id: str, content: str, *, chat_id: str) -> dict[str, Any]:
    from app.api.routes.chat.agents import get_agent, resolve_agent_from_message
    from app.api.routes.chat.llm import SYSTEM_PROMPT, stream_chat_with_tools
    from app.services.guardian.memory import build_memory_context, remember_chat_message

    room_uuid = uuid.UUID(room_id)
    user_uuid = uuid.UUID(user_id)
    room = get_chat_room_by_id(session, room_uuid)
    user = get_chat_user_by_id(session, user_uuid)
    if not room or not user:
        raise RuntimeError("Linked Telegram room or user no longer exists.")

    human_message = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=user_uuid,
        content=content,
        sender_type="HUMAN",
        meta_json={"source": "telegram", "telegram_chat_id": chat_id},
    )
    await _broadcast_room_message(room_id, str(human_message.id), content, user.username, "HUMAN")

    agent_name, agent_content = resolve_agent_from_message(content)
    try:
        remember_chat_message(user_id=user_id, room_id=room_id, role="user", content=agent_content)
    except Exception:
        pass

    history_msgs, _, _ = get_chat_messages(session=session, room_id=room_uuid, limit=20)
    openai_history: list[dict[str, str]] = []
    for msg in history_msgs:
        if str(msg.id) == str(human_message.id):
            continue
        role = "assistant" if str(msg.sender_type).upper() == "BOT" else "user"
        openai_history.append({"role": role, "content": msg.content})
    openai_history.append({"role": "user", "content": agent_content})

    base_prompt = SYSTEM_PROMPT
    if agent_name:
        agent = get_agent(agent_name)
        if agent and agent.get("system_prompt"):
            base_prompt = agent["system_prompt"]

    memories = get_user_memories(session, user_uuid)
    if memories:
        mem_block = "\n".join(f"- {m.fact}" for m in memories)
        system_prompt = base_prompt + f"\n\n## What you know about this user:\n{mem_block}"
    else:
        system_prompt = base_prompt

    try:
        memory_context = build_memory_context(user_id=user_id, room_id=room_id, query=agent_content)
    except Exception:
        memory_context = ""
    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    full_text = ""
    async for event in stream_chat_with_tools(
        [{"role": "system", "content": system_prompt}] + openai_history,
        user_id=user_id,
        db_session=session,
        room_id=room_id,
        agent_name=agent_name,
        room_execution_allowed=room.execution_allowed,
    ):
        etype = event.get("type")
        if etype == "token":
            full_text += str(event.get("token", ""))
        elif etype == "confirm_required":
            confirm_id = str(event.get("confirm_id", ""))
            tool_name = str(event.get("tool", "tool"))
            _set_pending_confirmation(chat_id, confirm_id, tool_name)
            text = f"Approval required for {tool_name}. Reply /approve to continue or /deny to cancel."
            bot_user = _find_or_create_bot_user(session)
            bot_msg = create_chat_message(
                session=session,
                room_id=room_uuid,
                sender_id=bot_user.id,
                content=text,
                sender_type="BOT",
                meta_json={"source": "telegram", "telegram_chat_id": chat_id, "confirm_required": True},
            )
            await _broadcast_room_message(room_id, str(bot_msg.id), text, bot_user.username, "BOT")
            return {"kind": "confirm", "text": text, "confirm_id": confirm_id, "tool_name": tool_name}

    final_text = full_text.strip() or "I did not generate a response."
    bot_user = _find_or_create_bot_user(session)
    bot_msg = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=bot_user.id,
        content=final_text,
        sender_type="BOT",
        meta_json={"source": "telegram", "telegram_chat_id": chat_id},
    )
    try:
        remember_chat_message(user_id=user_id, room_id=room_id, role="assistant", content=final_text)
    except Exception:
        pass
    await _broadcast_room_message(room_id, str(bot_msg.id), final_text, bot_user.username, "BOT")
    return {"kind": "reply", "text": final_text, "message_id": str(bot_msg.id)}


async def _execute_pending_confirmation(session: Session, room_id: str, user_id: str, confirm_id: str, *, chat_id: str) -> str:
    from app.api.routes.chat.llm import _redact_for_audit, consume_pending
    from app.api.routes.chat.tools import execute_tool
    from app.services.guardian.executive import exec_with_guard
    from app.services.guardian.memory import remember_tool_event
    from app.services.guardian.policy import decide_tool_use

    pending = consume_pending(confirm_id)
    if not pending:
        _clear_pending_confirmation(chat_id)
        return "Approval expired or is no longer valid."

    tool_name = str(pending.get("tool", ""))
    tool_args = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    room = get_chat_room_by_id(session, uuid.UUID(room_id))
    if not room:
        return "Linked room not found."

    decision = decide_tool_use(tool_name, tool_args, room_execution_allowed=room.execution_allowed)
    create_audit_log(
        session=session,
        tool_name="policy_decision",
        tool_input=json.dumps({"tool_name": tool_name, "tool_args": tool_args, "confirmed": True}),
        tool_result=decision.to_json(),
        user_id=uuid.UUID(user_id),
        room_id=uuid.UUID(room_id),
        model=None,
    )
    if decision.action == "deny":
        result = f"POLICY DENIED: {decision.reason}"
    else:
        result = await exec_with_guard(
            tool_name=tool_name,
            action_type=decision.action_type,
            expected_outcome=f"Confirmed Telegram execution for {tool_name}",
            perform_fn=lambda: execute_tool(
                tool_name,
                tool_args,
                user_id=user_id,
                session=session,
                room_id=room_id,
            ),
            metadata={"room_id": room_id, "user_id": user_id, "confirmed": True, "source": "telegram"},
        )
    result_text = str(result)
    redacted_input, redacted_result = _redact_for_audit(json.dumps(tool_args), result_text)
    create_audit_log(
        session=session,
        tool_name=tool_name,
        tool_input=redacted_input,
        tool_result=redacted_result,
        user_id=uuid.UUID(user_id),
        room_id=uuid.UUID(room_id),
        model=None,
    )
    try:
        remember_tool_event(
            user_id=user_id,
            room_id=room_id,
            tool_name=tool_name,
            args=tool_args,
            result=redacted_result,
        )
    except Exception:
        pass

    bot_user = _find_or_create_bot_user(session)
    bot_msg = create_chat_message(
        session=session,
        room_id=uuid.UUID(room_id),
        sender_id=bot_user.id,
        content=result_text,
        sender_type="BOT",
        meta_json={"source": "telegram", "telegram_chat_id": chat_id, "confirmed": True},
    )
    await _broadcast_room_message(room_id, str(bot_msg.id), result_text, bot_user.username, "BOT")
    _clear_pending_confirmation(chat_id)
    return result_text


def _help_text() -> str:
    return (
        "Sparkbot Telegram bridge is active.\n\n"
        "Send any normal message to chat with Sparkbot.\n"
        "Use /approve to confirm a pending action.\n"
        "Use /deny to cancel a pending action."
    )


async def _handle_private_message(message: dict[str, Any], get_db_session: Callable[[], Any]) -> None:
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", "")).strip()
    if not chat_id:
        return
    if not _chat_allowed(chat_id):
        await _send_text(chat_id, "This Telegram chat is not allowed to use Sparkbot.")
        return
    if _TELEGRAM_REQUIRE_PRIVATE_CHAT and str(chat.get("type", "")) != "private":
        await _send_text(chat_id, "Sparkbot Telegram currently supports private chats only.")
        return

    sender = message.get("from") or {}
    if sender.get("is_bot"):
        return

    text = str(message.get("text", "") or "").strip()
    if not text:
        await _send_text(chat_id, "I can currently process text messages only on Telegram.")
        return

    db = next(get_db_session())
    try:
        link = _ensure_linked_room(db, chat_id, sender)
        lower = text.lower()
        if lower in {"/start", "/help"}:
            await _send_text(chat_id, _help_text())
            return
        if lower in {"/deny", "/cancel"}:
            if not link.pending_confirm_id:
                await _send_text(chat_id, "There is no pending approval to cancel.")
                return
            from app.api.routes.chat.llm import discard_pending

            discard_pending(link.pending_confirm_id)
            _clear_pending_confirmation(chat_id)
            await _send_text(chat_id, "Pending action cancelled.")
            return
        if lower == "/approve":
            if not link.pending_confirm_id:
                await _send_text(chat_id, "There is no pending approval right now.")
                return
            result = await _execute_pending_confirmation(
                db,
                link.room_id,
                link.user_id,
                link.pending_confirm_id,
                chat_id=chat_id,
            )
            await _send_text(chat_id, result)
            return

        result = await _run_room_prompt(db, link.room_id, link.user_id, text, chat_id=chat_id)
        await _send_text(chat_id, str(result.get("text", "")))
    except Exception as exc:
        logger.exception("[telegram] Failed to process chat %s", chat_id)
        await _send_text(chat_id, f"Sparkbot Telegram error: {exc}")
    finally:
        db.close()


async def telegram_polling_loop(get_db_session: Callable[[], Any]) -> None:
    if not (_configured() and _TELEGRAM_POLL_ENABLED):
        logger.info("[telegram] Poller disabled")
        return
    logger.info("[telegram] Poller started")
    _init_store()
    offset = int(_get_state("telegram_update_offset", "0") or "0")
    while True:
        try:
            updates = await _telegram_api(
                "getUpdates",
                {
                    "offset": offset,
                    "timeout": _TELEGRAM_POLL_TIMEOUT_SECONDS,
                    "allowed_updates": ["message"],
                },
            )
            for update in updates or []:
                update_id = int(update.get("update_id", 0))
                if update_id:
                    offset = max(offset, update_id + 1)
                    _set_state("telegram_update_offset", str(offset))
                message = update.get("message")
                if message:
                    await _handle_private_message(message, get_db_session)
        except asyncio.CancelledError:
            logger.info("[telegram] Poller stopped")
            return
        except Exception as exc:
            logger.warning("[telegram] Poller error: %s", exc)
            await asyncio.sleep(_TELEGRAM_POLL_RETRY_SECONDS)
