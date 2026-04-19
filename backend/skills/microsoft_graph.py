"""
Sparkbot skill: microsoft_graph

Microsoft 365 integration via Microsoft Graph API.
Covers Outlook mail, Outlook Calendar, and OneDrive.

Tools:
  outlook_read_mail(folder="inbox", limit=10, query="")
  outlook_send_mail(to, subject, body)
  outlook_calendar_list(days=7)
  outlook_calendar_create(subject, start, end, location="", attendees="")
  onedrive_list(path="/")
  onedrive_read(path)

Env vars (register an Azure app at portal.azure.com):
  MICROSOFT_CLIENT_ID      — Azure app client ID
  MICROSOFT_CLIENT_SECRET  — Azure app client secret
  MICROSOFT_TENANT_ID      — Azure tenant ID (use "common" for personal accounts)
  MICROSOFT_REFRESH_TOKEN  — OAuth2 refresh token (get via device-code flow once)

Scopes needed: Mail.Read Mail.Send Calendars.Read Calendars.ReadWrite Files.Read
"""
from __future__ import annotations

import os
import time

import httpx

_CLIENT_ID     = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
_CLIENT_SECRET = os.getenv("MICROSOFT_CLIENT_SECRET", "").strip()
_TENANT_ID     = os.getenv("MICROSOFT_TENANT_ID", "common").strip() or "common"
_REFRESH_TOKEN = os.getenv("MICROSOFT_REFRESH_TOKEN", "").strip()

_GRAPH = "https://graph.microsoft.com/v1.0"
_TOKEN_CACHE: dict = {}


async def _get_token() -> tuple[str | None, str | None]:
    if not (_CLIENT_ID and _CLIENT_SECRET and _REFRESH_TOKEN):
        return None, "Microsoft Graph not configured. Set MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET, MICROSOFT_TENANT_ID, MICROSOFT_REFRESH_TOKEN."
    if _TOKEN_CACHE.get("token") and time.time() < _TOKEN_CACHE.get("expires", 0) - 60:
        return _TOKEN_CACHE["token"], None
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"https://login.microsoftonline.com/{_TENANT_ID}/oauth2/v2.0/token",
            data={
                "client_id": _CLIENT_ID,
                "client_secret": _CLIENT_SECRET,
                "refresh_token": _REFRESH_TOKEN,
                "grant_type": "refresh_token",
                "scope": "https://graph.microsoft.com/.default",
            },
        )
    if r.status_code != 200:
        return None, f"Microsoft auth error {r.status_code}: {r.text[:300]}"
    d = r.json()
    token = d.get("access_token")
    if not token:
        return None, "Microsoft auth: no access_token in response."
    _TOKEN_CACHE["token"] = token
    _TOKEN_CACHE["expires"] = time.time() + int(d.get("expires_in", 3600))
    return token, None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Outlook Mail ───────────────────────────────────────────────────────────────

async def _outlook_read_mail(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    folder = (args.get("folder") or "inbox").strip().lower()
    limit  = max(1, min(int(args.get("limit") or 10), 50))
    query  = (args.get("query") or "").strip()

    url = f"{_GRAPH}/me/mailFolders/{folder}/messages"
    params: dict = {"$top": limit, "$select": "subject,from,receivedDateTime,isRead,bodyPreview", "$orderby": "receivedDateTime desc"}
    if query:
        params["$search"] = f'"{query}"'

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, headers=_headers(token), params=params)
    if r.status_code != 200:
        return f"Outlook error {r.status_code}: {r.text[:300]}"
    messages = r.json().get("value", [])
    if not messages:
        return f"No messages in {folder}."
    lines = [f"**Outlook — {folder.title()} ({len(messages)} messages)**", ""]
    for m in messages:
        sender = m.get("from", {}).get("emailAddress", {})
        read = "" if m.get("isRead") else "🔵 "
        preview = m.get("bodyPreview", "")[:100]
        lines.append(
            f"{read}**{m.get('subject','(no subject)')}**\n"
            f"  From: {sender.get('name','')} <{sender.get('address','')}> · {m.get('receivedDateTime','')[:10]}\n"
            f"  {preview}"
        )
    return "\n\n".join(lines)


