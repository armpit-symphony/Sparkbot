"""
Discord gateway bot bridge for Sparkbot.

Architecture:
  - discord.py 2.x WebSocket gateway — persistent connection, no polling overhead
  - Launched via asyncio.create_task() from FastAPI startup (same pattern as Telegram)
  - Responds to DMs always; guild channel messages only when @mentioned
  - Slash commands: /start, /help, /approve, /deny (mirrors Telegram)
  - Room mapping: SQLite sidecar (same data dir as Telegram bridge)
  - All prompts go through stream_chat_with_tools() — policy/tool/guardian unchanged

Configuration (env vars):
  DISCORD_BOT_TOKEN       — bot token from Discord Developer Portal (required)
  DISCORD_ENABLED         — "true" to activate (default false)
  DISCORD_DM_ONLY         — "true" to ignore guild @mentions (default false)
  DISCORD_GUILD_IDS       — comma-separated guild snowflakes to restrict to (optional)

Developer Portal setup required:
  1. Bot Settings → "Message Content Intent" must be ENABLED (privileged intent)
     (Not strictly needed for DMs, but required for guild @mention text)
  2. Bot Settings → "Server Members Intent" — leave default (off is fine)
"""

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

import discord
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
from app.services.guardian import get_guardian_suite

logger = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

_DISCORD_UNCONFIGURED_RETRY_SECONDS = 30


def _discord_token() -> str:
    return os.getenv("DISCORD_BOT_TOKEN", "").strip()


def _discord_enabled() -> bool:
    return os.getenv("DISCORD_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _discord_dm_only() -> bool:
    return os.getenv("DISCORD_DM_ONLY", "false").strip().lower() in {"1", "true", "yes", "on"}


def _discord_guild_ids() -> set[int]:
    return {
        int(g.strip()) for g in os.getenv("DISCORD_GUILD_IDS", "").split(",")
        if g.strip().isdigit()
    }

# Module-level get_db holder — set when the bot task starts
_get_db_fn: Optional[Callable[[], Any]] = None

# ── SQLite sidecar ────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS discord_links (
  channel_id TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  discord_user_id TEXT,
  discord_username TEXT,
  discord_display_name TEXT,
  pending_confirm_id TEXT,
  pending_confirm_tool TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discord_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_discord_links_room_id ON discord_links(room_id);
"""


@dataclass(frozen=True)
class DiscordLink:
    channel_id: str
    room_id: str
    user_id: str
    discord_user_id: Optional[str]
    discord_username: Optional[str]
    discord_display_name: Optional[str]
    pending_confirm_id: Optional[str]
    pending_confirm_tool: Optional[str]
    created_at: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _data_root() -> Path:
    root = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    if root:
        return Path(root).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "guardian"


def _db_path() -> Path:
    path = _data_root() / "discord_bridge.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_store() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def _get_link(channel_id: str) -> Optional[DiscordLink]:
    _init_store()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM discord_links WHERE channel_id = ?", (channel_id,)).fetchone()
    if not row:
        return None
    return DiscordLink(**dict(row))


def _linked_channel_ids_for_room(room_id: str) -> list[str]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT channel_id FROM discord_links WHERE room_id = ? ORDER BY created_at ASC",
            (room_id,),
        ).fetchall()
    return [str(r[0]) for r in rows]


def _upsert_link(
    *,
    channel_id: str,
    room_id: str,
    user_id: str,
    discord_user_id: Optional[str],
    discord_username: Optional[str],
    discord_display_name: Optional[str],
) -> DiscordLink:
    _init_store()
    now = _now_iso()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO discord_links (
              channel_id, room_id, user_id, discord_user_id, discord_username,
              discord_display_name, pending_confirm_id, pending_confirm_tool,
              created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
              room_id = excluded.room_id,
              user_id = excluded.user_id,
              discord_user_id = excluded.discord_user_id,
              discord_username = excluded.discord_username,
              discord_display_name = excluded.discord_display_name,
              updated_at = excluded.updated_at
            """,
            (channel_id, room_id, user_id, discord_user_id, discord_username,
             discord_display_name, now, now),
        )
    link = _get_link(channel_id)
    if not link:
        raise RuntimeError("Failed to persist Discord room link")
    return link


def _set_pending_confirmation(channel_id: str, confirm_id: str, tool_name: str) -> None:
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE discord_links
            SET pending_confirm_id = ?, pending_confirm_tool = ?, updated_at = ?
            WHERE channel_id = ?
            """,
            (confirm_id, tool_name, _now_iso(), channel_id),
        )


def _clear_pending_confirmation(channel_id: str) -> None:
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE discord_links
            SET pending_confirm_id = NULL, pending_confirm_tool = NULL, updated_at = ?
            WHERE channel_id = ?
            """,
            (_now_iso(), channel_id),
        )


