"""
Sparkbot tool definitions and executors.

Each tool is declared in OpenAI function-calling format (litellm-compatible)
and has a corresponding async executor. Add new tools here — the dispatcher
and LLM definitions are updated automatically.
"""
import ast
import base64
import asyncio
import ipaddress
import json
import operator
import os
import re
import shlex
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote, urlparse, urlunparse

import httpx

from app.services.guardian import get_guardian_suite

# ─── Slack config ─────────────────────────────────────────────────────────────

_SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "").strip()
_SLACK_DEFAULT_CHANNEL = os.getenv("SLACK_DEFAULT_CHANNEL", "").strip()
_SLACK_API = "https://slack.com/api"

# ─── Notion config ────────────────────────────────────────────────────────────

_NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
_NOTION_DEFAULT_PARENT_ID = os.getenv("NOTION_DEFAULT_PARENT_ID", "").strip()
_NOTION_API = "https://api.notion.com/v1"

# ─── Confluence config ────────────────────────────────────────────────────────

_CONFLUENCE_URL = os.getenv("CONFLUENCE_URL", "").strip().rstrip("/")  # e.g. https://myteam.atlassian.net
_CONFLUENCE_USERNAME = os.getenv("CONFLUENCE_USERNAME", "").strip()
_CONFLUENCE_API_TOKEN = os.getenv("CONFLUENCE_API_TOKEN", "").strip()
_CONFLUENCE_DEFAULT_SPACE = os.getenv("CONFLUENCE_DEFAULT_SPACE", "").strip()

# ─── GitHub config ────────────────────────────────────────────────────────────

_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
_GITHUB_DEFAULT_REPO = os.getenv("GITHUB_DEFAULT_REPO", "").strip()  # "owner/repo"
_GITHUB_API = "https://api.github.com"

# ─── Google Workspace config ──────────────────────────────────────────────────

_GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "").strip()
_GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
_GOOGLE_REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN", "").strip()
_GOOGLE_GMAIL_USER = os.getenv("GOOGLE_GMAIL_USER", "me").strip() or "me"
_GOOGLE_DRIVE_SHARED_DRIVE_ID = os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID", "").strip()
_GOOGLE_OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GMAIL_API = "https://gmail.googleapis.com/gmail/v1"
_DRIVE_API = "https://www.googleapis.com/drive/v3"
_GOOGLE_TOKEN_CACHE: dict[str, float | str] = {"access_token": "", "expires_at": 0.0}


def _env_or_vault_value(env_var: str, vault_alias: str, default: str = "") -> str:
    value = os.getenv(env_var, "").strip()
    if value:
        return value
    try:
        return str(
            get_guardian_suite().vault.vault_use(
                alias=vault_alias,
                user_id="tools_runtime",
                operator="system",
            )
            or default
        ).strip()
    except Exception:
        return default.strip()


def _github_token() -> str:
    return _env_or_vault_value("GITHUB_TOKEN", "github_token")


def _github_default_repo() -> str:
    return os.getenv("GITHUB_DEFAULT_REPO", "").strip() or _GITHUB_DEFAULT_REPO


def _google_client_id() -> str:
    return _env_or_vault_value("GOOGLE_CLIENT_ID", "google_client_id")


def _google_client_secret() -> str:
    return _env_or_vault_value("GOOGLE_CLIENT_SECRET", "google_client_secret")


def _google_refresh_token() -> str:
    return _env_or_vault_value("GOOGLE_REFRESH_TOKEN", "google_refresh_token")


def _google_gmail_user() -> str:
    return os.getenv("GOOGLE_GMAIL_USER", "me").strip() or _GOOGLE_GMAIL_USER


def _google_drive_shared_drive_id() -> str:
    return os.getenv("GOOGLE_DRIVE_SHARED_DRIVE_ID", "").strip() or _GOOGLE_DRIVE_SHARED_DRIVE_ID


def _google_calendar_id() -> str:
    return os.getenv("GOOGLE_CALENDAR_ID", "").strip()

# ─── Email config ─────────────────────────────────────────────────────────────

_EMAIL_IMAP_HOST = os.getenv("EMAIL_IMAP_HOST", "").strip()
_EMAIL_IMAP_PORT = int(os.getenv("EMAIL_IMAP_PORT", "993"))
_EMAIL_IMAP_USERNAME = os.getenv("EMAIL_IMAP_USERNAME", "").strip()
_EMAIL_IMAP_PASSWORD = os.getenv("EMAIL_IMAP_PASSWORD", "").strip()
_EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "").strip()
_EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
_EMAIL_SMTP_USERNAME = os.getenv("EMAIL_SMTP_USERNAME", "").strip()
_EMAIL_SMTP_PASSWORD = os.getenv("EMAIL_SMTP_PASSWORD", "").strip()
_EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "Sparkbot").strip()

# ─── Calendar config ──────────────────────────────────────────────────────────

_CALDAV_URL = os.getenv("CALDAV_URL", "").strip()
_CALDAV_USERNAME = os.getenv("CALDAV_USERNAME", "").strip()
_CALDAV_PASSWORD = os.getenv("CALDAV_PASSWORD", "").strip()

# ─── Server operations config ─────────────────────────────────────────────────

