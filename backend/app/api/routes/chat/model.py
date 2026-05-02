"""
Model preference and onboarding control-plane endpoints.

GET  /chat/models          — list available models
GET  /chat/model           — get current user's active model
POST /chat/model           — set current user's model preference
GET  /chat/models/config   — get control-plane model/comms config
POST /chat/models/config   — update model stack, provider tokens, and comms config
"""

from __future__ import annotations

import os
import re
import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentChatUser, SessionDep
from app.api.routes.chat.agents import BUILT_IN_AGENTS, get_all_agents, register_agent, unregister_agent
from app.core.config import settings
from app.services.guardian import get_guardian_suite
from app.services.guardian.policy import (
    GLOBAL_COMPUTER_CONTROL_TTL_SECONDS,
    global_bypass_status,
)
from app.api.routes.chat.llm import (
    AGENT_MODEL_OVERRIDES_ENV,
    AVAILABLE_MODELS,
    VALID_AGENT_ROUTES,
    BACKUP_MODEL_1_ENV,
    BACKUP_MODEL_2_ENV,
    DEFAULT_CROSS_PROVIDER_FALLBACK_ENV,
    DEFAULT_PROVIDER_ENV,
    HEAVY_HITTER_MODEL_ENV,
    LOCAL_DEFAULT_MODEL_ENV,
    OPENROUTER_DEFAULT_MODEL_ENV,
    PRIMARY_MODEL_ENV,
    default_cross_provider_fallback_enabled,
    get_agent_model_overrides,
    get_default_provider,
    get_latency_stats,
    get_local_default_model,
    get_model,
    get_model_stack,
    get_model_stack_display,
    get_ollama_status,
    get_openrouter_default_model,
    is_valid_model,
    model_label,
    model_is_configured,
    model_provider,
    set_invite_agent_config,
    set_model,
    set_model_stack,
)
# Bridge status imports are deferred to avoid loading heavy libraries
# (discord.py, pywa, etc.) that are not bundled in the desktop (V1_LOCAL_MODE) build.
# Telegram uses only httpx and is always safe to import.

router = APIRouter(tags=["chat-model"])

_ENV_UPDATE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
_PROVIDER_ENV_KEYS = {
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
    "groq_api_key": "GROQ_API_KEY",
    "minimax_api_key": "MINIMAX_API_KEY",
    "xai_api_key": "XAI_API_KEY",
}
_PROVIDER_AUTH_MODE_ENV_KEYS = {
    "openai_auth_mode": "OPENAI_AUTH_MODE",
    "anthropic_auth_mode": "ANTHROPIC_AUTH_MODE",
}


def _provider_saved_auth_mode(provider_id: str) -> str:
    if provider_id == "openai":
        raw = os.getenv("OPENAI_AUTH_MODE", "").strip().lower()
        return raw if raw in {"api_key", "codex_sub"} else "api_key"
    if provider_id == "anthropic":
        raw = os.getenv("ANTHROPIC_AUTH_MODE", "").strip().lower()
        return raw if raw in {"api_key", "oauth"} else "api_key"
    return "api_key"
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _env_path() -> Path:
    # When running as a PyInstaller frozen desktop bundle, SPARKBOT_DATA_DIR is set
    # to the directory beside the exe by desktop_launcher.py.  Use it so that the
    # .env written here is the same file that the launcher loads on next startup.
    data_dir = os.environ.get("SPARKBOT_DATA_DIR")
    if data_dir:
        return Path(data_dir) / ".env"
    return _repo_root() / ".env"


def _load_version_markers() -> dict[str, str]:
    """Best-effort version markers for runtime self-inspection.

    Prefer explicit env overrides for packaged builds. Fall back to tracked
    source files when running from a checkout. If neither exists, keep the
    currently shipped desktop release visible instead of letting the model guess.
    """
    markers = {
        "app_version": os.getenv("SPARKBOT_VERSION", "").strip(),
        "backend_version": "",
        "frontend_version": "",
        "desktop_shell_version": "",
    }
    root = _repo_root()

    backend_pyproject = root / "backend" / "pyproject.toml"
    if backend_pyproject.is_file():
        try:
            text = backend_pyproject.read_text(encoding="utf-8")
            match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', text)
            if match:
                markers["backend_version"] = match.group(1).strip()
        except Exception:
            pass

    frontend_package = root / "frontend" / "package.json"
    if frontend_package.is_file():
        try:
            payload = json.loads(frontend_package.read_text(encoding="utf-8"))
            markers["frontend_version"] = str(payload.get("version") or "").strip()
        except Exception:
            pass

    tauri_conf = root / "src-tauri" / "tauri.conf.json"
    if tauri_conf.is_file():
        try:
            payload = json.loads(tauri_conf.read_text(encoding="utf-8"))
            markers["desktop_shell_version"] = str(payload.get("version") or "").strip()
        except Exception:
            pass

    if not markers["app_version"]:
        markers["app_version"] = (
            markers["desktop_shell_version"]
            or markers["backend_version"]
            or markers["frontend_version"]
            or "1.2.3"
        )

    return markers


def _require_operator(current_user: CurrentChatUser) -> None:
    if not current_user or not get_guardian_suite().auth.is_operator_identity(
        username=current_user.username,
        user_type=current_user.type,
    ):
        raise HTTPException(status_code=403, detail="Operator access required.")


def _sanitize_env_value(value: str) -> str:
    return str(value or "").replace("\r", "").replace("\n", "").strip()