def get_status() -> dict[str, Any]:
    _init_store()
    with _conn() as conn:
        count_row = conn.execute("SELECT COUNT(*) FROM discord_links").fetchone()
    enabled = os.getenv("DISCORD_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    dm_only = os.getenv("DISCORD_DM_ONLY", "false").strip().lower() in {"1", "true", "yes", "on"}
    restricted_guilds = [
        int(g.strip())
        for g in os.getenv("DISCORD_GUILD_IDS", "").split(",")
        if g.strip().isdigit()
    ]
    return {
        "configured": bool(os.getenv("DISCORD_BOT_TOKEN", "").strip()),
        "enabled": enabled,
        "dm_only": dm_only,
        "restricted_guilds": restricted_guilds,
        "linked_channels": int(count_row[0]) if count_row else 0,
        "data_path": str(_db_path()),
    }


# ── Room helpers ──────────────────────────────────────────────────────────────

def _find_or_create_bot_user(session: Session) -> ChatUser:
    bot_user = session.exec(
        select(ChatUser).where(ChatUser.username == "sparkbot")
    ).scalar_one_or_none()
    if bot_user:
        return bot_user
    bot_user = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
    session.add(bot_user)
    session.commit()
    session.refresh(bot_user)
    return bot_user


def _ensure_linked_room(
    session: Session,
    channel_id: str,
    discord_user: discord.User | discord.Member,
    is_dm: bool,
) -> DiscordLink:
    existing = _get_link(channel_id)
    if existing:
        return _upsert_link(
            channel_id=channel_id,
            room_id=existing.room_id,
            user_id=existing.user_id,
            discord_user_id=str(discord_user.id),
            discord_username=str(discord_user.name),
            discord_display_name=getattr(discord_user, "display_name", discord_user.name),
        )

    discord_user_id_str = str(discord_user.id)
    username = f"discord_{discord_user_id_str}"[:100]
    chat_user = get_chat_user_by_username(session, username)
    if not chat_user:
        chat_user = create_chat_user(session, username=username, user_type="HUMAN")

    display = getattr(discord_user, "display_name", discord_user.name)
    room_prefix = "Discord DM" if is_dm else "Discord"
    room = create_chat_room(
        session,
        name=f"{room_prefix} - {display}"[:200],
        created_by=chat_user.id,
        description=f"Discord bridge for channel {channel_id}",
    )
    return _upsert_link(
        channel_id=channel_id,
        room_id=str(room.id),
        user_id=str(chat_user.id),
        discord_user_id=discord_user_id_str,
        discord_username=str(discord_user.name),
        discord_display_name=display,
    )


# ── LLM integration ───────────────────────────────────────────────────────────

async def _run_room_prompt(
    session: Session,
    room_id: str,
    user_id: str,
    content: str,
    *,
    channel_id: str,
) -> dict[str, Any]:
    from app.api.routes.chat.agents import get_agent, resolve_agent_from_message
    from app.api.routes.chat.llm import SYSTEM_PROMPT, stream_chat_with_tools
    guardian_suite = get_guardian_suite()

    room_uuid = uuid.UUID(room_id)
    user_uuid = uuid.UUID(user_id)
    room = get_chat_room_by_id(session, room_uuid)
    user = get_chat_user_by_id(session, user_uuid)
    if not room or not user:
        raise RuntimeError("Linked Discord room or user no longer exists.")

    human_message = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=user_uuid,
        content=content,
        sender_type="HUMAN",
        meta_json={"source": "discord", "discord_channel_id": channel_id},
    )

    # Broadcast to browser WebSocket so the conversation appears in the web UI
    try:
        from app.api.routes.chat.websocket import ws_manager
        await ws_manager.broadcast(room_id, {
            "type": "message",
            "payload": {
                "id": str(human_message.id),
                "room_id": room_id,
                "content": content,
                "sender_type": "HUMAN",
                "sender": {"username": user.username},
                "created_at": _now_iso(),
            },
        })
    except Exception:
        pass

    agent_name, agent_content = resolve_agent_from_message(content)
    try:
        guardian_suite.memory.remember_chat_message(user_id=user_id, room_id=room_id, role="user", content=agent_content)
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
        from app.api.routes.chat.agents import get_agent
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
        memory_context = guardian_suite.memory.build_memory_context(user_id=user_id, room_id=room_id, query=agent_content)
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
        is_operator=guardian_suite.auth.is_operator_user_id(session, user_id),
        is_privileged=guardian_suite.auth.is_operator_privileged(user_id),
    ):
        etype = event.get("type")
        if etype == "token":
            full_text += str(event.get("token", ""))
        elif etype == "confirm_required":
            confirm_id = str(event.get("confirm_id", ""))
            tool_name = str(event.get("tool", "tool"))
            _set_pending_confirmation(channel_id, confirm_id, tool_name)
            text = (
                f"⚠️ Approval required for **{tool_name}**.\n"
                f"Reply `/approve` to continue or `/deny` to cancel."
            )
            bot_user = _find_or_create_bot_user(session)
            bot_msg = create_chat_message(
                session=session,
                room_id=room_uuid,
                sender_id=bot_user.id,
                content=text,
                sender_type="BOT",
                meta_json={"source": "discord", "discord_channel_id": channel_id, "confirm_required": True},
            )
            try:
                from app.api.routes.chat.websocket import ws_manager
                await ws_manager.broadcast(room_id, {
                    "type": "message",
                    "payload": {
                        "id": str(bot_msg.id), "room_id": room_id, "content": text,
                        "sender_type": "BOT", "sender": {"username": "sparkbot"},
                        "created_at": _now_iso(),
                    },
                })
            except Exception:
                pass
            return {"kind": "confirm", "text": text, "confirm_id": confirm_id, "tool_name": tool_name}

    final_text = full_text.strip() or "I did not generate a response."
    bot_user = _find_or_create_bot_user(session)
    bot_msg = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=bot_user.id,
        content=final_text,
        sender_type="BOT",
        meta_json={"source": "discord", "discord_channel_id": channel_id},
    )
    try:
        guardian_suite.memory.remember_chat_message(user_id=user_id, room_id=room_id, role="assistant", content=final_text)
    except Exception:
        pass
    try:
        from app.api.routes.chat.websocket import ws_manager
        await ws_manager.broadcast(room_id, {
            "type": "message",
            "payload": {
                "id": str(bot_msg.id), "room_id": room_id, "content": final_text,
                "sender_type": "BOT", "sender": {"username": "sparkbot"},
                "created_at": _now_iso(),
            },
        })
    except Exception:
        pass
    return {"kind": "reply", "text": final_text, "message_id": str(bot_msg.id)}


