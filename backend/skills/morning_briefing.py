"""
Sparkbot skill: morning_briefing

Compiles a personalized morning digest in one shot:
  • Today's date + optional weather
  • Google Calendar events (today + tomorrow by default)
  • Gmail unread inbox summary
  • Pending reminders for this room

No extra API keys beyond the existing GOOGLE_* OAuth vars.
All operations are read-only — policy: read/allow.

Perfect for a recurring Task Guardian job:
  guardian_schedule_task(
      name="Morning Brief",
      tool_name="morning_briefing",
      schedule="every:86400",         # daily
      tool_args={"timezone": "America/New_York", "location": "New York"}
  )

Optional env vars:
  GOOGLE_CALENDAR_ID  — calendar to query (default: primary)
  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN — standard OAuth
"""
from __future__ import annotations

import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import httpx

# ── Google OAuth (shared pattern) ────────────────────────────────────────────

_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
_GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary"
_GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
_TOKEN_CACHE: dict = {"access_token": "", "expires_at": 0.0}

DEFINITION = {
    "type": "function",
    "function": {
        "name": "morning_briefing",
        "description": (
            "Generate a fully personalized morning digest: date/time, weather, calendar events, "
            "unread Gmail or Outlook summary, news headlines, stock prices, and pending reminders. "
            "Use when the user asks for a morning brief, daily summary, 'what do I have today', "
            "or schedules a daily morning digest job. "
            "All sections are individually toggleable. Returns a formatted markdown summary."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone e.g. 'America/New_York'. Default: UTC.",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "Calendar look-ahead in days (1=today only, 2=today+tomorrow, default 2)",
                },
                "max_emails": {
                    "type": "integer",
                    "description": "Number of unread emails to summarize (1–10, default 5)",
                },
                "include_weather": {
                    "type": "boolean",
                    "description": "Include current weather (default false)",
                },
                "location": {
                    "type": "string",
                    "description": "City for weather, e.g. 'New York'",
                },
                "include_news": {
                    "type": "boolean",
                    "description": "Include top news headlines (default false)",
                },
                "news_topic": {
                    "type": "string",
                    "description": "News topic: technology, world, business, science, sports, health (default: technology)",
                },
                "include_stocks": {
                    "type": "boolean",
                    "description": "Include stock prices (default false)",
                },
                "stock_symbols": {
                    "type": "string",
                    "description": "Comma/space-separated ticker symbols e.g. 'AAPL MSFT TSLA'",
                },
            },
            "required": [],
        },
    },
}

POLICY = {
    "scope": "read",
    "resource": "workspace",
    "default_action": "allow",
    "action_type": "read",
    "high_risk": False,
    "requires_execution_gate": False,
}


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _get_google_token() -> tuple[str | None, str | None]:
    if not (_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET and _GOOGLE_REFRESH_TOKEN):
        return None, None  # Google not configured — skip those sections silently
    cached = str(_TOKEN_CACHE.get("access_token") or "")
    expires = float(_TOKEN_CACHE.get("expires_at") or 0.0)
    if cached and time.time() < expires - 60:
        return cached, None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": _GOOGLE_CLIENT_ID,
                    "client_secret": _GOOGLE_CLIENT_SECRET,
                    "refresh_token": _GOOGLE_REFRESH_TOKEN,
                    "grant_type": "refresh_token",
                },
            )
        if resp.status_code != 200:
            return None, f"Google OAuth error: {resp.text[:200]}"
        data = resp.json()
        token = data.get("access_token")
        if not token:
            return None, "Google OAuth: access_token missing."
        _TOKEN_CACHE["access_token"] = token
        _TOKEN_CACHE["expires_at"] = time.time() + int(data.get("expires_in", 3600))
        return token, None
    except Exception as exc:
        return None, f"Google OAuth error: {exc}"


# ── Section fetchers ──────────────────────────────────────────────────────────

