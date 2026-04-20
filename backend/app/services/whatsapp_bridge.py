"""
WhatsApp Cloud API bridge for Sparkbot via pywa (python-whatsapp).

Architecture:
  - Meta WhatsApp Business Cloud API (webhook-based, no long-polling)
  - pywa mounts two routes on the FastAPI app:
      GET  /whatsapp  — Meta webhook verification challenge (auto-handled)
      POST /whatsapp  — Inbound message events
  - register_whatsapp_bridge(app, get_db) must be called AFTER app = FastAPI(...)
    and BEFORE uvicorn starts serving
  - All prompts go through stream_chat_with_tools() — policy/tool/guardian unchanged

Messaging model (2026):
  - Service messages (user initiated): free-form text allowed within 24h window — no templates needed
  - Business-initiated messages: require pre-approved templates (not relevant for a chatbot)
  - Bottom line: reply freely to any user who messages first — no setup beyond registration

Configuration (env vars):
  WHATSAPP_PHONE_ID       — numeric Phone Number ID from Meta Developer Portal (required)
  WHATSAPP_TOKEN          — permanent system user token (required)
  WHATSAPP_VERIFY_TOKEN   — random secret string you set in Meta portal (required)
  WHATSAPP_ENABLED        — "true" to activate (default false)
  WHATSAPP_APP_ID         — app ID for auto webhook registration (optional)
  WHATSAPP_APP_SECRET     — app secret for auto webhook registration (optional)
  PUBLIC_URL              — e.g. https://your-domain.example (for auto-registration)

Meta Developer Portal setup:
  1. Create a Meta App → WhatsApp → Add Phone Number
  2. System User → generate permanent token with whatsapp_business_messaging scope
  3. Set Webhook URL: https://yourdomain.com/whatsapp
  4. Set Webhook Verify Token to match WHATSAPP_VERIFY_TOKEN
  5. Subscribe to: messages

Phone number constraint:
  The registered number cannot simultaneously be used in personal WhatsApp or
  WhatsApp Business App. Use a dedicated number or Meta's free sandbox test number
  (which can send to up to 5 pre-registered test recipients).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

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

# ── Config ────────────────────────────────────────────────────────────────────

def _wa_phone_id() -> str:
    return os.getenv("WHATSAPP_PHONE_ID", "").strip()

def _wa_token() -> str:
    return os.getenv("WHATSAPP_TOKEN", "").strip()

def _wa_verify_token() -> str:
    return os.getenv("WHATSAPP_VERIFY_TOKEN", "sparkbot-wa-verify").strip()

def _wa_app_id() -> str:
    return os.getenv("WHATSAPP_APP_ID", "").strip()

def _wa_app_secret() -> str:
    return os.getenv("WHATSAPP_APP_SECRET", "").strip()

def _wa_enabled() -> bool:
    return os.getenv("WHATSAPP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

def _wa_public_url() -> str:
    return os.getenv("PUBLIC_URL", "").strip().rstrip("/")

def _wa_allowed_phones() -> set[str]:
    return {p.strip() for p in os.getenv("WHATSAPP_ALLOWED_PHONES", "").split(",") if p.strip()}

# ── SQLite sidecar ────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS whatsapp_links (
  wa_phone TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  display_name TEXT,
  pending_confirm_id TEXT,
  pending_confirm_tool TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_links_room_id ON whatsapp_links(room_id);
"""


@dataclass(frozen=True)
class WhatsAppLink:
    wa_phone: str
    room_id: str
    user_id: str
    display_name: Optional[str]
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
    path = _data_root() / "whatsapp_bridge.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_store() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def _get_link(wa_phone: str) -> Optional[WhatsAppLink]:
    _init_store()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM whatsapp_links WHERE wa_phone = ?", (wa_phone,)
        ).fetchone()
    if not row:
        return None
    return WhatsAppLink(**dict(row))


def _linked_phones_for_room(room_id: str) -> list[str]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT wa_phone FROM whatsapp_links WHERE room_id = ? ORDER BY created_at ASC",
            (room_id,),
        ).fetchall()
    return [str(r[0]) for r in rows]


def _upsert_link(
    *,
    wa_phone: str,
    room_id: str,
    user_id: str,
    display_name: Optional[str],
) -> WhatsAppLink:
    _init_store()
    now = _now_iso()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO whatsapp_links (
              wa_phone, room_id, user_id, display_name,
              pending_confirm_id, pending_confirm_tool, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, NULL, NULL, ?, ?)
            ON CONFLICT(wa_phone) DO UPDATE SET
              room_id = excluded.room_id,
              user_id = excluded.user_id,
              display_name = excluded.display_name,
              updated_at = excluded.updated_at
            """,
            (wa_phone, room_id, user_id, display_name, now, now),
        )
    link = _get_link(wa_phone)
    if not link:
        raise RuntimeError("Failed to persist WhatsApp room link")
    return link


def _set_pending_confirmation(wa_phone: str, confirm_id: str, tool_name: str) -> None:
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE whatsapp_links
            SET pending_confirm_id = ?, pending_confirm_tool = ?, updated_at = ?
            WHERE wa_phone = ?
            """,
            (confirm_id, tool_name, _now_iso(), wa_phone),
        )


