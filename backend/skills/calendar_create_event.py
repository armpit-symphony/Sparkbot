"""
Sparkbot skill: calendar_create_event

Creates a new event on Google Calendar.
Reuses the same GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN env vars.

This skill has POLICY default_action="confirm" so the user is always shown
a confirmation modal before Sparkbot writes to their calendar.
"""
import os
import time

import httpx

_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
_GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary"
_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

_TOKEN_CACHE: dict = {"access_token": "", "expires_at": 0.0}

DEFINITION = {
    "type": "function",
    "function": {
        "name": "calendar_create_event",
        "description": (
            "Create a new event on the user's Google Calendar. "
            "Use when the user asks to schedule something, add a meeting, block time, "
            "or set up a reminder with a specific date and time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Event title / name",
                },
                "start_time": {
                    "type": "string",
                    "description": (
                        "Start time in ISO 8601 format with timezone offset, "
                        "e.g. 2026-03-10T14:00:00-05:00"
                    ),
                },
                "end_time": {
                    "type": "string",
                    "description": (
                        "End time in ISO 8601 format with timezone offset, "
                        "e.g. 2026-03-10T15:00:00-05:00"
                    ),
                },
                "description": {
                    "type": "string",
                    "description": "Event notes or agenda (optional)",
                },
                "location": {
                    "type": "string",
                    "description": "Physical or virtual location (optional)",
                },
                "attendees": {
                    "type": "string",
                    "description": "Comma-separated attendee email addresses (optional)",
                },
            },
            "required": ["summary", "start_time", "end_time"],
        },
    },
}

POLICY = {
    "scope": "write",
    "resource": "calendar",
    "default_action": "confirm",
    "action_type": "write_external",
    "high_risk": False,
    "requires_execution_gate": True,
}


async def _get_token() -> tuple:
    if not (_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET and _GOOGLE_REFRESH_TOKEN):
        return None, (
            "Google Calendar not configured. "
            "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
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
            return None, "Google OAuth error: access_token missing."
        _TOKEN_CACHE["access_token"] = token
        _TOKEN_CACHE["expires_at"] = time.time() + int(data.get("expires_in", 3600))
        return token, None
    except Exception as exc:
        return None, f"Google OAuth error: {exc}"


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    summary = (args.get("summary") or "").strip()
    start_time = (args.get("start_time") or "").strip()
    end_time = (args.get("end_time") or "").strip()
    description = (args.get("description") or "").strip()
    location = (args.get("location") or "").strip()
    attendees_raw = (args.get("attendees") or "").strip()

    if not summary or not start_time or not end_time:
        return "Error: summary, start_time, and end_time are all required."

    token, err = await _get_token()
    if err:
        return err

    event_body: dict = {
        "summary": summary,
        "start": {"dateTime": start_time},
        "end": {"dateTime": end_time},
    }
    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location
    if attendees_raw:
        emails = [e.strip() for e in attendees_raw.split(",") if e.strip()]
        event_body["attendees"] = [{"email": e} for e in emails]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_CALENDAR_API}/calendars/{_CALENDAR_ID}/events",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=event_body,
            )
        if resp.status_code not in (200, 201):
            return f"Google Calendar API error ({resp.status_code}): {resp.text[:300]}"

        ev = resp.json()
        html_link = ev.get("htmlLink", "")
        link_str = f"\n🔗 {html_link}" if html_link else ""
        return f"✅ Event created: **{summary}** ({start_time} → {end_time}){link_str}"

    except Exception as exc:
        return f"Calendar error: {exc}"
