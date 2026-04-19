"""
Sparkbot skill: apple_integrations

macOS-native integrations via AppleScript (osascript).
Only active on macOS — returns a graceful message on other platforms.

Tools:
  apple_contacts_search(query)              — search macOS Contacts
  apple_reminders_list(list_name="")        — list Reminders
  apple_reminders_create(title, notes="", due_date="", list_name="Reminders")
  apple_notes_search(query)                 — search Notes app
  apple_notes_create(title, body, folder="")

No API keys required — uses the system apps directly.
Requires macOS and appropriate permissions (Contacts, Reminders, Notes) granted to the terminal/app.
"""
from __future__ import annotations

import asyncio
import platform
import subprocess
import sys

_IS_MACOS = platform.system() == "Darwin"


def _run_applescript(script: str) -> str:
    if not _IS_MACOS:
        return "Apple integrations are only available on macOS."
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return f"AppleScript error: {result.stderr.strip()}"
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "AppleScript timed out."
    except FileNotFoundError:
        return "osascript not found — this only works on macOS."
    except Exception as e:
        return f"AppleScript error: {e}"


def _contacts_search_sync(args: dict, **_) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "Error: query is required."
    script = f"""
tell application "Contacts"
    set results to {{}}
    set allPeople to every person whose name contains "{query}" or (email exists and value of emails contains "{query}")
    repeat with p in allPeople
        set pName to name of p
        set pEmail to ""
        set pPhone to ""
        try
            set pEmail to value of first email of p
        end try
        try
            set pPhone to value of first phone of p
        end try
        set end of results to pName & " | " & pEmail & " | " & pPhone
    end repeat
    return results as string
end tell
"""
    output = _run_applescript(script)
    if not output or output.startswith("Apple integrations") or output.startswith("AppleScript"):
        return output or f"No contacts found matching '{query}'."
    lines = [f"**Contacts matching '{query}':**", ""]
    for line in output.split(", "):
        parts = line.split(" | ")
        if len(parts) >= 1 and parts[0].strip():
            name = parts[0].strip()
            email = parts[1].strip() if len(parts) > 1 else ""
            phone = parts[2].strip() if len(parts) > 2 else ""
            lines.append(f"• **{name}**" + (f" — {email}" if email else "") + (f" · {phone}" if phone else ""))
    return "\n".join(lines) if len(lines) > 2 else f"No contacts found matching '{query}'."


def _reminders_list_sync(args: dict, **_) -> str:
    list_name = (args.get("list_name") or "").strip()
    filter_clause = f'whose name is "{list_name}"' if list_name else ""
    script = f"""
tell application "Reminders"
    set output to ""
    set rl to every list {filter_clause}
    repeat with aList in rl
        set listName to name of aList
        set incompleteReminders to every reminder of aList whose completed is false
        repeat with r in incompleteReminders
            set rName to name of r
            set rDue to ""
            try
                set rDue to (due date of r) as string
            end try
            set output to output & listName & " | " & rName & " | " & rDue & linefeed
        end repeat
    end repeat
    return output
end tell
"""
    output = _run_applescript(script)
    if not output or output.startswith("Apple") or not output.strip():
        return "No pending reminders." if not output.startswith("Apple") else output
    lines = [f"**Reminders{' — ' + list_name if list_name else ''}:**", ""]
    for line in output.strip().split("\n"):
        parts = line.split(" | ")
        if len(parts) >= 2:
            lst, name = parts[0], parts[1]
            due = parts[2].strip() if len(parts) > 2 and parts[2].strip() else ""
            lines.append(f"• [{lst}] **{name}**" + (f" — due {due}" if due else ""))
    return "\n".join(lines)


def _reminders_create_sync(args: dict, **_) -> str:
    title     = (args.get("title") or "").strip()
    notes     = (args.get("notes") or "").strip()
    due_date  = (args.get("due_date") or "").strip()
    list_name = (args.get("list_name") or "Reminders").strip()
    if not title:
        return "Error: title is required."
    due_clause = f'set due date of newReminder to date "{due_date}"' if due_date else ""
    notes_clause = f'set body of newReminder to "{notes}"' if notes else ""
    script = f"""
tell application "Reminders"
    set targetList to list "{list_name}"
    set newReminder to make new reminder at end of targetList
    set name of newReminder to "{title}"
    {due_clause}
    {notes_clause}
    return "Created"
end tell
"""
    result = _run_applescript(script)
    if "Created" in result:
        return f"✅ Reminder created: **{title}**" + (f" in {list_name}" if list_name != "Reminders" else "")
    return result


