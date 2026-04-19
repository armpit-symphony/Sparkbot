"""
Sparkbot skill: proactive_alerts

Push notifications to Telegram, Discord, or both — designed for Task Guardian jobs.
Set up a scheduled job to check something (email, price, calendar) and call send_alert
to push the result to your phone even when you're away from the desktop.

Tools:
  send_alert(message, channel="auto", priority="normal")

Env vars (at least one required):
  TELEGRAM_BOT_TOKEN        — your bot token from @BotFather
  TELEGRAM_CHAT_ID          — your personal chat ID (run /start with the bot, check /api/getUpdates)
  DISCORD_WEBHOOK_URL       — Discord channel webhook URL
  SPARKBOT_ALERT_CHANNEL    — default channel: "telegram", "discord", "both" (default: "auto")
"""
from __future__ import annotations

import os

import httpx

def _cfg() -> tuple[str, str, str, str]:
    return (
        os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        os.getenv("DISCORD_WEBHOOK_URL", "").strip(),
        os.getenv("SPARKBOT_ALERT_CHANNEL", "auto").strip().lower(),
    )

DEFINITION = {
    "type": "function",
    "function": {
        "name": "send_alert",
        "description": (
            "Send a push notification to Telegram or Discord. "
            "Use this inside Task Guardian scheduled jobs to notify the user proactively — "
            "e.g. 'price dropped', 'urgent email arrived', 'reminder fires in 30 min', "
            "'morning briefing', 'daily digest'. "
            "Works even when the user is not at their computer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The notification text. Markdown supported for Telegram.",
                },
                "channel": {
                    "type": "string",
                    "description": "'telegram', 'discord', 'both', or 'auto' (uses whichever is configured, default).",
                },
                "priority": {
                    "type": "string",
                    "description": "'normal' or 'high' — high adds 🚨 prefix and disables Telegram silent mode.",
                },
            },
            "required": ["message"],
        },
    },
}

POLICY = {
    "scope": "write",
    "resource": "external",
    "default_action": "allow",
    "action_type": "notify",
    "high_risk": False,
    "requires_execution_gate": False,
}


async def _send_telegram(text: str, silent: bool, token: str, chat_id: str) -> str:
    if not token or not chat_id:
        return "Telegram not configured (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID missing)."
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_notification": silent,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, json=payload)
    if r.status_code == 200:
        return "Telegram: sent ✓"
    return f"Telegram error {r.status_code}: {r.text[:200]}"


async def _send_discord(text: str, hook: str) -> str:
    if not hook:
        return "Discord not configured (DISCORD_WEBHOOK_URL missing)."
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(hook, json={"content": text})
    if r.status_code in (200, 204):
        return "Discord: sent ✓"
    return f"Discord error {r.status_code}: {r.text[:200]}"


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    message = (args.get("message") or "").strip()
    if not message:
        return "Error: message is required."

    tg_token, tg_chat, discord_hook, default_chan = _cfg()

    channel = (args.get("channel") or default_chan or "auto").strip().lower()
    priority = (args.get("priority") or "normal").strip().lower()
    high = priority == "high"
    text = f"🚨 {message}" if high else message
    silent = not high

    if channel == "auto":
        channel = "both" if (tg_token and discord_hook) else ("telegram" if tg_token else "discord")

    results: list[str] = []
    if channel in ("telegram", "both"):
        results.append(await _send_telegram(text, silent, tg_token, tg_chat))
    if channel in ("discord", "both"):
        results.append(await _send_discord(text, discord_hook))
    if not results:
        return "No alert channel configured. Set TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID or DISCORD_WEBHOOK_URL."
    return "\n".join(results)