async def _execute_pending_confirmation(
    session: Session,
    room_id: str,
    user_id: str,
    confirm_id: str,
    *,
    channel_id: str,
) -> str:
    from app.api.routes.chat.llm import (
        consume_pending,
        mask_tool_result_for_external,
        redact_tool_call_for_audit,
        serialize_tool_args_for_audit,
    )
    from app.api.routes.chat.tools import execute_tool
    guardian_suite = get_guardian_suite()

    pending = consume_pending(confirm_id)
    if not pending:
        _clear_pending_confirmation(channel_id)
        return "Approval expired or is no longer valid."

    tool_name = str(pending.get("tool", ""))
    tool_args = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    room = get_chat_room_by_id(session, uuid.UUID(room_id))
    if not room:
        return "Linked room not found."

    decision = guardian_suite.policy.decide_tool_use(
        tool_name,
        tool_args,
        room_execution_allowed=room.execution_allowed,
        is_operator=guardian_suite.auth.is_operator_user_id(session, user_id),
        is_privileged=guardian_suite.auth.is_operator_privileged(user_id),
    )
    create_audit_log(
        session=session,
        tool_name="policy_decision",
        tool_input=json.dumps(
            {
                "tool_name": tool_name,
                "tool_args": json.loads(serialize_tool_args_for_audit(tool_name, tool_args)),
                "confirmed": True,
            }
        ),
        tool_result=decision.to_json(),
        user_id=uuid.UUID(user_id),
        room_id=uuid.UUID(room_id),
        model=None,
    )
    if decision.action == "deny":
        result = f"POLICY DENIED: {decision.reason}"
    else:
        result = await guardian_suite.executive.exec_with_guard(
            tool_name=tool_name,
            action_type=decision.action_type,
            expected_outcome=f"Confirmed Discord execution for {tool_name}",
            perform_fn=lambda: execute_tool(
                tool_name, tool_args,
                user_id=user_id, session=session, room_id=room_id,
            ),
            metadata={"room_id": room_id, "user_id": user_id, "confirmed": True, "source": "discord"},
        )
    result_text = mask_tool_result_for_external(tool_name, tool_args, result)
    redacted_input, redacted_result = redact_tool_call_for_audit(tool_name, tool_args, result)
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
        guardian_suite.memory.remember_tool_event(
            user_id=user_id, room_id=room_id,
            tool_name=tool_name, args=tool_args, result=redacted_result,
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
        meta_json={"source": "discord", "discord_channel_id": channel_id, "confirmed": True},
    )
    try:
        from app.api.routes.chat.websocket import ws_manager
        await ws_manager.broadcast(room_id, {
            "type": "message",
            "payload": {
                "id": str(bot_msg.id), "room_id": room_id, "content": result_text,
                "sender_type": "BOT", "sender": {"username": "sparkbot"},
                "created_at": _now_iso(),
            },
        })
    except Exception:
        pass
    _clear_pending_confirmation(channel_id)
    return result_text


