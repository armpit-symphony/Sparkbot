#!/usr/bin/env python3
"""
Sparkbot CLI — chat with Sparkbot from your terminal.

Requires Python 3.10+. No external packages needed.

Usage:
    python sparkbot-cli.py                              # interactive chat
    python sparkbot-cli.py "What's the weather?"        # one-shot message
    echo "Summarise my inbox" | python sparkbot-cli.py  # piped input

    python sparkbot-cli.py --url http://localhost:8000 --passphrase mypass
    python sparkbot-cli.py --setup   # configure provider keys + model stack
    python sparkbot-cli.py --reset   # clear saved config and re-prompt

Config is saved to ~/.sparkbot/cli.json on first successful login.
Override any time with --url / --passphrase flags or env vars:
    SPARKBOT_URL          e.g. http://localhost:8000
    SPARKBOT_PASSPHRASE   your chat passphrase

The CLI does not run models locally. It connects to a Sparkbot server.
Use --setup or /setup to store provider API keys and choose model roles
on your own Sparkbot instance.
"""

import argparse
import getpass
import http.cookiejar
import json
import os
import sys
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

CONFIG_PATH = Path.home() / ".sparkbot" / "cli.json"
DEFAULT_URL = "http://localhost:8000"
API = "/api/v1"
PROVIDER_FIELDS = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google": "google_api_key",
    "groq": "groq_api_key",
    "minimax": "minimax_api_key",
}
STACK_ROLES = [
    ("primary", "Primary", "default day-to-day assistant model"),
    ("backup_1", "Backup 1", "fast/basic fallback model"),
    ("backup_2", "Backup 2", "secondary fallback model"),
    ("heavy_hitter", "Heavy hitter", "deeper reasoning / harder tasks"),
]


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

    def _get_json(self, path: str) -> dict:
        req = urllib.request.Request(self._url(path), method="GET")
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

    def get_models(self) -> dict:
        try:
            return self._get_json("/chat/models")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Model catalog failed ({exc.code}): {body}") from exc

    def get_models_config(self) -> dict:
        try:
            return self._get_json("/chat/models/config")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Model config failed ({exc.code}): {body}") from exc

    def update_models_config(self, body: dict) -> dict:
        try:
            return self._post_json("/chat/models/config", body)
        except urllib.error.HTTPError as exc:
            body_text = exc.read().decode(errors="replace")
            raise RuntimeError(f"Model config update failed ({exc.code}): {body_text}") from exc

    def get_current_model(self) -> dict:
        try:
            return self._get_json("/chat/model")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Current model lookup failed ({exc.code}): {body}") from exc

    def set_current_model(self, model: str) -> dict:
        try:
            return self._post_json("/chat/model", {"model": model})
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            raise RuntimeError(f"Set model failed ({exc.code}): {body}") from exc

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
  /model      list models or switch one: /model gpt-5-mini
  /room       show current room id
  /setup      configure API keys and model roles on this Sparkbot instance
  /clear      clear the terminal screen
  /quit       exit (also: Ctrl-D, Ctrl-C)