_SAFE_SERVICE_RE = re.compile(r"^[A-Za-z0-9@._-]+$")
_SAFE_SSH_HOST_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_ALLOWED_LOCAL_SERVICES = {
    item.strip()
    for item in os.getenv("SPARKBOT_ALLOWED_SERVICES", "sparkbot-v2").split(",")
    if item.strip()
}
_ALLOWED_SSH_SERVICES = {
    item.strip()
    for item in os.getenv("SPARKBOT_SSH_ALLOWED_SERVICES", "").split(",")
    if item.strip()
}
_ALLOWED_SSH_HOSTS = {
    item.strip()
    for item in os.getenv("SPARKBOT_SSH_ALLOWED_HOSTS", "").split(",")
    if item.strip()
}
_SERVICE_USE_SUDO = os.getenv("SPARKBOT_SERVICE_USE_SUDO", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_SERVER_COMMAND_TIMEOUT_SECONDS = max(
    5,
    min(int(os.getenv("SPARKBOT_SERVER_COMMAND_TIMEOUT_SECONDS", "20")), 60),
)
_SSH_COMMAND_TIMEOUT_SECONDS = max(
    5,
    min(int(os.getenv("SPARKBOT_SSH_COMMAND_TIMEOUT_SECONDS", "30")), 120),
)
_SSH_CONNECT_TIMEOUT_SECONDS = max(
    3,
    min(int(os.getenv("SPARKBOT_SSH_CONNECT_TIMEOUT_SECONDS", "10")), 30),
)
_BROWSER_SESSION_TTL_SECONDS = max(
    120,
    min(int(os.getenv("SPARKBOT_BROWSER_SESSION_TTL_SECONDS", "1800")), 86400),
)
_BROWSER_MAX_TEXT_CHARS = max(
    800,
    min(int(os.getenv("SPARKBOT_BROWSER_MAX_TEXT_CHARS", "4000")), 20000),
)
_BROWSER_NAV_TIMEOUT_MS = max(
    5000,
    min(int(os.getenv("SPARKBOT_BROWSER_NAV_TIMEOUT_MS", "30000")), 120000),
)
_BROWSER_ALLOW_PRIVATE_NETWORK = os.getenv("SPARKBOT_BROWSER_ALLOW_PRIVATE_NETWORK", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_BROWSER_ALLOW_INSECURE_SSL = os.getenv("SPARKBOT_BROWSER_ALLOW_INSECURE_SSL", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_BROWSER_HEADLESS = os.getenv("SPARKBOT_BROWSER_HEADLESS", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_BROWSER_SESSIONS: dict[str, dict] = {}
_BROWSER_SESSION_LOCK = asyncio.Lock()
# Named sessions: human-readable name → active session_id (in-memory only)
_NAMED_SESSIONS: dict[str, str] = {}


def _browser_data_dir() -> Path:
    """Resolve the directory for persisted browser session state files."""
    root = os.getenv("SPARKBOT_DATA_DIR", "").strip()
    if root:
        base = Path(root).expanduser()
    else:
        base = Path(__file__).resolve().parents[4] / "data"
    p = base / "browser_sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


from app.services.skills import _registry as _skill_registry

# ─── Tool definitions (sent to the LLM) ──────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": (
                "Store a fact about the user for future conversations. "
                "Call this proactively when the user reveals their name, role, timezone, "
                "preferred language, an ongoing project, or any preference you should remember. "
                "Keep facts short, specific, and in third-person: 'User prefers Python over JavaScript'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "A concise, specific fact about the user (max 200 chars)",
                    }
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_fact",
            "description": "Remove a stored fact about the user by its ID. Use when the user asks you to forget something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "UUID of the memory to delete (shown in /memory list)",
                    }
                },
                "required": ["memory_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_recall",
            "description": (
                "Search Guardian memory for relevant facts, prior messages, or tool results. "
                "Use this when you need to recall what the user has said before, what tools "
                "have been run, or any durable fact tied to this user/room. Returns ranked "
                "items with provenance (source, confidence, score). Prefer this over guessing."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language query — keywords from the user's question work fine.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum items to return (default 6, max 25).",
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["fts", "embed", "hybrid"],
                        "description": "Retrieval mode. Default: hybrid (FTS + embedding rerank).",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_retrieval_stats",
            "description": (
                "Return in-process telemetry for the Guardian Memory pipeline (writes, recalls, "
                "hit rate, latency, current retriever mode, embed index size). Useful for self-"
                "diagnostics or to surface to the user when they ask how memory is performing."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memory_reindex",
            "description": (
                "Rebuild the Guardian memory FTS + embedding indexes from the on-disk ledger. "
                "Safe to run any time; idempotent. Schedulable via Task Guardian."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the web for current information. Use this for recent events, "
                "facts you are uncertain about, prices, news, or anything requiring "
                "up-to-date data beyond your training cutoff."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Concise search query (3-10 words is ideal)",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Fetch and read the content of any public web page or URL. "
                "Use this when the user gives you a specific URL to visit, asks you to read a page, "
                "check a website, or participate in a site (e.g. read a research page, forum, or article). "
                "Returns the page text. After reading, you can summarise, respond to, or act on the content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Full URL to fetch, e.g. https://thesparkpit.com/research",
                    },
                    "instruction": {
                        "type": "string",
                        "description": "Optional: what to do with the page (e.g. 'summarise', 'find the research questions', 'list all links')",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_open",
            "description": (
                "Open a real browser session (Playwright) and load a website. "
                "Use this for interactive website workflows such as registration, login, "
                "navigation, and forum/social interactions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Website URL to open",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional existing browser session ID to reuse",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_navigate",
            "description": "Navigate an existing browser session to another URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Browser session ID returned by browser_open",
                    },
                    "url": {
                        "type": "string",
                        "description": "Destination URL",
                    },
                },
                "required": ["session_id", "url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_snapshot",
            "description": (
                "Read the currently loaded page in a browser session. "
                "Returns page title, URL, readable text excerpt, links, inputs, and buttons."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Browser session ID returned by browser_open",
                    }
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_fill_field",
            "description": (
                "Fill a form field in a browser session. "
                "Field can be a label, placeholder, name, id, or CSS selector."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Browser session ID",
                    },
                    "field": {
                        "type": "string",
                        "description": "Field label/name/id/placeholder/CSS selector",
                    },
                    "value": {
                        "type": "string",
                        "description": "Value to type into the field",
                    },
                },
                "required": ["session_id", "field", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": (
                "Click an element in a browser session by text or CSS selector. "
                "Use this to proceed through interactive website flows, including submit actions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Browser session ID",
                    },
                    "target": {
                        "type": "string",
                        "description": "Button/link text or CSS selector",
                    },
                    "target_type": {
                        "type": "string",
                        "enum": ["auto", "text", "selector"],
                        "description": "How to interpret target. Default: auto",
                    },
                },
                "required": ["session_id", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_close",
            "description": "Close a browser session and release resources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Browser session ID",
                    }
                },
                "required": ["session_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_save_session",
            "description": (
                "Save the current browser session (cookies, localStorage) to disk under a "
                "human-readable name so it can be restored in a future conversation. "
                "Use after logging in to a site so you don't need to log in again."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Active browser session ID to save",
                    },
                    "name": {
                        "type": "string",
                        "description": "Name for this saved session (alphanumeric, hyphens, underscores; e.g. 'twitter-account' or 'github-sparky')",
                    },
                },
                "required": ["session_id", "name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_restore_session",
            "description": (
                "Restore a previously saved browser session by name, creating a new browser "
                "instance with the saved cookies loaded. Use at the start of a task that "
                "requires a site you've already logged in to."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Name of the saved session to restore",
                    },
                    "url": {
                        "type": "string",
                        "description": "Optional: navigate to this URL after restoring (e.g. the site home page)",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_list_sessions",
            "description": (
                "List all active browser sessions (in-memory, current server run) and all "
                "saved sessions (on-disk, survive restarts). Use this to find a session to "
                "restore or to check which sites you're already logged in to."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_list_sessions",
            "description": (
                "List active terminal sessions open in the Workstation panel. "
                "Returns session IDs, shell, and status. Use before terminal_send to find a session."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "terminal_send",
            "description": (
                "Send a command or text to a running terminal session in the Workstation. "
                "The output appears in the visual terminal panel the user is watching. "
                "Use terminal_list_sessions first to get the session_id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Terminal session ID from terminal_list_sessions.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text or command to send. A newline (Enter) is appended unless press_enter is false.",
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Append a newline to submit the command (default true).",
                        "default": True,
                    },
                },
                "required": ["session_id", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Get the current date and time (UTC). Use when the user asks what time or date it is.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a mathematical expression and return the result. "
                "Use for arithmetic, percentages, unit conversions, and simple formulas. "
                "Supports: +, -, *, /, **, ( )"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression, e.g. '(150 * 1.2) / 3'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": (
                "Create a task or to-do item in the current room. Use when the user says "
                "'add a task', 'remind me to', 'we need to', or asks you to track something."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short task title (what needs to be done)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional longer description or notes",
                    },
                    "assignee": {
                        "type": "string",
                        "description": "Optional username to assign the task to",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "Optional due date in ISO 8601 format, e.g. '2026-03-10'",
                    },
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": (
                "List tasks in the current room. Use when the user asks about open tasks, "
                "'what's on the todo list', or 'what do we need to do'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "enum": ["open", "done", "all"],
                        "description": "Filter by status: 'open' (default), 'done', or 'all'",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": (
                "Mark a task as done. Use when the user says a task is finished, "
                "completed, or done. Requires the task ID from list_tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID (first 8 chars from list_tasks, or full UUID)",
                    }
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_prs",
            "description": (
                "List pull requests on a GitHub repository. Use when asked about open PRs, "
                "what's in review, or the current PR queue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repository in owner/repo format (uses default if not specified)",
                    },
                    "state": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "description": "PR state filter — 'open' (default), 'closed', or 'all'",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_pr",
            "description": (
                "Get details of a specific pull request — title, author, description, "
                "changed files, review status, and CI check results."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pr_number": {
                        "type": "integer",
                        "description": "The PR number",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository in owner/repo format (uses default if not specified)",
                    },
                },
                "required": ["pr_number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_create_issue",
            "description": (
                "Create a new GitHub issue. Use when asked to file a bug, "
                "create a ticket, or log a feature request."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Issue title",
                    },
                    "body": {
                        "type": "string",
                        "description": "Issue body — markdown supported",
                    },
                    "labels": {
                        "type": "string",
                        "description": "Comma-separated label names, e.g. 'bug,high-priority'",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository in owner/repo format (uses default if not specified)",
                    },
                },
                "required": ["title", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_ci_status",
            "description": (
                "Get the latest CI / GitHub Actions workflow run status for a branch. "
                "Use when asked about build status, CI results, or whether a branch is green."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "branch": {
                        "type": "string",
                        "description": "Branch name (default: 'main')",
                    },
                    "repo": {
                        "type": "string",
                        "description": "Repository in owner/repo format (uses default if not specified)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "slack_send_message",
            "description": (
                "Send a message to a Slack channel. Use when asked to post, notify, "
                "or message a channel or person on Slack."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name (e.g. '#general') or channel ID. Uses SLACK_DEFAULT_CHANNEL if omitted.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Message text to send",
                    },
                    "thread_ts": {
                        "type": "string",
                        "description": "Optional timestamp of a parent message to reply in thread",
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "slack_list_channels",
            "description": (
                "List public Slack channels. Use when asked what channels exist "
                "or to find the right channel to post in."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max number of channels to return (default 20, max 100)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "slack_get_channel_history",
            "description": (
                "Fetch recent messages from a Slack channel. Use when asked what was "
                "said in a channel, to catch up, or to summarise recent activity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {
                        "type": "string",
                        "description": "Channel name or ID",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent messages (default 10, max 50)",
                    },
                },
                "required": ["channel"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notion_search",
            "description": (
                "Search Notion pages by keyword. Use when asked to find a Notion doc, "
                "wiki page, or meeting notes. Returns matching page titles and URLs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notion_get_page",
            "description": (
                "Retrieve the full content of a Notion page. Use when asked to read, "
                "summarise, or quote a specific Notion page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Notion page ID (UUID) or full Notion page URL",
                    },
                },
                "required": ["page_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notion_create_page",
            "description": (
                "Create a new Notion page with a title and text content. "
                "Use when asked to write a doc, capture meeting notes, or create a wiki page in Notion."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Page title",
                    },
                    "content": {
                        "type": "string",
                        "description": "Page body as plain text or markdown (headings with #, lists with -, bold with **)",
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Parent page or database ID (uses NOTION_DEFAULT_PARENT_ID if omitted)",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confluence_search",
            "description": (
                "Search Confluence pages by keyword using CQL. Use when asked to find "
                "a Confluence doc, design spec, or runbook."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keywords",
                    },
                    "space_key": {
                        "type": "string",
                        "description": "Confluence space key to restrict the search (e.g. 'ENG'). Optional.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confluence_get_page",
            "description": (
                "Retrieve the full text content of a Confluence page. "
                "Use when asked to read or summarise a specific Confluence page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {
                        "type": "string",
                        "description": "Confluence page ID (numeric string, visible in the page URL)",
                    },
                },
                "required": ["page_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confluence_create_page",
            "description": (
                "Create a new Confluence page with a title and content. "
                "Use when asked to write a doc or publish notes to Confluence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Page title",
                    },
                    "content": {
                        "type": "string",
                        "description": "Page body as plain text or basic HTML",
                    },
                    "space_key": {
                        "type": "string",
                        "description": "Confluence space key (uses CONFLUENCE_DEFAULT_SPACE if omitted)",
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Optional numeric parent page ID",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_fetch_inbox",
            "description": (
                "Fetch recent Gmail messages from the authenticated inbox. "
                "Use when asked to check Gmail, recent email, or unread messages."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_emails": {
                        "type": "integer",
                        "description": "How many recent Gmail messages to fetch (default 5, max 20)",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "If true, only fetch unread Gmail messages (default false)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_search",
            "description": (
                "Search Gmail using Gmail query syntax. Use for requests like "
                "'find emails from Alice', 'search Gmail for invoice', or 'show unread finance mail'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Gmail search query, e.g. 'from:alice@example.com is:unread'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5, max 20)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_get_message",
            "description": (
                "Read a specific Gmail message in detail by message ID. "
                "Use after gmail_fetch_inbox or gmail_search when the user wants the full email."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {
                        "type": "string",
                        "description": "Gmail message ID returned by gmail_fetch_inbox or gmail_search",
                    },
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_send",
            "description": (
                "Send an email through Gmail. Always confirm the recipient, subject, and body "
                "with the user before calling this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body in plain text",
                    },
                    "cc": {
                        "type": "string",
                        "description": "Optional CC email address",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_search",
            "description": (
                "Search Google Drive files and folders by name or text. "
                "Use when asked to find a file, folder, document, sheet, or presentation in Drive."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text for Drive file names or content",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 10, max 25)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_get_file",
            "description": (
                "Read metadata and, when possible, text content from a Google Drive file by file ID. "
                "Use after drive_search when the user wants to open a specific file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_id": {
                        "type": "string",
                        "description": "Google Drive file ID returned by drive_search",
                    },
                },
                "required": ["file_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "drive_create_folder",
            "description": (
                "Create a Google Drive folder. Always confirm the folder name and destination "
                "with the user before calling this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Folder name to create",
                    },
                    "parent_id": {
                        "type": "string",
                        "description": "Optional parent folder ID; omit to create in the default Drive root",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "server_read_command",
            "description": (
                "Run an approved read-only diagnostic command on the local server. "
                "Use for checking uptime, disk, memory, network listeners, top processes, "
                "service status, or recent service logs. "
                "If the user asks to show the status of a service or show logs, use this tool, not service management. "
                "Never use this for writing or destructive actions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "enum": [
                            "system_overview",
                            "disk_usage",
                            "memory",
                            "network_listeners",
                            "process_snapshot",
                            "service_status",
                            "service_logs",
                        ],
                        "description": "Approved diagnostic profile to run on the local server",
                    },
                    "service": {
                        "type": "string",
                        "description": "Required for service_status or service_logs; must be an allowed systemd unit name",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "For service_logs only: how many recent log lines to return (default 50, max 200)",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "server_manage_service",
            "description": (
                "Start, stop, or restart an approved local system service. "
                "Use this only for explicit service control requests such as restart, stop, or start. "
                "Do not use this for status, logs, or diagnostics. "
                "Always confirm the target service and action with the user before calling this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {
                        "type": "string",
                        "description": "Allowed local systemd service name, for example 'sparkbot-v2'",
                    },
                    "action": {
                        "type": "string",
                        "enum": ["start", "stop", "restart"],
                        "description": "Service action to run",
                    },
                },
                "required": ["service", "action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_read_command",
            "description": (
                "Run an approved read-only diagnostic command on a configured SSH host alias. "
                "Use when asked to inspect a remote server or PC. Host must be in the SSH allowlist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "host": {
                        "type": "string",
                        "description": "SSH host alias from the approved allowlist",
                    },
                    "command": {
                        "type": "string",
                        "enum": [
                            "system_overview",
                            "disk_usage",
                            "memory",
                            "network_listeners",
                            "process_snapshot",
                            "service_status",
                            "service_logs",
                        ],
                        "description": "Approved diagnostic profile to run on the remote host",
                    },
                    "service": {
                        "type": "string",
                        "description": "Required for service_status or service_logs; must be an allowed remote systemd unit name",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "For service_logs only: how many recent log lines to return (default 50, max 200)",
                    },
                },
                "required": ["host", "command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "email_fetch_inbox",
            "description": (
                "Fetch recent emails from the inbox. Use when asked about email, "
                "the inbox, or recent messages. Returns subjects, senders, dates, and snippets."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_emails": {
                        "type": "integer",
                        "description": "How many recent emails to fetch (default 5, max 20)",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "If true, only fetch unread emails (default false)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "email_search",
            "description": (
                "Search the inbox for emails matching a keyword. "
                "Searches subject and sender fields."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search term (searches subject and from fields)",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results to return (default 5)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "email_send",
            "description": (
                "Send an email. Always confirm the recipient, subject, and content with the user "
                "before calling this tool. Use for drafting and sending emails on behalf of the user."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line",
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body — plain text",
                    },
                    "cc": {
                        "type": "string",
                        "description": "Optional CC email address",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_reminder",
            "description": (
                "Schedule a reminder message to be sent to this room at a specific time. "
                "Use when the user asks to be reminded, wants a scheduled alert, or says "
                "'remind me', 'ping me', 'alert us at', 'daily standup reminder', etc. "
                "Always call get_datetime first if you need to know the current time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The reminder message to send to the room",
                    },
                    "fire_at": {
                        "type": "string",
                        "description": "When to send it — ISO 8601 UTC datetime, e.g. '2026-03-06T09:00:00'",
                    },
                    "recurrence": {
                        "type": "string",
                        "enum": ["once", "daily", "weekly"],
                        "description": "How often to repeat — 'once' (default), 'daily', or 'weekly'",
                    },
                },
                "required": ["message", "fire_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List pending reminders for this room. Use when the user asks what reminders are set.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": "Cancel a pending reminder by its ID. Get IDs from list_reminders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reminder_id": {
                        "type": "string",
                        "description": "Reminder ID (first 8 chars or full UUID from list_reminders)",
                    }
                },
                "required": ["reminder_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardian_schedule_task",
            "description": (
                "Schedule a Task Guardian job that runs a tool on a recurring schedule and posts the result "
                "back into this room — and fans out to Telegram/Discord/WhatsApp if configured. "
                "Use for recurring inbox digests, morning briefings, PR checks, calendar lookups, "
                "server diagnostics, scheduled emails, Slack posts, and similar office workflows. "
                "Read-only tools run automatically. Write tools (gmail_send, slack_send_message, "
                "calendar_create_event) require SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true and "
                "will prompt for confirmation before the job is created."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short descriptive task name",
                    },
                    "tool_name": {
                        "type": "string",
                        "description": (
                            "Tool to run on schedule. Read-only: web_search, github_list_prs, "
                            "github_get_ci_status, slack_get_channel_history, notion_search, "
                            "confluence_search, gmail_fetch_inbox, gmail_search, drive_search, "
                            "calendar_list_events, server_read_command, ssh_read_command, "
                            "list_tasks, list_reminders, morning_briefing. "
                            "Write (requires confirmation + WRITE_ENABLED env var): "
                            "gmail_send, slack_send_message, calendar_create_event."
                        ),
                    },
                    "schedule": {
                        "type": "string",
                        "description": (
                            "Run cadence: every:<seconds> for intervals, daily:<HH:MM> for a UTC daily run "
                            "(e.g. daily:13:00 = 9am America/New_York during daylight time), "
                            "or at:<ISO-8601 UTC datetime> for a one-shot future run."
                        ),
                    },
                    "tool_args": {
                        "type": "object",
                        "description": "Arguments forwarded to the selected tool",
                        "additionalProperties": True,
                    },
                },
                "required": ["name", "tool_name", "schedule"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardian_list_tasks",
            "description": "List Task Guardian jobs configured for this room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardian_list_runs",
            "description": "List recent Task Guardian job runs for this room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of runs to return",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardian_propose_improvement",
            "description": (
                "Record a governed Sparkbot self-improvement proposal for operator approval. "
                "Use when you notice a repeated failure, missing capability, weak workflow, "
                "uncertain answer pattern, missing documentation, or a code/config change that "
                "would make Sparkbot better. This does not apply the change; it creates an "
                "approval-ready proposal first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "One-sentence improvement summary.",
                    },
                    "evidence": {
                        "type": "string",
                        "description": "Observed failure, user feedback, missing info, or telemetry that supports the proposal.",
                    },
                    "suggested_change": {
                        "type": "string",
                        "description": "Concrete change Sparkbot should make after explicit operator approval.",
                    },
                    "risk": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Risk level if the proposed change is later applied.",
                    },
                },
                "required": ["summary", "suggested_change"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardian_simulate_policy",
            "description": (
                "Run a Guardian policy what-if check for a tool call without executing the tool. "
                "Use before enabling automation or when the user asks whether an action would allow, "
                "ask for confirmation, require break-glass, or be denied."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "Tool name to test, such as gmail_send, shell_run, browser_click, or github_create_issue.",
                    },
                    "tool_args": {
                        "type": "object",
                        "description": "Arguments that would be sent to the tool. No action is executed.",
                        "additionalProperties": True,
                    },
                    "room_execution_allowed": {
                        "type": "boolean",
                        "description": "Optional override for the room Computer Control setting.",
                    },
                    "is_operator": {
                        "type": "boolean",
                        "description": "Optional what-if override for whether the requester is a Sparkbot operator.",
                    },
                    "is_privileged": {
                        "type": "boolean",
                        "description": "Optional what-if override for whether break-glass privileged mode is active.",
                    },
                },
                "required": ["tool_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardian_list_improvements",
            "description": "List pending Sparkbot self-improvement proposals for this room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Proposal status to list. Default: proposed.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of proposals to return.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardian_run_task",
            "description": "Run an existing Task Guardian job immediately by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID from guardian_list_tasks",
                    }
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "guardian_pause_task",
            "description": "Pause or resume a Task Guardian job by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID from guardian_list_tasks",
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": "Set to false to pause, true to resume",
                    },
                },
                "required": ["task_id", "enabled"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": (
                "List upcoming calendar events. Use when the user asks about their schedule, "
                "upcoming meetings, appointments, or what's happening this week."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {
                        "type": "integer",
                        "description": "How many days ahead to look (default 7, max 30)",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create_event",
            "description": (
                "Create a new calendar event. Use when the user asks to schedule something, "
                "add a meeting, or book an appointment. Dates must be ISO 8601 format."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title",
                    },
                    "start": {
                        "type": "string",
                        "description": "Start datetime in ISO 8601, e.g. '2026-03-10T14:00:00'",
                    },
                    "end": {
                        "type": "string",
                        "description": "End datetime in ISO 8601, e.g. '2026-03-10T15:00:00'",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event notes or description",
                    },
                    "location": {
                        "type": "string",
                        "description": "Optional location",
                    },
                },
                "required": ["title", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "telegram_test_connection",
            "description": (
                "Test the Telegram bot connection by calling the Telegram API directly. "
                "Returns the bot name and username on success, or a specific error with "
                "troubleshooting guidance on failure. Use when the user asks whether Telegram "
                "is working, why they are not receiving messages, or to diagnose bot token issues."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# ─── Vault tool definitions ───────────────────────────────────────────────────
_VAULT_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "vault_list_secrets",
            "description": (
                "List all secrets stored in the Guardian Vault. "
                "Returns alias, category, access policy, and metadata only — no plaintext values."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vault_use_secret",
            "description": (
                "Retrieve a secret from the Guardian Vault and use its value internally. "
                "The plaintext value is passed to you for use in tool calls but should NOT be echoed in your response. "
                "Use this when you need to authenticate with an external service using a stored credential."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {
                        "type": "string",
                        "description": "The alias of the secret to retrieve.",
                    },
                },
                "required": ["alias"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vault_reveal_secret",
            "description": (
                "Reveal the plaintext value of a secret to the operator. "
                "Only works for secrets with policy 'privileged_reveal' or 'admin_reveal'. "
                "Requires break-glass privileged mode and explicit confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {
                        "type": "string",
                        "description": "The alias of the secret to reveal.",
                    },
                },
                "required": ["alias"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vault_add_secret",
            "description": (
                "Add a new encrypted secret to the Guardian Vault. "
                "Requires break-glass privileged mode."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {
                        "type": "string",
                        "description": "Short unique name for this secret (e.g. 'github_token', 'prod_db_password').",
                    },
                    "value": {
                        "type": "string",
                        "description": "The secret value to encrypt and store.",
                    },
                    "category": {
                        "type": "string",
                        "description": "Category label (e.g. 'api_key', 'password', 'token'). Defaults to 'general'.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional human-readable notes about this secret.",
                    },
                    "access_policy": {
                        "type": "string",
                        "enum": ["use_only", "privileged_reveal", "disabled"],
                        "description": (
                            "'use_only': value can be passed to tools but never shown in chat. "
                            "'privileged_reveal': operator can reveal it in break-glass mode. "
                            "'disabled': secret is stored but cannot be used."
                        ),
                    },
                },
                "required": ["alias", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vault_update_secret",
            "description": (
                "Update the value of an existing secret in the Guardian Vault. "
                "Requires break-glass privileged mode."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {
                        "type": "string",
                        "description": "Alias of the secret to update.",
                    },
                    "value": {
                        "type": "string",
                        "description": "New encrypted value.",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Updated notes (optional).",
                    },
                    "access_policy": {
                        "type": "string",
                        "enum": ["use_only", "privileged_reveal", "disabled"],
                        "description": "Updated access policy (optional).",
                    },
                },
                "required": ["alias", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vault_delete_secret",
            "description": (
                "Permanently delete a secret from the Guardian Vault. "
                "Requires break-glass privileged mode and explicit confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "alias": {
                        "type": "string",
                        "description": "Alias of the secret to delete.",
                    },
                },
                "required": ["alias"],
            },
        },
    },
]

# Extend with dynamically loaded skills, deduping by tool name. Native definitions
# in this file always win over a same-named skill so behaviour is predictable.
def _dedupe_tool_definitions(*sources: list[dict]) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []
    for source in sources:
        for tool in source:
            fn = tool.get("function") if isinstance(tool, dict) else None
            name = (fn or {}).get("name") if isinstance(fn, dict) else None
            if not name or name in seen:
                if name:
                    import logging as _logging
                    _logging.getLogger(__name__).warning(
                        "Duplicate tool definition '%s' ignored", name
                    )
                continue
            seen.add(name)
            merged.append(tool)
    return merged


TOOL_DEFINITIONS = _dedupe_tool_definitions(
    list(TOOL_DEFINITIONS),
    _VAULT_TOOL_DEFINITIONS,
    _skill_registry.definitions,
)


# ─── Executors ────────────────────────────────────────────────────────────────

async def _web_search(query: str) -> str:
    q = (query or "").strip()
    if not q:
        return "Search failed: empty query"

    # Cache identical queries briefly to reduce provider rate-limit issues.
    cached = _search_cache_get(q)
    if cached:
        return cached

    errors: list[str] = []

    brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    if not brave_key:
        brave_key = _load_openclaw_search_key()
    if brave_key:
        try:
            brave_results = await _search_brave(q, brave_key, max_results=4)
            if brave_results:
                output = _format_search_results("brave", brave_results)
                _search_cache_set(q, output)
                return output
            errors.append("brave: no results")
        except Exception as exc:
            errors.append(f"brave: {exc}")

    serpapi_key = os.getenv("SERPAPI_KEY", "").strip()
    if serpapi_key:
        try:
            serp_results = await _search_serpapi(q, serpapi_key, max_results=4)
            if serp_results:
                output = _format_search_results("serpapi", serp_results)
                _search_cache_set(q, output)
                return output
            errors.append("serpapi: no results")
        except Exception as exc:
            errors.append(f"serpapi: {exc}")

    try:
        ddgs_results = await _search_ddgs(q, max_results=4)
        if ddgs_results:
            output = _format_search_results("ddgs", ddgs_results)
            _search_cache_set(q, output)
            return output
        errors.append("ddgs: no results")
    except Exception as exc:
        errors.append(f"ddgs: {exc}")

    detail = "; ".join(errors) if errors else "no providers configured"
    return f"Search failed for '{q}'. {detail}"


_SEARCH_CACHE: dict[str, tuple[float, str]] = {}
_OPENCLAW_KEY_CACHE: str | None = None


def _search_cache_ttl_seconds() -> int:
    raw = os.getenv("SEARCH_CACHE_TTL_SECONDS", "300").strip()
    try:
        val = int(raw)
    except Exception:
        return 300
    return max(30, min(val, 3600))


def _search_cache_get(query: str) -> str | None:
    item = _SEARCH_CACHE.get(query)
    if not item:
        return None
    expires_at, payload = item
    if time.time() > expires_at:
        _SEARCH_CACHE.pop(query, None)
        return None
    return payload


def _search_cache_set(query: str, payload: str) -> None:
    _SEARCH_CACHE[query] = (time.time() + _search_cache_ttl_seconds(), payload)


def _load_openclaw_search_key() -> str:
    """
    Best-effort bridge to OpenClaw's existing web-search key so Sparkbot can
    reuse local config without duplicating key setup.
    """
    global _OPENCLAW_KEY_CACHE
    if _OPENCLAW_KEY_CACHE is not None:
        return _OPENCLAW_KEY_CACHE

    cfg_path = os.getenv("OPENCLAW_CONFIG_PATH", "").strip()
    if not cfg_path:
        cfg_path = str(Path.home() / ".openclaw" / "openclaw.json")
    p = Path(cfg_path).expanduser()
    if not p.exists():
        _OPENCLAW_KEY_CACHE = ""
        return ""

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        key = str(
            (((data.get("tools") or {}).get("web") or {}).get("search") or {}).get("apiKey", "")
        ).strip()
    except Exception:
        key = ""
    _OPENCLAW_KEY_CACHE = key
    return key


def _normalize_results(rows: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for row in rows:
        title = str(row.get("title", "")).strip()
        snippet = str(row.get("snippet", "")).strip()
        url = str(row.get("url", "")).strip()
        if not (title or snippet or url):
            continue
        normalized.append({"title": title, "snippet": snippet, "url": url})
    return normalized


def _format_search_results(provider: str, rows: list[dict]) -> str:
    lines = [f"Search provider: {provider}", ""]
    for idx, row in enumerate(rows, start=1):
        title = row.get("title", "")
        snippet = row.get("snippet", "")
        url = row.get("url", "")
        lines.append(f"{idx}. {title}")
        if snippet:
            lines.append(f"   {snippet}")
        if url:
            lines.append(f"   {url}")
        lines.append("")
    return "\n".join(lines).strip()


async def _search_brave(query: str, api_key: str, max_results: int = 4) -> list[dict]:
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": max_results}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        payload = resp.json()

    results = payload.get("web", {}).get("results", []) or []
    rows = [
        {
            "title": item.get("title", ""),
            "snippet": item.get("description", ""),
            "url": item.get("url", ""),
        }
        for item in results
    ]
    return _normalize_results(rows)


async def _search_serpapi(query: str, api_key: str, max_results: int = 4) -> list[dict]:
    url = "https://serpapi.com/search.json"
    params = {"engine": "google", "q": query, "api_key": api_key, "num": max_results}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        payload = resp.json()

    results = payload.get("organic_results", []) or []
    rows = [
        {
            "title": item.get("title", ""),
            "snippet": item.get("snippet", ""),
            "url": item.get("link", ""),
        }
        for item in results
    ]
    return _normalize_results(rows)


def _search_ddgs_sync(query: str, max_results: int = 4) -> list[dict]:
    from ddgs import DDGS

    with DDGS() as ddgs:
        raw = list(ddgs.text(query, max_results=max_results))
    rows = [
        {
            "title": item.get("title", ""),
            "snippet": item.get("body", ""),
            "url": item.get("href", ""),
        }
        for item in raw
    ]
    return _normalize_results(rows)


async def _search_ddgs(query: str, max_results: int = 4) -> list[dict]:
    return await asyncio.to_thread(_search_ddgs_sync, query, max_results)


async def _fetch_url(url: str, instruction: str = "") -> str:
    """Fetch a public URL and return cleaned readable text (max ~6 000 chars)."""
    import html2text
    from bs4 import BeautifulSoup

    url = (url or "").strip()
    if not url:
        return "fetch_url failed: no URL provided"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # SSRF guard — block private/internal network targets
    try:
        _parsed = urlparse(url)
        _host = (_parsed.hostname or "").lower()
        if _host in ("localhost", "127.0.0.1", "::1") or _host.endswith(".local"):
            return f"fetch_url blocked: local/private network URLs are not allowed"
        try:
            _addr = ipaddress.ip_address(_host)
            if (
                _addr.is_private
                or _addr.is_loopback
                or _addr.is_link_local
                or _addr.is_reserved
                or _addr.is_multicast
                or _addr.is_unspecified
            ):
                return "fetch_url blocked: private or reserved IP targets are not allowed"
        except ValueError:
            pass
    except Exception:
        pass

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    raw_html: str | None = None
    for verify in (True, False):
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers, verify=verify) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "html" not in ct and "text" not in ct:
                    return f"fetch_url: non-HTML content ({ct}) at {url} — cannot extract text"
                raw_html = resp.text
                break
        except httpx.HTTPStatusError as exc:
            return f"fetch_url failed: HTTP {exc.response.status_code} for {url}"
        except Exception:
            if not verify:
                import traceback
                return f"fetch_url failed: {traceback.format_exc(limit=2)}"
    if raw_html is None:
        return f"fetch_url failed: could not retrieve {url}"

    # Strip script/style noise then convert to clean markdown
    soup = BeautifulSoup(raw_html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    converter = html2text.HTML2Text()
    converter.ignore_links = False
    converter.ignore_images = True
    converter.body_width = 0  # no wrapping
    text = converter.handle(str(soup))

    # Collapse excessive blank lines
    import re as _re
    text = _re.sub(r"\n{3,}", "\n\n", text).strip()

    MAX = 6000
    if len(text) > MAX:
        text = text[:MAX] + f"\n\n[...page truncated at {MAX} chars — use fetch_url with a more specific sub-URL if needed]"

    prefix = f"**Fetched:** {url}\n"
    if instruction:
        prefix += f"**Task:** {instruction}\n"
    return prefix + "\n" + text


async def _terminal_list_sessions(user_id: Optional[str]) -> str:
    """List active PTY terminal sessions for this user."""
    try:
        from app.services.terminal_service import terminal_manager as _tm
    except Exception:
        return "Terminal service is not available on this instance."
    if user_id is None:
        return "No user context — cannot list terminal sessions."
    sessions = _tm.list_user_sessions(str(user_id))
    if not sessions:
        return (
            "No active terminal sessions found. "
            "Open the Workstation and connect a terminal panel first."
        )
    lines = ["Active terminal sessions:"]
    for s in sessions:
        lines.append(f"  • {s.session_id[:8]}…  shell={s.shell}  status={s.status}")
    lines.append("\nUse the full session_id with terminal_send.")
    # Provide full IDs as well
    for s in sessions:
        lines.append(f"  full id: {s.session_id}")
    return "\n".join(lines)


async def _terminal_send(session_id: str, text: str, press_enter: bool = True) -> str:
    """Write text/command to a running PTY terminal session."""
    try:
        from app.services.terminal_service import terminal_manager as _tm
    except Exception:
        return "Terminal service is not available on this instance."
    sid = (session_id or "").strip()
    if not sid:
        return "Error: session_id is required. Use terminal_list_sessions first."
    # Accept short prefix match
    if len(sid) < 36:
        matches = [s for s in _tm._sessions if s.startswith(sid)]
        if len(matches) == 1:
            sid = matches[0]
        elif len(matches) > 1:
            return f"Ambiguous session prefix '{sid}' — provide more characters."
        else:
            return f"No session found matching '{sid}'. Use terminal_list_sessions to get the ID."
    session = _tm.get_session(sid)
    if not session:
        return f"Session '{sid[:8]}…' not found. Use terminal_list_sessions."
    if session.status in ("closed", "error"):
        return f"Session '{sid[:8]}…' is {session.status}. Open a new terminal in the Workstation."
    payload = text
    if press_enter and not payload.endswith("\n"):
        payload += "\n"
    ok = await _tm.write_input(sid, payload.encode("utf-8"))
    if ok:
        return f"Sent to terminal session {sid[:8]}…: {repr(text)}"
    return f"Write to session {sid[:8]}… failed — the shell may have exited."


def _normalize_browser_url(
    raw_url: str,
    *,
    allow_private_network: bool | None = None,
) -> tuple[str | None, str | None]:
    allow_private = _BROWSER_ALLOW_PRIVATE_NETWORK if allow_private_network is None else allow_private_network
    url = (raw_url or "").strip()
    if not url:
        return None, "browser_open failed: no URL provided"
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except Exception:
        return None, f"browser_open failed: invalid URL '{raw_url}'"

    if parsed.scheme not in {"http", "https"}:
        return None, "browser_open failed: only http:// and https:// URLs are allowed"
    if not parsed.hostname:
        return None, f"browser_open failed: invalid URL '{raw_url}'"

    host = parsed.hostname.lower()
    if host == "localhost" and not allow_private:
        return None, "browser_open blocked: localhost/private network URLs are disabled"
    if host.endswith(".local") and not allow_private:
        return None, "browser_open blocked: .local/private network URLs are disabled"

    try:
        addr = ipaddress.ip_address(host)
        if (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
            or addr.is_unspecified
        ) and not allow_private:
            return None, "browser_open blocked: private or loopback IP targets are disabled"
    except ValueError:
        pass

    if not parsed.path:
        parsed = parsed._replace(path="/")
    parsed = parsed._replace(fragment="")
    return urlunparse(parsed), None


def _playwright_install_hint(exc: Exception | None = None) -> str:
    suffix = f" ({exc})" if exc else ""
    return (
        "Browser automation unavailable: Playwright is not ready"
        f"{suffix}. Install with `pip install playwright` and run `playwright install chromium`."
    )


async def _close_browser_session_entry(entry: dict) -> None:
    context = entry.get("context")
    browser = entry.get("browser")
    playwright = entry.get("playwright")
    for obj in (context, browser):
        if obj is None:
            continue
        try:
            await obj.close()
        except Exception:
            pass
    if playwright is not None:
        try:
            await playwright.stop()
        except Exception:
            pass


async def _cleanup_browser_sessions(*, force: bool = False) -> None:
    now = time.time()
    stale: list[tuple[str, dict]] = []
    async with _BROWSER_SESSION_LOCK:
        for sid, entry in list(_BROWSER_SESSIONS.items()):
            expired = now - float(entry.get("last_used_at", now)) > _BROWSER_SESSION_TTL_SECONDS
            if force or expired:
                stale.append((sid, entry))
                _BROWSER_SESSIONS.pop(sid, None)
    for _, entry in stale:
        await _close_browser_session_entry(entry)


async def _browser_get_session(session_id: str) -> dict | None:
    await _cleanup_browser_sessions()
    sid = (session_id or "").strip()
    if not sid:
        return None
    async with _BROWSER_SESSION_LOCK:
        entry = _BROWSER_SESSIONS.get(sid)
        if entry is not None:
            entry["last_used_at"] = time.time()
        return entry


async def _browser_create_session() -> tuple[str | None, dict | None, str | None]:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return None, None, _playwright_install_hint(exc)

    playwright = None
    browser = None
    context = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=_BROWSER_HEADLESS,
            timeout=60000,  # 60s max — fail fast if Chromium isn't installed
        )
        context = await browser.new_context(ignore_https_errors=_BROWSER_ALLOW_INSECURE_SSL)
        page = await context.new_page()
    except Exception as exc:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass
        return None, None, f"browser_open failed: could not launch browser ({exc})"

    sid = str(uuid.uuid4())[:12]
    entry = {
        "playwright": playwright,
        "browser": browser,
        "context": context,
        "page": page,
        "created_at": time.time(),
        "last_used_at": time.time(),
    }
    async with _BROWSER_SESSION_LOCK:
        _BROWSER_SESSIONS[sid] = entry
    return sid, entry, None


def _browser_text_excerpt(text: str, max_chars: int = _BROWSER_MAX_TEXT_CHARS) -> str:
    cleaned = re.sub(r"\n{3,}", "\n\n", (text or "").strip())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars] + f"\n\n[...truncated at {max_chars} chars]"


async def _browser_snapshot_payload(page) -> dict:
    title = await page.title()
    body_text = await page.evaluate("() => (document.body && document.body.innerText) ? document.body.innerText : ''")
    links = await page.evaluate(
        """() => Array.from(document.querySelectorAll('a[href]')).slice(0, 12).map((a) => ({
            text: (a.innerText || '').trim().slice(0, 90),
            href: a.href || '',
        }))"""
    )
    inputs = await page.evaluate(
        """() => Array.from(document.querySelectorAll('input, textarea, select')).slice(0, 12).map((el) => ({
            tag: (el.tagName || '').toLowerCase(),
            type: (el.getAttribute('type') || '').toLowerCase(),
            id: el.id || '',
            name: el.getAttribute('name') || '',
            placeholder: el.getAttribute('placeholder') || '',
            label: (el.getAttribute('aria-label') || '').trim(),
        }))"""
    )
    buttons = await page.evaluate(
        """() => Array.from(document.querySelectorAll('button, input[type="submit"], input[type="button"], a[role="button"]'))
            .slice(0, 12)
            .map((el) => ({
                tag: (el.tagName || '').toLowerCase(),
                text: ((el.innerText || el.getAttribute('value') || '').trim()).slice(0, 90),
                id: el.id || '',
                name: el.getAttribute('name') || '',
                type: (el.getAttribute('type') || '').toLowerCase(),
            }))"""
    )
    return {
        "title": (title or "").strip(),
        "url": page.url,
        "text": _browser_text_excerpt(body_text),
        "links": links or [],
        "inputs": inputs or [],
        "buttons": buttons or [],
    }


def _format_browser_snapshot(session_id: str, payload: dict) -> str:
    lines = [
        f"Browser session: {session_id}",
        f"Page title: {payload.get('title') or '(untitled)'}",
        f"URL: {payload.get('url') or '(unknown)'}",
        "",
        "Page text:",
        payload.get("text") or "(no readable text found)",
        "",
    ]
    links = payload.get("links") or []
    if links:
        lines.append("Top links:")
        for idx, item in enumerate(links, start=1):
            text = str(item.get("text") or "").strip() or "(no text)"
            href = str(item.get("href") or "").strip()
            lines.append(f"{idx}. {text} -> {href}")
        lines.append("")
    inputs = payload.get("inputs") or []
    if inputs:
        lines.append("Inputs:")
        for idx, item in enumerate(inputs, start=1):
            tag = str(item.get("tag") or "")
            typ = str(item.get("type") or "")
            field_id = str(item.get("id") or "")
            name = str(item.get("name") or "")
            placeholder = str(item.get("placeholder") or "")
            label = str(item.get("label") or "")
            lines.append(
                f"{idx}. {tag}[type={typ}] id='{field_id}' name='{name}' "
                f"placeholder='{placeholder}' aria-label='{label}'"
            )
        lines.append("")
    buttons = payload.get("buttons") or []
    if buttons:
        lines.append("Buttons/actions:")
        for idx, item in enumerate(buttons, start=1):
            tag = str(item.get("tag") or "")
            text = str(item.get("text") or "").strip() or "(no text)"
            field_id = str(item.get("id") or "")
            name = str(item.get("name") or "")
            typ = str(item.get("type") or "")
            lines.append(f"{idx}. {tag} text='{text}' id='{field_id}' name='{name}' type='{typ}'")
    return "\n".join(lines).strip()


def _looks_like_selector(target: str) -> bool:
    t = (target or "").strip()
    return t.startswith(("#", ".", "[", "//")) or ">>" in t or ":" in t


def _escape_css_attr(value: str) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


# ─── Named / persistent browser sessions ─────────────────────────────────────

async def _browser_save_session(session_id: str, name: str) -> str:
    """Save browser session cookies+storage to disk under a human-readable name."""
    name = (name or "").strip()
    if not name or not re.fullmatch(r"[\w\-]+", name):
        return "Error: Session name must contain only letters, numbers, hyphens, or underscores."

    entry = await _browser_get_session(session_id)
    if not entry:
        return f"Error: No active browser session with ID '{session_id}'. Start one with browser_open() first."

    try:
        state = await entry["context"].storage_state()
    except Exception as exc:
        return f"Error capturing session state: {exc}"

    save_path = _browser_data_dir() / f"{name}.json"
    try:
        save_path.write_text(json.dumps(state), encoding="utf-8")
    except Exception as exc:
        return f"Error saving session to disk: {exc}"

    _NAMED_SESSIONS[name] = session_id
    entry["saved_name"] = name

    n_cookies = len(state.get("cookies", []))
    return (
        f"Session saved as '{name}' ({n_cookies} cookies stored). "
        f"Use browser_restore_session('{name}') to resume in any future conversation."
    )


async def _browser_restore_session(name: str, url: str = "") -> str:
    """Create a new browser instance pre-loaded with a previously saved session."""
    name = (name or "").strip()
    save_path = _browser_data_dir() / f"{name}.json"

    if not save_path.is_file():
        return (
            f"Error: No saved session named '{name}'. "
            "Use browser_list_sessions() to see available sessions."
        )

    try:
        state = json.loads(save_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return f"Error loading saved session '{name}': {exc}"

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        return _playwright_install_hint(exc)

    playwright = None
    browser = None
    context = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=_BROWSER_HEADLESS, timeout=60000)
        context = await browser.new_context(
            storage_state=state,
            ignore_https_errors=_BROWSER_ALLOW_INSECURE_SSL,
        )
        page = await context.new_page()
    except Exception as exc:
        for obj in (context, browser):
            if obj:
                try:
                    await obj.close()
                except Exception:
                    pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass
        return f"Error restoring session '{name}': {exc}"

    sid = str(uuid.uuid4())[:12]
    entry = {
        "playwright": playwright,
        "browser": browser,
        "context": context,
        "page": page,
        "created_at": time.time(),
        "last_used_at": time.time(),
        "saved_name": name,
    }
    async with _BROWSER_SESSION_LOCK:
        _BROWSER_SESSIONS[sid] = entry
    _NAMED_SESSIONS[name] = sid

    n_cookies = len(state.get("cookies", []))
    result = f"Session '{name}' restored (session_id: {sid}, {n_cookies} cookies loaded)."

    if url:
        nav_result = await _browser_navigate(sid, url)
        result += f"\n{nav_result}"
    else:
        result += " Use this session_id for browser_navigate/snapshot/fill/click calls."

    return result


async def _browser_list_sessions() -> str:
    """List active (in-memory) and saved (on-disk) browser sessions."""
    await _cleanup_browser_sessions()
    now = time.time()
    lines: list[str] = ["## Active browser sessions (in-memory)"]

    async with _BROWSER_SESSION_LOCK:
        active = dict(_BROWSER_SESSIONS)

    if active:
        for sid, entry in active.items():
            age = int(now - entry.get("created_at", now))
            idle = int(now - entry.get("last_used_at", now))
            name_tag = f" [{entry['saved_name']}]" if entry.get("saved_name") else ""
            lines.append(f"- {sid}{name_tag} — age {age}s, idle {idle}s")
    else:
        lines.append("(none)")

    lines.append("\n## Saved sessions (on-disk, survive restarts)")
    save_dir = _browser_data_dir()
    saved = sorted(save_dir.glob("*.json"))
    if saved:
        for p in saved:
            try:
                state = json.loads(p.read_text(encoding="utf-8"))
                n_cookies = len(state.get("cookies", []))
                mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                active_marker = " ✓ active" if _NAMED_SESSIONS.get(p.stem) in active else ""
                lines.append(f"- {p.stem} — {n_cookies} cookies, saved {mtime}{active_marker}")
            except Exception:
                lines.append(f"- {p.stem} — (unreadable)")
    else:
        lines.append("(none — use browser_save_session() after logging in to a site)")

    return "\n".join(lines)


async def _browser_open(url: str, session_id: str = "") -> str:
    normalized_url, err = _normalize_browser_url(url)
    if err:
        return err

    sid = (session_id or "").strip()
    entry = await _browser_get_session(sid) if sid else None
    if entry is None:
        sid, entry, create_err = await _browser_create_session()
        if create_err:
            return create_err
    if not sid or entry is None:
        return "browser_open failed: could not create or find a browser session"

    page = entry.get("page")
    try:
        await page.goto(normalized_url, wait_until="domcontentloaded", timeout=_BROWSER_NAV_TIMEOUT_MS)
    except Exception as exc:
        return f"browser_open failed: navigation error for {normalized_url} ({exc})"

    payload = await _browser_snapshot_payload(page)
    return _format_browser_snapshot(sid, payload)


async def _browser_navigate(session_id: str, url: str) -> str:
    normalized_url, err = _normalize_browser_url(url)
    if err:
        return err.replace("browser_open", "browser_navigate")
    entry = await _browser_get_session(session_id)
    if entry is None:
        return f"browser_navigate failed: unknown or expired session '{session_id}'"
    page = entry.get("page")
    try:
        await page.goto(normalized_url, wait_until="domcontentloaded", timeout=_BROWSER_NAV_TIMEOUT_MS)
    except Exception as exc:
        return f"browser_navigate failed: navigation error for {normalized_url} ({exc})"
    payload = await _browser_snapshot_payload(page)
    return _format_browser_snapshot(session_id, payload)


async def _browser_snapshot(session_id: str) -> str:
    entry = await _browser_get_session(session_id)
    if entry is None:
        return f"browser_snapshot failed: unknown or expired session '{session_id}'"
    payload = await _browser_snapshot_payload(entry.get("page"))
    return _format_browser_snapshot(session_id, payload)


async def _browser_fill_field(session_id: str, field: str, value: str) -> str:
    entry = await _browser_get_session(session_id)
    if entry is None:
        return f"browser_fill_field failed: unknown or expired session '{session_id}'"
    field = (field or "").strip()
    if not field:
        return "browser_fill_field failed: missing field name/selector"

    page = entry.get("page")
    escaped = _escape_css_attr(field)
    attempts = []
    if _looks_like_selector(field):
        attempts.append(("selector", page.locator(field)))
    attempts.extend(
        [
            ("label", page.get_by_label(field, exact=False)),
            ("placeholder", page.get_by_placeholder(field, exact=False)),
            ("id", page.locator(f"#{escaped}")),
            ("name", page.locator(f'input[name="{escaped}"], textarea[name="{escaped}"], select[name="{escaped}"]')),
        ]
    )

    for source, locator in attempts:
        try:
            count = await locator.count()
            if count <= 0:
                continue
            first = locator.first
            tag_name = (await first.evaluate("el => (el.tagName || '').toLowerCase()")).strip()
            if tag_name == "select":
                await first.select_option(value=value, timeout=_BROWSER_NAV_TIMEOUT_MS)
            else:
                await first.fill(value, timeout=_BROWSER_NAV_TIMEOUT_MS)
            return f"Filled field '{field}' via {source} in browser session {session_id}. Current URL: {page.url}"
        except Exception:
            continue

    return (
        f"browser_fill_field failed: could not find fillable field '{field}'. "
        "Call browser_snapshot to inspect available inputs and use id/name/placeholder."
    )


async def _browser_click(session_id: str, target: str, target_type: str = "auto") -> str:
    entry = await _browser_get_session(session_id)
    if entry is None:
        return f"browser_click failed: unknown or expired session '{session_id}'"
    target = (target or "").strip()
    if not target:
        return "browser_click failed: missing target"

    page = entry.get("page")
    mode = (target_type or "auto").strip().lower()
    locator_attempts = []
    if mode == "selector" or (mode == "auto" and _looks_like_selector(target)):
        locator_attempts.append(("selector", page.locator(target)))
    if mode in {"auto", "text"}:
        locator_attempts.extend(
            [
                ("button_text", page.get_by_role("button", name=target, exact=False)),
                ("link_text", page.get_by_role("link", name=target, exact=False)),
                ("text", page.get_by_text(target, exact=False)),
            ]
        )

    for source, locator in locator_attempts:
        try:
            count = await locator.count()
            if count <= 0:
                continue
            await locator.first.click(timeout=_BROWSER_NAV_TIMEOUT_MS)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass
            return (
                f"Clicked '{target}' via {source} in browser session {session_id}. "
                f"Now at: {page.url}"
            )
        except Exception:
            continue

    return (
        f"browser_click failed: target '{target}' not found/clickable. "
        "Call browser_snapshot and use an exact button/link text or CSS selector."
    )


async def _browser_close(session_id: str) -> str:
    sid = (session_id or "").strip()
    if not sid:
        return "browser_close failed: missing session_id"
    entry = None
    async with _BROWSER_SESSION_LOCK:
        entry = _BROWSER_SESSIONS.pop(sid, None)
    if entry is None:
        return f"browser_close: session '{sid}' is already closed or unknown"
    await _close_browser_session_entry(entry)
    return f"Closed browser session {sid}."


async def _get_datetime() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("UTC: %A, %B %d %Y — %H:%M:%S")


# Safe math evaluator — no eval(), only whitelisted AST nodes
_OPS = {
    ast.Add:  operator.add,
    ast.Sub:  operator.sub,
    ast.Mult: operator.mul,
    ast.Div:  operator.truediv,
    ast.Pow:  operator.pow,
    ast.Mod:  operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval_node(node.operand))
    raise ValueError(f"Unsupported: {ast.dump(node)}")

async def _calculate(expression: str) -> str:
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval_node(tree.body)
        # Format: strip unnecessary .0 for whole numbers
        if isinstance(result, float) and result.is_integer():
            return f"{expression} = {int(result)}"
        return f"{expression} = {result}"
    except Exception as e:
        return f"Could not evaluate '{expression}': {e}"


# ─── Task tool executors ──────────────────────────────────────────────────────

async def _create_task(
    title: str,
    description: str,
    assignee: str,
    due_date: str,
    room_id: Optional[str],
    user_id: Optional[str],
    session,
) -> str:
    if not room_id or not user_id or session is None:
        return "Task creation unavailable (no room/session context)."
    from app.crud import create_task, get_chat_user_by_username
    import uuid as _uuid
    from datetime import datetime

    assigned_uuid: Optional[_uuid.UUID] = None
    if assignee:
        assignee_user = get_chat_user_by_username(session, assignee.lstrip("@"))
        if not assignee_user:
            return f"User '{assignee}' not found — task not created."
        assigned_uuid = assignee_user.id

    due: Optional[datetime] = None
    if due_date:
        try:
            due = datetime.fromisoformat(due_date)
        except ValueError:
            pass

    task = create_task(
        session=session,
        room_id=_uuid.UUID(room_id),
        created_by=_uuid.UUID(user_id),
        title=title,
        description=description or None,
        assigned_to=assigned_uuid,
        due_date=due,
    )
    short_id = str(task.id)[:8]
    assign_note = f", assigned to @{assignee}" if assignee else ""
    due_note = f", due {due_date}" if due_date else ""
    return f"Task created [{short_id}]: {task.title}{assign_note}{due_note}"


async def _list_tasks(
    filter: str,
    room_id: Optional[str],
    session,
) -> str:
    if not room_id or session is None:
        return "Task listing unavailable (no room/session context)."
    from app.crud import get_tasks
    from app.models import TaskStatus
    import uuid as _uuid

    status_map = {"open": TaskStatus.OPEN, "done": TaskStatus.DONE, "all": None}
    status = status_map.get(filter or "open", TaskStatus.OPEN)

    tasks = get_tasks(session, _uuid.UUID(room_id), status=status)
    if not tasks:
        label = filter or "open"
        return f"No {label} tasks in this room."

    lines = []
    for t in tasks:
        short_id = str(t.id)[:8]
        status_icon = "✅" if str(t.status).endswith("DONE") else "⬜"
        assignee = f" (@{t.assigned_to})" if t.assigned_to else ""
        due = f" [due {t.due_date.date()}]" if t.due_date else ""
        lines.append(f"{status_icon} [{short_id}] {t.title}{assignee}{due}")
    return "\n".join(lines)


async def _complete_task(
    task_id: str,
    room_id: Optional[str],
    session,
) -> str:
    if not task_id or session is None:
        return "No task ID provided."
    from app.crud import complete_task, get_tasks
    from app.models import TaskStatus
    import uuid as _uuid

    # Accept short (8-char prefix) or full UUID
    resolved_id: Optional[_uuid.UUID] = None
    if len(task_id) == 36:
        try:
            resolved_id = _uuid.UUID(task_id)
        except ValueError:
            pass
    if resolved_id is None and room_id:
        # Match by short prefix
        all_tasks = get_tasks(session, _uuid.UUID(room_id))
        for t in all_tasks:
            if str(t.id).startswith(task_id):
                resolved_id = t.id
                break

    if not resolved_id:
        return f"Task '{task_id}' not found."

    task = complete_task(session, resolved_id)
    if not task:
        return f"Task '{task_id}' not found."
    return f"Task marked done: {task.title}"


# ─── GitHub tool executors ────────────────────────────────────────────────────

def _gh_headers() -> dict:
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = _github_token()
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _resolve_repo(repo: str) -> str | None:
    r = (repo or "").strip() or _github_default_repo()
    return r if r else None


def _gh_not_configured() -> str:
    return (
        "GitHub not configured. Set GITHUB_TOKEN and optionally GITHUB_DEFAULT_REPO "
        "environment variables."
    )


async def _github_list_prs(repo: str, state: str) -> str:
    r = _resolve_repo(repo)
    if not r:
        return _gh_not_configured() if not _github_token() else "No repo specified. Set GITHUB_DEFAULT_REPO or pass a repo name."
    state = state if state in ("open", "closed", "all") else "open"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{r}/pulls",
                headers=_gh_headers(),
                params={"state": state, "per_page": 15, "sort": "updated", "direction": "desc"},
            )
            resp.raise_for_status()
            prs = resp.json()
    except Exception as exc:
        return f"GitHub API error: {exc}"

    if not prs:
        return f"No {state} pull requests in {r}."

    lines = []
    for pr in prs:
        num = pr["number"]
        title = pr["title"]
        author = pr.get("user", {}).get("login", "?")
        draft = " [DRAFT]" if pr.get("draft") else ""
        reviews = pr.get("requested_reviewers", [])
        rev_note = f" — {len(reviews)} reviewer(s) requested" if reviews else ""
        lines.append(f"#{num}{draft} **{title}** by @{author}{rev_note}")

    return f"{state.title()} PRs in {r} ({len(prs)}):\n\n" + "\n".join(lines)


async def _github_get_pr(repo: str, pr_number: int) -> str:
    r = _resolve_repo(repo)
    if not r:
        return _gh_not_configured() if not _github_token() else "No repo specified."
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # PR details + files + checks in parallel
            pr_resp, files_resp, checks_resp = await asyncio.gather(
                client.get(f"{_GITHUB_API}/repos/{r}/pulls/{pr_number}", headers=_gh_headers()),
                client.get(f"{_GITHUB_API}/repos/{r}/pulls/{pr_number}/files", headers=_gh_headers(), params={"per_page": 30}),
                client.get(f"{_GITHUB_API}/repos/{r}/commits/$(echo)/check-runs", headers=_gh_headers()),
                return_exceptions=True,
            )
            pr = pr_resp.json() if not isinstance(pr_resp, Exception) else {}
            files = files_resp.json() if not isinstance(files_resp, Exception) else []
            # Get check runs via PR head SHA
            head_sha = pr.get("head", {}).get("sha", "")
            checks: list = []
            if head_sha:
                cr = await client.get(
                    f"{_GITHUB_API}/repos/{r}/commits/{head_sha}/check-runs",
                    headers=_gh_headers(),
                    params={"per_page": 10},
                )
                if cr.status_code == 200:
                    checks = cr.json().get("check_runs", [])
    except Exception as exc:
        return f"GitHub API error: {exc}"

    if not pr:
        return f"PR #{pr_number} not found in {r}."

    title = pr.get("title", "")
    author = pr.get("user", {}).get("login", "?")
    state = pr.get("state", "?")
    draft = " (draft)" if pr.get("draft") else ""
    body = (pr.get("body") or "").strip()[:500]
    body_note = f"\n\n{body}" if body else ""
    mergeable = pr.get("mergeable_state", "?")
    additions = pr.get("additions", 0)
    deletions = pr.get("deletions", 0)

    file_lines = [f"  - `{f['filename']}` +{f['additions']}/-{f['deletions']}" for f in (files if isinstance(files, list) else [])[:20]]
    files_section = ("\n\nChanged files:\n" + "\n".join(file_lines)) if file_lines else ""

    check_lines = []
    for c in checks:
        icon = {"success": "✅", "failure": "❌", "neutral": "⬜", "skipped": "⏭️"}.get(c.get("conclusion", ""), "🔄")
        check_lines.append(f"  {icon} {c['name']}: {c.get('conclusion') or c.get('status', '?')}")
    checks_section = ("\n\nCI checks:\n" + "\n".join(check_lines)) if check_lines else ""

    return (
        f"**PR #{pr_number}: {title}**{draft}\n"
        f"Author: @{author} | State: {state} | Mergeable: {mergeable}\n"
        f"Changes: +{additions}/-{deletions}"
        f"{body_note}{files_section}{checks_section}"
    )


async def _github_create_issue(repo: str, title: str, body: str, labels: str) -> str:
    r = _resolve_repo(repo)
    if not r:
        return _gh_not_configured() if not _github_token() else "No repo specified."
    if not _github_token():
        return _gh_not_configured()
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = [l.strip() for l in labels.split(",") if l.strip()]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_GITHUB_API}/repos/{r}/issues",
                headers=_gh_headers(),
                json=payload,
            )
            resp.raise_for_status()
            issue = resp.json()
    except Exception as exc:
        return f"GitHub API error: {exc}"

    num = issue.get("number")
    url = issue.get("html_url", "")
    return f"Issue #{num} created in {r}: **{title}**\n{url}"


async def _github_get_ci_status(repo: str, branch: str) -> str:
    r = _resolve_repo(repo)
    if not r:
        return _gh_not_configured() if not _github_token() else "No repo specified."
    branch = branch or "main"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_GITHUB_API}/repos/{r}/actions/runs",
                headers=_gh_headers(),
                params={"branch": branch, "per_page": 5},
            )
            resp.raise_for_status()
            runs = resp.json().get("workflow_runs", [])
    except Exception as exc:
        return f"GitHub API error: {exc}"

    if not runs:
        return f"No CI runs found for branch '{branch}' in {r}."

    icons = {"success": "✅", "failure": "❌", "cancelled": "🚫", "skipped": "⏭️", "in_progress": "🔄", "queued": "⏳"}
    lines = []
    for run in runs:
        icon = icons.get(run.get("conclusion") or run.get("status", ""), "❓")
        name = run.get("name", "?")
        status = run.get("conclusion") or run.get("status", "?")
        updated = run.get("updated_at", "")[:10]
        commit_msg = run.get("head_commit", {}).get("message", "")[:60]
        lines.append(f"{icon} **{name}** — {status} ({updated})\n   _{commit_msg}_")

    return f"CI runs on `{branch}` in {r}:\n\n" + "\n\n".join(lines)


# ─── Slack tool executors ─────────────────────────────────────────────────────

def _slack_configured() -> bool:
    return bool(_SLACK_BOT_TOKEN)


def _slack_headers() -> dict:
    return {"Authorization": f"Bearer {_SLACK_BOT_TOKEN}", "Content-Type": "application/json"}


def _slack_not_configured() -> str:
    return "Slack not configured. Set the SLACK_BOT_TOKEN environment variable."


async def _slack_send_message(channel: str, text: str, thread_ts: str = "") -> str:
    if not _slack_configured():
        return _slack_not_configured()
    ch = (channel or _SLACK_DEFAULT_CHANNEL).strip()
    if not ch:
        return "No channel specified. Pass a channel name or set SLACK_DEFAULT_CHANNEL."
    if not text:
        return "No message text provided."
    payload: dict = {"channel": ch, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_SLACK_API}/chat.postMessage",
                headers=_slack_headers(),
                json=payload,
            )
            data = resp.json()
    except Exception as exc:
        return f"Slack API error: {exc}"
    if not data.get("ok"):
        return f"Slack error: {data.get('error', 'unknown')}"
    return f"Message sent to {ch}."


async def _slack_list_channels(limit: int = 20) -> str:
    if not _slack_configured():
        return _slack_not_configured()
    limit = max(1, min(limit, 100))
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_SLACK_API}/conversations.list",
                headers=_slack_headers(),
                params={"limit": limit, "exclude_archived": "true", "types": "public_channel"},
            )
            data = resp.json()
    except Exception as exc:
        return f"Slack API error: {exc}"
    if not data.get("ok"):
        return f"Slack error: {data.get('error', 'unknown')}"
    channels = data.get("channels", [])
    if not channels:
        return "No public channels found."
    lines = [f"#{c['name']} (ID: {c['id']}){' [archived]' if c.get('is_archived') else ''}" for c in channels]
    return f"Slack channels ({len(lines)}):\n" + "\n".join(lines)


async def _slack_get_channel_history(channel: str, limit: int = 10) -> str:
    if not _slack_configured():
        return _slack_not_configured()
    if not channel:
        return "No channel specified."
    limit = max(1, min(limit, 50))
    # Resolve channel name → ID if it starts with #
    ch = channel.lstrip("#")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # If it looks like a channel ID (starts with C) use directly, else look up
            if not ch.startswith("C"):
                list_resp = await client.get(
                    f"{_SLACK_API}/conversations.list",
                    headers=_slack_headers(),
                    params={"limit": 200, "exclude_archived": "true"},
                )
                list_data = list_resp.json()
                ch_id = next(
                    (c["id"] for c in list_data.get("channels", []) if c["name"] == ch),
                    None,
                )
                if not ch_id:
                    return f"Channel '#{ch}' not found."
            else:
                ch_id = ch

            hist_resp = await client.get(
                f"{_SLACK_API}/conversations.history",
                headers=_slack_headers(),
                params={"channel": ch_id, "limit": limit},
            )
            hist_data = hist_resp.json()
    except Exception as exc:
        return f"Slack API error: {exc}"

    if not hist_data.get("ok"):
        return f"Slack error: {hist_data.get('error', 'unknown')}"

    messages = hist_data.get("messages", [])
    if not messages:
        return f"No messages in #{ch}."

    lines = []
    for msg in reversed(messages):  # oldest first
        user = msg.get("user", msg.get("username", "?"))
        text = (msg.get("text") or "").replace("\n", " ")[:200]
        ts = msg.get("ts", "")
        try:
            from datetime import datetime
            dt = datetime.fromtimestamp(float(ts)).strftime("%H:%M")
        except Exception:
            dt = ts
        lines.append(f"[{dt}] @{user}: {text}")

    return f"Recent messages in #{ch}:\n" + "\n".join(lines)


# ─── Notion tool executors ────────────────────────────────────────────────────

def _notion_headers() -> dict:
    return {
        "Authorization": f"Bearer {_NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }


def _notion_configured() -> bool:
    return bool(_NOTION_TOKEN)


def _notion_extract_page_id(page_id_or_url: str) -> str:
    """Return bare UUID from a page ID or Notion URL."""
    s = page_id_or_url.strip()
    # Strip URL parts: last path segment without dashes, then reformat as UUID
    if "notion.so" in s:
        s = s.split("?")[0].rstrip("/").split("/")[-1]
        # Notion URLs end in a 32-char hex string (optionally with hyphens)
        s = s.split("-")[-1]
    # Remove hyphens to get raw 32-char hex, then reinsert as UUID
    raw = s.replace("-", "")
    if len(raw) == 32:
        return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return s  # return as-is if it already looks like a UUID


def _notion_rich_text_to_plain(rich_texts: list) -> str:
    return "".join(rt.get("plain_text", "") for rt in rich_texts)


def _notion_blocks_to_text(blocks: list) -> str:
    lines = []
    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype, {})
        rich_texts = content.get("rich_text", [])
        text = _notion_rich_text_to_plain(rich_texts)
        if btype == "heading_1":
            lines.append(f"# {text}")
        elif btype == "heading_2":
            lines.append(f"## {text}")
        elif btype == "heading_3":
            lines.append(f"### {text}")
        elif btype == "bulleted_list_item":
            lines.append(f"- {text}")
        elif btype == "numbered_list_item":
            lines.append(f"1. {text}")
        elif btype == "to_do":
            checked = content.get("checked", False)
            lines.append(f"{'[x]' if checked else '[ ]'} {text}")
        elif btype == "code":
            lang = content.get("language", "")
            lines.append(f"```{lang}\n{text}\n```")
        elif btype == "quote":
            lines.append(f"> {text}")
        elif btype == "divider":
            lines.append("---")
        elif text:
            lines.append(text)
    return "\n".join(lines)


def _text_to_notion_blocks(text: str) -> list:
    """Convert plain text / simple markdown to Notion blocks (≤100)."""
    blocks = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": [{"type": "text", "text": {"content": stripped[4:]}}]}})
        elif stripped.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": [{"type": "text", "text": {"content": stripped[3:]}}]}})
        elif stripped.startswith("# "):
            blocks.append({"object": "block", "type": "heading_1",
                           "heading_1": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]}})
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": stripped[2:]}}]}})
        else:
            blocks.append({"object": "block", "type": "paragraph",
                           "paragraph": {"rich_text": [{"type": "text", "text": {"content": line}}]}})
    return blocks[:100]


async def _notion_search(query: str) -> str:
    if not _notion_configured():
        return "Notion not configured. Set the NOTION_TOKEN environment variable."
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{_NOTION_API}/search",
                headers=_notion_headers(),
                json={"query": query, "filter": {"property": "object", "value": "page"}, "page_size": 10},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return f"Notion API error: {exc}"

    results = data.get("results", [])
    if not results:
        return f"No Notion pages found for '{query}'."

    lines = []
    for page in results:
        title_prop = page.get("properties", {})
        # Title can be under "title", "Name", or other key
        title = ""
        for prop in title_prop.values():
            if prop.get("type") == "title":
                title = _notion_rich_text_to_plain(prop.get("title", []))
                break
        if not title:
            title = "(Untitled)"
        url = page.get("url", "")
        lines.append(f"- **{title}**\n  {url}")

    return f"Notion pages matching '{query}' ({len(results)}):\n\n" + "\n\n".join(lines)


async def _notion_get_page(page_id: str) -> str:
    if not _notion_configured():
        return "Notion not configured. Set the NOTION_TOKEN environment variable."
    pid = _notion_extract_page_id(page_id)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            page_resp, blocks_resp = await asyncio.gather(
                client.get(f"{_NOTION_API}/pages/{pid}", headers=_notion_headers()),
                client.get(f"{_NOTION_API}/blocks/{pid}/children", headers=_notion_headers(), params={"page_size": 100}),
            )
            if page_resp.status_code == 404:
                return f"Notion page '{page_id}' not found."
            page_resp.raise_for_status()
            blocks_resp.raise_for_status()
            page = page_resp.json()
            blocks = blocks_resp.json().get("results", [])
    except Exception as exc:
        return f"Notion API error: {exc}"

    # Extract title
    title = ""
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            title = _notion_rich_text_to_plain(prop.get("title", []))
            break
    url = page.get("url", "")
    body = _notion_blocks_to_text(blocks)

    return f"**{title or '(Untitled)'}**\n{url}\n\n{body or '(No text content)'}"


async def _notion_create_page(title: str, content: str, parent_id: str = "") -> str:
    if not _notion_configured():
        return "Notion not configured. Set the NOTION_TOKEN environment variable."
    pid = (parent_id or _NOTION_DEFAULT_PARENT_ID).strip()
    if not pid:
        return (
            "No parent page specified. Pass parent_id or set NOTION_DEFAULT_PARENT_ID."
        )
    pid = _notion_extract_page_id(pid)
    blocks = _text_to_notion_blocks(content)
    payload = {
        "parent": {"page_id": pid},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": blocks,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_NOTION_API}/pages",
                headers=_notion_headers(),
                json=payload,
            )
            resp.raise_for_status()
            page = resp.json()
    except Exception as exc:
        return f"Notion API error: {exc}"

    url = page.get("url", "")
    return f"Notion page created: **{title}**\n{url}"


# ─── Confluence tool executors ─────────────────────────────────────────────────

def _confluence_configured() -> bool:
    return bool(_CONFLUENCE_URL and _CONFLUENCE_USERNAME and _CONFLUENCE_API_TOKEN)


def _cf_auth() -> tuple[str, str]:
    return (_CONFLUENCE_USERNAME, _CONFLUENCE_API_TOKEN)


def _cf_not_configured() -> str:
    return (
        "Confluence not configured. Set CONFLUENCE_URL, CONFLUENCE_USERNAME, "
        "and CONFLUENCE_API_TOKEN environment variables."
    )


def _strip_html(html: str) -> str:
    """Very basic HTML → plain text for Confluence storage format."""
    import re
    # Replace block tags with newlines
    html = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Strip all remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Collapse whitespace
    lines = [ln.strip() for ln in html.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


async def _confluence_search(query: str, space_key: str = "") -> str:
    if not _confluence_configured():
        return _cf_not_configured()
    cql = f'text ~ "{query}"'
    if space_key:
        cql += f' AND space.key = "{space_key}"'
    cql += " ORDER BY lastmodified DESC"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_CONFLUENCE_URL}/wiki/rest/api/content/search",
                auth=_cf_auth(),
                params={"cql": cql, "limit": 10, "expand": "excerpt,space"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        return f"Confluence API error: {exc}"

    results = data.get("results", [])
    if not results:
        return f"No Confluence pages found for '{query}'."

    lines = []
    for page in results:
        title = page.get("title", "(Untitled)")
        pid = page.get("id", "")
        space = page.get("space", {}).get("key", "")
        excerpt = _strip_html(page.get("excerpt", "")).replace("\n", " ")[:120]
        page_url = f"{_CONFLUENCE_URL}/wiki{page.get('_links', {}).get('webui', '')}"
        lines.append(f"- **{title}** [{space}] (ID: {pid})\n  {excerpt}\n  {page_url}")

    return f"Confluence results for '{query}' ({len(results)}):\n\n" + "\n\n".join(lines)


async def _confluence_get_page(page_id: str) -> str:
    if not _confluence_configured():
        return _cf_not_configured()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_CONFLUENCE_URL}/wiki/rest/api/content/{page_id}",
                auth=_cf_auth(),
                params={"expand": "body.storage,version,space"},
            )
            if resp.status_code == 404:
                return f"Confluence page '{page_id}' not found."
            resp.raise_for_status()
            page = resp.json()
    except Exception as exc:
        return f"Confluence API error: {exc}"

    title = page.get("title", "(Untitled)")
    space = page.get("space", {}).get("key", "")
    version = page.get("version", {}).get("number", "?")
    html_body = page.get("body", {}).get("storage", {}).get("value", "")
    body = _strip_html(html_body)[:4000]
    page_url = f"{_CONFLUENCE_URL}/wiki{page.get('_links', {}).get('webui', '')}"

    return (
        f"**{title}** [{space}] v{version}\n{page_url}\n\n"
        + (body or "(No content)")
    )


async def _confluence_create_page(
    title: str, content: str, space_key: str = "", parent_id: str = ""
) -> str:
    if not _confluence_configured():
        return _cf_not_configured()
    space = (space_key or _CONFLUENCE_DEFAULT_SPACE).strip()
    if not space:
        return "No space key provided. Pass space_key or set CONFLUENCE_DEFAULT_SPACE."

    # Wrap plain text in minimal XHTML storage format
    import html as _html
    paragraphs = "".join(
        f"<p>{_html.escape(line)}</p>" if line.strip() else "<p></p>"
        for line in content.split("\n")
    )

    payload: dict = {
        "type": "page",
        "title": title,
        "space": {"key": space},
        "body": {"storage": {"value": paragraphs, "representation": "storage"}},
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_CONFLUENCE_URL}/wiki/rest/api/content",
                auth=_cf_auth(),
                json=payload,
            )
            resp.raise_for_status()
            page = resp.json()
    except Exception as exc:
        return f"Confluence API error: {exc}"

    pid = page.get("id", "")
    page_url = f"{_CONFLUENCE_URL}/wiki{page.get('_links', {}).get('webui', '')}"
    return f"Confluence page created: **{title}** (ID: {pid})\n{page_url}"


# ─── Google Workspace executors ───────────────────────────────────────────────

def _google_configured() -> bool:
    return bool(_google_client_id() and _google_client_secret() and _google_refresh_token())


def _google_not_configured() -> str:
    return (
        "Google Workspace not configured. Set GOOGLE_CLIENT_ID, "
        "GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
    )


def _google_error_text(resp: httpx.Response, service_name: str) -> str:
    try:
        data = resp.json()
    except Exception:
        data = {}
    error_obj = data.get("error")
    if isinstance(error_obj, dict):
        error_detail = error_obj.get("message") or error_obj.get("status")
    else:
        error_detail = error_obj
    detail = (
        data.get("error_description")
        or error_detail
        or resp.text[:200]
    )
    return f"{service_name} error: {detail}"


async def _google_access_token() -> tuple[Optional[str], Optional[str]]:
    if not _google_configured():
        return None, _google_not_configured()

    credential_fingerprint = "|".join(
        [
            _google_client_id(),
            _google_client_secret(),
            _google_refresh_token(),
        ]
    )
    cached_token = str(_GOOGLE_TOKEN_CACHE.get("access_token") or "")
    expires_at = float(_GOOGLE_TOKEN_CACHE.get("expires_at") or 0.0)
    cached_fingerprint = str(_GOOGLE_TOKEN_CACHE.get("credential_fingerprint") or "")
    if cached_token and cached_fingerprint == credential_fingerprint and time.time() < expires_at - 60:
        return cached_token, None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _GOOGLE_OAUTH_TOKEN_URL,
                data={
                    "client_id": _google_client_id(),
                    "client_secret": _google_client_secret(),
                    "refresh_token": _google_refresh_token(),
                    "grant_type": "refresh_token",
                },
            )
    except Exception as exc:
        return None, f"Google OAuth error: {exc}"

    if resp.status_code != 200:
        return None, _google_error_text(resp, "Google OAuth")

    data = resp.json()
    token = data.get("access_token")
    if not token:
        return None, "Google OAuth error: access_token missing in token response."

    _GOOGLE_TOKEN_CACHE["access_token"] = token
    _GOOGLE_TOKEN_CACHE["expires_at"] = time.time() + int(data.get("expires_in", 3600))
    _GOOGLE_TOKEN_CACHE["credential_fingerprint"] = credential_fingerprint
    return str(token), None


def _google_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _gmail_header(headers: list[dict], name: str) -> str:
    target = name.lower()
    for header in headers or []:
        if str(header.get("name", "")).lower() == target:
            return str(header.get("value", ""))
    return ""


def _gmail_decode_data(data: str) -> str:
    raw = (data or "").encode("utf-8")
    raw += b"=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _gmail_extract_text(payload: Optional[dict]) -> str:
    import re

    if not payload:
        return ""

    plain_parts: list[str] = []
    html_parts: list[str] = []

    def walk(node: dict) -> None:
        mime_type = str(node.get("mimeType", ""))
        body = node.get("body") or {}
        encoded = body.get("data")
        if encoded:
            decoded = _gmail_decode_data(str(encoded))
            if decoded:
                if mime_type == "text/plain":
                    plain_parts.append(decoded)
                elif mime_type == "text/html":
                    html_parts.append(re.sub(r"<[^>]+>", " ", decoded))
        for part in node.get("parts") or []:
            if isinstance(part, dict):
                walk(part)

    walk(payload)

    for part in plain_parts + html_parts:
        flattened = " ".join(part.split()).strip()
        if flattened:
            return flattened
    return ""


def _gmail_summary(message: dict, include_body: bool = False) -> str:
    payload = message.get("payload") or {}
    headers = payload.get("headers") or []
    body = _gmail_extract_text(payload)
    lines = [
        f"ID: {message.get('id', '')}",
        f"Subject: {_gmail_header(headers, 'Subject') or '(No Subject)'}",
        f"From: {_gmail_header(headers, 'From') or '(Unknown)'}",
        f"Date: {_gmail_header(headers, 'Date') or '(Unknown)'}",
    ]
    snippet = " ".join((message.get("snippet") or body or "").split()).strip()
    if include_body:
        preview = body or snippet or "(No readable body)"
        lines.extend(["", (preview[:5000] + ("..." if len(preview) > 5000 else ""))])
    elif snippet:
        lines.append(f"Snippet: {snippet[:300]}{'...' if len(snippet) > 300 else ''}")
    return "\n".join(lines)


async def _gmail_get_message_by_id(message_id: str) -> tuple[Optional[dict], Optional[str]]:
    token, err = await _google_access_token()
    if err:
        return None, err

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_GMAIL_API}/users/{_google_gmail_user()}/messages/{message_id}",
                headers=_google_headers(token),
                params={"format": "full"},
            )
    except Exception as exc:
        return None, f"Gmail API error: {exc}"

    if resp.status_code != 200:
        return None, _google_error_text(resp, "Gmail API")
    return resp.json(), None


async def _gmail_fetch_inbox(max_emails: int = 5, unread_only: bool = False) -> str:
    token, err = await _google_access_token()
    if err:
        return err

    max_emails = max(1, min(max_emails, 20))
    params: dict[str, object] = {
        "maxResults": max_emails,
        "labelIds": ["INBOX"],
        "includeSpamTrash": "false",
    }
    if unread_only:
        params["q"] = "is:unread"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_GMAIL_API}/users/{_google_gmail_user()}/messages",
                headers=_google_headers(token),
                params=params,
            )
    except Exception as exc:
        return f"Gmail API error: {exc}"

    if resp.status_code != 200:
        return _google_error_text(resp, "Gmail API")

    messages = resp.json().get("messages", [])
    if not messages:
        return "No Gmail messages found." if unread_only else "Gmail inbox is empty."

    details = await asyncio.gather(
        *(_gmail_get_message_by_id(str(msg.get("id", ""))) for msg in messages if msg.get("id")),
    )
    summaries = [summary for message, summary in details if not message and summary]
    summaries += [_gmail_summary(message) for message, summary in details if message]
    return (
        f"Gmail inbox ({len(summaries)} message{'s' if len(summaries) != 1 else ''}):\n\n"
        + "\n\n---\n\n".join(summaries)
    )


async def _gmail_search(query: str, max_results: int = 5) -> str:
    token, err = await _google_access_token()
    if err:
        return err

    q = (query or "").strip()
    if not q:
        return "Gmail search failed: empty query."
    max_results = max(1, min(max_results, 20))

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_GMAIL_API}/users/{_google_gmail_user()}/messages",
                headers=_google_headers(token),
                params={"q": q, "maxResults": max_results, "includeSpamTrash": "false"},
            )
    except Exception as exc:
        return f"Gmail API error: {exc}"

    if resp.status_code != 200:
        return _google_error_text(resp, "Gmail API")

    messages = resp.json().get("messages", [])
    if not messages:
        return f"No Gmail messages found for '{q}'."

    details = await asyncio.gather(
        *(_gmail_get_message_by_id(str(msg.get("id", ""))) for msg in messages if msg.get("id")),
    )
    summaries = [summary for message, summary in details if not message and summary]
    summaries += [_gmail_summary(message) for message, summary in details if message]
    return f"Gmail results for '{q}' ({len(summaries)}):\n\n" + "\n\n---\n\n".join(summaries)