def _notes_search_sync(args: dict, **_) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return "Error: query is required."
    script = f"""
tell application "Notes"
    set results to every note whose name contains "{query}" or body contains "{query}"
    set output to ""
    repeat with n in results
        set output to output & name of n & " | " & (text 1 thru (min of 200 and (length of (body of n))) of (body of n)) & linefeed
    end repeat
    return output
end tell
"""
    output = _run_applescript(script)
    if not output or output.startswith("Apple"):
        return output or f"No notes found matching '{query}'."
    lines = [f"**Notes matching '{query}':**", ""]
    for line in output.strip().split("\n"):
        parts = line.split(" | ", 1)
        if parts:
            title = parts[0].strip()
            preview = parts[1][:150].strip() if len(parts) > 1 else ""
            lines.append(f"• **{title}**\n  _{preview}_")
    return "\n\n".join(lines)


def _notes_create_sync(args: dict, **_) -> str:
    title  = (args.get("title") or "").strip()
    body   = (args.get("body") or "").strip()
    folder = (args.get("folder") or "").strip()
    if not title:
        return "Error: title is required."
    folder_clause = f'set container of newNote to folder "{folder}"' if folder else ""
    script = f"""
tell application "Notes"
    set newNote to make new note
    set name of newNote to "{title}"
    set body of newNote to "{body}"
    {folder_clause}
    return "Created"
end tell
"""
    result = _run_applescript(script)
    if "Created" in result:
        return f"✅ Note created: **{title}**"
    return result


DEFINITIONS = [
    {"type": "function", "function": {"name": "apple_contacts_search", "description": "Search macOS Contacts app by name or email. macOS only.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "apple_reminders_list", "description": "List incomplete reminders from the macOS Reminders app. macOS only.", "parameters": {"type": "object", "properties": {"list_name": {"type": "string", "description": "Optional list name filter"}}, "required": []}}},
    {"type": "function", "function": {"name": "apple_reminders_create", "description": "Create a reminder in the macOS Reminders app. macOS only.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "notes": {"type": "string"}, "due_date": {"type": "string", "description": "e.g. 'April 30, 2026 at 9:00 AM'"}, "list_name": {"type": "string", "description": "Reminders list name (default: Reminders)"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "apple_notes_search", "description": "Search the macOS Notes app by title or content. macOS only.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "apple_notes_create", "description": "Create a note in the macOS Notes app. macOS only.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}, "folder": {"type": "string", "description": "Optional folder name"}}, "required": ["title", "body"]}}},
]

POLICIES = {
    "apple_contacts_search":  {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "apple_reminders_list":   {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "apple_reminders_create": {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
    "apple_notes_search":     {"scope": "read",  "resource": "local_machine", "default_action": "allow", "action_type": "data_read",  "high_risk": False, "requires_execution_gate": False},
    "apple_notes_create":     {"scope": "write", "resource": "local_machine", "default_action": "allow", "action_type": "data_write", "high_risk": False, "requires_execution_gate": False},
}

_SYNC_FNS = {
    "apple_contacts_search":  _contacts_search_sync,
    "apple_reminders_list":   _reminders_list_sync,
    "apple_reminders_create": _reminders_create_sync,
    "apple_notes_search":     _notes_search_sync,
    "apple_notes_create":     _notes_create_sync,
}

DEFINITION = DEFINITIONS[0]
POLICY = POLICIES["apple_contacts_search"]


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return await asyncio.to_thread(_contacts_search_sync, args)


def _make_executor(fn):
    async def _exec(args: dict, *, user_id=None, room_id=None, session=None) -> str:
        return await asyncio.to_thread(fn, args)
    return _exec


def _register_extra(registry) -> None:
    for defn in DEFINITIONS:
        name = defn["function"]["name"]
        if name not in registry.executors:
            registry.definitions.append(defn)
            registry.policies[name] = POLICIES[name]
            registry.executors[name] = _make_executor(_SYNC_FNS[name])