def _reload_persisted_env() -> None:
    """Re-read the data/.env file and apply all keys to os.environ.

    In multi-worker deployments (e.g. 4 uvicorn workers), only the worker
    that handled the save request has updated os.environ.  Other workers
    still carry the original container env vars.  This function ensures
    every config read reflects the latest saved state on disk.
    """
    env_path = _env_path()
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = _ENV_UPDATE_RE.match(line)
            if not match:
                continue
            key = match.group(1)
            value = line[match.end():]
            os.environ[key] = value
    except Exception:
        pass


def _write_env_updates(updates: dict[str, str]) -> None:
    env_path = _env_path()
    existing_lines = env_path.read_text().splitlines() if env_path.exists() else []
    pending = {key: _sanitize_env_value(value) for key, value in updates.items()}
    rendered: list[str] = []

    for line in existing_lines:
        match = _ENV_UPDATE_RE.match(line.strip())
        if not match:
            rendered.append(line)
            continue
        key = match.group(1)
        if key not in pending:
            rendered.append(line)
            continue
        rendered.append(f"{key}={pending.pop(key)}")

    for key, value in pending.items():
        rendered.append(f"{key}={value}")

    content = "\n".join(rendered).rstrip() + "\n"
    env_path.write_text(content)


def _apply_env_updates(updates: dict[str, str]) -> None:
    for key, value in updates.items():
        os.environ[key] = _sanitize_env_value(value)


def _upsert_vault_secret(
    *,
    alias: str,
    value: str,
    category: str,
    notes: str,
    current_user: CurrentChatUser,
) -> bool:
    """Persist a secret into Vault when a privileged session is active."""
    if not value:
        return False
    guardian_suite = get_guardian_suite()
    priv_session = guardian_suite.auth.get_active_session(str(current_user.id))
    if not priv_session:
        return False
    from app.services.guardian.vault import vault_get_metadata

    operator = str(current_user.username or "system")
    if vault_get_metadata(alias):
        guardian_suite.vault.vault_update(
            alias=alias,
            value=value,
            operator=operator,
            session_id=priv_session.session_id,
            notes=notes,
            policy="use_only",
        )
    else:
        guardian_suite.vault.vault_add(
            alias=alias,
            value=value,
            category=category,
            notes=notes,
            policy="use_only",
            operator=operator,
            session_id=priv_session.session_id,
        )
    return True


def _env_or_vault_has_secret(env_var: str, vault_alias: str) -> bool:
    if os.getenv(env_var, "").strip():
        return True
    try:
        from app.services.guardian.vault import vault_get_metadata

        meta = vault_get_metadata(vault_alias)
        if not meta:
            return False
        return str(meta.get("access_policy") or "") != "disabled"
    except Exception:
        return False