async def _gmail_get_message(message_id: str) -> str:
    message_id = (message_id or "").strip()
    if not message_id:
        return "Missing required field: message_id."
    message, err = await _gmail_get_message_by_id(message_id)
    if err:
        return err
    return _gmail_summary(message or {}, include_body=True)


async def _gmail_send(to: str, subject: str, body: str, cc: str = "") -> str:
    from email.message import EmailMessage

    if not to or not subject or not body:
        return "Missing required fields: to, subject, body."

    token, err = await _google_access_token()
    if err:
        return err

    message = EmailMessage()
    message["To"] = to
    message["Subject"] = subject
    if cc:
        message["Cc"] = cc
    message.set_content(body)
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_GMAIL_API}/users/{_google_gmail_user()}/messages/send",
                headers=_google_headers(token),
                json={"raw": raw_message},
            )
    except Exception as exc:
        return f"Gmail API error: {exc}"

    if resp.status_code not in (200, 202):
        return _google_error_text(resp, "Gmail API")
    return f"Gmail message sent to {to}: '{subject}'"


def _drive_query_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _drive_list_params(max_results: int) -> dict[str, object]:
    params: dict[str, object] = {
        "pageSize": max_results,
        "fields": "files(id,name,mimeType,modifiedTime,webViewLink,size,owners(displayName))",
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }
    shared_drive_id = _google_drive_shared_drive_id()
    if shared_drive_id:
        params["corpora"] = "drive"
        params["driveId"] = shared_drive_id
    else:
        params["corpora"] = "user"
    return params