All other input is sent as a chat message.
"""


def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def _prompt_yes_no(prompt: str, *, default: bool = True) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{prompt} [{suffix}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Enter y or n.")


def _prompt_secret(prompt: str) -> str:
    try:
        return getpass.getpass(f"{prompt}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _provider_name(provider: dict) -> str:
    return provider.get("label") or provider.get("id") or "Provider"


def _provider_label_by_id(config: dict) -> dict[str, str]:
    return {
        str(provider.get("id")): _provider_name(provider)
        for provider in config.get("providers", [])
    }


def _provider_field_for_model(model: dict) -> str | None:
    provider_id = str(model.get("provider", "")).strip()
    return PROVIDER_FIELDS.get(provider_id)


def _pick_model(
    *,
    role_label: str,
    role_help: str,
    models: list[dict],
    default_model: str,
) -> str:
    print(f"\n{role_label}: {role_help}")
    choices = []
    for idx, model in enumerate(models, start=1):
        provider = model.get("provider", "other")
        status = "configured" if model.get("configured") else "needs key"
        active = " default" if model["id"] == default_model else ""
        print(f"  {idx}. {model['id']}  [{provider}, {status}{active}]")
        print(f"     {model.get('description', '')}")
        choices.append(model["id"])

    while True:
        raw = input(f"Select {role_label} model [default: {default_model}]: ").strip()
        if not raw:
            return default_model
        if raw.isdigit():
            pos = int(raw)
            if 1 <= pos <= len(choices):
                return choices[pos - 1]
        if raw in choices:
            return raw
        print("Enter a model number or exact model id from the list above.")


def run_setup_wizard(client: SparkbotClient) -> None:
    try:
        config = client.get_models_config()
        models_payload = client.get_models()
    except RuntimeError as exc:
        print(f"\nSetup unavailable: {exc}", file=sys.stderr)
        return

    providers = config.get("providers", [])
    stack_defaults = config.get("stack", {}) or {}
    models = models_payload.get("models", []) or []

    print("\nSparkbot setup")
    print("This stores provider API keys on your Sparkbot instance.")
    print("Keys are not saved in ~/.sparkbot/cli.json.\n")

    updates: dict[str, dict] = {}
    provider_updates: dict[str, str] = {}
    for provider in providers:
        provider_id = provider.get("id", "")
        field_name = PROVIDER_FIELDS.get(provider_id)
        if not field_name:
            continue
        configured = bool(provider.get("configured"))
        label = _provider_name(provider)
        models_for_provider = provider.get("models", []) or []
        status = "configured" if configured else "not configured"
        print(f"{label}: {status}")
        if models_for_provider:
            print("  Models:", ", ".join(models_for_provider))
        if not _prompt_yes_no(f"Set or update the {label} API key?", default=not configured):
            continue
        secret = _prompt_secret(f"{label} API key")
        if secret:
            provider_updates[field_name] = secret

    if provider_updates:
        updates["providers"] = provider_updates

    usable_models = []
    provider_updates_by_id = {
        provider_id
        for provider_id, field_name in PROVIDER_FIELDS.items()
        if field_name in provider_updates
    }
    for model in models:
        provider_id = model.get("provider", "other")
        if model.get("configured") or provider_id in provider_updates_by_id:
            usable_models.append(model)

    if not usable_models:
        print("\nNo usable models are available yet.")
        print("Add at least one provider API key before choosing model roles.\n")
    elif _prompt_yes_no("Configure primary, backup, and heavy-hitter model roles now?", default=True):
        stack_update: dict[str, str] = {}
        chosen_models: set[str] = set()
        for role_key, role_label, role_help in STACK_ROLES:
            role_default = stack_defaults.get(role_key) or stack_defaults.get("primary") or usable_models[0]["id"]
            candidates = [model for model in usable_models if model["id"] not in chosen_models or model["id"] == role_default]
            if not candidates:
                candidates = usable_models
            if role_default in chosen_models:
                role_default = candidates[0]["id"]
            selected = _pick_model(
                role_label=role_label,
                role_help=role_help,
                models=candidates,
                default_model=role_default,
            )
            stack_update[role_key] = selected
            chosen_models.add(selected)
        updates["stack"] = stack_update

    if not updates:
        print("\nNo setup changes were submitted.\n")
        return

    try:
        result = client.update_models_config(updates)
    except RuntimeError as exc:
        print(f"\nSetup failed: {exc}", file=sys.stderr)
        return

    print("\nSetup saved.")
    for notice in result.get("notices", []):
        print(f"- {notice}")
    print()


def _list_models(client: SparkbotClient) -> None:
    try:
        payload = client.get_models()
    except RuntimeError as exc:
        print(f"\nModel lookup failed: {exc}\n", file=sys.stderr)
        return

    print("\nAvailable models")
    for model in payload.get("models", []):
        active = " *" if model.get("active") else ""
        status = "configured" if model.get("configured") else "needs key"
        provider = model.get("provider", "other")
        print(f"- {model['id']}{active} [{provider}, {status}]")
        print(f"  {model.get('description', '')}")
    print("\nUse /model <id> to switch.")
    print("If the provider is missing, Sparkbot will ask for that API key.\n")


def _set_model_with_optional_key(client: SparkbotClient, args: str) -> None:
    parts = args.split(maxsplit=1)
    if not parts:
        _list_models(client)
        return

    target_model = parts[0].strip()
    inline_token = parts[1].strip() if len(parts) > 1 else ""

    try:
        models_payload = client.get_models()
        config_payload = client.get_models_config()
    except RuntimeError as exc:
        print(f"\nModel setup failed: {exc}\n", file=sys.stderr)
        return

    model_by_id = {
        str(model.get("id")): model
        for model in models_payload.get("models", [])
    }
    selected = model_by_id.get(target_model)
    if not selected:
        print(f"\nUnknown model: {target_model}")
        _list_models(client)
        return

    if not selected.get("configured"):
        provider_id = str(selected.get("provider", "")).strip()
        provider_field = _provider_field_for_model(selected)
        provider_labels = _provider_label_by_id(config_payload)
        provider_label = provider_labels.get(provider_id, provider_id or "Provider")
        if not provider_field:
            print(f"\n{target_model} is not configured and Sparkbot does not know how to store a key for its provider.\n", file=sys.stderr)
            return
        token = inline_token or _prompt_secret(f"{provider_label} API key for {target_model}")
        if not token:
            print("\nNo API key entered. Model was not changed.\n")
            return
        try:
            result = client.update_models_config({"providers": {provider_field: token}})
        except RuntimeError as exc:
            print(f"\nProvider setup failed: {exc}\n", file=sys.stderr)
            return
        for notice in result.get("notices", []):
            print(f"- {notice}")

    try:
        current = client.set_current_model(target_model)
    except RuntimeError as exc:
        print(f"\nModel switch failed: {exc}\n", file=sys.stderr)
        return

    print(f"\nActive model: {current['model']} — {current['description']}\n")


def handle_cli_command(raw: str, client: SparkbotClient) -> bool:
    stripped = raw.strip()
    if not stripped.startswith("/"):
        return False

    cmd, _, args = stripped.partition(" ")
    args = args.strip()

    if cmd == "/help":
        print(HELP_TEXT)
        return True
    if cmd == "/room":
        print(f"Room: {client.room_id}\n")
        return True
    if cmd == "/setup":
        run_setup_wizard(client)
        return True
    if cmd == "/model":
        if args:
            _set_model_with_optional_key(client, args)
        else:
            _list_models(client)
        return True
    if cmd == "/clear":
        _clear()
        return True
    return False


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
        if handle_cli_command(user_input, client):
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
    parser.add_argument("--setup", action="store_true", help="Configure provider keys and model roles.")
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

    if args.setup:
        run_setup_wizard(client)
        return

    if sys.stdin.isatty():
        try:
            config = client.get_models_config()
        except RuntimeError:
            config = {}
        providers = config.get("providers", []) if isinstance(config, dict) else []
        if providers and not any(provider.get("configured") for provider in providers):
            print("\nNo provider API keys are configured on this Sparkbot instance.")
            print("Use /model <id> for a quick terminal-only setup, or /setup for the full onboarding flow.\n")

    # Dispatch: one-shot arg / piped stdin / interactive
    if args.message:
        if handle_cli_command(args.message, client):
            return
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
            if handle_cli_command(line, client):
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