def _clear_pending_confirmation(wa_phone: str) -> None:
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE whatsapp_links
            SET pending_confirm_id = NULL, pending_confirm_tool = NULL, updated_at = ?
            WHERE wa_phone = ?
            """,
            (_now_iso(), wa_phone),
        )


def get_status() -> dict[str, Any]:
    _init_store()
    with _conn() as conn:
        count_row = conn.execute("SELECT COUNT(*) FROM whatsapp_links").fetchone()
    allowed_phones = {
        p.strip() for p in os.getenv("WHATSAPP_ALLOWED_PHONES", "").split(",") if p.strip()
    }
    return {
        "configured": bool(os.getenv("WHATSAPP_PHONE_ID", "").strip() and os.getenv("WHATSAPP_TOKEN", "").strip()),
        "enabled": os.getenv("WHATSAPP_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"},
        "allowed_phones_count": len(allowed_phones),
        "linked_numbers": int(count_row[0]) if count_row else 0,
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
    wa_phone: str,
    display_name: str,
) -> WhatsAppLink:
    existing = _get_link(wa_phone)
    if existing:
        return _upsert_link(
            wa_phone=wa_phone,
            room_id=existing.room_id,
            user_id=existing.user_id,
            display_name=display_name or existing.display_name,
        )

    username = f"whatsapp_{wa_phone}"[:100]
    chat_user = get_chat_user_by_username(session, username)
    if not chat_user:
        chat_user = create_chat_user(session, username=username, user_type="HUMAN")

    room = create_chat_room(
        session,
        name=f"WhatsApp - {display_name or wa_phone}"[:200],
        created_by=chat_user.id,
        description=f"WhatsApp bridge for +{wa_phone}",
    )
    return _upsert_link(
        wa_phone=wa_phone,
        room_id=str(room.id),
        user_id=str(chat_user.id),
        display_name=display_name,
    )


# ── LLM integration ───────────────────────────────────────────────────────────

async def _run_room_prompt(
    session: Session,
    room_id: str,
    user_id: str,
    content: str,
    *,
    wa_phone: str,
) -> dict[str, Any]:
    from app.api.routes.chat.agents import get_agent, resolve_agent_from_message
    from app.api.routes.chat.llm import SYSTEM_PROMPT, stream_chat_with_tools
    guardian_suite = get_guardian_suite()

    room_uuid = uuid.UUID(room_id)
    user_uuid = uuid.UUID(user_id)
    room = get_chat_room_by_id(session, room_uuid)
    user = get_chat_user_by_id(session, user_uuid)
    if not room or not user:
        raise RuntimeError("Linked WhatsApp room or user no longer exists.")

    human_message = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=user_uuid,
        content=content,
        sender_type="HUMAN",
        meta_json={"source": "whatsapp", "wa_phone": wa_phone},
    )

    try:
        from app.api.routes.chat.websocket import ws_manager
        await ws_manager.broadcast(room_id, {
            "type": "message",
            "payload": {
                "id": str(human_message.id), "room_id": room_id, "content": content,
                "sender_type": "HUMAN", "sender": {"username": user.username},
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
            _set_pending_confirmation(wa_phone, confirm_id, tool_name)
            text = (
                f"⚠️ Approval required for *{tool_name}*.\n"
                f"Reply *approve* to continue or *deny* to cancel."
            )
            bot_user = _find_or_create_bot_user(session)
            bot_msg = create_chat_message(
                session=session,
                room_id=room_uuid,
                sender_id=bot_user.id,
                content=text,
                sender_type="BOT",
                meta_json={"source": "whatsapp", "wa_phone": wa_phone, "confirm_required": True},
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
        meta_json={"source": "whatsapp", "wa_phone": wa_phone},
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
    wa_phone: str,
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
        _clear_pending_confirmation(wa_phone)
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
            expected_outcome=f"Confirmed WhatsApp execution for {tool_name}",
            perform_fn=lambda: execute_tool(
                tool_name, tool_args,
                user_id=user_id, session=session, room_id=room_id,
            ),
            metadata={"room_id": room_id, "user_id": user_id, "confirmed": True, "source": "whatsapp"},
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
        meta_json={"source": "whatsapp", "wa_phone": wa_phone, "confirmed": True},
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
    _clear_pending_confirmation(wa_phone)
    return result_text


# ── Text helpers ──────────────────────────────────────────────────────────────

def _chunk_text(text: str, limit: int = 4000) -> list[str]:
    """WhatsApp max message = 4096 chars; use 4000 for safety."""
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
        "🤖 *Sparkbot WhatsApp bridge is active.*\n\n"
        "Send any message to chat with Sparkbot.\n"
        "• *approve* — confirm a pending tool action\n"
        "• *deny* — cancel a pending tool action\n\n"
        "_All conversations are stored in your private Sparkbot room._"
    )


# ── Public notification helper ────────────────────────────────────────────────

# Holds the pywa WhatsApp client after registration
_wa_client: Any = None


async def send_room_notification(room_id: str, text: str) -> None:
    """Send a text notification to all WhatsApp numbers linked to a Sparkbot room."""
    if not _wa_client:
        return
    for wa_phone in _linked_phones_for_room(room_id):
        for chunk in _chunk_text(text):
            try:
                await _wa_client.send_message(to=wa_phone, text=chunk)
            except Exception as exc:
                logger.warning("[whatsapp] send_room_notification failed for %s: %s", wa_phone, exc)


# ── Registration (called from main.py) ───────────────────────────────────────

def register_whatsapp_bridge(app: Any, get_db: Callable[[], Any]) -> None:
    """
    Mount the WhatsApp webhook on the FastAPI app and register message handlers.

    Must be called AFTER app = FastAPI(...) and BEFORE uvicorn starts.
    Idempotent — safe to call even if WHATSAPP_ENABLED is false or creds are missing.
    """
    if not (_wa_enabled() and _wa_phone_id() and _wa_token()):
        logger.info("[whatsapp] Bridge disabled or not configured")
        return

    try:
        from pywa_async import WhatsApp, filters, types  # type: ignore[import]
    except ImportError:
        logger.warning("[whatsapp] pywa not installed — bridge disabled")
        return

    global _wa_client

    kwargs: dict[str, Any] = {
        "phone_id": _wa_phone_id(),
        "token": _wa_token(),
        "server": app,
        "verify_token": _wa_verify_token(),
        "filter_updates": True,
    }
    if _wa_app_id() and _wa_app_secret() and _wa_public_url():
        kwargs["app_id"] = int(_wa_app_id())
        kwargs["app_secret"] = _wa_app_secret()
        kwargs["callback_url"] = _wa_public_url() + "/"

    wa = WhatsApp(**kwargs)
    _wa_client = wa

    def _get_db() -> Any:
        return next(get_db())

    @wa.on_message(filters.text)
    async def on_text_message(client: WhatsApp, msg: types.Message) -> None:  # type: ignore[name-defined]
        wa_phone = str(msg.from_user.wa_id)
        text = (msg.text or "").strip()

        # Allowlist check
        if _wa_allowed_phones() and wa_phone not in _wa_allowed_phones():
            await client.send_message(
                to=wa_phone,
                text="This WhatsApp number is not authorised to use Sparkbot.",
            )
            return

        if not text:
            await client.send_message(to=wa_phone, text="I can only process text messages.")
            return

        display_name = getattr(msg.from_user, "name", None) or wa_phone
        lower = text.lower()

        db = _get_db()
        try:
            link = _ensure_linked_room(db, wa_phone, display_name)

            if lower in {"hi", "hello", "/start", "/help", "help"}:
                await client.send_message(to=wa_phone, text=_help_text())
                return

            if lower in {"deny", "cancel", "/deny", "/cancel"}:
                if not link.pending_confirm_id:
                    await client.send_message(to=wa_phone, text="There is no pending approval to cancel.")
                    return
                from app.api.routes.chat.llm import discard_pending

                discard_pending(link.pending_confirm_id)
                _clear_pending_confirmation(wa_phone)
                await client.send_message(to=wa_phone, text="Pending action cancelled.")
                return

            if lower in {"approve", "/approve"}:
                if not link.pending_confirm_id:
                    await client.send_message(to=wa_phone, text="There is no pending approval right now.")
                    return
                result = await _execute_pending_confirmation(
                    db, link.room_id, link.user_id, link.pending_confirm_id,
                    wa_phone=wa_phone,
                )
                for chunk in _chunk_text(result):
                    await client.send_message(to=wa_phone, text=chunk)
                return

            # Normal message
            result = await _run_room_prompt(db, link.room_id, link.user_id, text, wa_phone=wa_phone)
            for chunk in _chunk_text(str(result.get("text", ""))):
                await client.send_message(to=wa_phone, text=chunk)

        except Exception:
            logger.exception("[whatsapp] Error handling message from %s", wa_phone)
            await client.send_message(
                to=wa_phone,
                text="Sorry, I encountered an error processing your message.",
            )
        finally:
            db.close()

    _init_store()
    logger.info("[whatsapp] Bridge registered on /whatsapp (verify_token=%s...)", _wa_verify_token()[:6])