async def _fetch_calendar(token: str, days_ahead: int, tz_name: str) -> str:
    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_CALENDAR_API}/calendars/{_CALENDAR_ID}/events",
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "timeMin": time_min,
                    "timeMax": time_max,
                    "maxResults": 10,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                },
            )
        if resp.status_code != 200:
            return f"_(Calendar unavailable: {resp.status_code})_"
        events = resp.json().get("items", [])
        if not events:
            label = "today" if days_ahead == 1 else f"the next {days_ahead} days"
            return f"_(No calendar events for {label})_"
        lines = []
        for ev in events:
            summary = ev.get("summary", "(No title)")
            start = ev.get("start", {})
            start_str = start.get("dateTime") or start.get("date") or "?"
            try:
                if "T" in start_str:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    start_str = dt.strftime("%-I:%M %p")
            except Exception:
                pass
            loc = ev.get("location", "")
            loc_str = f" @ {loc}" if loc else ""
            lines.append(f"  • {start_str} — {summary}{loc_str}")
        return "\n".join(lines)
    except Exception as exc:
        return f"_(Calendar error: {exc})_"


async def _fetch_gmail(token: str, max_emails: int) -> str:
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # List unread messages
            list_resp = await client.get(
                f"{_GMAIL_API}/users/me/messages",
                headers={"Authorization": f"Bearer {token}"},
                params={"q": "is:unread", "maxResults": max_emails},
            )
            if list_resp.status_code != 200:
                return f"_(Gmail unavailable: {list_resp.status_code})_"
            messages = list_resp.json().get("messages", [])
            if not messages:
                return "  _(Inbox is clear — no unread messages)_"

            lines = []
            for msg in messages[:max_emails]:
                detail = await client.get(
                    f"{_GMAIL_API}/users/me/messages/{msg['id']}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
                )
                if detail.status_code != 200:
                    continue
                headers = {
                    h["name"].lower(): h["value"]
                    for h in detail.json().get("payload", {}).get("headers", [])
                }
                sender = headers.get("from", "?")
                # Shorten "Name <email@domain>" → "Name"
                if "<" in sender:
                    sender = sender.split("<")[0].strip().strip('"')
                subject = headers.get("subject", "(no subject)")
                lines.append(f"  • **{subject}** — from {sender}")

            total = list_resp.json().get("resultSizeEstimate", len(messages))
            header = f"  ({total} unread)" if total > max_emails else ""
            return (header + "\n" if header else "") + "\n".join(lines)
    except Exception as exc:
        return f"_(Gmail error: {exc})_"


async def _fetch_reminders(room_id: str | None, session) -> str:
    if not room_id or session is None:
        return "  _(Reminders unavailable — no room context)_"
    try:
        import uuid as _uuid_mod
        from app.crud import get_room_reminders
        from app.models import ReminderStatus

        reminders = get_room_reminders(session, _uuid_mod.UUID(room_id), status=ReminderStatus.PENDING)
        if not reminders:
            return "  _(No pending reminders)_"
        lines = []
        for r in reminders[:8]:
            fire_at = r.fire_at
            if hasattr(fire_at, "strftime"):
                ts = fire_at.strftime("%a %b %-d %-I:%M %p")
            else:
                ts = str(fire_at)
            rec = r.recurrence.value if hasattr(r.recurrence, "value") else str(r.recurrence)
            rec_str = f" ({rec})" if rec != "once" else ""
            lines.append(f"  • {ts}{rec_str} — {r.message}")
        return "\n".join(lines)
    except Exception as exc:
        return f"  _(Reminders error: {exc})_"