async def _drive_search(query: str, max_results: int = 10) -> str:
    token, err = await _google_access_token()
    if err:
        return err

    q = (query or "").strip()
    if not q:
        return "Drive search failed: empty query."
    max_results = max(1, min(max_results, 25))

    params = _drive_list_params(max_results)
    safe_q = _drive_query_escape(q)
    params["q"] = f"trashed = false and (name contains '{safe_q}' or fullText contains '{safe_q}')"
    params["orderBy"] = "modifiedTime desc"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{_DRIVE_API}/files",
                headers=_google_headers(token),
                params=params,
            )
    except Exception as exc:
        return f"Google Drive API error: {exc}"

    if resp.status_code != 200:
        return _google_error_text(resp, "Google Drive API")

    files = resp.json().get("files", [])
    if not files:
        return f"No Google Drive files found for '{q}'."

    lines = []
    for file in files:
        owner = ", ".join(
            str(owner.get("displayName", ""))
            for owner in file.get("owners", [])
            if owner.get("displayName")
        )
        meta = [
            f"ID: {file.get('id', '')}",
            f"Name: {file.get('name', '(Untitled)')}",
            f"Type: {file.get('mimeType', '(Unknown)')}",
        ]
        if owner:
            meta.append(f"Owner: {owner}")
        if file.get("modifiedTime"):
            meta.append(f"Modified: {file.get('modifiedTime')}")
        if file.get("webViewLink"):
            meta.append(f"Link: {file.get('webViewLink')}")
        lines.append("\n".join(meta))

    return f"Google Drive results for '{q}' ({len(lines)}):\n\n" + "\n\n---\n\n".join(lines)


