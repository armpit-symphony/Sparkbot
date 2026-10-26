#!/usr/bin/env python3
"""
Sparkbot Roundtable connector — let an AI agent (or a person) sit at a
Sparkbot Roundtable room from a terminal or as an MCP server.

Requires Python 3.10+. No external packages needed.

It talks to the Roundtable *seats* API (docs/roundtable-seats.md). A room owner
creates a seat in Sparkbot and gets a one-time key that starts with ``rts_``.
Save it once with ``login``; the key is never needed on the command line again.

Usage:
    python sparkbot-roundtable.py login --profile codex     # paste URL + seat key once
    python sparkbot-roundtable.py whoami --profile codex
    python sparkbot-roundtable.py read   --profile codex    # only messages you haven't seen
    python sparkbot-roundtable.py read   --profile codex --all
    python sparkbot-roundtable.py post   --profile codex "Taking RT-002"
    python sparkbot-roundtable.py wait   --profile codex --timeout 300
    python sparkbot-roundtable.py mcp    --profile codex    # MCP server on stdio

Profiles let several agents on one computer each use their own seat
(``--profile codex``, ``--profile claude``). Files live in ``~/.sparkbot/``:
    roundtable-<profile>.json        url, seat key, default room (owner-only perms)
    roundtable-<profile>-state.json  last message seen per room

Env vars override the profile: SPARKBOT_URL, SPARKBOT_SEAT_KEY,
SPARKBOT_ROOM_ID, ROUNDTABLE_PROFILE, ROUNDTABLE_HOME.

MCP setup (no secrets in these configs — the key stays in the profile file):

    Claude Code:
      claude mcp add --scope user --transport stdio roundtable -- python /path/to/sparkbot-roundtable.py mcp --profile claude

    Codex (~/.codex/config.toml):
      [mcp_servers.roundtable]
      command = "python"
      args = ["/path/to/sparkbot-roundtable.py", "mcp", "--profile", "codex"]

The seat can only read and post in rooms it was added to. It cannot use
Sparkbot's tools, settings or other rooms — that is enforced by the server.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
DEFAULT_URL = "http://localhost:8000"
API_PREFIX = "/api/v1/chat"
MCP_WAIT_MAX_SECONDS = 50  # Codex's default tool timeout is 60s; stay under it.
MCP_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

# transport(method, url, body, headers) -> (status, parsed_json_or_text)
Transport = Callable[[str, str, dict | None, dict], "tuple[int, Any]"]


def _out(text: str = "", err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    stream.write(f"{text}\n")
    stream.flush()


class RoundtableError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# ── Profile + state files ─────────────────────────────────────────────────────


def _home() -> Path:
    return Path(os.getenv("ROUNDTABLE_HOME") or (Path.home() / ".sparkbot"))


def _profile_name(profile: str | None) -> str:
    name = (profile or os.getenv("ROUNDTABLE_PROFILE") or "default").strip().lower()
    if not name or not all(c.isalnum() or c in "-_" for c in name):
        raise RoundtableError("Profile names may only use letters, digits, '-' and '_'")
    return name


def config_path(profile: str | None) -> Path:
    return _home() / f"roundtable-{_profile_name(profile)}.json"


def state_path(profile: str | None) -> Path:
    return _home() / f"roundtable-{_profile_name(profile)}-state.json"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_private_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)  # best effort on Windows
    except OSError:
        pass
    os.replace(tmp, path)


def load_settings(profile: str | None) -> dict:
    cfg = _read_json(config_path(profile))
    return {
        "url": (os.getenv("SPARKBOT_URL") or cfg.get("url") or DEFAULT_URL).rstrip("/"),
        "key": os.getenv("SPARKBOT_SEAT_KEY") or cfg.get("key") or "",
        "room_id": os.getenv("SPARKBOT_ROOM_ID") or cfg.get("room_id") or "",
    }


# ── HTTP ──────────────────────────────────────────────────────────────────────


def urllib_transport(
    method: str, url: str, body: dict | None, headers: dict
) -> tuple[int, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        status = e.code
    except urllib.error.URLError as e:
        raise RoundtableError(
            f"Can't reach Sparkbot at {url.split(API_PREFIX)[0]} ({e.reason}). Is it running?"
        ) from e
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw


class Client:
    """Seat API client. One instance per seat; refreshes its token automatically."""

    def __init__(self, url: str, key: str, transport: Transport | None = None):
        if not key:
            raise RoundtableError(
                "No seat key. Run: python sparkbot-roundtable.py login"
            )
        self.url = url.rstrip("/")
        self.key = key.strip()
        self.transport = transport or urllib_transport
        self._token: str | None = None
        self._token_exp = 0.0
        self.seat: dict | None = None

    def _call(
        self, method: str, path: str, body: dict | None = None, auth: bool = True
    ) -> Any:
        for attempt in (1, 2):
            headers = {"Accept": "application/json"}
            if auth:
                headers["Authorization"] = f"Bearer {self._ensure_token()}"
            status, data = self.transport(
                method, f"{self.url}{API_PREFIX}{path}", body, headers
            )
            if status == 401 and auth and attempt == 1:
                self._token = None  # expired or rotated: exchange the key again
                continue
            if status >= 400:
                detail = data.get("detail") if isinstance(data, dict) else data
                raise RoundtableError(
                    f"{detail or 'Request failed'} (HTTP {status})", status
                )
            return data
        raise RoundtableError("Seat token was refused twice", 401)

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        data = self._call("POST", "/seats/token", {"key": self.key}, auth=False)
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        self.seat = data.get("seat")
        return self._token

    def me(self) -> dict:
        return self._call("GET", "/seats/me")

    def messages(
        self, room_id: str, after_id: str | None = None, limit: int = 50
    ) -> list[dict]:
        q = {"limit": str(limit)}
        if after_id:
            q["after_id"] = after_id
        return self._call(
            "GET", f"/seats/rooms/{room_id}/messages?{urllib.parse.urlencode(q)}"
        )

    def post(self, room_id: str, content: str, reply_to_id: str | None = None) -> dict:
        body: dict[str, Any] = {"content": content}
        if reply_to_id:
            body["reply_to_id"] = reply_to_id
        return self._call("POST", f"/seats/rooms/{room_id}/messages", body)


# ── Session: client + room choice + "what have I seen" ────────────────────────


class Session:
    def __init__(self, profile: str | None = None, transport: Transport | None = None):
        self.profile = _profile_name(profile)
        self.settings = load_settings(self.profile)
        self.client = Client(self.settings["url"], self.settings["key"], transport)
        self._rooms: list[dict] | None = None

    def rooms(self) -> list[dict]:
        if self._rooms is None:
            self._rooms = self.client.me()["rooms"]
        return self._rooms

    def room(self, room_id: str | None = None) -> str:
        chosen = room_id or self.settings["room_id"]
        if chosen:
            return chosen
        rooms = self.rooms()
        if len(rooms) == 1:
            return rooms[0]["id"]
        if not rooms:
            raise RoundtableError(
                "This seat isn't in any room yet. Ask the room owner to add it."
            )
        listing = ", ".join(f"{r['name']} ({r['id']})" for r in rooms)
        raise RoundtableError(
            f"This seat is in several rooms; pick one with --room / room_id: {listing}"
        )

    def _state(self) -> dict:
        return _read_json(state_path(self.profile))

    def _mark_seen(self, room_id: str, message_id: str) -> None:
        state = self._state()
        state.setdefault("last_seen", {})[room_id] = message_id
        _write_private_json(state_path(self.profile), state)

    def read(
        self, room_id: str | None = None, only_new: bool = True, limit: int = 50
    ) -> tuple[str, list[dict]]:
        rid = self.room(room_id)
        after = self._state().get("last_seen", {}).get(rid) if only_new else None
        try:
            msgs = self.client.messages(rid, after_id=after, limit=limit)
        except RoundtableError as e:
            if after and e.status == 400:  # remembered message is gone; start fresh
                msgs = self.client.messages(rid, limit=limit)
            else:
                raise
        if msgs:
            self._mark_seen(rid, msgs[-1]["id"])
        return rid, msgs

    def wait(
        self, room_id: str | None = None, timeout: float = 300, interval: float = 3.0
    ) -> tuple[str, list[dict]]:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            rid, msgs = self.read(room_id)
            if msgs or time.monotonic() >= deadline:
                return rid, msgs
            time.sleep(min(interval, max(0.0, deadline - time.monotonic())))

    def post(
        self, content: str, room_id: str | None = None, reply_to_id: str | None = None
    ) -> dict:
        return self.client.post(self.room(room_id), content, reply_to_id)


def format_messages(msgs: list[dict], my_id: str | None = None) -> str:
    if not msgs:
        return "(no new messages)"
    lines = []
    for m in msgs:
        when = str(m.get("created_at", ""))[:16].replace("T", " ")
        who = m.get("sender_name") or "unknown"
        if m.get("sender_slug"):
            who += f" @{m['sender_slug']}"
        kind = "agent" if m.get("sender_type") == "BOT" else "human"
        you = " (you)" if my_id and m.get("sender_id") == my_id else ""
        reply = f" ↪ {m['reply_to_id']}" if m.get("reply_to_id") else ""
        lines.append(
            f"[{when}] {who} [{kind}]{you}{reply}  id={m['id']}\n{m.get('content', '')}"
        )
    return "\n\n".join(lines)


# ── MCP server (JSON-RPC 2.0 over stdio, newline-delimited) ───────────────────

_ROOM_PROP = {
    "type": "string",
    "description": "Room id. Optional when the seat is in exactly one room.",
}

MCP_TOOLS = [
    {
        "name": "roundtable_whoami",
        "description": "Show this seat's name and the Roundtable rooms it can read and post in.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "roundtable_read",
        "description": (
            "Read messages in a Sparkbot Roundtable room where humans and other agents coordinate. "
            "By default returns only messages you haven't seen yet (oldest first). "
            "Each message shows its id so you can reply to it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "room_id": _ROOM_PROP,
                "only_new": {
                    "type": "boolean",
                    "default": True,
                    "description": "False = latest messages, seen or not.",
                },
                "limit": {
                    "type": "integer",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
        },
    },
    {
        "name": "roundtable_post",
        "description": (
            "Post a message to the Roundtable room as this seat — status updates, questions, handoffs, "
            "task claims. Everyone in the room sees it. Keep it short; don't paste secrets."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Message text (max 8000 chars).",
                },
                "room_id": _ROOM_PROP,
                "reply_to_id": {
                    "type": "string",
                    "description": "Optional id of the message you're answering.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "roundtable_wait",
        "description": (
            f"Wait up to timeout_seconds (max {MCP_WAIT_MAX_SECONDS}) for new messages in the room, "
            "then return them. Use after posting a question to hear the answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "room_id": _ROOM_PROP,
                "timeout_seconds": {
                    "type": "integer",
                    "default": 45,
                    "minimum": 1,
                    "maximum": MCP_WAIT_MAX_SECONDS,
                },
            },
        },
    },
]


class McpServer:
    def __init__(
        self, session_factory: Callable[[], Session], wait_interval: float = 3.0
    ):
        self._factory = session_factory
        self._session: Session | None = None
        self.wait_interval = wait_interval

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = self._factory()
        return self._session

    def _my_id(self) -> str | None:
        seat = self.session.client.seat
        return seat.get("id") if seat else None

    def call_tool(self, name: str, args: dict) -> str:
        s = self.session
        if name == "roundtable_whoami":
            me = s.client.me()
            seat = me["seat"]
            rooms = (
                "\n".join(
                    f"- {r['name']} (id={r['id']}, role={r['role']})"
                    for r in me["rooms"]
                )
                or "- (none)"
            )
            return f"You are {seat['display_name']} (@{seat['slug']}, {seat['kind']}).\nRooms:\n{rooms}"
        if name == "roundtable_read":
            limit = max(1, min(int(args.get("limit") or 50), 200))
            _, msgs = s.read(
                args.get("room_id"),
                only_new=bool(args.get("only_new", True)),
                limit=limit,
            )
            return format_messages(msgs, self._my_id())
        if name == "roundtable_post":
            content = str(args.get("content") or "").strip()
            if not content:
                raise RoundtableError("content is required")
            m = s.post(content, args.get("room_id"), args.get("reply_to_id"))
            return f"Posted as {m['sender_name']} (id={m['id']})."
        if name == "roundtable_wait":
            timeout = max(
                1, min(int(args.get("timeout_seconds") or 45), MCP_WAIT_MAX_SECONDS)
            )
            _, msgs = s.wait(
                args.get("room_id"), timeout=timeout, interval=self.wait_interval
            )
            return (
                format_messages(msgs, self._my_id())
                if msgs
                else f"(no new messages after {timeout}s)"
            )
        raise KeyError(name)

    def handle(self, msg: dict) -> dict | None:
        """Handle one JSON-RPC message. Returns a response, or None for notifications."""
        method = msg.get("method")
        msg_id = msg.get("id")
        if msg_id is None:
            return None  # notification (e.g. notifications/initialized)

        def ok(result: dict) -> dict:
            return {"jsonrpc": "2.0", "id": msg_id, "result": result}

        def err(code: int, message: str) -> dict:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": code, "message": message},
            }

        if method == "initialize":
            asked = (msg.get("params") or {}).get("protocolVersion")
            version = (
                asked if asked in MCP_PROTOCOL_VERSIONS else MCP_PROTOCOL_VERSIONS[0]
            )
            return ok(
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "sparkbot-roundtable", "version": VERSION},
                    "instructions": (
                        "This connects you to a Sparkbot Roundtable room shared with humans and other agents. "
                        "Read new messages before starting work, post short status updates and handoffs, "
                        "and use roundtable_wait to hear replies."
                    ),
                }
            )
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": MCP_TOOLS})
        if method == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            try:
                text = self.call_tool(name, params.get("arguments") or {})
                return ok(
                    {"content": [{"type": "text", "text": text}], "isError": False}
                )
            except KeyError:
                return err(-32602, f"Unknown tool: {name}")
            except RoundtableError as e:
                return ok(
                    {
                        "content": [{"type": "text", "text": f"Roundtable error: {e}"}],
                        "isError": True,
                    }
                )
            except Exception as e:  # never let one bad call kill the server
                _out(f"[roundtable] tool {name} failed: {e!r}", err=True)
                return ok(
                    {
                        "content": [{"type": "text", "text": f"Roundtable error: {e}"}],
                        "isError": True,
                    }
                )
        return err(-32601, f"Method not found: {method}")

    def serve(self, stdin=None, stdout=None) -> None:
        """Byte streams in and out (UTF-8, one JSON message per line). Logs go to stderr."""
        stdin = stdin or sys.stdin.buffer
        stdout = stdout or sys.stdout.buffer
        for raw in stdin:
            line = raw.decode("utf-8").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                resp: dict | None = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error"},
                }
            else:
                resp = self.handle(msg) if isinstance(msg, dict) else None
            if resp is not None:
                stdout.write(
                    (json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8")
                )
                stdout.flush()


# ── CLI ───────────────────────────────────────────────────────────────────────


def cmd_login(args) -> int:
    path = config_path(args.profile)
    cfg = _read_json(path)
    url = (
        args.url
        or input(f"Sparkbot URL [{cfg.get('url') or DEFAULT_URL}]: ").strip()
        or cfg.get("url")
        or DEFAULT_URL
    ).rstrip("/")
    key = (
        os.getenv("SPARKBOT_SEAT_KEY")
        or getpass.getpass("Seat key (starts with rts_, input hidden): ").strip()
    )
    client = Client(url, key)
    me = client.me()
    cfg.update({"url": url, "key": key})
    if args.room:
        cfg["room_id"] = args.room
    _write_private_json(path, cfg)
    seat = me["seat"]
    _out(f"Signed in as {seat['display_name']} (@{seat['slug']}). Saved to {path}")
    for r in me["rooms"]:
        _out(f"  room: {r['name']}  id={r['id']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sparkbot-roundtable", description="Sit at a Sparkbot Roundtable room."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name: str, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_)
        p.add_argument("--profile", help="Which saved seat to use (default: 'default')")
        return p

    p = add("login", "Save the Sparkbot URL and your seat key")
    p.add_argument("--url")
    p.add_argument(
        "--room", help="Default room id (only needed if the seat is in several rooms)"
    )
    add("whoami", "Show this seat and its rooms")
    p = add("read", "Show messages you haven't seen")
    p.add_argument("--room")
    p.add_argument(
        "--all", action="store_true", help="Show the latest messages, seen or not"
    )
    p.add_argument("--limit", type=int, default=50)
    p = add("post", "Post a message ('-' reads it from stdin)")
    p.add_argument("text", nargs="+")
    p.add_argument("--room")
    p.add_argument("--reply", help="Message id you're replying to")
    p = add("wait", "Wait until new messages arrive, then show them")
    p.add_argument("--room")
    p.add_argument("--timeout", type=float, default=300)
    add("mcp", "Run as an MCP server on stdio (for Claude Code, Codex, ...)")
    add("logout", "Forget this profile's saved key and state")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)

    try:
        if args.cmd == "login":
            return cmd_login(args)
        if args.cmd == "logout":
            for path in (config_path(args.profile), state_path(args.profile)):
                path.unlink(missing_ok=True)
            _out("Forgot this profile.")
            return 0
        if args.cmd == "mcp":
            profile = args.profile
            McpServer(lambda: Session(profile)).serve()
            return 0

        s = Session(args.profile)
        if args.cmd == "whoami":
            me = s.client.me()
            seat = me["seat"]
            _out(
                f"{seat['display_name']} (@{seat['slug']}, {seat['kind']}) at {s.settings['url']}"
            )
            for r in me["rooms"]:
                _out(f"  room: {r['name']}  id={r['id']}  role={r['role']}")
            return 0
        if args.cmd == "read":
            _, msgs = s.read(args.room, only_new=not args.all, limit=args.limit)
        elif args.cmd == "wait":
            _, msgs = s.wait(args.room, timeout=args.timeout)
        elif args.cmd == "post":
            text = sys.stdin.read() if args.text == ["-"] else " ".join(args.text)
            m = s.post(text.strip(), args.room, args.reply)
            _out(f"Posted as {m['sender_name']} (id={m['id']})")
            return 0
        else:
            parser.error(f"unknown command {args.cmd}")
        seat = s.client.seat or {}
        _out(format_messages(msgs, seat.get("id")))
        return 0
    except RoundtableError as e:
        _out(f"Error: {e}", err=True)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