async def _fetch_weather(location: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                f"https://wttr.in/{location}",
                params={"format": "j1"},
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            d = r.json()["current_condition"][0]
            desc = d["weatherDesc"][0]["value"]
            return f"  {desc}, {d['temp_C']}°C / {d['temp_F']}°F (feels {d['FeelsLikeC']}°C)"
    except Exception as exc:
        return f"  _(Weather unavailable: {exc})_"


# ── Main entry point ──────────────────────────────────────────────────────────

async def _fetch_news(topic: str, count: int = 5) -> str:
    try:
        import xml.etree.ElementTree as ET
        _BBC = {
            "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
            "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
            "science": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
            "sports": "https://feeds.bbci.co.uk/sport/rss.xml",
            "health": "https://feeds.bbci.co.uk/news/health/rss.xml",
        }
        if topic in ("technology", "tech"):
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get("https://hacker-news.firebaseio.com/v1/topstories.json")
                ids = r.json()[:count]
                items = []
                for sid in ids:
                    sr = await client.get(f"https://hacker-news.firebaseio.com/v1/item/{sid}.json")
                    d = sr.json()
                    items.append(f"  • [{d.get('title','')}]({d.get('url', f'https://news.ycombinator.com/item?id={sid}')})")
            return "\n".join(items)
        feed_url = _BBC.get(topic, _BBC["world"])
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(feed_url, headers={"User-Agent": "Sparkbot/1.0"})
        root = ET.fromstring(r.text)
        items_xml = root.findall(".//item")[:count]
        lines = []
        for item in items_xml:
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            lines.append(f"  • [{title}]({link})" if link else f"  • {title}")
        return "\n".join(lines)
    except Exception as exc:
        return f"  _(News unavailable: {exc})_"


async def _fetch_stocks(symbols_str: str) -> str:
    symbols = [s.strip().upper() for s in symbols_str.replace(",", " ").split() if s.strip()]
    if not symbols:
        return "  _(No symbols configured)_"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": ",".join(symbols), "fields": "regularMarketPrice,regularMarketChangePercent,shortName"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
        quotes = r.json().get("quoteResponse", {}).get("result", [])
        lines = []
        for q in quotes:
            price = q.get("regularMarketPrice", 0)
            pct   = q.get("regularMarketChangePercent", 0)
            arrow = "▲" if pct >= 0 else "▼"
            lines.append(f"  • **{q['symbol']}** {price:.2f}  {arrow} {pct:+.2f}%")
        return "\n".join(lines) if lines else "  _(No quote data)_"
    except Exception as exc:
        return f"  _(Stocks unavailable: {exc})_"


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    days_ahead     = max(1, min(int(args.get("days_ahead") or 2), 7))
    max_emails     = max(1, min(int(args.get("max_emails") or 5), 10))
    include_weather = bool(args.get("include_weather"))
    include_news   = bool(args.get("include_news"))
    include_stocks = bool(args.get("include_stocks"))
    location       = (args.get("location") or "").strip()
    tz_name        = (args.get("timezone") or "UTC").strip()
    news_topic     = (args.get("news_topic") or "technology").strip().lower()
    stock_symbols  = (args.get("stock_symbols") or "").strip()

    now_utc = datetime.now(timezone.utc)
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(tz_name)
        now_local = now_utc.astimezone(tz)
        date_str = now_local.strftime("%A, %B %-d %Y")
        time_str = now_local.strftime("%-I:%M %p %Z")
    except Exception:
        date_str = now_utc.strftime("%A, %B %-d %Y")
        time_str = now_utc.strftime("%-I:%M %p UTC")

    sections: list[str] = [f"# ☀️ Good morning! — {date_str}", f"*{time_str}*", ""]

    # Weather
    if include_weather and location:
        sections.append("## 🌤 Weather")
        sections.append(await _fetch_weather(location))
        sections.append("")

    # Stocks
    if include_stocks and stock_symbols:
        sections.append("## 📈 Markets")
        sections.append(await _fetch_stocks(stock_symbols))
        sections.append("")

    # Google sections
    token, _err = await _get_google_token()

    # Calendar
    sections.append("## 📅 Calendar")
    if token:
        sections.append(await _fetch_calendar(token, days_ahead, tz_name))
    else:
        sections.append("  _(Google Calendar not configured)_")
    sections.append("")

    # Gmail
    sections.append("## 📬 Unread Email")
    if token:
        sections.append(await _fetch_gmail(token, max_emails))
    else:
        sections.append("  _(Gmail not configured)_")
    sections.append("")

    # Reminders
    sections.append("## ⏰ Reminders")
    sections.append(await _fetch_reminders(room_id, session))
    sections.append("")

    # News
    if include_news:
        sections.append(f"## 📰 News — {news_topic.title()}")
        sections.append(await _fetch_news(news_topic))
        sections.append("")

    sections.append("---")
    sections.append("_Have a productive day!_")

    return "\n".join(sections)