async def _drive_get_file(file_id: str) -> str:
    token, err = await _google_access_token()
    if err:
        return err

    file_id = (file_id or "").strip()
    if not file_id:
        return "Missing required field: file_id."

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            meta_resp = await client.get(
                f"{_DRIVE_API}/files/{file_id}",
                headers=_google_headers(token),
                params={
                    "fields": "id,name,mimeType,modifiedTime,webViewLink,size",
                    "supportsAllDrives": "true",
                },
            )
    except Exception as exc:
        return f"Google Drive API error: {exc}"

    if meta_resp.status_code != 200:
        return _google_error_text(meta_resp, "Google Drive API")

    file_meta = meta_resp.json()
    mime_type = str(file_meta.get("mimeType", ""))
    file_name = str(file_meta.get("name", "(Untitled)"))
    header = (
        f"Name: {file_name}\n"
        f"ID: {file_meta.get('id', '')}\n"
        f"Type: {mime_type}\n"
        f"Modified: {file_meta.get('modifiedTime', '(Unknown)')}\n"
        f"Link: {file_meta.get('webViewLink', '')}"
    )

    export_mime = {
        "application/vnd.google-apps.document": "text/plain",
    }.get(mime_type, "")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            if export_mime:
                content_resp = await client.get(
                    f"{_DRIVE_API}/files/{file_id}/export",
                    headers=_google_headers(token),
                    params={"mimeType": export_mime},
                )
            elif mime_type.startswith("text/") or mime_type in {
                "application/json",
                "application/xml",
                "application/javascript",
            }:
                content_resp = await client.get(
                    f"{_DRIVE_API}/files/{file_id}",
                    headers=_google_headers(token),
                    params={"alt": "media", "supportsAllDrives": "true"},
                )
            else:
                content_resp = None
    except Exception as exc:
        return f"Google Drive API error: {exc}"

    if content_resp is None:
        return header + "\n\nPreview unavailable for this file type."

    if content_resp.status_code != 200:
        return header + "\n\n" + _google_error_text(content_resp, "Google Drive API")

    content = content_resp.text.strip()
    if not content:
        content = "(No readable text content)"
    if len(content) > 12000:
        content = content[:12000] + "..."
    return header + "\n\n" + content


