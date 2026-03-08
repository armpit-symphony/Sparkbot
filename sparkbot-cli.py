#!/usr/bin/env python3
"""
Sparkbot CLI — chat with Sparkbot from your terminal.

Requires Python 3.10+. No external packages needed.

Usage:
    python sparkbot-cli.py                              # interactive chat
    python sparkbot-cli.py "What's the weather?"        # one-shot message
    echo "Summarise my inbox" | python sparkbot-cli.py  # piped input

    python sparkbot-cli.py --url http://localhost:8000 --passphrase mypass
    python sparkbot-cli.py --reset   # clear saved config and re-prompt

Config is saved to ~/.sparkbot/cli.json on first successful login.
Override any time with --url / --passphrase flags or env vars:
    SPARKBOT_URL          e.g. http://localhost:8000
    SPARKBOT_PASSPHRASE   your chat passphrase
"""

import argparse
import http.client
import http.cookiejar
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

CONFIG_PATH = Path.home() / ".sparkbot" / "cli.json"
DEFAULT_URL = "http://localhost:8000"
API = "/api/v1"


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class _RelaxedCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """Send secure-flagged cookies over plain HTTP too (needed for local dev)."""
    def return_ok_secure(self, cookie, request):
        return True


class SparkbotClient:
    def __init__(self, base_url: str, passphrase: str):
        self.base_url = base_url.rstrip("/")
        self.passphrase = passphrase
        self.room_id: str | None = None
        jar = http.cookiejar.CookieJar(policy=_RelaxedCookiePolicy())
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar)
        )

    # --- internals ----------------------------------------------------------

    def _url(self, path: str) -> str:
        return f"{self.base_url}{API}{path}"

    def _post_json(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            self._url(path),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(req) as resp:
            return json.loads(resp.read())

    # --- public API ---------------------------------------------------------

    def login(self) -> None:
        """Authenticate and obtain a session cookie."""
        try:
            self._post_json("/chat/users/login", {"passphrase": self.passphrase})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Login failed ({exc.code}): {body}") from exc

    def bootstrap(self) -> str:
        """Get or create the user's DM room. Returns room_id."""
        try:
            result = self._post_json("/chat/users/bootstrap", {})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Bootstrap failed ({exc.code}): {body}") from exc
        self.room_id = result["room_id"]
        return self.room_id

    def stream_message(self, text: str, on_token=None, on_tool=None) -> str:
        """Send a message and stream the response. Returns full reply text."""
        if not self.room_id:
            raise RuntimeError("No room — call bootstrap() first.")
        url = self._url(f"/chat/rooms/{self.room_id}/messages/stream")
        data = json.dumps({"content": text}).encode()
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
            method="POST",
        )
        tokens: list[str] = []
        try:
            with self.opener.open(req) as resp:
                while True:
                    raw = resp.readline()
                    if not raw:
                        break
                    line = raw.decode("utf-8").rstrip("\r\n")
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except Exception:
                        continue
                    etype = event.get("type")
                    if etype == "token":
                        tok = event.get("token", "")
                        tokens.append(tok)
                        if on_token:
                            on_token(tok)
                    elif etype == "tool_chip":
                        tool = event.get("tool", "")
                        status = event.get("status", "")
                        if on_tool and status == "running":
                            on_tool(tool)
                    elif etype == "confirm":
                        # Write-tool confirmation required — show the prompt
                        msg = event.get("message", f"Confirm action: {event.get('tool','?')}")
                        if on_token:
                            on_token(f"\n[CONFIRM REQUIRED] {msg}\n")
                    elif etype == "error":
                        raise RuntimeError(event.get("detail", "Stream error"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Stream error ({exc.code}): {body}") from exc
        return "".join(tokens)


# ---------------------------------------------------------------------------
# Interactive REPL
# ---------------------------------------------------------------------------

HELP_TEXT = """\
Commands:
  /help       show this help
  /room       show current room id
  /clear      clear the terminal screen
  /quit       exit (also: Ctrl-D, Ctrl-C)

All other input is sent as a chat message.
"""


def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def interactive(client: SparkbotClient) -> None:
    print("Sparkbot CLI  —  connected to", client.base_url)
    print('Type /help for commands, Ctrl-C or /quit to exit.\n')
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not user_input:
            continue
        if user_input in ("/quit", "/exit"):
            print("Goodbye!")
            break
        if user_input == "/help":
            print(HELP_TEXT)
            continue
        if user_input == "/room":
            print(f"Room: {client.room_id}\n")
            continue
        if user_input == "/clear":
            _clear()
            continue
        # Send message
        print("Sparkbot: ", end="", flush=True)
        try:
            client.stream_message(
                user_input,
                on_token=lambda t: print(t, end="", flush=True),
                on_tool=lambda tool: print(f"\n  [using {tool}]", end="", flush=True),
            )
        except RuntimeError as exc:
            print(f"\nError: {exc}", file=sys.stderr)
        print("\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sparkbot CLI — chat with Sparkbot from your terminal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("message", nargs="?", help="Send a single message and exit.")
    parser.add_argument("--url", help=f"Sparkbot base URL (default: {DEFAULT_URL})")
    parser.add_argument("--passphrase", help="Chat passphrase")
    parser.add_argument("--reset", action="store_true", help="Reset saved config.")
    args = parser.parse_args()

    if args.reset:
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        print("Config cleared.")
        return

    cfg = _load_config()
    url = args.url or os.getenv("SPARKBOT_URL") or cfg.get("url") or DEFAULT_URL
    passphrase = args.passphrase or os.getenv("SPARKBOT_PASSPHRASE") or cfg.get("passphrase")

    if not passphrase:
        try:
            passphrase = input(f"Sparkbot passphrase for {url}: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)

    client = SparkbotClient(url, passphrase)

    # Login + bootstrap
    try:
        client.login()
        client.bootstrap()
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Cannot connect to {url}: {exc}", file=sys.stderr)
        print("Is Sparkbot running? Check: python sparkbot-cli.py --url <URL>", file=sys.stderr)
        sys.exit(1)

    # Persist working config
    _save_config({"url": url, "passphrase": passphrase})

    # Dispatch: one-shot arg / piped stdin / interactive
    if args.message:
        try:
            client.stream_message(
                args.message,
                on_token=lambda t: print(t, end="", flush=True),
                on_tool=lambda tool: print(f"\n  [using {tool}]", end="", flush=True),
            )
            print()
        except RuntimeError as exc:
            print(f"\nError: {exc}", file=sys.stderr)
            sys.exit(1)
    elif not sys.stdin.isatty():
        # Piped / redirected input — process each line
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                client.stream_message(
                    line,
                    on_token=lambda t: print(t, end="", flush=True),
                    on_tool=lambda tool: print(f"\n  [using {tool}]", end="", flush=True),
                )
                print()
            except RuntimeError as exc:
                print(f"\nError: {exc}", file=sys.stderr)
    else:
        interactive(client)


if __name__ == "__main__":
    main()