async def _outlook_send_mail(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    to      = (args.get("to") or "").strip()
    subject = (args.get("subject") or "").strip()
    body    = (args.get("body") or "").strip()
    if not (to and subject and body):
        return "Error: to, subject, and body are required."

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": a.strip()}} for a in to.split(",")],
        }
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(f"{_GRAPH}/me/sendMail", json=payload, headers=_headers(token))
    if r.status_code in (200, 202):
        return f"✅ Email sent to {to}"
    return f"Outlook send error {r.status_code}: {r.text[:300]}"


# ── Outlook Calendar ───────────────────────────────────────────────────────────

async def _outlook_calendar_list(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    days = max(1, min(int(args.get("days") or 7), 30))
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days)
    params = {
        "startDateTime": now.isoformat(),
        "endDateTime": end.isoformat(),
        "$top": 20,
        "$select": "subject,start,end,location,organizer",
        "$orderby": "start/dateTime",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(f"{_GRAPH}/me/calendarView", headers=_headers(token), params=params)
    if r.status_code != 200:
        return f"Outlook Calendar error {r.status_code}: {r.text[:300]}"
    events = r.json().get("value", [])
    if not events:
        return f"No calendar events in the next {days} days."
    lines = [f"**Outlook Calendar — next {days} days**", ""]
    for ev in events:
        start = ev.get("start", {}).get("dateTime", "")[:16].replace("T", " ")
        loc   = ev.get("location", {}).get("displayName", "")
        loc_str = f" @ {loc}" if loc else ""
        lines.append(f"• {start}{loc_str} — **{ev.get('subject','(no title)')}**")
    return "\n".join(lines)


async def _outlook_calendar_create(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    subject   = (args.get("subject") or "").strip()
    start     = (args.get("start") or "").strip()
    end       = (args.get("end") or "").strip()
    location  = (args.get("location") or "").strip()
    attendees = (args.get("attendees") or "").strip()
    if not (subject and start and end):
        return "Error: subject, start, and end are required (ISO 8601 format)."

    payload: dict = {
        "subject": subject,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
    }
    if location:
        payload["location"] = {"displayName": location}
    if attendees:
        payload["attendees"] = [
            {"emailAddress": {"address": a.strip()}, "type": "required"}
            for a in attendees.split(",")
        ]

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(f"{_GRAPH}/me/events", json=payload, headers=_headers(token))
    if r.status_code in (200, 201):
        ev = r.json()
        return f"✅ Event created: **{ev.get('subject')}** — {ev.get('webLink','')}"
    return f"Outlook Calendar create error {r.status_code}: {r.text[:300]}"


# ── OneDrive ───────────────────────────────────────────────────────────────────

async def _onedrive_list(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    path = (args.get("path") or "/").strip()
    if path in ("/", ""):
        url = f"{_GRAPH}/me/drive/root/children"
    else:
        url = f"{_GRAPH}/me/drive/root:{path}:/children"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url, headers=_headers(token), params={"$top": 50, "$select": "name,size,lastModifiedDateTime,file,folder"})
    if r.status_code != 200:
        return f"OneDrive error {r.status_code}: {r.text[:300]}"
    items = r.json().get("value", [])
    if not items:
        return f"No items at path: {path}"
    lines = [f"**OneDrive — {path}**", ""]
    for item in items:
        is_folder = "folder" in item
        icon = "📁" if is_folder else "📄"
        size = f" ({item['size']//1024} KB)" if not is_folder and "size" in item else ""
        modified = item.get("lastModifiedDateTime","")[:10]
        lines.append(f"{icon} **{item['name']}**{size} — {modified}")
    return "\n".join(lines)


async def _onedrive_read(args: dict, **_) -> str:
    token, err = await _get_token()
    if err:
        return err
    path = (args.get("path") or "").strip()
    if not path:
        return "Error: path is required."
    url = f"{_GRAPH}/me/drive/root:{path}:/content"
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        r = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        return f"OneDrive read error {r.status_code}: {r.text[:300]}"
    content_type = r.headers.get("content-type", "")
    if "text" in content_type or "json" in content_type:
        text = r.text[:8000]
        return f"**{path}** ({len(r.text)} chars):\n\n{text}"
    return f"File at {path} is binary ({len(r.content)} bytes). Download it to view."


DEFINITIONS = [
    {"type": "function", "function": {"name": "outlook_read_mail", "description": "Read Outlook/Microsoft 365 email from inbox or other folders.", "parameters": {"type": "object", "properties": {"folder": {"type": "string", "description": "inbox, sentitems, drafts, deleteditems (default: inbox)"}, "limit": {"type": "integer"}, "query": {"type": "string", "description": "Search query"}}, "required": []}}},
    {"type": "function", "function": {"name": "outlook_send_mail", "description": "Send an email via Outlook/Microsoft 365.", "parameters": {"type": "object", "properties": {"to": {"type": "string", "description": "Recipient email(s), comma-separated"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]}}},
    {"type": "function", "function": {"name": "outlook_calendar_list", "description": "List upcoming Outlook calendar events.", "parameters": {"type": "object", "properties": {"days": {"type": "integer", "description": "Days to look ahead (default 7)"}}, "required": []}}},
    {"type": "function", "function": {"name": "outlook_calendar_create", "description": "Create an Outlook calendar event.", "parameters": {"type": "object", "properties": {"subject": {"type": "string"}, "start": {"type": "string", "description": "ISO 8601 datetime e.g. 2026-05-01T09:00:00"}, "end": {"type": "string"}, "location": {"type": "string"}, "attendees": {"type": "string", "description": "Comma-separated email addresses"}}, "required": ["subject", "start", "end"]}}},
    {"type": "function", "function": {"name": "onedrive_list", "description": "List files and folders in OneDrive.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Folder path (default: root /)"}, }, "required": []}}},
    {"type": "function", "function": {"name": "onedrive_read", "description": "Read the contents of a text file from OneDrive.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path e.g. /Documents/notes.txt"}}, "required": ["path"]}}},
]

