"""
Sparkbot skill: calendar_list_events

Lists upcoming events from Google Calendar.
Reuses the same GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN env vars
as the Gmail and Drive tools. No extra packages needed — pure httpx.

Optional:
  GOOGLE_CALENDAR_ID  — calendar to query (default: "primary")
"""
import os
import time

import httpx

_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
_GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

# Module-level token cache (refreshed automatically before expiry)
_TOKEN_CACHE: dict = {"access_token": "", "expires_at": 0.0}

DEFINITION = {
    "type": "function",
    "function": {
        "name": "calendar_list_events",
        "description": (
            "List upcoming events from the user's Google Calendar. "
            "Use for questions like 'what's on my calendar', 'do I have meetings today', "
            "'what's my schedule this week', or 'am I free on Friday'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of events to return (1–20, default 10)",
                },
                "days_ahead": {
                    "type": "integer",
                    "description": "How many days ahead to look (1–30, default 7)",
                },
            },
            "required": [],
        },
    },
}

POLICY = {
    "scope": "read",
    "resource": "calendar",
    "default_action": "allow",
    "action_type": "read",
    "high_risk": False,
    "requires_execution_gate": False,
}


async def _get_token() -> tuple:
    if not (_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET and _GOOGLE_REFRESH_TOKEN):
        return None, (
            "Google Calendar not configured. "
            "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN "
            "(same credentials used for Gmail)."
        )
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
            return None, "Google OAuth error: access_token missing in response."
        _TOKEN_CACHE["access_token"] = token
        _TOKEN_CACHE["expires_at"] = time.time() + int(data.get("expires_in", 3600))
        return token, None
    except Exception as exc:
        return None, f"Google OAuth error: {exc}"


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    from datetime import datetime, timedelta, timezone

    max_results = max(1, min(int(args.get("max_results") or 10), 20))
    days_ahead = max(1, min(int(args.get("days_ahead") or 7), 30))

    token, err = await _get_token()
    if err:
        return err

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
                    "maxResults": max_results,
                    "singleEvents": "true",
                    "orderBy": "startTime",
                },
            )
        if resp.status_code != 200:
            return f"Google Calendar API error ({resp.status_code}): {resp.text[:300]}"

        events = resp.json().get("items", [])
        if not events:
            return f"No events found in the next {days_ahead} day(s)."

        lines = [f"📅 Upcoming events (next {days_ahead} day(s)):"]
        for ev in events:
            summary = ev.get("summary", "(No title)")
            start = ev.get("start", {})
            start_str = start.get("dateTime") or start.get("date") or "?"
            location = ev.get("location", "")
            loc_str = f" @ {location}" if location else ""
            # Pretty-print datetime strings
            try:
                if "T" in start_str:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    start_str = dt.strftime("%a %b %-d at %-I:%M %p %Z").strip()
            except Exception:
                pass
            lines.append(f"• {summary}{loc_str} — {start_str}")
        return "\n".join(lines)

    except Exception as exc:
        return f"Calendar error: {exc}"