async def _drive_create_folder(name: str, parent_id: str = "") -> str:
    token, err = await _google_access_token()
    if err:
        return err

    folder_name = (name or "").strip()
    if not folder_name:
        return "Missing required field: name."

    payload: dict[str, object] = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        payload["parents"] = [parent_id.strip()]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{_DRIVE_API}/files",
                headers=_google_headers(token),
                params={"fields": "id,name,webViewLink", "supportsAllDrives": "true"},
                json=payload,
            )
    except Exception as exc:
        return f"Google Drive API error: {exc}"

    if resp.status_code not in (200, 201):
        return _google_error_text(resp, "Google Drive API")

    folder = resp.json()
    return (
        f"Google Drive folder created: **{folder.get('name', folder_name)}** "
        f"(ID: {folder.get('id', '')})\n{folder.get('webViewLink', '')}"
    )


# ─── Server operations executors ──────────────────────────────────────────────

_SERVER_READ_COMMANDS = {
    "system_overview": "system_overview",
    "disk_usage": "disk_usage",
    "memory": "memory",
    "network_listeners": "network_listeners",
    "process_snapshot": "process_snapshot",
    "service_status": "service_status",
    "service_logs": "service_logs",
}
_SERVER_SERVICE_ACTIONS = {"start", "stop", "restart"}


def _format_allowed_list(values: set[str]) -> str:
    if not values:
        return "(none)"
    return ", ".join(sorted(values))


def _truncate_tool_output(text: str, limit: int = 12000) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text or "(no output)"
    return text[:limit] + "\n...[truncated]"


async def _run_exec(argv: list[str], timeout: int) -> tuple[int, str]:
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, f"Command not found: {argv[0]}"
    except Exception as exc:
        return 1, f"Command failed to start: {exc}"

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        return 124, f"Command timed out after {timeout} seconds."

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    if stdout_text and stderr_text:
        output = f"{stdout_text}\n\n[stderr]\n{stderr_text}"
    else:
        output = stdout_text or stderr_text or "(no output)"
    return process.returncode, _truncate_tool_output(output)


def _validate_service_name(service: str, allowed_services: set[str]) -> tuple[Optional[str], Optional[str]]:
    unit = (service or "").strip()
    if not unit:
        return None, "Missing required field: service."
    if not _SAFE_SERVICE_RE.fullmatch(unit):
        return None, "Invalid service name."
    if unit not in allowed_services:
        return None, (
            "Service is not allowed. Configure SPARKBOT_ALLOWED_SERVICES or "
            f"SPARKBOT_SSH_ALLOWED_SERVICES. Allowed: {_format_allowed_list(allowed_services)}"
        )
    return unit, None


def _validate_ssh_host(host: str) -> tuple[Optional[str], Optional[str]]:
    target = (host or "").strip()
    if not target:
        return None, "Missing required field: host."
    if not _ALLOWED_SSH_HOSTS:
        return None, "SSH access is not configured. Set SPARKBOT_SSH_ALLOWED_HOSTS to approved SSH host aliases."
    if not _SAFE_SSH_HOST_RE.fullmatch(target):
        return None, "Invalid SSH host alias."
    if target not in _ALLOWED_SSH_HOSTS:
        return None, f"SSH host is not allowed. Allowed hosts: {_format_allowed_list(_ALLOWED_SSH_HOSTS)}"
    return target, None


def _ops_profile_commands(
    command: str,
    service: str = "",
    lines: int = 50,
    *,
    allowed_services: set[str],
) -> tuple[Optional[list[tuple[str, list[str]]]], Optional[str]]:
    profile = (command or "").strip()
    if profile not in _SERVER_READ_COMMANDS:
        return None, f"Unsupported server command. Allowed: {', '.join(sorted(_SERVER_READ_COMMANDS))}"

    _is_windows = sys.platform == "win32"

    if profile == "system_overview":
        if _is_windows:
            return [
                ("uptime", ["powershell", "-NoProfile", "-Command",
                    "(Get-Date) - (gcim Win32_OperatingSystem).LastBootUpTime | "
                    "Select-Object -Property Days,Hours,Minutes | Format-List"]),
                ("disk_usage", ["powershell", "-NoProfile", "-Command",
                    "Get-PSDrive -PSProvider FileSystem | "
                    "Select-Object Name,@{N='Used(GB)';E={[math]::Round($_.Used/1GB,1)}},"
                    "@{N='Free(GB)';E={[math]::Round($_.Free/1GB,1)}} | Format-Table -AutoSize"]),
                ("memory", ["powershell", "-NoProfile", "-Command",
                    "$os=gcim Win32_OperatingSystem; "
                    "[PSCustomObject]@{"
                    "TotalGB=[math]::Round($os.TotalVisibleMemorySize/1MB,1);"
                    "FreeGB=[math]::Round($os.FreePhysicalMemory/1MB,1);"
                    "UsedGB=[math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1MB,1)"
                    "} | Format-List"]),
            ], None
        return [
            ("uptime", ["uptime"]),
            ("disk_usage", ["df", "-h", "/"]),
            ("memory", ["free", "-h"]),
        ], None
    if profile == "disk_usage":
        if _is_windows:
            return [("disk_usage", ["powershell", "-NoProfile", "-Command",
                "Get-PSDrive -PSProvider FileSystem | "
                "Select-Object Name,@{N='Used(GB)';E={[math]::Round($_.Used/1GB,1)}},"
                "@{N='Free(GB)';E={[math]::Round($_.Free/1GB,1)}} | Format-Table -AutoSize"])], None
        return [("disk_usage", ["df", "-h"])], None
    if profile == "memory":
        if _is_windows:
            return [("memory", ["powershell", "-NoProfile", "-Command",
                "$os=gcim Win32_OperatingSystem; "
                "[PSCustomObject]@{"
                "TotalGB=[math]::Round($os.TotalVisibleMemorySize/1MB,1);"
                "FreeGB=[math]::Round($os.FreePhysicalMemory/1MB,1);"
                "UsedGB=[math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1MB,1)"
                "} | Format-List"])], None
        return [("memory", ["free", "-h"])], None
    if profile == "network_listeners":
        if _is_windows:
            return [("network_listeners", ["powershell", "-NoProfile", "-Command",
                "Get-NetTCPConnection -State Listen | "
                "Select-Object LocalAddress,LocalPort,OwningProcess | "
                "Sort-Object LocalPort | Format-Table -AutoSize"])], None
        return [("network_listeners", ["ss", "-ltnp"])], None
    if profile == "process_snapshot":
        if _is_windows:
            return [("process_snapshot", ["powershell", "-NoProfile", "-Command",
                "Get-Process | Sort-Object CPU -Descending | Select-Object -First 20 "
                "Id,ProcessName,@{N='CPU(s)';E={[math]::Round($_.CPU,1)}},"
                "@{N='Mem(MB)';E={[math]::Round($_.WorkingSet/1MB,1)}} | Format-Table -AutoSize"])], None
        return [("process_snapshot", ["ps", "-eo", "pid,ppid,%cpu,%mem,comm", "--sort=-%cpu"])], None

    unit, err = _validate_service_name(service, allowed_services)
    if err:
        return None, err

    if profile == "service_status":
        if _is_windows:
            return [("service_status", ["powershell", "-NoProfile", "-Command",
                f"Get-Service -Name '{unit}' | Select-Object Name,Status,StartType | Format-List"])], None
        return [("service_status", ["systemctl", "status", "--no-pager", unit])], None

    safe_lines = max(1, min(int(lines), 200))
    if _is_windows:
        return [("service_logs", ["powershell", "-NoProfile", "-Command",
            f"Get-EventLog -LogName Application -Source '{unit}' -Newest {safe_lines} "
            f"-ErrorAction SilentlyContinue | Format-List TimeGenerated,EntryType,Message"])], None
    return [("service_logs", ["journalctl", "-u", unit, "-n", str(safe_lines), "--no-pager"])], None


async def _run_profile_commands(commands: list[tuple[str, list[str]]], timeout: int) -> str:
    sections: list[str] = []
    for label, argv in commands:
        code, output = await _run_exec(argv, timeout=timeout)
        heading = f"== {label} ==\n$ {' '.join(shlex.quote(arg) for arg in argv)}"
        body = output
        if code != 0:
            body = f"(exit {code})\n{output}"
        sections.append(f"{heading}\n{body}")
    return "\n\n".join(sections)


async def _server_read_command(command: str, service: str = "", lines: int = 50) -> str:
    commands, err = _ops_profile_commands(
        command,
        service,
        lines,
        allowed_services=_ALLOWED_LOCAL_SERVICES,
    )
    if err:
        return err
    return await _run_profile_commands(commands or [], timeout=_SERVER_COMMAND_TIMEOUT_SECONDS)


async def _server_manage_service(service: str, action: str) -> str:
    unit, err = _validate_service_name(service, _ALLOWED_LOCAL_SERVICES)
    if err:
        return err

    op = (action or "").strip().lower()
    if op in {"status", "service_status", "show_status"}:
        return await _server_read_command("service_status", service=unit)
    if op in {"logs", "log", "service_logs", "show_logs"}:
        return await _server_read_command("service_logs", service=unit, lines=50)
    if op not in _SERVER_SERVICE_ACTIONS:
        return (
            f"Unsupported service action. Allowed: {', '.join(sorted(_SERVER_SERVICE_ACTIONS))}. "
            "For status or logs, use the read-only server command tool."
        )

    if sys.platform == "win32":
        ps_action = {"start": "Start-Service", "stop": "Stop-Service", "restart": "Restart-Service"}[op]
        argv = ["powershell", "-NoProfile", "-Command", f"{ps_action} -Name '{unit}'"]
    else:
        argv = ["systemctl", op, unit]
        if _SERVICE_USE_SUDO:
            argv = ["sudo", "-n", *argv]

    code, output = await _run_exec(argv, timeout=_SERVER_COMMAND_TIMEOUT_SECONDS)
    if code != 0:
        if not sys.platform == "win32" and _SERVICE_USE_SUDO and ("password" in output.lower() or "sudo" in output.lower()):
            return (
                f"FAILED: service action failed for {unit}. Passwordless sudo may be required for this Sparkbot service user.\n\n{output}"
            )
        return f"FAILED: service action failed for {unit}.\n\n{output}"

    return f"SUCCESS: service action succeeded: {op} {unit}\n\n{output}"


def _build_ssh_script(commands: list[tuple[str, list[str]]]) -> str:
    script_parts = ["set -euo pipefail"]
    for label, argv in commands:
        script_parts.append(f"printf '%s\\n' {shlex.quote(f'== {label} ==')}")
        script_parts.append(" ".join(shlex.quote(arg) for arg in argv))
        script_parts.append("printf '\\n'")
    return "; ".join(script_parts)


async def _ssh_read_command(host: str, command: str, service: str = "", lines: int = 50) -> str:
    target, err = _validate_ssh_host(host)
    if err:
        return err

    allowed_remote_services = _ALLOWED_SSH_SERVICES or _ALLOWED_LOCAL_SERVICES
    commands, profile_err = _ops_profile_commands(
        command,
        service,
        lines,
        allowed_services=allowed_remote_services,
    )
    if profile_err:
        return profile_err

    script = _build_ssh_script(commands or [])
    argv = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={_SSH_CONNECT_TIMEOUT_SECONDS}",
        target,
        "bash",
        "-lc",
        script,
    ]
    code, output = await _run_exec(argv, timeout=_SSH_COMMAND_TIMEOUT_SECONDS)
    if code != 0:
        return f"SSH command failed for {target}.\n\n{output}"
    return f"SSH results from {target}:\n\n{output}"


# ─── Email tool executors ─────────────────────────────────────────────────────

def _email_configured_imap() -> bool:
    return bool(_EMAIL_IMAP_HOST and _EMAIL_IMAP_USERNAME and _EMAIL_IMAP_PASSWORD)


def _email_configured_smtp() -> bool:
    return bool(_EMAIL_SMTP_HOST and _EMAIL_SMTP_USERNAME and _EMAIL_SMTP_PASSWORD)


def _decode_header_val(raw: str) -> str:
    """Decode RFC 2047 encoded email header value."""
    import email.header as _hdr
    parts = _hdr.decode_header(raw or "")
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(str(part))
    return " ".join(out)


def _extract_text_from_msg(msg) -> str:
    """Extract plain-text body from an email.message.Message object."""
    import re
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    return re.sub(r"<[^>]+>", " ", html).strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def _imap_fetch_sync(max_emails: int, unread_only: bool) -> str:
    import imaplib
    import email as _email

    if not _email_configured_imap():
        return "Email not configured. Set EMAIL_IMAP_HOST, EMAIL_IMAP_USERNAME, EMAIL_IMAP_PASSWORD."

    with imaplib.IMAP4_SSL(_EMAIL_IMAP_HOST, _EMAIL_IMAP_PORT) as imap:
        imap.login(_EMAIL_IMAP_USERNAME, _EMAIL_IMAP_PASSWORD)
        imap.select("INBOX")
        criteria = "UNSEEN" if unread_only else "ALL"
        _, data = imap.search(None, criteria)
        ids = data[0].split()
        if not ids:
            return "No emails found." if unread_only else "Inbox is empty."

        recent = ids[-max_emails:][::-1]  # newest first
        results = []
        for mid in recent:
            _, msg_data = imap.fetch(mid, "(RFC822)")
            msg = _email.message_from_bytes(msg_data[0][1])
            subject = _decode_header_val(msg.get("Subject", "(No Subject)"))
            from_addr = _decode_header_val(msg.get("From", ""))
            date = msg.get("Date", "")
            body = _extract_text_from_msg(msg)
            snippet = " ".join(body[:300].split())  # flatten whitespace
            results.append(f"**{subject}**\nFrom: {from_addr}\nDate: {date}\n{snippet}{'…' if len(body) > 300 else ''}")

        label = "unread " if unread_only else ""
        total = len(ids)
        header = f"Showing {len(recent)} of {total} {label}emails:\n\n"
        return header + "\n\n---\n\n".join(results)