POLICIES = {
    "outlook_read_mail":        {"scope": "read",  "resource": "workspace", "default_action": "allow",   "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
    "outlook_send_mail":        {"scope": "write", "resource": "external",  "default_action": "confirm", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "outlook_calendar_list":    {"scope": "read",  "resource": "workspace", "default_action": "allow",   "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
    "outlook_calendar_create":  {"scope": "write", "resource": "workspace", "default_action": "confirm", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "onedrive_list":            {"scope": "read",  "resource": "workspace", "default_action": "allow",   "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
    "onedrive_read":            {"scope": "read",  "resource": "workspace", "default_action": "allow",   "action_type": "read",       "high_risk": False, "requires_execution_gate": False},
}

_EXECUTORS = {
    "outlook_read_mail":       _outlook_read_mail,
    "outlook_send_mail":       _outlook_send_mail,
    "outlook_calendar_list":   _outlook_calendar_list,
    "outlook_calendar_create": _outlook_calendar_create,
    "onedrive_list":           _onedrive_list,
    "onedrive_read":           _onedrive_read,
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["outlook_read_mail"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await _outlook_read_mail(args)


def _wrap(fn):
    async def _e(args: dict, *, user_id=None, room_id=None, session=None) -> str:
        return await fn(args)
    return _e


def _register_extra(registry) -> None:
    for defn in DEFINITIONS:
        name = defn["function"]["name"]
        if name not in registry.executors:
            registry.definitions.append(defn)
            registry.policies[name] = POLICIES[name]
            registry.executors[name] = _wrap(_EXECUTORS[name])
