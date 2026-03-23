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
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import CurrentChatUser, SessionDep
from app.api.routes.chat.agents import BUILT_IN_AGENTS, get_all_agents, register_agent, unregister_agent
from app.core.config import settings
from app.api.routes.chat.llm import (
    AGENT_MODEL_OVERRIDES_ENV,
    AVAILABLE_MODELS,
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
    get_local_default_model,
    get_model,
    get_model_stack,
    get_ollama_status,
    get_openrouter_default_model,
    is_valid_model,
    model_label,
    model_is_configured,
    model_provider,
    set_model,
    set_model_stack,
)
# Bridge status imports are deferred to avoid loading bridge libraries
# (discord.py, pywa, etc.) when V1_LOCAL_MODE is active.
# In V1_LOCAL_MODE the comms status section returns None for all bridges.

router = APIRouter(tags=["chat-model"])

_ENV_UPDATE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
_PROVIDER_ENV_KEYS = {
    "openrouter_api_key": "OPENROUTER_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "google_api_key": "GOOGLE_API_KEY",
    "groq_api_key": "GROQ_API_KEY",
    "minimax_api_key": "MINIMAX_API_KEY",
}
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


def _require_operator(current_user: CurrentChatUser) -> None:
    from app.services.guardian.auth import is_operator_identity

    if not current_user or not is_operator_identity(
        username=current_user.username,
        user_type=current_user.type,
    ):
        raise HTTPException(status_code=403, detail="Operator access required.")