async def _email_fetch_inbox(max_emails: int = 5, unread_only: bool = False) -> str:
    max_emails = max(1, min(max_emails, 20))
    return await asyncio.to_thread(_imap_fetch_sync, max_emails, unread_only)


def _imap_search_sync(query: str, max_results: int) -> str:
    import imaplib
    import email as _email

    if not _email_configured_imap():
        return "Email not configured. Set EMAIL_IMAP_HOST, EMAIL_IMAP_USERNAME, EMAIL_IMAP_PASSWORD."

    with imaplib.IMAP4_SSL(_EMAIL_IMAP_HOST, _EMAIL_IMAP_PORT) as imap:
        imap.login(_EMAIL_IMAP_USERNAME, _EMAIL_IMAP_PASSWORD)
        imap.select("INBOX")
        # Search subject OR from
        safe_q = query.replace('"', "'")
        _, sub_data = imap.search(None, f'SUBJECT "{safe_q}"')
        _, frm_data = imap.search(None, f'FROM "{safe_q}"')
        sub_ids = set(sub_data[0].split())
        frm_ids = set(frm_data[0].split())
        all_ids = sorted(sub_ids | frm_ids, key=lambda x: int(x))

        if not all_ids:
            return f"No emails found matching '{query}'."

        recent = all_ids[-max_results:][::-1]
        results = []
        for mid in recent:
            _, msg_data = imap.fetch(mid, "(RFC822)")
            msg = _email.message_from_bytes(msg_data[0][1])
            subject = _decode_header_val(msg.get("Subject", "(No Subject)"))
            from_addr = _decode_header_val(msg.get("From", ""))
            date = msg.get("Date", "")
            results.append(f"**{subject}**\nFrom: {from_addr}\nDate: {date}")

        return (
            f"Found {len(all_ids)} email(s) matching '{query}' "
            f"(showing {len(recent)}):\n\n" + "\n\n---\n\n".join(results)
        )


async def _email_search(query: str, max_results: int = 5) -> str:
    max_results = max(1, min(max_results, 20))
    return await asyncio.to_thread(_imap_search_sync, query, max_results)


def _smtp_send_sync(to: str, subject: str, body: str, cc: str) -> str:
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    if not _email_configured_smtp():
        return "Email sending not configured. Set EMAIL_SMTP_HOST, EMAIL_SMTP_USERNAME, EMAIL_SMTP_PASSWORD."

    msg = MIMEMultipart()
    msg["From"] = f"{_EMAIL_FROM_NAME} <{_EMAIL_SMTP_USERNAME}>"
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain", "utf-8"))

    recipients = [to] + ([cc] if cc else [])
    try:
        if _EMAIL_SMTP_PORT == 465:
            with smtplib.SMTP_SSL(_EMAIL_SMTP_HOST, _EMAIL_SMTP_PORT) as server:
                server.login(_EMAIL_SMTP_USERNAME, _EMAIL_SMTP_PASSWORD)
                server.sendmail(_EMAIL_SMTP_USERNAME, recipients, msg.as_string())
        else:
            with smtplib.SMTP(_EMAIL_SMTP_HOST, _EMAIL_SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(_EMAIL_SMTP_USERNAME, _EMAIL_SMTP_PASSWORD)
                server.sendmail(_EMAIL_SMTP_USERNAME, recipients, msg.as_string())
        return f"Email sent to {to}: '{subject}'"
    except Exception as exc:
        return f"Failed to send email: {exc}"


async def _email_send(to: str, subject: str, body: str, cc: str = "") -> str:
    if not to or not subject or not body:
        return "Missing required fields: to, subject, body."
    return await asyncio.to_thread(_smtp_send_sync, to, subject, body, cc)


# ─── Reminder tool executors ──────────────────────────────────────────────────

async def _set_reminder(
    message: str,
    fire_at: str,
    recurrence: str,
    room_id: Optional[str],
    user_id: Optional[str],
    session,
) -> str:
    if not room_id or not user_id or session is None:
        return "Reminder unavailable (no room/session context)."
    from app.crud import create_reminder
    from app.models import ReminderRecurrence
    import uuid as _uuid

    try:
        dt = datetime.fromisoformat(fire_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return f"Invalid fire_at datetime: '{fire_at}'. Use ISO 8601 format, e.g. '2026-03-06T09:00:00'."

    rec_map = {"daily": ReminderRecurrence.DAILY, "weekly": ReminderRecurrence.WEEKLY}
    rec = rec_map.get(recurrence or "once", ReminderRecurrence.ONCE)

    reminder = create_reminder(
        session=session,
        room_id=_uuid.UUID(room_id),
        created_by=_uuid.UUID(user_id),
        message=message,
        fire_at=dt,
        recurrence=rec,
    )
    short_id = str(reminder.id)[:8]
    rec_note = f" (repeats {recurrence})" if recurrence and recurrence != "once" else ""
    fire_label = dt.strftime("%Y-%m-%d %H:%M UTC")
    return f"Reminder set [{short_id}]: '{message}' at {fire_label}{rec_note}"


async def _list_reminders(room_id: Optional[str], session) -> str:
    if not room_id or session is None:
        return "Reminder listing unavailable (no room/session context)."
    from app.crud import get_room_reminders
    import uuid as _uuid

    reminders = get_room_reminders(session, _uuid.UUID(room_id))
    if not reminders:
        return "No pending reminders in this room."

    lines = []
    for r in reminders:
        short_id = str(r.id)[:8]
        fire_label = r.fire_at.strftime("%Y-%m-%d %H:%M UTC")
        rec = f" [{r.recurrence.value}]" if r.recurrence and r.recurrence.value != "once" else ""
        lines.append(f"⏰ [{short_id}] {fire_label}{rec} — {r.message}")
    return "Pending reminders:\n" + "\n".join(lines)


async def _cancel_reminder(
    reminder_id: str,
    room_id: Optional[str],
    session,
) -> str:
    if not reminder_id or session is None:
        return "No reminder ID provided."
    from app.crud import cancel_reminder, get_room_reminders
    import uuid as _uuid

    resolved_id: Optional[_uuid.UUID] = None
    if len(reminder_id) == 36:
        try:
            resolved_id = _uuid.UUID(reminder_id)
        except ValueError:
            pass
    if resolved_id is None and room_id:
        for r in get_room_reminders(session, _uuid.UUID(room_id)):
            if str(r.id).startswith(reminder_id):
                resolved_id = r.id
                break

    if not resolved_id:
        return f"Reminder '{reminder_id}' not found."

    ok = cancel_reminder(session, resolved_id)
    return "Reminder cancelled." if ok else f"Reminder '{reminder_id}' not found."


# ─── Task Guardian executors ──────────────────────────────────────────────────

async def _guardian_schedule_task(
    name: str,
    tool_name: str,
    schedule: str,
    tool_args: dict,
    room_id: Optional[str],
    user_id: Optional[str],
) -> str:
    if not room_id or not user_id:
        return "Task Guardian unavailable (no room or user context)."
    task_guardian = get_guardian_suite().task_guardian
    WRITE_TASK_TOOLS = task_guardian.WRITE_TASK_TOOLS

    if tool_name in task_guardian.WRITE_TASK_TOOLS and not task_guardian.TASK_GUARDIAN_WRITE_ENABLED:
        return (
            f"'{tool_name}' is a write-action tool. "
            "Scheduled write tasks are disabled by default. "
            "Ask the admin to set SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true to enable them."
        )

    try:
        task = task_guardian.schedule_task(
            name=name,
            tool_name=tool_name,
            tool_args=tool_args or {},
            schedule=schedule,
            room_id=room_id,
            user_id=user_id,
        )
    except Exception as exc:
        return f"Task Guardian error: {exc}"

    write_note = " ⚠️ Write task — pre-authorized via this confirmation." if tool_name in WRITE_TASK_TOOLS else ""
    return (
        f"Scheduled Task Guardian job `{task['name']}` ({task['id'][:8]}) "
        f"for `{task['tool_name']}` on `{task['schedule']}`. "
        f"Next run: {task['next_run_at']}{write_note}"
    )


async def _guardian_list_tasks(room_id: Optional[str], limit: int = 10) -> str:
    if not room_id:
        return "Task Guardian unavailable (no room context)."
    tasks = get_guardian_suite().task_guardian.list_tasks(room_id=room_id, limit=limit)
    if not tasks:
        return "No Task Guardian jobs configured for this room."

    lines = []
    for task in tasks:
        status = "enabled" if task.enabled else "paused"
        retry_note = ""
        if (task.consecutive_failures or 0) > 0:
            retry_note = (
                f" — failures {task.consecutive_failures}/{task.retry_budget or 0}"
            )
        if task.escalated_at:
            retry_note += f" — escalated {task.escalated_at}"
        lines.append(
            f"- [{task.id[:8]}] {task.name} — {task.tool_name} — {task.schedule} — {status}"
            + (f" — next {task.next_run_at}" if task.next_run_at else "")
            + retry_note
        )
    return "Task Guardian jobs:\n" + "\n".join(lines)


async def _guardian_list_runs(room_id: Optional[str], limit: int = 10) -> str:
    if not room_id:
        return "Task Guardian unavailable (no room context)."
    runs = get_guardian_suite().task_guardian.list_runs(room_id=room_id, limit=limit)
    if not runs:
        return "No Task Guardian runs recorded for this room yet."

    lines = []
    for run in runs:
        lines.append(
            f"- [{run.task_id[:8]}] {run.status.upper()} at {run.created_at} — {run.message}"
        )
    return "Recent Task Guardian runs:\n" + "\n".join(lines)


async def _guardian_propose_improvement(
    *,
    summary: str,
    evidence: str,
    suggested_change: str,
    risk: str,
    room_id: str | None,
    user_id: str | None,
) -> str:
    proposal = get_guardian_suite().improvement.propose_improvement(
        user_id=user_id,
        room_id=room_id,
        summary=summary,
        evidence=evidence,
        suggested_change=suggested_change,
        risk=risk,
        source="chat_tool",
    )
    if proposal is None:
        return "Improvement loop is disabled or the proposal was empty."
    return (
        f"Improvement proposal `{proposal['id']}` recorded and awaiting operator approval.\n"
        f"- Summary: {proposal['summary']}\n"
        f"- Risk: {proposal['risk']}\n"
        "- No code, config, or workflow change has been applied yet."
    )


async def _guardian_simulate_policy(
    *,
    tool_name: str,
    tool_args: dict,
    room_execution_allowed: bool | None,
    is_operator: bool | None,
    is_privileged: bool | None,
    room_id: str | None,
    user_id: str | None,
    session,
) -> str:
    if not tool_name:
        return "Policy simulation unavailable: tool_name is required."

    resolved_room_execution = room_execution_allowed
    if resolved_room_execution is None and room_id and session is not None:
        try:
            import uuid as _uuid

            from sqlmodel import select

            from app.models import ChatRoom

            room = session.exec(
                select(ChatRoom).where(ChatRoom.id == _uuid.UUID(str(room_id)))
            ).first()
            if room is not None:
                resolved_room_execution = bool(room.execution_allowed)
        except Exception:
            resolved_room_execution = None

    resolved_operator = bool(is_operator) if is_operator is not None else False
    if is_operator is None and user_id and session is not None:
        try:
            resolved_operator = bool(get_guardian_suite().auth.is_operator_user_id(session, user_id))
        except Exception:
            resolved_operator = False

    resolved_privileged = bool(is_privileged) if is_privileged is not None else False
    if is_privileged is None and user_id:
        try:
            resolved_privileged = bool(get_guardian_suite().auth.is_operator_privileged(str(user_id)))
        except Exception:
            resolved_privileged = False

    payload = get_guardian_suite().policy.simulate_tool_policy(
        tool_name,
        tool_args if isinstance(tool_args, dict) else {},
        room_execution_allowed=resolved_room_execution,
        is_operator=resolved_operator,
        is_privileged=resolved_privileged,
    )
    return "Guardian policy simulation (no action executed):\n" + json.dumps(payload, indent=2, sort_keys=True)


async def _guardian_list_improvements(
    *,
    room_id: str | None,
    user_id: str | None,
    status: str = "proposed",
    limit: int = 10,
) -> str:
    proposals = get_guardian_suite().improvement.list_improvement_proposals(
        user_id=user_id,
        room_id=room_id,
        status=status or "proposed",
        limit=limit,
    )
    if not proposals:
        return "No matching Sparkbot improvement proposals."

    lines = []
    for proposal in proposals:
        lines.append(
            f"- [{proposal['id']}] {proposal['summary']} — {proposal['risk']} risk — {proposal['status']}"
        )
    return "Sparkbot improvement proposals:\n" + "\n".join(lines)


async def _guardian_run_task(task_id: str, room_id: Optional[str], session) -> str:
    if not room_id or session is None:
        return "Task Guardian unavailable (no room/session context)."
    task_guardian = get_guardian_suite().task_guardian
    task = task_guardian.get_task(task_id)
    if not task or task.room_id != room_id:
        return f"Task Guardian job '{task_id}' not found in this room."

    result = await task_guardian.run_task_once(task, session)
    return (
        f"Task Guardian job `{task.name}` ran with status {result['status'].upper()}.\n\n"
        f"{result['output']}"
        + (
            f"\n\nRetry {result['consecutive_failures']}/{result['retry_budget']} scheduled for {result['next_run_at']}."
            if result["status"] != "verified" and result.get("next_run_at")
            else ""
        )
        + (
            f"\n\nTask paused after {result['consecutive_failures']} consecutive non-verified runs."
            if result.get("escalated")
            else ""
        )
    )


async def _guardian_pause_task(task_id: str, enabled: bool, room_id: Optional[str]) -> str:
    if not room_id:
        return "Task Guardian unavailable (no room context)."
    task_guardian = get_guardian_suite().task_guardian
    task = task_guardian.get_task(task_id)
    if not task or task.room_id != room_id:
        return f"Task Guardian job '{task_id}' not found in this room."

    ok = task_guardian.set_task_enabled(task_id, enabled)
    if not ok:
        return f"Task Guardian job '{task_id}' not found."
    return f"Task Guardian job `{task.name}` is now {'enabled' if enabled else 'paused'}."


# ─── Calendar tool executors ──────────────────────────────────────────────────

def _calendar_configured() -> bool:
    return bool(_google_configured() and _google_calendar_id())


def _calendar_not_configured() -> str:
    return (
        "Google Calendar not configured. "
        "Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN, and GOOGLE_CALENDAR_ID."
    )


def _calendar_endpoint() -> str:
    calendar_id = quote(_google_calendar_id(), safe="")
    return f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"


def _calendar_format_start(value: dict[str, str]) -> str:
    date_time = str(value.get("dateTime") or "").strip()
    if date_time:
        try:
            dt = datetime.fromisoformat(date_time.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            return date_time
    all_day = str(value.get("date") or "").strip()
    return f"{all_day} (all day)" if all_day else "Unknown start"


async def _calendar_list_events(days_ahead: int = 7) -> str:
    if not _calendar_configured():
        return _calendar_not_configured()
    days_ahead = max(1, min(days_ahead, 30))
    token, err = await _google_access_token()
    if err:
        return err

    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                _calendar_endpoint(),
                headers=_google_headers(token),
                params={
                    "singleEvents": "true",
                    "orderBy": "startTime",
                    "timeMin": now.isoformat().replace("+00:00", "Z"),
                    "timeMax": end.isoformat().replace("+00:00", "Z"),
                    "maxResults": 25,
                },
            )
    except Exception as exc:
        return f"Google Calendar error: {exc}"

    if resp.status_code != 200:
        return _google_error_text(resp, "Google Calendar")

    items = resp.json().get("items", [])
    if not items:
        return f"No events in the next {days_ahead} day(s)."

    lines: list[str] = []
    for item in items:
        start_value = item.get("start") or {}
        label = _calendar_format_start(start_value if isinstance(start_value, dict) else {})
        summary = str(item.get("summary") or "(No title)")
        lines.append(f"- {label}: {summary}")

    return f"Upcoming events (next {days_ahead} day(s)):\n" + "\n".join(lines)


async def _calendar_create_event(
    title: str, start: str, end: str, description: str = "", location: str = ""
) -> str:
    if not _calendar_configured():
        return _calendar_not_configured()
    if not title or not start or not end:
        return "Missing required fields: title, start, end."
    token, err = await _google_access_token()
    if err:
        return err
    try:
        dtstart = datetime.fromisoformat(start)
        dtend = datetime.fromisoformat(end)
        if dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=timezone.utc)
        if dtend.tzinfo is None:
            dtend = dtend.replace(tzinfo=timezone.utc)
        payload: dict[str, object] = {
            "summary": title,
            "start": {
                "dateTime": dtstart.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": dtend.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "timeZone": "UTC",
            },
        }
        if description:
            payload["description"] = description
        if location:
            payload["location"] = location
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _calendar_endpoint(),
                headers=_google_headers(token),
                json=payload,
            )
    except Exception as exc:
        return f"Google Calendar error: {exc}"
    if resp.status_code not in (200, 201):
        return _google_error_text(resp, "Google Calendar")
    start_label = dtstart.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"Event created: '{title}' on {start_label}"


# ─── Memory tool executors ────────────────────────────────────────────────────