# ── Text helpers ──────────────────────────────────────────────────────────────

def _chunk_text(text: str, limit: int = 1900) -> list[str]:
    """Discord max message = 2000 chars; use 1900 for safety."""
    text = (text or "").strip()
    if not text:
        return ["(empty response)"]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < 200:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks or ["(empty response)"]


def _help_text() -> str:
    return (
        "**Sparkbot Discord bridge is active.**\n\n"
        "Send me a DM or @mention me in a channel to chat.\n"
        "• `/approve` — confirm a pending tool action\n"
        "• `/deny` — cancel a pending tool action\n\n"
        "_All conversations are stored in your private Sparkbot room._"
    )


# ── Discord bot ───────────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True   # privileged — must be enabled in Developer Portal
intents.dm_messages = True

bot = discord.Client(intents=intents)


@bot.event
async def on_ready() -> None:
    logger.info("[discord] Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "?")


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return

    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user is not None and bot.user in message.mentions

    if not is_dm and not is_mention:
        return
    if _discord_dm_only() and not is_dm:
        return

    # Restrict to configured guilds if set
    guild_ids = _discord_guild_ids()
    if guild_ids and not is_dm:
        if not hasattr(message.guild, "id") or message.guild.id not in guild_ids:  # type: ignore[union-attr]
            return

    # Strip @mention from text
    text = message.content or ""
    if is_mention and bot.user:
        text = text.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()
    if not text:
        await message.reply("I can process text messages. Try asking me something!")
        return

    if not _get_db_fn:
        logger.warning("[discord] on_message fired before _get_db_fn was set")
        return

    channel_id = str(message.channel.id)
    lower = text.strip().lower()

    db = _get_db_fn()
    try:
        link = _ensure_linked_room(db, channel_id, message.author, is_dm)

        if lower in {"/start", "/help"}:
            await message.reply(_help_text())
            return

        if lower in {"/deny", "/cancel"}:
            if not link.pending_confirm_id:
                await message.reply("There is no pending approval to cancel.")
                return
            from app.api.routes.chat.llm import discard_pending

            discard_pending(link.pending_confirm_id)
            _clear_pending_confirmation(channel_id)
            await message.reply("Pending action cancelled.")
            return

        if lower == "/approve":
            if not link.pending_confirm_id:
                await message.reply("There is no pending approval right now.")
                return
            result = await _execute_pending_confirmation(
                db, link.room_id, link.user_id, link.pending_confirm_id,
                channel_id=channel_id,
            )
            for chunk in _chunk_text(result):
                await message.reply(chunk)
            return

        # Normal message
        result = await _run_room_prompt(db, link.room_id, link.user_id, text, channel_id=channel_id)
        reply_text = str(result.get("text", ""))
        for chunk in _chunk_text(reply_text):
            await message.reply(chunk)

    except Exception:
        logger.exception("[discord] Error handling message in channel %s", channel_id)
        await message.reply("Sorry, I encountered an error processing your message.")
    finally:
        db.close()


# ── Public notification helper ────────────────────────────────────────────────

async def send_room_notification(room_id: str, text: str) -> None:
    """Send a text notification to all Discord channels linked to a Sparkbot room."""
    if not (bot.is_ready() and _discord_token()):
        return
    for channel_id in _linked_channel_ids_for_room(room_id):
        try:
            channel = bot.get_channel(int(channel_id))
            if channel and hasattr(channel, "send"):
                for chunk in _chunk_text(text):
                    await channel.send(chunk)  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("[discord] send_room_notification failed for channel %s: %s", channel_id, exc)


# ── Background task entry point ───────────────────────────────────────────────

async def discord_bot_task(get_db_session: Callable[[], Any]) -> None:
    """
    Started by FastAPI via asyncio.create_task() in _start_background_guardians().
    Waits for token to be configured rather than exiting immediately.
    """
    while not (_discord_enabled() and _discord_token()):
        await asyncio.sleep(_DISCORD_UNCONFIGURED_RETRY_SECONDS)

    global _get_db_fn
    _get_db_fn = lambda: next(get_db_session())  # noqa: E731

    _init_store()
    logger.info("[discord] Bot starting")
    try:
        await bot.start(_discord_token())
    except asyncio.CancelledError:
        logger.info("[discord] Bot stopped")
        await bot.close()
    except Exception as exc:
        logger.exception("[discord] Fatal error: %s", exc)
        await bot.close()
