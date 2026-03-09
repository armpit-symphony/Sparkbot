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

router = APIRouter(tags=["slack"])

_SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
_SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "").strip()
_SLACK_API = "https://slack.com/api"

# In-memory dedup cache: event_id → unix timestamp
_seen_events: dict[str, float] = {}
_DEDUP_TTL = 300.0  # 5 minutes


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack HMAC-SHA256 request signature."""
    if not _SLACK_SIGNING_SECRET:
        return True  # dev: skip verification when secret is not set
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


async def _handle_slack_event(text: str, channel: str, thread_ts: Optional[str]) -> None:
    """Process a Slack message through the Sparkbot LLM and reply to Slack."""
    from app.api.routes.chat.llm import SYSTEM_PROMPT, stream_chat_with_tools

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    tokens: list[str] = []
    try:
        async for event in stream_chat_with_tools(messages):
            if event.get("type") == "token":
                tokens.append(event["token"])
    except Exception as exc:
        await _slack_reply(channel, f"⚠️ Sparkbot error: {exc}", thread_ts)
        return

    response = "".join(tokens).strip()
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
        raw_text = event.get("text", "")
        # Strip all <@MENTIONS> from the message
        text = re.sub(r"<@[A-Z0-9]+>", "", raw_text).strip()

        if not text or not channel:
            return {"ok": True}

        # Thread reply keeps Slack channels tidy
        thread_ts = event.get("thread_ts") or event.get("ts")

        if etype == "app_mention":
            background_tasks.add_task(_handle_slack_event, text, channel, thread_ts)
        elif etype == "message" and event.get("channel_type") == "im":
            # DMs: no threading needed
            background_tasks.add_task(_handle_slack_event, text, channel, None)

    return {"ok": True}