async def _memory_recall(
    query: str,
    user_id: Optional[str],
    room_id: Optional[str],
    limit: int = 6,
    mode: str = "",
) -> str:
    """Hybrid Guardian recall — surfaces relevant durable + room memory with scores."""
    if not user_id:
        return "Memory recall unavailable (no user context)."
    if not query.strip():
        return "Provide a query string to recall."
    try:
        from app.services.guardian.memory import recall_relevant_events

        events = recall_relevant_events(
            user_id=user_id,
            room_id=room_id,
            query=query,
            limit=int(limit) if limit else 6,
            mode=(mode or None),
        )
    except Exception as exc:
        return f"Memory recall failed: {exc}"
    if not events:
        return "No relevant memory found."
    out_lines: list[str] = [f"Recalled {len(events)} item(s):"]
    for item in events:
        ts = (item.get("timestamp") or "")[:19].replace("T", " ")
        score = item.get("score")
        source = item.get("source") or item.get("type")
        confidence = item.get("confidence")
        prefix_bits = [f"score={score}"]
        if confidence is not None:
            prefix_bits.append(f"conf={confidence}")
        if source:
            prefix_bits.append(f"source={source}")
        if ts:
            prefix_bits.append(f"ts={ts}")
        prefix = " ".join(prefix_bits)
        out_lines.append(f"- [{prefix}] {item.get('content','')}")
    return "\n".join(out_lines)


async def _memory_retrieval_stats() -> str:
    """Show in-process memory recall telemetry."""
    try:
        from app.services.guardian.memory import memory_retrieval_stats
    except Exception as exc:
        return f"Memory stats unavailable: {exc}"
    snap = memory_retrieval_stats()
    parts = [
        "Memory Guardian retrieval telemetry:",
        f"- mode: {snap.get('retriever_mode')}",
        f"- embeddings_enabled: {snap.get('embeddings_enabled')}",
        f"- embed_index_size: {snap.get('embed_index_size')}",
        f"- writes: {snap.get('writes')} (failures {snap.get('write_failures')})",
        f"- recalls: {snap.get('recalls')} (empty {snap.get('empty_recalls')})",
        f"- memory_hit_rate: {snap.get('memory_hit_rate')}",
        f"- recall_precision@5: {snap.get('recall_precision@5')}",
        f"- guardian_job_success_rate: {snap.get('guardian_job_success_rate')}",
        f"- pending_approvals_rate: {snap.get('pending_approvals_rate')}",
        f"- avg_latency_ms: {snap.get('avg_latency_ms')}",
        f"- avg_retrieval_latency: {snap.get('avg_retrieval_latency')}",
        f"- last_latency_ms: {snap.get('last_latency_ms')}",
        f"- recalls_by_mode: {snap.get('recalls_by_mode')}",
    ]
    if snap.get("last_query"):
        parts.append(
            f"- last: query={snap.get('last_query')!r} mode={snap.get('last_mode')} "
            f"events={snap.get('last_event_count')} top_score={snap.get('last_top_score')}"
        )
    return "\n".join(parts)


async def _memory_reindex() -> str:
    """Rebuild Guardian memory FTS + embedding indexes from the ledger."""
    try:
        from app.services.guardian.memory import reindex_memory_indexes
    except Exception as exc:
        return f"Memory reindex unavailable: {exc}"
    summary = reindex_memory_indexes()
    return (
        "Reindex complete -- "
        f"fts={summary.get('fts_indexed')} embed={summary.get('embed_indexed')} "
        f"mode={summary.get('retriever_mode')} embeddings={summary.get('embeddings_enabled')}"
    )


async def _remember_fact(fact: str, user_id: Optional[str], session) -> str:
    if not user_id or session is None:
        return "Memory unavailable (no session context)."
    from app.crud import add_user_memory
    try:
        mem = add_user_memory(session, uuid.UUID(user_id), fact)
    except ValueError:
        return "Memory blocked: that text looks like a secret or low-value memory candidate."
    try:
        get_guardian_suite().memory.remember_fact(user_id=user_id, fact=mem.fact, memory_id=str(mem.id))
    except Exception:
        pass
    return f"Remembered: {mem.fact}"


async def _forget_fact(memory_id: str, user_id: Optional[str], session) -> str:
    if not user_id or session is None:
        return "Memory unavailable (no session context)."
    from app.crud import delete_user_memory
    ok = delete_user_memory(session, uuid.UUID(memory_id), uuid.UUID(user_id))
    if ok:
        try:
            get_guardian_suite().memory.delete_fact_memory(user_id=user_id, memory_id=memory_id)
        except Exception:
            pass
    return "Forgotten." if ok else "Memory not found or not yours."


# ─── Dispatcher ───────────────────────────────────────────────────────────────

async def execute_tool(
    name: str,
    args: dict,
    user_id: Optional[str] = None,
    session=None,
    room_id: Optional[str] = None,
) -> str:
    """Execute a tool by name and return its string result."""
    guardrail = get_guardian_suite().tool_guardrails.validate_tool_input(name, args)
    if not guardrail.allowed:
        return f"TOOL GUARDRAIL REJECTED: {guardrail.reason}"
    if name == "remember_fact":
        return await _remember_fact(args.get("fact", ""), user_id, session)
    if name == "forget_fact":
        return await _forget_fact(args.get("memory_id", ""), user_id, session)
    if name == "memory_recall":
        return await _memory_recall(
            args.get("query", ""),
            user_id,
            room_id,
            int(args.get("limit") or 6),
            str(args.get("mode") or ""),
        )
    if name == "memory_retrieval_stats":
        return await _memory_retrieval_stats()
    if name == "memory_reindex":
        return await _memory_reindex()
    if name == "web_search":
        return await _web_search(args.get("query", ""))
    if name == "fetch_url":
        return await _fetch_url(args.get("url", ""), args.get("instruction", ""))
    if name == "terminal_list_sessions":
        return await _terminal_list_sessions(user_id)
    if name == "terminal_send":
        return await _terminal_send(
            args.get("session_id", ""),
            args.get("text", ""),
            bool(args.get("press_enter", True)),
        )
    if name == "browser_open":
        return await _browser_open(args.get("url", ""), args.get("session_id", ""))
    if name == "browser_navigate":
        return await _browser_navigate(args.get("session_id", ""), args.get("url", ""))
    if name == "browser_snapshot":
        return await _browser_snapshot(args.get("session_id", ""))
    if name == "browser_fill_field":
        return await _browser_fill_field(
            args.get("session_id", ""),
            args.get("field", ""),
            args.get("value", ""),
        )
    if name == "browser_click":
        return await _browser_click(
            args.get("session_id", ""),
            args.get("target", ""),
            args.get("target_type", "auto"),
        )
    if name == "browser_close":
        return await _browser_close(args.get("session_id", ""))
    if name == "browser_save_session":
        return await _browser_save_session(args.get("session_id", ""), args.get("name", ""))
    if name == "browser_restore_session":
        return await _browser_restore_session(args.get("name", ""), args.get("url", ""))
    if name == "browser_list_sessions":
        return await _browser_list_sessions()
    if name == "get_datetime":
        return await _get_datetime()
    if name == "calculate":
        return await _calculate(args.get("expression", ""))
    if name == "create_task":
        return await _create_task(
            title=args.get("title", ""),
            description=args.get("description", ""),
            assignee=args.get("assignee", ""),
            due_date=args.get("due_date", ""),
            room_id=room_id,
            user_id=user_id,
            session=session,
        )
    if name == "list_tasks":
        return await _list_tasks(
            filter=args.get("filter", "open"),
            room_id=room_id,
            session=session,
        )
    if name == "complete_task":
        return await _complete_task(
            task_id=args.get("task_id", ""),
            room_id=room_id,
            session=session,
        )
    if name == "slack_send_message":
        return await _slack_send_message(
            channel=args.get("channel", ""),
            text=args.get("text", ""),
            thread_ts=args.get("thread_ts", ""),
        )
    if name == "slack_list_channels":
        return await _slack_list_channels(limit=int(args.get("limit", 20)))
    if name == "slack_get_channel_history":
        return await _slack_get_channel_history(
            channel=args.get("channel", ""),
            limit=int(args.get("limit", 10)),
        )
    if name == "notion_search":
        return await _notion_search(args.get("query", ""))
    if name == "notion_get_page":
        return await _notion_get_page(args.get("page_id", ""))
    if name == "notion_create_page":
        return await _notion_create_page(
            title=args.get("title", ""),
            content=args.get("content", ""),
            parent_id=args.get("parent_id", ""),
        )
    if name == "confluence_search":
        return await _confluence_search(
            query=args.get("query", ""),
            space_key=args.get("space_key", ""),
        )
    if name == "confluence_get_page":
        return await _confluence_get_page(args.get("page_id", ""))
    if name == "confluence_create_page":
        return await _confluence_create_page(
            title=args.get("title", ""),
            content=args.get("content", ""),
            space_key=args.get("space_key", ""),
            parent_id=args.get("parent_id", ""),
        )
    if name == "github_list_prs":
        return await _github_list_prs(
            repo=args.get("repo", ""),
            state=args.get("state", "open"),
        )
    if name == "github_get_pr":
        return await _github_get_pr(
            repo=args.get("repo", ""),
            pr_number=int(args.get("pr_number", 0)),
        )
    if name == "github_create_issue":
        return await _github_create_issue(
            repo=args.get("repo", ""),
            title=args.get("title", ""),
            body=args.get("body", ""),
            labels=args.get("labels", ""),
        )
    if name == "github_get_ci_status":
        return await _github_get_ci_status(
            repo=args.get("repo", ""),
            branch=args.get("branch", "main"),
        )
    if name == "gmail_fetch_inbox":
        return await _gmail_fetch_inbox(
            max_emails=int(args.get("max_emails", 5)),
            unread_only=bool(args.get("unread_only", False)),
        )
    if name == "gmail_search":
        return await _gmail_search(
            query=args.get("query", ""),
            max_results=int(args.get("max_results", 5)),
        )
    if name == "gmail_get_message":
        return await _gmail_get_message(args.get("message_id", ""))
    if name == "gmail_send":
        return await _gmail_send(
            to=args.get("to", ""),
            subject=args.get("subject", ""),
            body=args.get("body", ""),
            cc=args.get("cc", ""),
        )
    if name == "drive_search":
        return await _drive_search(
            query=args.get("query", ""),
            max_results=int(args.get("max_results", 10)),
        )
    if name == "drive_get_file":
        return await _drive_get_file(args.get("file_id", ""))
    if name == "drive_create_folder":
        return await _drive_create_folder(
            name=args.get("name", ""),
            parent_id=args.get("parent_id", ""),
        )
    if name == "server_read_command":
        return await _server_read_command(
            command=args.get("command", ""),
            service=args.get("service", ""),
            lines=int(args.get("lines", 50)),
        )
    if name == "server_manage_service":
        return await _server_manage_service(
            service=args.get("service", ""),
            action=args.get("action", ""),
        )
    if name == "ssh_read_command":
        return await _ssh_read_command(
            host=args.get("host", ""),
            command=args.get("command", ""),
            service=args.get("service", ""),
            lines=int(args.get("lines", 50)),
        )
    if name == "email_fetch_inbox":
        return await _email_fetch_inbox(
            max_emails=int(args.get("max_emails", 5)),
            unread_only=bool(args.get("unread_only", False)),
        )
    if name == "email_search":
        return await _email_search(
            query=args.get("query", ""),
            max_results=int(args.get("max_results", 5)),
        )
    if name == "email_send":
        return await _email_send(
            to=args.get("to", ""),
            subject=args.get("subject", ""),
            body=args.get("body", ""),
            cc=args.get("cc", ""),
        )
    if name == "set_reminder":
        return await _set_reminder(
            message=args.get("message", ""),
            fire_at=args.get("fire_at", ""),
            recurrence=args.get("recurrence", "once"),
            room_id=room_id,
            user_id=user_id,
            session=session,
        )
    if name == "list_reminders":
        return await _list_reminders(room_id=room_id, session=session)
    if name == "cancel_reminder":
        return await _cancel_reminder(
            reminder_id=args.get("reminder_id", ""),
            room_id=room_id,
            session=session,
        )
    if name == "guardian_schedule_task":
        return await _guardian_schedule_task(
            name=args.get("name", ""),
            tool_name=args.get("tool_name", ""),
            schedule=args.get("schedule", ""),
            tool_args=args.get("tool_args", {}) or {},
            room_id=room_id,
            user_id=user_id,
        )
    if name == "guardian_list_tasks":
        return await _guardian_list_tasks(
            room_id=room_id,
            limit=int(args.get("limit", 10)),
        )
    if name == "guardian_list_runs":
        return await _guardian_list_runs(
            room_id=room_id,
            limit=int(args.get("limit", 10)),
        )
    if name == "guardian_propose_improvement":
        return await _guardian_propose_improvement(
            summary=args.get("summary", ""),
            evidence=args.get("evidence", ""),
            suggested_change=args.get("suggested_change", ""),
            risk=args.get("risk", "medium"),
            room_id=room_id,
            user_id=user_id,
        )
    if name == "guardian_simulate_policy":
        room_execution_allowed = args.get("room_execution_allowed")
        is_operator = args.get("is_operator")
        is_privileged = args.get("is_privileged")
        return await _guardian_simulate_policy(
            tool_name=args.get("tool_name", ""),
            tool_args=args.get("tool_args", {}) or {},
            room_execution_allowed=(
                room_execution_allowed if isinstance(room_execution_allowed, bool) else None
            ),
            is_operator=is_operator if isinstance(is_operator, bool) else None,
            is_privileged=is_privileged if isinstance(is_privileged, bool) else None,
            room_id=room_id,
            user_id=user_id,
            session=session,
        )
    if name == "guardian_list_improvements":
        return await _guardian_list_improvements(
            room_id=room_id,
            user_id=user_id,
            status=args.get("status", "proposed"),
            limit=int(args.get("limit", 10)),
        )
    if name == "guardian_run_task":
        return await _guardian_run_task(
            task_id=args.get("task_id", ""),
            room_id=room_id,
            session=session,
        )
    if name == "guardian_pause_task":
        return await _guardian_pause_task(
            task_id=args.get("task_id", ""),
            enabled=bool(args.get("enabled", False)),
            room_id=room_id,
        )
    if name == "calendar_list_events":
        return await _calendar_list_events(int(args.get("days_ahead", 7)))
    if name == "calendar_create_event":
        return await _calendar_create_event(
            title=args.get("title", ""),
            start=args.get("start", ""),
            end=args.get("end", ""),
            description=args.get("description", ""),
            location=args.get("location", ""),
        )
    # ── Vault tools ──────────────────────────────────────────────────────────
    if name == "vault_list_secrets":
        try:
            entries = get_guardian_suite().vault.vault_list()
            if not entries:
                return "The Guardian Vault is empty. No secrets stored."
            lines = [f"Guardian Vault — {len(entries)} secret(s):"]
            for e in entries:
                policy = e.get("access_policy", "?")
                cat = e.get("category", "general")
                notes = f" — {e['notes']}" if e.get("notes") else ""
                lines.append(f"  • {e['alias']} [{cat}] policy={policy}{notes}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Vault error: {exc}"

    if name == "vault_use_secret":
        try:
            alias = str(args.get("alias", "")).strip()
            if not alias:
                return "Error: alias is required."
            plaintext = get_guardian_suite().vault.vault_use(alias, user_id=user_id or "", operator=user_id or "system")
            return plaintext
        except Exception as exc:
            return f"Vault error: {exc}"

    if name == "vault_reveal_secret":
        try:
            alias = str(args.get("alias", "")).strip()
            if not alias:
                return "Error: alias is required."
            plaintext = get_guardian_suite().vault.vault_reveal(alias, user_id=user_id or "", operator=user_id or "system")
            return f"Secret: {alias}\nValue: {plaintext}"
        except Exception as exc:
            return f"Vault error: {exc}"

    if name == "vault_add_secret":
        try:
            alias = str(args.get("alias", "")).strip()
            value = str(args.get("value", ""))
            if not alias or not value:
                return "Error: alias and value are required."
            result = get_guardian_suite().vault.vault_add(
                alias=alias,
                value=value,
                category=str(args.get("category", "general")),
                notes=args.get("notes") or None,
                policy=str(args.get("access_policy", "use_only")),
                operator=user_id or "system",
            )
            return f"Secret '{result['alias']}' added to the vault (policy={result['access_policy']})."
        except Exception as exc:
            return f"Vault error: {exc}"

    if name == "vault_update_secret":
        try:
            alias = str(args.get("alias", "")).strip()
            value = str(args.get("value", ""))
            if not alias or not value:
                return "Error: alias and value are required."
            get_guardian_suite().vault.vault_update(
                alias=alias,
                value=value,
                operator=user_id or "system",
                notes=args.get("notes") or None,
                policy=args.get("access_policy") or None,
            )
            return f"Secret '{alias}' updated in the vault."
        except Exception as exc:
            return f"Vault error: {exc}"

    if name == "vault_delete_secret":
        try:
            alias = str(args.get("alias", "")).strip()
            if not alias:
                return "Error: alias is required."
            ok = get_guardian_suite().vault.vault_delete(alias, operator=user_id or "system")
            return f"Secret '{alias}' deleted." if ok else f"Secret '{alias}' not found."
        except Exception as exc:
            return f"Vault error: {exc}"

    if name == "telegram_test_connection":
        from app.services.telegram_bridge import test_connection as _tg_test
        try:
            result = await _tg_test()
            if result.get("ok"):
                lines = [
                    "Telegram bot connected successfully.",
                    f"Bot: @{result.get('bot_username', '')} ({result.get('bot_name', '')})",
                    f"Polling active: {result.get('poll_enabled', False)}",
                    f"Linked chats: {result.get('linked_chats', 0)}",
                ]
                return "\n".join(lines)
            return f"Telegram connection test FAILED: {result.get('error', 'Unknown error')}"
        except Exception as exc:
            return f"Telegram test error: {exc}"

    # Fall through to skill plugins
    if name in _skill_registry.executors:
        from app.services.skill_executor import run_skill
        return await run_skill(
            name,
            _skill_registry.executors[name],
            args,
            user_id=user_id,
            room_id=room_id,
            session=session,
        )
    return f"Unknown tool: {name}"
