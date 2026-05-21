"""
Slack integration — inbound Events API webhook.

Inbound flow:
  POST /api/v1/chat/slack/events  ← Slack sends events here
    • URL verification challenge (one-time during app setup)
    • app_mention  → process text through Sparkbot LLM → reply to Slack thread
    • message (DM) → same, but no threading

Outbound tools (slack_send_message, slack_list_channels, slack_get_channel_history)
are registered in tools.py and available to the LLM in normal chat.

Setup:
  1. Create a Slack App at api.slack.com/apps
  2. Add Bot Token Scopes: chat:write, channels:read, channels:history, im:history
  3. Enable Events: app_mention + message.im
  4. Set Request URL to https://your-domain.example/api/v1/chat/slack/events
  5. Set env vars: SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET
"""
import hashlib
import hmac
import json
import os
import re
import time
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Request, Response
from sqlmodel import Session, select

router = APIRouter(tags=["slack"])

_SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
_SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "").strip()
_SLACK_API = "https://slack.com/api"

# In-memory dedup cache: event_id → unix timestamp
_seen_events: dict[str, float] = {}
_DEDUP_TTL = 300.0  # 5 minutes
_SLACK_MEMORY_ROOM_NAME = "Slack Bridge"


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack HMAC-SHA256 request signature. Public webhooks fail closed."""
    if not _SLACK_SIGNING_SECRET:
        return False
    try:
        if abs(time.time() - int(timestamp)) > 300:
            return False
        base = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected = "v0=" + hmac.new(
            _SLACK_SIGNING_SECRET.encode(), base.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
    except Exception:
        return False


async def _slack_reply(channel: str, text: str, thread_ts: Optional[str]) -> None:
    """Post a message to Slack (fire-and-forget)."""
    if not _SLACK_BOT_TOKEN:
        return
    payload: dict = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{_SLACK_API}/chat.postMessage",
                headers={"Authorization": f"Bearer {_SLACK_BOT_TOKEN}", "Content-Type": "application/json"},
                json=payload,
            )
    except Exception:
        pass  # best-effort


def _allowed_slack_channel_ids() -> set[str]:
    return {part.strip() for part in os.getenv("SLACK_ALLOWED_CHANNEL_IDS", "").split(",") if part.strip()}


def _allowed_slack_user_ids() -> set[str]:
    return {part.strip() for part in os.getenv("SLACK_ALLOWED_USER_IDS", "").split(",") if part.strip()}


def _slack_identity_setup_message() -> str:
    return (
        "Sparkbot Slack memory recall is not linked for this channel yet. "
        "Use Main Chat or configure SLACK_SIGNING_SECRET, SLACK_ALLOWED_CHANNEL_IDS, "
        "SLACK_ALLOWED_USER_IDS, and SPARKBOT_SLACK_OWNER_USERNAME for a real Sparkbot operator account."
    )


def _slack_identity_authorized(channel: str, slack_user_id: str) -> bool:
    allowed_channels = _allowed_slack_channel_ids()
    allowed_users = _allowed_slack_user_ids()
    return bool(
        channel
        and slack_user_id
        and allowed_channels
        and allowed_users
        and channel in allowed_channels
        and slack_user_id in allowed_users
    )


def _get_slack_memory_context(session: Session) -> tuple[str, str] | None:
    from app.models import ChatRoom, ChatRoomMember, ChatUser, RoomRole

    owner_username = os.getenv("SPARKBOT_SLACK_OWNER_USERNAME", "").strip()
    if not owner_username:
        return None
    owner = session.exec(select(ChatUser).where(ChatUser.username == owner_username)).first()
    if not owner:
        return None

    room = session.exec(select(ChatRoom).where(ChatRoom.name == _SLACK_MEMORY_ROOM_NAME)).first()
    if not room:
        room = ChatRoom(
            name=_SLACK_MEMORY_ROOM_NAME,
            description="Slack connector memory room for an explicitly linked Sparkbot operator.",
            created_by=owner.id,
        )
        session.add(room)
        session.commit()
        session.refresh(room)

    membership = session.exec(
        select(ChatRoomMember).where(ChatRoomMember.room_id == room.id).where(ChatRoomMember.user_id == owner.id)
    ).first()
    if not membership:
        session.add(ChatRoomMember(room_id=room.id, user_id=owner.id, role=RoomRole.OWNER))
        session.commit()

    return str(owner.id), str(room.id)


async def _handle_slack_event(text: str, channel: str, thread_ts: Optional[str], slack_user_id: str) -> None:
    """Process a Slack message through the Sparkbot LLM and reply to Slack."""
    from app.api.routes.chat.llm import SYSTEM_PROMPT, stream_chat_with_tools
    from app.api.deps import get_db
    from app.services.guardian import memory as guardian_memory

    if not _slack_identity_authorized(channel, slack_user_id):
        await _slack_reply(channel, _slack_identity_setup_message(), thread_ts)
        return

    db_gen = get_db()
    db = next(db_gen)
    context = _get_slack_memory_context(db)
    if context is None:
        db_gen.close()
        await _slack_reply(channel, _slack_identity_setup_message(), thread_ts)
        return
    user_id, room_id = context

    from app.services import connector_verification

    if connector_verification.is_logout_command(text):
        connector_verification.close_connector_session(connector="slack", external_identity=slack_user_id, channel_id=channel)
        db_gen.close()
        await _slack_reply(channel, connector_verification.verification_closed_message(), thread_ts)
        return

    connector_pin = connector_verification.parse_pin_command(text)
    if connector_pin:
        verified = connector_verification.verify_connector_pin(
            connector="slack",
            external_identity=slack_user_id,
            channel_id=channel,
            submitted_pin=connector_pin,
            linked_sparkbot_user_id=user_id,
        )
        db_gen.close()
        await _slack_reply(
            channel,
            connector_verification.verification_success_message(verified)
            if verified
            else "Operator verification failed. Private meeting memory remains locked.",
            thread_ts,
        )
        return

    try:
        guardian_memory.remember_context_event(
            user_id=user_id,
            room_id=room_id,
            source_type="slack",
            actor_label="user",
            role="user",
            content_summary=text,
            metadata={"slack_channel": channel, "slack_thread_ts": thread_ts or "", "slack_user_id": slack_user_id},
        )
    except Exception:
        pass
    try:
        context_user_id = user_id
        if connector_verification.private_recall_requested(text):
            allowed, verified_user_id, _reason = connector_verification.private_recall_gate(
                db,
                connector="slack",
                external_identity=slack_user_id,
                channel_id=channel,
                current_user_id=user_id,
                linked_operator_identity=True,
            )
            if not allowed:
                db_gen.close()
                await _slack_reply(channel, connector_verification.verification_required_message("Slack"), thread_ts)
                return
            context_user_id = verified_user_id or user_id
        memory_context = guardian_memory.build_unified_context(
            user_id=context_user_id,
            room_id=room_id,
            query=text,
        )
    except Exception:
        memory_context = ""
    system_prompt = SYSTEM_PROMPT
    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    tokens: list[str] = []
    try:
        async for event in stream_chat_with_tools(
            messages,
            user_id=user_id,
            db_session=db,
            room_id=room_id,
            agent_name="slack",
            room_execution_allowed=False,
        ):
            if event.get("type") == "token":
                tokens.append(event["token"])
    except Exception as exc:
        db_gen.close()
        await _slack_reply(channel, f"⚠️ Sparkbot error: {exc}", thread_ts)
        return

    response = "".join(tokens).strip()
    try:
        if response:
            guardian_memory.remember_context_event(
                user_id=user_id,
                room_id=room_id,
                source_type="slack",
                actor_label="sparkbot",
                role="assistant",
                content_summary=response,
                metadata={"slack_channel": channel, "slack_thread_ts": thread_ts or "", "slack_user_id": slack_user_id},
            )
    except Exception:
        pass
    db_gen.close()
    if response:
        await _slack_reply(channel, response, thread_ts)


@router.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    """
    Slack Events API webhook.

    Responds immediately (required within 3s), processes LLM call in background.
    """
    body = await request.body()

    # Verify Slack signature
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_slack_signature(body, timestamp, signature):
        return Response(status_code=403, content="Invalid Slack signature")

    # Ignore Slack retries (Slack retries if we don't respond in 3s — we already did)
    if request.headers.get("X-Slack-Retry-Num"):
        return {"ok": True}

    try:
        data = json.loads(body)
    except Exception:
        return Response(status_code=400, content="Invalid JSON")

    # ── One-time URL verification (during Slack app setup) ────────────────────
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge", "")}

    # ── Event callbacks ───────────────────────────────────────────────────────
    if data.get("type") == "event_callback":
        event_id = data.get("event_id", "")
        now = time.time()

        # Dedup: skip already-processed events
        if event_id and event_id in _seen_events:
            return {"ok": True}
        if event_id:
            _seen_events[event_id] = now

        # Prune stale entries
        stale = [k for k, v in _seen_events.items() if now - v > _DEDUP_TTL]
        for k in stale:
            del _seen_events[k]

        event = data.get("event", {})
        etype = event.get("type", "")

        # Skip bot messages to avoid reply loops
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return {"ok": True}

        channel = event.get("channel", "")
        slack_user_id = event.get("user", "")
        raw_text = event.get("text", "")
        # Strip all <@MENTIONS> from the message
        text = re.sub(r"<@[A-Z0-9]+>", "", raw_text).strip()

        if not text or not channel or not slack_user_id:
            return {"ok": True}

        # Thread reply keeps Slack channels tidy
        thread_ts = event.get("thread_ts") or event.get("ts")

        if etype == "app_mention":
            background_tasks.add_task(_handle_slack_event, text, channel, thread_ts, slack_user_id)
        elif etype == "message" and event.get("channel_type") == "im":
            # DMs: no threading needed
            background_tasks.add_task(_handle_slack_event, text, channel, None, slack_user_id)

    return {"ok": True}