def _provider_catalog(ollama_status: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    models_by_provider: dict[str, list[str]] = {}
    for model in AVAILABLE_MODELS:
        provider = model_provider(model)
        models_by_provider.setdefault(provider, []).append(model)

    ordered = [
        ("openrouter", "OpenRouter", "OPENROUTER_API_KEY"),
        ("openai", "OpenAI", "OPENAI_API_KEY"),
        ("anthropic", "Anthropic", "ANTHROPIC_API_KEY"),
        ("google", "Google", "GOOGLE_API_KEY"),
        ("groq", "Groq", "GROQ_API_KEY"),
        ("minimax", "MiniMax", "MINIMAX_API_KEY"),
        ("xai", "xAI (Grok)", "XAI_API_KEY"),
    ]
    items: list[dict[str, Any]] = []
    for provider_id, label, env_key in ordered:
        saved_auth_mode = _provider_saved_auth_mode(provider_id)
        items.append(
            {
                "id": provider_id,
                "label": label,
                "configured": bool(os.getenv(env_key, "").strip()),
                "reachable": None,
                "models_available": None,
                "available_models": [],
                "models": sorted(models_by_provider.get(provider_id, [])),
                "auth_modes": (
                    ["api_key", "codex_sub"]
                    if provider_id == "openai"
                    else ["api_key", "oauth"]
                    if provider_id == "anthropic"
                    else ["api_key"]
                ),
                "saved_auth_mode": saved_auth_mode,
            }
        )
    ollama_status = ollama_status or {
        "reachable": False,
        "models_available": False,
        "models": [],
    }
    # Ollama is "configured" when the user has actually selected local usage,
    # while reachability/models_available reflect live runtime status now.
    primary_model = get_model_stack().get("primary", "")
    saved_local_model = bool(os.getenv(LOCAL_DEFAULT_MODEL_ENV, "").strip())
    agent_local_override = any(
        str((value or {}).get("route") or "").strip().lower() == "local"
        for value in get_agent_model_overrides().values()
    )
    ollama_configured = saved_local_model or primary_model.startswith("ollama/") or agent_local_override
    items.append(
        {
            "id": "ollama",
            "label": "Local (Ollama)",
            "configured": ollama_configured,
            "reachable": bool(ollama_status.get("reachable")),
            "models_available": bool(ollama_status.get("models_available")),
            "available_models": list(ollama_status.get("model_ids") or []),
            "models": sorted(models_by_provider.get("ollama", [])),
        }
    )
    return items


def _build_google_comms_status() -> dict[str, Any]:
    """Return configured status for Google (Gmail + Calendar) credentials."""
    has_oauth = bool(
        _env_or_vault_has_secret("GOOGLE_CLIENT_ID", "google_client_id")
        and _env_or_vault_has_secret("GOOGLE_CLIENT_SECRET", "google_client_secret")
        and _env_or_vault_has_secret("GOOGLE_REFRESH_TOKEN", "google_refresh_token")
    )
    return {
        "gmail_configured": has_oauth,
        "calendar_configured": has_oauth and bool(os.getenv("GOOGLE_CALENDAR_ID", "").strip()),
    }


def _build_comms_status() -> dict[str, Any]:
    """Return bridge comms status. Discord/WhatsApp use heavy third-party
    libraries not bundled in V1_LOCAL_MODE; Telegram and GitHub use httpx/local
    helpers and are safe to report in the desktop build."""
    google_status = _build_google_comms_status()
    # Telegram bridge uses plain httpx — always report real status so the UI
    # correctly shows configured/linked state in the desktop (V1_LOCAL_MODE) build.
    from app.services.telegram_bridge import get_status as get_telegram_status
    from app.services.github_bridge import get_status as get_github_status
    if settings.V1_LOCAL_MODE:
        return {
            "telegram": get_telegram_status(),
            "discord": {"enabled": False, "dm_only": False},
            "whatsapp": {"enabled": False},
            "github": get_github_status(),
            "google": google_status,
        }
    from app.services.discord_bridge import get_status as get_discord_status
    from app.services.whatsapp_bridge import get_status as get_whatsapp_status
    return {
        "telegram": get_telegram_status(),
        "discord": get_discord_status(),
        "whatsapp": get_whatsapp_status(),
        "github": get_github_status(),
        "google": google_status,
    }


async def _build_controls_config(current_user: CurrentChatUser, notices: list[str] | None = None) -> dict[str, Any]:
    _reload_persisted_env()
    ollama_status = await get_ollama_status()
    # Only expose a model in default_selection/stack when the user has explicitly
    # configured one.  Fall back to empty string so the UI shows a clean slate on
    # first launch instead of pre-selecting our hardcoded fallbacks.
    _configured_primary = os.getenv(PRIMARY_MODEL_ENV, "").strip()
    _display_model = _configured_primary or ""
    _configured_local = os.getenv(LOCAL_DEFAULT_MODEL_ENV, "").strip()
    global_control = global_bypass_status()
    return {
        "active_model": get_model(str(current_user.id)),
        "stack": get_model_stack_display(),
        "default_selection": {
            "provider": model_provider(_display_model) or get_default_provider() if _display_model else "openrouter",
            "model": _display_model,
            "label": model_label(_display_model) if _display_model else "",
        },
        "local_runtime": {
            "default_local_model": _configured_local,
            "base_url": os.getenv("OLLAMA_API_BASE", "http://localhost:11434").strip() or "http://localhost:11434",
        },
        "routing_policy": {
            "default_provider_authoritative": True,
            "cross_provider_fallback": default_cross_provider_fallback_enabled(),
        },
        "global_computer_control": global_control["active"],
        "global_computer_control_expires_at": global_control["expires_at"],
        "global_computer_control_ttl_remaining": global_control["ttl_remaining"],
        "agent_overrides": get_agent_model_overrides(),
        "available_agents": [
            {
                "name": "sparkbot",
                "emoji": "S",
                "description": "Main everyday Sparkbot chat",
                "is_builtin": True,
                "identity": {
                    "owner": "sparkbot-core",
                    "purpose": "Main everyday Sparkbot chat",
                    "scopes": ["chat", "tools_via_policy", "orchestration"],
                    "allowed_tools": ["policy_registry"],
                    "expires_at": None,
                    "risk_tier": "standard",
                    "kill_switch": False,
                },
            },
            *[
                {
                    "name": name,
                    "emoji": info["emoji"],
                    "description": info["description"],
                    "is_builtin": name in BUILT_IN_AGENTS,
                    "identity": info.get("identity") or {},
                }
                for name, info in get_all_agents().items()
            ],
        ],
        "token_guardian_mode": os.getenv("SPARKBOT_TOKEN_GUARDIAN_MODE", "shadow").strip().lower() or "shadow",
        "providers": _provider_catalog(ollama_status=ollama_status),
        # Friendly label for every model — keyed by model ID so the frontend
        # can show "GPT-5 Mini — fast…" instead of a raw model string.
        # Auto-updates whenever AVAILABLE_MODELS is updated; no frontend change needed.
        "model_labels": {
            **dict(AVAILABLE_MODELS),
            **({_display_model: model_label(_display_model)} if _display_model else {}),
            **({_configured_local: model_label(_configured_local)} if _configured_local else {}),
        },
        "comms": _build_comms_status(),
        "ollama_status": ollama_status,
        "notices": notices or [],
    }


async def build_safe_runtime_state(current_user: CurrentChatUser) -> dict[str, Any]:
    """Return a safe runtime/config snapshot suitable for chat self-inspection."""
    from app.services.guardian.auth import get_active_session

    config = await _build_controls_config(current_user)
    provider_flags = {
        str(item.get("id")): {
            "configured": bool(item.get("configured")),
            "reachable": item.get("reachable"),
            "models_available": item.get("models_available"),
        }
        for item in list(config.get("providers") or [])
    }
    active_session = get_active_session(str(current_user.id))
    default_provider = str((config.get("default_selection") or {}).get("provider") or "")
    version_markers = _load_version_markers()
    return {
        "assistant_name": "Sparkbot",
        "app_version": version_markers.get("app_version") or "",
        "backend_version": version_markers.get("backend_version") or "",
        "frontend_version": version_markers.get("frontend_version") or "",
        "desktop_shell_version": version_markers.get("desktop_shell_version") or "",
        "active_model": str(config.get("active_model") or ""),
        "default_selection": config.get("default_selection") or {},
        "model_stack": config.get("stack") or {},
        "local_runtime": config.get("local_runtime") or {},
        "default_route_mode": "local" if default_provider == "ollama" else "cloud",
        "routing_policy": config.get("routing_policy") or {},
        "token_guardian_mode": str(config.get("token_guardian_mode") or "unknown"),
        "agent_overrides": config.get("agent_overrides") or {},
        "ollama_status": config.get("ollama_status") or {},
        "openrouter_configured": bool((provider_flags.get("openrouter") or {}).get("configured")),
        "providers": provider_flags,
        "breakglass": {
            "active": active_session is not None,
            "ttl_remaining": active_session.ttl_remaining() if active_session else 0,
            "scopes": list(active_session.scopes) if active_session else [],
        },
        "global_computer_control": {
            "active": bool(config.get("global_computer_control")),
            "ttl_remaining": int(config.get("global_computer_control_ttl_remaining") or 0),
            "expires_at": config.get("global_computer_control_expires_at"),
        },
    }


class ModelSelect(BaseModel):
    model: str


class ModelStackInput(BaseModel):
    primary: str
    backup_1: str = ""
    backup_2: str = ""
    heavy_hitter: str


class ProviderSecretsInput(BaseModel):
    openrouter_api_key: str | None = None
    openai_api_key: str | None = None
    openai_auth_mode: str | None = None
    anthropic_api_key: str | None = None
    anthropic_auth_mode: str | None = None
    google_api_key: str | None = None
    groq_api_key: str | None = None
    minimax_api_key: str | None = None
    xai_api_key: str | None = None
    ollama_base_url: str | None = None


class LocalRuntimeInput(BaseModel):
    default_local_model: str | None = None


class RoutingPolicyInput(BaseModel):
    cross_provider_fallback: bool | None = None


class TelegramConfigInput(BaseModel):
    bot_token: str | None = None
    chat_id: str | None = None
    enabled: bool | None = None
    private_only: bool | None = None


class DiscordConfigInput(BaseModel):
    bot_token: str | None = None
    enabled: bool | None = None
    dm_only: bool | None = None


class WhatsAppConfigInput(BaseModel):
    token: str | None = None
    phone_id: str | None = None
    verify_token: str | None = None
    enabled: bool | None = None


class GitHubConfigInput(BaseModel):
    token: str | None = None
    webhook_secret: str | None = None
    ssh_private_key: str | None = None
    ssh_key_path: str | None = None
    app_id: str | None = None
    app_installation_id: str | None = None
    app_private_key: str | None = None
    bot_login: str | None = None
    default_repo: str | None = None
    allowed_repos: str | None = None
    enabled: bool | None = None


class GoogleConfigInput(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    refresh_token: str | None = None
    calendar_id: str | None = None


class CommsConfigInput(BaseModel):
    telegram: TelegramConfigInput | None = None
    discord: DiscordConfigInput | None = None
    whatsapp: WhatsAppConfigInput | None = None
    github: GitHubConfigInput | None = None
    google: GoogleConfigInput | None = None


class ControlsConfigUpdate(BaseModel):
    stack: ModelStackInput | None = None
    default_selection: dict[str, str] | None = None
    local_runtime: LocalRuntimeInput | None = None
    routing_policy: RoutingPolicyInput | None = None
    agent_overrides: dict[str, dict[str, str]] | None = None
    providers: ProviderSecretsInput | None = None
    comms: CommsConfigInput | None = None
    token_guardian_mode: str | None = Field(default=None, pattern="^(off|shadow|live)$")
    global_computer_control: bool | None = None


def _global_computer_control_enabled() -> bool:
    return bool(global_bypass_status()["active"])


@router.get("/models")
def list_models(current_user: CurrentChatUser) -> dict:
    """Return all available models with descriptions and latency stats."""
    active = get_model(str(current_user.id))
    return {
        "models": [
            {
                "id": k,
                "description": model_label(k),
                "active": k == active,
                "configured": model_is_configured(k),
                "provider": model_provider(k),
                "latency": get_latency_stats(k),
            }
            for k in AVAILABLE_MODELS
        ],
        "active": active,
    }


@router.get("/model")
def get_current_model(current_user: CurrentChatUser) -> dict:
    """Return the active model for the current user."""
    model = get_model(str(current_user.id))
    return {"model": model, "description": model_label(model)}


@router.get("/agents")
def list_agents(current_user: CurrentChatUser) -> dict:
    """Return all available named agents, including spawned custom agents."""
    return {
        "agents": [
            {
                "name": name,
                "emoji": info["emoji"],
                "description": info["description"],
                "is_builtin": name in BUILT_IN_AGENTS,
                "identity": info.get("identity") or {},
            }
            for name, info in get_all_agents().items()
        ]
    }


class AgentCreate(BaseModel):
    name: str = Field(..., max_length=50, pattern=r"^[a-z0-9_]+$")
    emoji: str = Field(default="🤖", max_length=10)
    description: str = Field(default="", max_length=300)
    system_prompt: str = Field(..., min_length=10)
    owner: str | None = Field(default=None, max_length=100)
    purpose: str | None = Field(default=None, max_length=300)
    scopes: list[str] | None = None
    allowed_tools: list[str] | None = None
    expires_at: str | None = Field(default=None, max_length=80)
    risk_tier: str | None = Field(default=None, max_length=40)
    kill_switch: bool = False


@router.post("/agents", status_code=201)
def create_agent(body: AgentCreate, current_user: CurrentChatUser, session: SessionDep) -> dict:
    """Spawn a custom agent — persists to DB and registers immediately (no restart needed)."""
    from sqlmodel import select
    from app.models import CustomAgent

    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    name = body.name.lower().strip()
    if name in BUILT_IN_AGENTS:
        raise HTTPException(status_code=409, detail=f"'{name}' is a built-in agent name.")

    try:
        CustomAgent.__table__.create(session.get_bind(), checkfirst=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not prepare custom agent storage: {exc}")

    existing = session.exec(select(CustomAgent).where(CustomAgent.name == name)).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Agent '{name}' already exists.")

    agent = CustomAgent(
        name=name,
        emoji=body.emoji,
        description=body.description,
        system_prompt=body.system_prompt,
        created_by=current_user.id,
    )
    session.add(agent)
    session.commit()

    identity = {
        "owner": body.owner or current_user.username,
        "purpose": body.purpose or body.description,
        "scopes": body.scopes or ["chat", "room_context"],
        "allowed_tools": body.allowed_tools or ["policy_registry"],
        "expires_at": body.expires_at,
        "risk_tier": body.risk_tier or "standard",
        "kill_switch": bool(body.kill_switch),
    }
    register_agent(name, body.emoji, body.description, body.system_prompt, identity=identity)
    return {
        "name": name,
        "emoji": body.emoji,
        "description": body.description,
        "is_builtin": False,
        "identity": identity,
    }


@router.delete("/agents/{name}", status_code=200)
def delete_agent(name: str, current_user: CurrentChatUser, session: SessionDep) -> dict:
    """Delete a custom agent from DB and unregister from the runtime registry."""
    from sqlmodel import select
    from app.models import CustomAgent

    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    name = name.lower().strip()
    if name in BUILT_IN_AGENTS:
        raise HTTPException(status_code=403, detail=f"Cannot delete built-in agent '{name}'.")

    try:
        CustomAgent.__table__.create(session.get_bind(), checkfirst=True)
    except Exception:
        pass

    agent = session.exec(select(CustomAgent).where(CustomAgent.name == name)).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found.")

    session.delete(agent)
    session.commit()
    unregister_agent(name)
    return {"deleted": name}


class InviteRouteConfig(BaseModel):
    model: str | None = Field(default=None)
    api_key: str | None = Field(default=None)
    # "api_key" (default) or "oauth" — "oauth" means the api_key is a Claude
    # subscription OAuth access token (sk-ant-oat01-…) and should be sent as
    # Authorization: Bearer with the anthropic-beta oauth header, matching how
    # openclaw / Hermes let Claude Pro/Max subscriptions drive the API.
    # "codex_sub" means the api_key is an OpenAI key generated after signing
    # into Codex with a ChatGPT plan; routing is identical to a normal OpenAI key
    # but the UI can preserve the setup mode explicitly.
    auth_mode: str | None = Field(default=None)


@router.post("/agents/{name}/invite-route", status_code=200)
def set_agent_invite_route(name: str, body: InviteRouteConfig, current_user: CurrentChatUser) -> dict:
    """Register a custom model and API key for an invite-seat agent (runtime only, cleared on restart)."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    auth_mode = (body.auth_mode or "").strip().lower() or None
    if auth_mode not in (None, "api_key", "oauth", "codex_sub"):
        auth_mode = None
    set_invite_agent_config(
        name.lower().strip(),
        model=(body.model or "").strip() or None,
        api_key=(body.api_key or "").strip() or None,
        auth_mode=auth_mode,
    )
    return {"name": name.lower().strip(), "configured": True}


@router.post("/model")
def set_current_model(body: ModelSelect, current_user: CurrentChatUser) -> dict:
    """Set the active model for the current user."""
    try:
        chosen = set_model(str(current_user.id), body.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"model": chosen, "description": model_label(chosen)}


@router.get("/models/config")
async def get_models_config(current_user: CurrentChatUser) -> dict[str, Any]:
    _require_operator(current_user)
    return await _build_controls_config(current_user)


@router.get("/ollama/status")
async def ollama_status(current_user: CurrentChatUser) -> dict:
    """Check Ollama server connectivity and list available local models."""
    return await get_ollama_status()


@router.get("/models/latency")
def models_latency(current_user: CurrentChatUser) -> dict:
    """Return latency stats (avg, min, max, last, sample count) for all models seen this session."""
    from app.api.routes.chat.llm import _MODEL_LATENCIES
    return {
        "latency": {
            model: get_latency_stats(model)
            for model in _MODEL_LATENCIES
        }
    }


@router.get("/performance")
def performance_snapshot(current_user: CurrentChatUser) -> dict:
    """Return aggregated chat performance metrics — model + tool latency, error rates, last error."""
    from app.api.routes.chat.llm import get_performance_snapshot
    return get_performance_snapshot()


@router.post("/performance/reset")
def performance_reset(current_user: CurrentChatUser) -> dict:
    """Clear in-memory performance counters. Operator-only."""
    _require_operator(current_user)
    from app.api.routes.chat.llm import reset_performance_snapshot
    reset_performance_snapshot()
    return {"ok": True}


@router.get("/system/watcher")
def system_watcher_status(current_user: CurrentChatUser) -> dict:
    """Return process watcher state: enabled, thresholds, currently throttled processes."""
    from app.services.process_watcher import get_watcher_status
    return get_watcher_status()


@router.get("/openrouter/models")
async def openrouter_models(current_user: CurrentChatUser) -> dict[str, Any]:
    _require_operator(current_user)
    import httpx

    headers = {"Accept": "application/json"}
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not load OpenRouter models: {exc}")
    rows: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        raw_id = str(item.get("id") or "").strip()
        if not raw_id:
            continue
        pricing = item.get("pricing") or {}
        prompt_price = str(pricing.get("prompt") or "1").strip()
        completion_price = str(pricing.get("completion") or "1").strip()
        is_free = raw_id.endswith(":free") or (prompt_price == "0" and completion_price == "0")
        rows.append(
            {
                "id": f"openrouter/{raw_id}",
                "raw_id": raw_id,
                "label": str(item.get("name") or raw_id),
                "context_length": item.get("context_length"),
                "pricing": pricing,
                "is_free": is_free,
            }
        )

    # Sort: free models first, then alphabetically by label
    rows.sort(key=lambda m: (not m.get("is_free", False), str(m.get("label") or m["raw_id"]).lower()))
    return {"models": rows}


@router.post("/models/config")
async def update_models_config(
    body: ControlsConfigUpdate,
    current_user: CurrentChatUser,
    session: SessionDep,
) -> dict[str, Any]:
    _require_operator(current_user)

    env_updates: dict[str, str] = {}
    runtime_only_env_updates: dict[str, str] = {}
    notices: list[str] = []
    restart_required = False

    if body.stack is not None:
        try:
            stack = set_model_stack(
                primary=body.stack.primary,
                backup_1=body.stack.backup_1,
                backup_2=body.stack.backup_2,
                heavy_hitter=body.stack.heavy_hitter,
                user_id=str(current_user.id),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        _new_primary_provider = model_provider(stack["primary"])
        _stack_env: dict[str, str] = {
            PRIMARY_MODEL_ENV: stack["primary"],
            BACKUP_MODEL_1_ENV: stack["backup_1"],
            BACKUP_MODEL_2_ENV: stack["backup_2"],
            HEAVY_HITTER_MODEL_ENV: stack["heavy_hitter"],
        }
        if _new_primary_provider:
            _stack_env[DEFAULT_PROVIDER_ENV] = _new_primary_provider
        if _new_primary_provider == "openrouter":
            _stack_env[OPENROUTER_DEFAULT_MODEL_ENV] = stack["primary"]
        env_updates.update(_stack_env)
        notices.append("Model stack updated for Sparkbot.")

    if body.default_selection is not None:
        provider = str(body.default_selection.get("provider") or "").strip().lower()
        model = str(body.default_selection.get("model") or "").strip()
        if provider not in {"openrouter", "ollama", "openai", "anthropic", "google", "groq", "minimax"}:
            raise HTTPException(status_code=400, detail="Unknown default provider.")
        if not is_valid_model(model):
            raise HTTPException(status_code=400, detail=f"Unknown model '{model}'.")
        actual_provider = model_provider(model)
        if provider == "ollama":
            provider = "ollama"
        if provider != actual_provider:
            raise HTTPException(
                status_code=400,
                detail=f"Model '{model}' does not match provider '{provider}'.",
            )
        env_updates[DEFAULT_PROVIDER_ENV] = provider
        env_updates[PRIMARY_MODEL_ENV] = model
        if provider == "openrouter":
            env_updates[OPENROUTER_DEFAULT_MODEL_ENV] = model
        if provider == "ollama":
            env_updates[LOCAL_DEFAULT_MODEL_ENV] = model
        notices.append(f"Default model set to {model_label(model)}.")

    if body.local_runtime is not None and body.local_runtime.default_local_model is not None:
        local_model = str(body.local_runtime.default_local_model or "").strip()
        if not local_model:
            raise HTTPException(status_code=400, detail="Default local model cannot be empty.")
        if not is_valid_model(local_model) or model_provider(local_model) != "ollama":
            raise HTTPException(status_code=400, detail=f"Local runtime model '{local_model}' must be an Ollama model.")
        env_updates[LOCAL_DEFAULT_MODEL_ENV] = local_model
        notices.append(f"Preferred local model set to {model_label(local_model)}.")

    if body.routing_policy is not None and body.routing_policy.cross_provider_fallback is not None:
        enabled = bool(body.routing_policy.cross_provider_fallback)
        env_updates[DEFAULT_CROSS_PROVIDER_FALLBACK_ENV] = "true" if enabled else "false"
        if enabled:
            notices.append("Cross-provider fallback enabled for the default route.")
        else:
            notices.append("Default provider is now authoritative for everyday chat.")

    if body.global_computer_control is not None:
        new_state = bool(body.global_computer_control)
        prior_state = _global_computer_control_enabled()
        expires_at = time.time() + GLOBAL_COMPUTER_CONTROL_TTL_SECONDS if new_state else 0
        env_updates["SPARKBOT_GLOBAL_COMPUTER_CONTROL"] = "true" if new_state else "false"
        env_updates["SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT"] = str(expires_at) if new_state else ""
        if new_state != prior_state:
            try:
                from app.crud import create_audit_log
                create_audit_log(
                    session=session,
                    tool_name="policy_bypass_global_on" if new_state else "policy_bypass_global_off",
                    tool_input=json.dumps({"operator": str(current_user.username or current_user.id)}),
                    tool_result="enabled" if new_state else "disabled",
                    user_id=current_user.id,
                    room_id=None,
                    model=None,
                )
            except Exception:
                pass
        if new_state:
            notices.append("Global Computer Control is ON for 24 hours. Vault tools remain PIN-protected; edits/deletes/critical changes still ask yes/no.")
        else:
            notices.append("Global Computer Control is OFF. Agents ask for PIN authorization before gated actions.")

    if body.agent_overrides is not None:
        cleaned: dict[str, dict[str, str]] = {}
        _route_to_provider = {"openrouter": "openrouter", "local": "ollama", "openai": "openai", "anthropic": "anthropic", "google": "google", "groq": "groq", "minimax": "minimax", "xai": "xai"}
        for agent_name, value in body.agent_overrides.items():
            route = str((value or {}).get("route") or "default").strip().lower()
            model = str((value or {}).get("model") or "").strip()
            if route not in VALID_AGENT_ROUTES:
                raise HTTPException(status_code=400, detail=f"Invalid route for agent '{agent_name}'.")
            if model and not is_valid_model(model):
                raise HTTPException(status_code=400, detail=f"Unknown model '{model}' for agent '{agent_name}'.")
            if route in _route_to_provider and model:
                expected_provider = _route_to_provider[route]
                if model_provider(model) != expected_provider:
                    raise HTTPException(status_code=400, detail=f"Agent '{agent_name}' route '{route}' requires a {expected_provider} model.")
            cleaned[agent_name.strip().lower()] = {"route": route, "model": model}
        env_updates[AGENT_MODEL_OVERRIDES_ENV] = json.dumps(cleaned, separators=(",", ":"))
        notices.append("Agent routing overrides updated.")

    if body.providers is not None:
        for field_name, env_key in _PROVIDER_ENV_KEYS.items():
            value = getattr(body.providers, field_name)
            if value:
                env_updates[env_key] = value
                notices.append(f"{env_key} stored for runtime use.")
        for field_name, env_key in _PROVIDER_AUTH_MODE_ENV_KEYS.items():
            value = str(getattr(body.providers, field_name) or "").strip().lower()
            if field_name == "openai_auth_mode" and value in {"api_key", "codex_sub"}:
                env_updates[env_key] = value
                notices.append(f"{env_key} stored for runtime use.")
            if field_name == "anthropic_auth_mode" and value in {"api_key", "oauth"}:
                env_updates[env_key] = value
                notices.append(f"{env_key} stored for runtime use.")
        if body.providers.ollama_base_url:
            env_updates["OLLAMA_API_BASE"] = body.providers.ollama_base_url
            notices.append("OLLAMA_API_BASE stored for runtime use.")

    if body.comms is not None:
        if body.comms.telegram is not None:
            token_saved = bool(body.comms.telegram.bot_token)
            if token_saved:
                env_updates["TELEGRAM_BOT_TOKEN"] = body.comms.telegram.bot_token
            chat_id_clean = ""
            if body.comms.telegram.chat_id:
                chat_id_clean = body.comms.telegram.chat_id.strip()
                env_updates["TELEGRAM_CHAT_ID"] = chat_id_clean
                # The bridge reads SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS to map the
                # incoming chat to the operator identity, and TELEGRAM_ALLOWED_CHAT_IDS
                # to restrict who can talk to the bot. Mirror the single UI field
                # into both so saving works without requiring env-file edits.
                env_updates["SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS"] = chat_id_clean
                env_updates["TELEGRAM_ALLOWED_CHAT_IDS"] = chat_id_clean
            if body.comms.telegram.enabled is not None:
                env_updates["TELEGRAM_POLL_ENABLED"] = "true" if body.comms.telegram.enabled else "false"
            elif token_saved:
                # Auto-enable polling when a token is saved and the user didn't
                # explicitly toggle the checkbox. Without this, the poller stays
                # parked and incoming messages never arrive.
                env_updates["TELEGRAM_POLL_ENABLED"] = "true"
            if body.comms.telegram.private_only is not None:
                env_updates["TELEGRAM_REQUIRE_PRIVATE_CHAT"] = "true" if body.comms.telegram.private_only else "false"
            # Telegram poller auto-detects the new token within 30 seconds — no restart needed.
            notices.append("Telegram credentials saved. The bridge will activate within 30 seconds.")
        if body.comms.discord is not None:
            if body.comms.discord.bot_token:
                if _upsert_vault_secret(
                    alias="discord_bot_token",
                    value=body.comms.discord.bot_token,
                    category="communications",
                    notes="Discord bridge bot token",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["DISCORD_BOT_TOKEN"] = body.comms.discord.bot_token
                    notices.append("Discord bot token saved to Vault.")
                else:
                    env_updates["DISCORD_BOT_TOKEN"] = body.comms.discord.bot_token
                    notices.append("Discord bot token saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.discord.enabled is not None:
                env_updates["DISCORD_ENABLED"] = "true" if body.comms.discord.enabled else "false"
            if body.comms.discord.dm_only is not None:
                env_updates["DISCORD_DM_ONLY"] = "true" if body.comms.discord.dm_only else "false"
            restart_required = True
        if body.comms.whatsapp is not None:
            if body.comms.whatsapp.token:
                if _upsert_vault_secret(
                    alias="whatsapp_token",
                    value=body.comms.whatsapp.token,
                    category="communications",
                    notes="WhatsApp bridge access token",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["WHATSAPP_TOKEN"] = body.comms.whatsapp.token
                    notices.append("WhatsApp token saved to Vault.")
                else:
                    env_updates["WHATSAPP_TOKEN"] = body.comms.whatsapp.token
                    notices.append("WhatsApp token saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.whatsapp.phone_id:
                env_updates["WHATSAPP_PHONE_ID"] = body.comms.whatsapp.phone_id
            if body.comms.whatsapp.verify_token:
                if _upsert_vault_secret(
                    alias="whatsapp_verify_token",
                    value=body.comms.whatsapp.verify_token,
                    category="communications",
                    notes="WhatsApp bridge webhook verify token",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["WHATSAPP_VERIFY_TOKEN"] = body.comms.whatsapp.verify_token
                    notices.append("WhatsApp verify token saved to Vault.")
                else:
                    env_updates["WHATSAPP_VERIFY_TOKEN"] = body.comms.whatsapp.verify_token
                    notices.append("WhatsApp verify token saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.whatsapp.enabled is not None:
                env_updates["WHATSAPP_ENABLED"] = "true" if body.comms.whatsapp.enabled else "false"
            restart_required = True
        if body.comms.github is not None:
            if body.comms.github.token:
                if _upsert_vault_secret(
                    alias="github_token",
                    value=body.comms.github.token,
                    category="communications",
                    notes="GitHub bridge access token",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["GITHUB_TOKEN"] = body.comms.github.token
                    notices.append("GitHub token saved to Vault.")
                else:
                    env_updates["GITHUB_TOKEN"] = body.comms.github.token
                    notices.append("GitHub token saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.github.ssh_private_key:
                if _upsert_vault_secret(
                    alias="github_ssh_private_key",
                    value=body.comms.github.ssh_private_key,
                    category="communications",
                    notes="GitHub SSH private key for git access",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["GITHUB_SSH_PRIVATE_KEY"] = body.comms.github.ssh_private_key
                    notices.append("GitHub SSH key saved to Vault.")
                else:
                    env_updates["GITHUB_SSH_PRIVATE_KEY"] = body.comms.github.ssh_private_key
                    notices.append("GitHub SSH key saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.github.ssh_key_path is not None:
                env_updates["GITHUB_SSH_KEY_PATH"] = body.comms.github.ssh_key_path.strip()
            if body.comms.github.app_id is not None:
                env_updates["GITHUB_APP_ID"] = body.comms.github.app_id.strip()
            if body.comms.github.app_installation_id is not None:
                env_updates["GITHUB_APP_INSTALLATION_ID"] = body.comms.github.app_installation_id.strip()
            if body.comms.github.app_private_key:
                if _upsert_vault_secret(
                    alias="github_app_private_key",
                    value=body.comms.github.app_private_key,
                    category="communications",
                    notes="GitHub App private key",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["GITHUB_APP_PRIVATE_KEY"] = body.comms.github.app_private_key
                    notices.append("GitHub App private key saved to Vault.")
                else:
                    env_updates["GITHUB_APP_PRIVATE_KEY"] = body.comms.github.app_private_key
                    notices.append("GitHub App private key saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.github.webhook_secret:
                if _upsert_vault_secret(
                    alias="github_webhook_secret",
                    value=body.comms.github.webhook_secret,
                    category="communications",
                    notes="GitHub bridge webhook secret",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["GITHUB_WEBHOOK_SECRET"] = body.comms.github.webhook_secret
                    notices.append("GitHub webhook secret saved to Vault.")
                else:
                    env_updates["GITHUB_WEBHOOK_SECRET"] = body.comms.github.webhook_secret
                    notices.append("GitHub webhook secret saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.github.bot_login:
                env_updates["GITHUB_BOT_LOGIN"] = body.comms.github.bot_login
            if body.comms.github.default_repo is not None:
                env_updates["GITHUB_DEFAULT_REPO"] = body.comms.github.default_repo
            if body.comms.github.allowed_repos is not None:
                normalized = ",".join(
                    repo.strip() for repo in body.comms.github.allowed_repos.split(",") if repo.strip()
                )
                env_updates["GITHUB_ALLOWED_REPOS"] = normalized
            if body.comms.github.enabled is not None:
                env_updates["GITHUB_BRIDGE_ENABLED"] = "true" if body.comms.github.enabled else "false"
            restart_required = True
        if body.comms.google is not None:
            if body.comms.google.client_id:
                if _upsert_vault_secret(
                    alias="google_client_id",
                    value=body.comms.google.client_id,
                    category="communications",
                    notes="Google OAuth client id",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["GOOGLE_CLIENT_ID"] = body.comms.google.client_id
                    notices.append("Google client ID saved to Vault.")
                else:
                    env_updates["GOOGLE_CLIENT_ID"] = body.comms.google.client_id
                    notices.append("Google client ID saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.google.client_secret:
                if _upsert_vault_secret(
                    alias="google_client_secret",
                    value=body.comms.google.client_secret,
                    category="communications",
                    notes="Google OAuth client secret",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["GOOGLE_CLIENT_SECRET"] = body.comms.google.client_secret
                    notices.append("Google client secret saved to Vault.")
                else:
                    env_updates["GOOGLE_CLIENT_SECRET"] = body.comms.google.client_secret
                    notices.append("Google client secret saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.google.refresh_token:
                if _upsert_vault_secret(
                    alias="google_refresh_token",
                    value=body.comms.google.refresh_token,
                    category="communications",
                    notes="Google OAuth refresh token",
                    current_user=current_user,
                ):
                    runtime_only_env_updates["GOOGLE_REFRESH_TOKEN"] = body.comms.google.refresh_token
                    notices.append("Google refresh token saved to Vault.")
                else:
                    env_updates["GOOGLE_REFRESH_TOKEN"] = body.comms.google.refresh_token
                    notices.append("Google refresh token saved to env storage. Use break-glass access to persist it in Vault.")
            if body.comms.google.calendar_id is not None:
                env_updates["GOOGLE_CALENDAR_ID"] = body.comms.google.calendar_id
            notices.append("Google credentials saved — Gmail and Calendar skills are live immediately.")

    if body.token_guardian_mode is not None:
        env_updates["SPARKBOT_TOKEN_GUARDIAN_MODE"] = body.token_guardian_mode
        notices.append(f"Token Guardian set to {body.token_guardian_mode}.")

    if not env_updates and not runtime_only_env_updates:
        raise HTTPException(status_code=400, detail="No model, provider, or comms updates were supplied.")

    _apply_env_updates(env_updates)
    _apply_env_updates(runtime_only_env_updates)
    if env_updates:
        _write_env_updates(env_updates)

    if restart_required:
        notices.append("Communications changes were saved. Restart sparkbot-v2 to apply bridge startup changes.")
    elif body.providers is not None:
        notices.append("Provider tokens are live in the current process and persisted for restart.")

    response = await _build_controls_config(current_user, notices=notices)
    response["restart_required"] = restart_required
    return response