def _sanitize_env_value(value: str) -> str:
    return str(value or "").replace("\r", "").replace("\n", "").strip()


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
    ]
    items: list[dict[str, Any]] = []
    for provider_id, label, env_key in ordered:
        items.append(
            {
                "id": provider_id,
                "label": label,
                "configured": bool(os.getenv(env_key, "").strip()),
                "reachable": None,
                "models_available": None,
                "available_models": [],
                "models": sorted(models_by_provider.get(provider_id, [])),
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


def _build_comms_status() -> dict[str, Any]:
    """Return bridge comms status. Imports bridge modules lazily so that
    discord.py / pywa / telegram are not loaded in V1_LOCAL_MODE."""
    if settings.V1_LOCAL_MODE:
        return {
            "telegram": {"poll_enabled": False, "private_only": True},
            "discord": {"enabled": False, "dm_only": False},
            "whatsapp": {"enabled": False},
            "github": {"enabled": False, "bot_login": "sparkbot", "default_repo": "", "allowed_repos": []},
        }
    from app.services.discord_bridge import get_status as get_discord_status
    from app.services.github_bridge import get_status as get_github_status
    from app.services.telegram_bridge import get_status as get_telegram_status
    from app.services.whatsapp_bridge import get_status as get_whatsapp_status
    return {
        "telegram": get_telegram_status(),
        "discord": get_discord_status(),
        "whatsapp": get_whatsapp_status(),
        "github": get_github_status(),
    }


async def _build_controls_config(current_user: CurrentChatUser, notices: list[str] | None = None) -> dict[str, Any]:
    ollama_status = await get_ollama_status()
    return {
        "active_model": get_model(str(current_user.id)),
        "stack": get_model_stack(),
        "default_selection": {
            "provider": model_provider(get_model()) or get_default_provider(),
            "model": get_model(),
            "label": model_label(get_model()),
        },
        "local_runtime": {
            "default_local_model": get_local_default_model(),
            "base_url": os.getenv("OLLAMA_API_BASE", "http://localhost:11434").strip() or "http://localhost:11434",
        },
        "routing_policy": {
            "default_provider_authoritative": True,
            "cross_provider_fallback": default_cross_provider_fallback_enabled(),
        },
        "agent_overrides": get_agent_model_overrides(),
        "available_agents": [
            {
                "name": "sparkbot",
                "emoji": "S",
                "description": "Main everyday Sparkbot chat",
                "is_builtin": True,
            },
            *[
                {
                    "name": name,
                    "emoji": info["emoji"],
                    "description": info["description"],
                    "is_builtin": name in BUILT_IN_AGENTS,
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
            get_model(): model_label(get_model()),
            get_openrouter_default_model(): model_label(get_openrouter_default_model()),
            get_local_default_model(): model_label(get_local_default_model()),
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
    return {
        "assistant_name": "Sparkbot",
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
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    groq_api_key: str | None = None
    minimax_api_key: str | None = None
    ollama_base_url: str | None = None


class LocalRuntimeInput(BaseModel):
    default_local_model: str | None = None


class RoutingPolicyInput(BaseModel):
    cross_provider_fallback: bool | None = None


class TelegramConfigInput(BaseModel):
    bot_token: str | None = None
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
    bot_login: str | None = None
    default_repo: str | None = None
    allowed_repos: str | None = None
    enabled: bool | None = None


class CommsConfigInput(BaseModel):
    telegram: TelegramConfigInput | None = None
    discord: DiscordConfigInput | None = None
    whatsapp: WhatsAppConfigInput | None = None
    github: GitHubConfigInput | None = None


class ControlsConfigUpdate(BaseModel):
    stack: ModelStackInput | None = None
    default_selection: dict[str, str] | None = None
    local_runtime: LocalRuntimeInput | None = None
    routing_policy: RoutingPolicyInput | None = None
    agent_overrides: dict[str, dict[str, str]] | None = None
    providers: ProviderSecretsInput | None = None
    comms: CommsConfigInput | None = None
    token_guardian_mode: str | None = Field(default=None, pattern="^(off|shadow|live)$")


@router.get("/models")
def list_models(current_user: CurrentChatUser) -> dict:
    """Return all available models with descriptions."""
    active = get_model(str(current_user.id))
    return {
        "models": [
            {"id": k, "description": model_label(k), "active": k == active, "configured": model_is_configured(k), "provider": model_provider(k)}
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
            }
            for name, info in get_all_agents().items()
        ]
    }


class AgentCreate(BaseModel):
    name: str = Field(..., max_length=50, pattern=r"^[a-z0-9_]+$")
    emoji: str = Field(default="🤖", max_length=10)
    description: str = Field(default="", max_length=300)
    system_prompt: str = Field(..., min_length=10)


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

    register_agent(name, body.emoji, body.description, body.system_prompt)
    return {"name": name, "emoji": body.emoji, "description": body.description, "is_builtin": False}


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

    agent = session.exec(select(CustomAgent).where(CustomAgent.name == name)).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found.")

    session.delete(agent)
    session.commit()
    unregister_agent(name)
    return {"deleted": name}


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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not load OpenRouter models: {exc}")

    payload = response.json()
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
async def update_models_config(body: ControlsConfigUpdate, current_user: CurrentChatUser) -> dict[str, Any]:
    _require_operator(current_user)

    env_updates: dict[str, str] = {}
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

    if body.agent_overrides is not None:
        cleaned: dict[str, dict[str, str]] = {}
        for agent_name, value in body.agent_overrides.items():
            route = str((value or {}).get("route") or "default").strip().lower()
            model = str((value or {}).get("model") or "").strip()
            if route not in {"default", "openrouter", "local"}:
                raise HTTPException(status_code=400, detail=f"Invalid route for agent '{agent_name}'.")
            if model and not is_valid_model(model):
                raise HTTPException(status_code=400, detail=f"Unknown model '{model}' for agent '{agent_name}'.")
            if route == "openrouter" and model and model_provider(model) != "openrouter":
                raise HTTPException(status_code=400, detail=f"Agent '{agent_name}' must use an OpenRouter model.")
            if route == "local" and model and model_provider(model) != "ollama":
                raise HTTPException(status_code=400, detail=f"Agent '{agent_name}' must use a local Ollama model.")
            cleaned[agent_name.strip().lower()] = {"route": route, "model": model}
        env_updates[AGENT_MODEL_OVERRIDES_ENV] = json.dumps(cleaned, separators=(",", ":"))
        notices.append("Agent routing overrides updated.")

    if body.providers is not None:
        for field_name, env_key in _PROVIDER_ENV_KEYS.items():
            value = getattr(body.providers, field_name)
            if value:
                env_updates[env_key] = value
                notices.append(f"{env_key} stored for runtime use.")
        if body.providers.ollama_base_url:
            env_updates["OLLAMA_API_BASE"] = body.providers.ollama_base_url
            notices.append("OLLAMA_API_BASE stored for runtime use.")

    if body.comms is not None:
        if body.comms.telegram is not None:
            if body.comms.telegram.bot_token:
                env_updates["TELEGRAM_BOT_TOKEN"] = body.comms.telegram.bot_token
            if body.comms.telegram.enabled is not None:
                env_updates["TELEGRAM_POLL_ENABLED"] = "true" if body.comms.telegram.enabled else "false"
            if body.comms.telegram.private_only is not None:
                env_updates["TELEGRAM_REQUIRE_PRIVATE_CHAT"] = "true" if body.comms.telegram.private_only else "false"
            restart_required = True
        if body.comms.discord is not None:
            if body.comms.discord.bot_token:
                env_updates["DISCORD_BOT_TOKEN"] = body.comms.discord.bot_token
            if body.comms.discord.enabled is not None:
                env_updates["DISCORD_ENABLED"] = "true" if body.comms.discord.enabled else "false"
            if body.comms.discord.dm_only is not None:
                env_updates["DISCORD_DM_ONLY"] = "true" if body.comms.discord.dm_only else "false"
            restart_required = True
        if body.comms.whatsapp is not None:
            if body.comms.whatsapp.token:
                env_updates["WHATSAPP_TOKEN"] = body.comms.whatsapp.token
            if body.comms.whatsapp.phone_id:
                env_updates["WHATSAPP_PHONE_ID"] = body.comms.whatsapp.phone_id
            if body.comms.whatsapp.verify_token:
                env_updates["WHATSAPP_VERIFY_TOKEN"] = body.comms.whatsapp.verify_token
            if body.comms.whatsapp.enabled is not None:
                env_updates["WHATSAPP_ENABLED"] = "true" if body.comms.whatsapp.enabled else "false"
            restart_required = True
        if body.comms.github is not None:
            if body.comms.github.token:
                env_updates["GITHUB_TOKEN"] = body.comms.github.token
            if body.comms.github.webhook_secret:
                env_updates["GITHUB_WEBHOOK_SECRET"] = body.comms.github.webhook_secret
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

    if body.token_guardian_mode is not None:
        env_updates["SPARKBOT_TOKEN_GUARDIAN_MODE"] = body.token_guardian_mode
        notices.append(f"Token Guardian set to {body.token_guardian_mode}.")

    if not env_updates:
        raise HTTPException(status_code=400, detail="No model, provider, or comms updates were supplied.")

    _apply_env_updates(env_updates)
    _write_env_updates(env_updates)

    if restart_required:
        notices.append("Communications changes were saved. Restart sparkbot-v2 to apply bridge startup changes.")
    elif body.providers is not None:
        notices.append("Provider tokens are live in the current process and persisted for restart.")

    response = await _build_controls_config(current_user, notices=notices)
    response["restart_required"] = restart_required
    return response
