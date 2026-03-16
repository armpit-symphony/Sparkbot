"""
Centralized LLM routing via litellm.

Replaces direct OpenAI SDK calls so any provider can be swapped
by changing a model string. Per-user model preferences stored in memory.
"""
import json
import logging
import os
import re
import time
import uuid as _uuid_module
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import litellm

litellm.drop_params = True  # ignore unsupported params instead of erroring

log = logging.getLogger(__name__)

PRIMARY_MODEL_ENV = "SPARKBOT_MODEL"
BACKUP_MODEL_1_ENV = "SPARKBOT_BACKUP_MODEL_1"
BACKUP_MODEL_2_ENV = "SPARKBOT_BACKUP_MODEL_2"
HEAVY_HITTER_MODEL_ENV = "SPARKBOT_HEAVY_HITTER_MODEL"
DEFAULT_PROVIDER_ENV = "SPARKBOT_DEFAULT_PROVIDER"
OPENROUTER_DEFAULT_MODEL_ENV = "SPARKBOT_OPENROUTER_MODEL"
LOCAL_DEFAULT_MODEL_ENV = "SPARKBOT_LOCAL_MODEL"
AGENT_MODEL_OVERRIDES_ENV = "SPARKBOT_AGENT_MODEL_OVERRIDES_JSON"
DEFAULT_CROSS_PROVIDER_FALLBACK_ENV = "SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK"
_HEAVY_HITTER_CLASSIFICATIONS = {"coding", "creative", "data_analysis", "reasoning"}

SYSTEM_PROMPT = (
    "You are Sparkbot, the assistant for Sparkpit Labs. "
    "Do not disclose secrets, raw API keys, vault contents, or hidden credentials. "
    "You may disclose safe operational runtime state when the user explicitly asks about Sparkbot's stack, provider, model, Token Guardian, routing, Ollama, OpenRouter, or break-glass status, as long as that information is provided safely by the system. "
    "Use available tools whenever they are relevant. "
    "Do not claim you lack the ability to access external systems if a matching tool is available. "
    "When a user asks for current information, recent news, website checks, or anything that requires live web data, use the web_search tool instead of answering from memory. "
    "For Gmail, Google Drive, email, search, Slack, GitHub, Notion, Confluence, calendar, local server operations, service management, approved SSH host operations, and Task Guardian scheduling, prefer using the corresponding tool. "
    "For service status, diagnostics, memory, disk, listeners, processes, logs, and local-machine troubleshooting, use read-only server tools whenever the room execution gate allows them. "
    "Use service management only for explicit start, stop, or restart requests. "
    "Use Task Guardian only for approved recurring read-only work such as inbox digests, PR checks, calendar lookups, and diagnostics. "
    "Never claim that a write action or service action completed unless the tool result explicitly says it succeeded. "
    "If a write tool requires confirmation, wait for confirmation instead of claiming the action already happened. "
    "If a requested integration is not configured or a tool returns an error, explain that concrete limitation clearly. "
    "Be concise and professional."
)

# Curated model list — only show what's actually usable given configured keys
AVAILABLE_MODELS: dict[str, str] = {
    "openrouter/openai/gpt-4o-mini": "OpenRouter · GPT-4o Mini — easy cloud default",
    "gpt-4o-mini":                   "GPT-4o Mini — fast, cost-effective (default)",
    "gpt-4o":                        "GPT-4o — most capable OpenAI model",
    "gpt-4.5":                       "GPT-4.5 — OpenAI advanced reasoning model",
    "gpt-5-mini":                    "GPT-5 Mini — fast, cost-effective next-gen model",
    "claude-3-5-haiku-20241022":     "Claude Haiku — fast Anthropic model",
    "claude-sonnet-4-5":             "Claude Sonnet — balanced Anthropic model",
    "gemini/gemini-2.0-flash":       "Gemini Flash — fast Google model",
    "groq/llama-3.3-70b-versatile":  "Llama 3.3 70B via Groq — very fast",
    "minimax/MiniMax-M2.5":          "MiniMax M2.5 — reasoning + tool calling (MINIMAX_API_KEY)",
}

OLLAMA_MODELS: dict[str, str] = {
    "ollama/llama3.2:1b":    "Llama 3.2 1B — fastest, lowest memory (~1 GB)",
    "ollama/llama3.2:3b":    "Llama 3.2 3B — fast and balanced (~2 GB)",
    "ollama/phi4-mini":      "Phi-4 Mini — best default quality/speed balance (~2.5 GB)",
    "ollama/phi3.5":         "Phi 3.5 — reasoning-focused, efficient (~2 GB)",
    "ollama/gemma2:2b":      "Gemma 2 2B — compact quality (~1.6 GB)",
    "ollama/granite3.3:2b":  "Granite 3.3 2B — long-context, compact (~1.5 GB)",
    "ollama/mistral:7b":     "Mistral 7B — stronger quality (~4.1 GB)",
    "ollama/falcon3:1b":       "Falcon3 1B — ultra-light (~0.6 GB)",
    "ollama/falcon3:3b":       "Falcon3 3B — light and capable (~1.7 GB)",
    "ollama/falcon3:7b":       "Falcon3 7B — powerful, good reasoning (~4 GB)",
    "ollama/gemma2:9b":        "Gemma 2 9B — strong quality, larger model (~5.5 GB)",
    "ollama/granite3.3:8b":    "Granite 3.3 8B — long-context, stronger (~4.9 GB)",
}
# Merge into AVAILABLE_MODELS so model routing works
AVAILABLE_MODELS.update(OLLAMA_MODELS)

# In-memory per-user model preferences  {user_id: model_name}
# Resets on service restart — good enough until DB persistence is added
_user_models: dict[str, str] = {}

# Pending confirmations: confirm_id -> {tool, args, user_id, room_id, created_at}
_pending: dict[str, dict] = {}
_PENDING_TTL = 600  # 10 minutes


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _pending_ttl_cleanup() -> None:
    now = time.time()
    stale = [k for k, v in _pending.items() if now - v["created_at"] > _PENDING_TTL]
    for k in stale:
        _pending.pop(k, None)


def consume_pending(confirm_id: str) -> dict | None:
    """Pop and return a pending confirmation entry, or None if not found/expired."""
    entry = _pending.pop(confirm_id, None)
    if entry and time.time() - entry["created_at"] > _PENDING_TTL:
        try:
            from app.services.guardian.pending_approvals import discard_pending_approval

            discard_pending_approval(confirm_id)
        except Exception:
            pass
        return None
    if entry:
        try:
            from app.services.guardian.pending_approvals import discard_pending_approval

            discard_pending_approval(confirm_id)
        except Exception:
            pass
        return entry
    try:
        from app.services.guardian.pending_approvals import consume_pending_approval

        return consume_pending_approval(confirm_id)
    except Exception:
        return None


def discard_pending(confirm_id: str) -> None:
    _pending.pop(confirm_id, None)
    try:
        from app.services.guardian.pending_approvals import discard_pending_approval

        discard_pending_approval(confirm_id)
    except Exception:
        pass


# ── Audit log redaction ───────────────────────────────────────────────────────

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|access_key|credential|auth_token|passphrase|private_key)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"xoxb-[A-Za-z0-9\-]+"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"secret_[A-Za-z0-9]{40,}"),
]

# Tools whose plaintext result must never leave the LLM context boundary.
# Result is replaced with a placeholder in all outward-facing paths:
# SSE tool_done events, audit logs, memory, Telegram responses, chat DB.
_VAULT_INTERNAL_TOOLS: frozenset[str] = frozenset({"vault_use_secret"})
_VAULT_VALUE_ARG_TOOLS: frozenset[str] = frozenset({"vault_add_secret", "vault_update_secret"})


def _masked_vault_placeholder(tool_args: dict | None) -> str:
    alias = "secret"
    if isinstance(tool_args, dict):
        alias = str(tool_args.get("alias") or alias).strip() or alias
    return f"[vault:{alias}]"


def mask_tool_result_for_external(tool_name: str, tool_args: dict | None, result: object) -> str:
    if tool_name in _VAULT_INTERNAL_TOOLS:
        return _masked_vault_placeholder(tool_args)
    return str(result)


def _sanitize_tool_args_for_audit(tool_name: str, tool_args: dict | None) -> str:
    safe_args = dict(tool_args) if isinstance(tool_args, dict) else {}
    if tool_name in _VAULT_VALUE_ARG_TOOLS and "value" in safe_args:
        safe_args["value"] = "[REDACTED]"
    return json.dumps(safe_args)


def serialize_tool_args_for_audit(tool_name: str, tool_args: dict | None) -> str:
    return _sanitize_tool_args_for_audit(tool_name, tool_args)


def redact_tool_call_for_audit(
    tool_name: str,
    tool_args: dict | None,
    result: object,
) -> tuple[str, str]:
    outward_result = mask_tool_result_for_external(tool_name, tool_args, result)
    return _redact_for_audit(_sanitize_tool_args_for_audit(tool_name, tool_args), outward_result)


_GENERIC_SECRET_PAIR_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|auth[_-]?token|passphrase|private[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)


def _redact_secret_like_text(text: str) -> str:
    return _GENERIC_SECRET_PAIR_RE.sub(r"\1\2[REDACTED]", text)


def _redact_for_audit(tool_input: str, tool_result: str) -> tuple[str, str]:
    """Redact sensitive values from audit log entries."""
    try:
        data = json.loads(tool_input)
        for key in list(data.keys()):
            if _SECRET_KEY_RE.search(key):
                data[key] = "[REDACTED]"
        tool_input = json.dumps(data)
    except Exception:
        pass
    tool_input = _redact_secret_like_text(tool_input)
    for pattern in _SECRET_VALUE_PATTERNS:
        tool_result = pattern.sub("[REDACTED]", tool_result)
    # Also redact secret-keyed fields if result is a JSON dict
    try:
        result_data = json.loads(tool_result)
        if isinstance(result_data, dict):
            for key in list(result_data.keys()):
                if _SECRET_KEY_RE.search(key):
                    result_data[key] = "[REDACTED]"
            tool_result = json.dumps(result_data)
    except Exception:
        pass
    tool_result = _redact_secret_like_text(tool_result)
    return tool_input, tool_result


async def get_ollama_status() -> dict:
    """Check Ollama server connectivity and list available local models."""
    import httpx
    base_url = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                model_ids = [
                    name if name.startswith("ollama/") else f"ollama/{name}"
                    for name in models
                ]
                return {
                    "reachable": True,
                    "base_url": base_url,
                    "models": models,
                    "model_ids": model_ids,
                    "models_available": bool(model_ids),
                }
    except Exception:
        pass
    return {
        "reachable": False,
        "base_url": base_url,
        "models": [],
        "model_ids": [],
        "models_available": False,
    }


def is_valid_model(model: str) -> bool:
    normalized = (model or "").strip()
    if not normalized:
        return False
    if normalized in AVAILABLE_MODELS:
        return True
    if normalized.startswith("openrouter/"):
        return True
    if normalized.startswith("ollama/"):
        return True
    return False


def model_label(model: str) -> str:
    normalized = (model or "").strip()
    if normalized in AVAILABLE_MODELS:
        return AVAILABLE_MODELS[normalized]
    if normalized.startswith("openrouter/"):
        slug = normalized.removeprefix("openrouter/")
        return f"OpenRouter · {slug}"
    if normalized.startswith("ollama/"):
        slug = normalized.removeprefix("ollama/")
        return f"Local Ollama · {slug}"
    return normalized


def _default_model() -> str:
    return (
        os.getenv(PRIMARY_MODEL_ENV, os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip()
        or "gpt-4o-mini"
    )


def get_default_provider() -> str:
    explicit = os.getenv(DEFAULT_PROVIDER_ENV, "").strip().lower()
    if explicit:
        return explicit
    return model_provider(_default_model())


def get_openrouter_default_model() -> str:
    configured = os.getenv(OPENROUTER_DEFAULT_MODEL_ENV, "").strip()
    if configured:
        return configured
    primary = _default_model()
    if model_provider(primary) == "openrouter":
        return primary
    return "openrouter/openai/gpt-4o-mini"


def get_local_default_model() -> str:
    configured = os.getenv(LOCAL_DEFAULT_MODEL_ENV, "").strip()
    if configured:
        return configured
    primary = _default_model()
    if model_provider(primary) == "ollama":
        return primary
    return "ollama/phi4-mini"


def default_cross_provider_fallback_enabled() -> bool:
    raw = os.getenv(DEFAULT_CROSS_PROVIDER_FALLBACK_ENV, "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    # Local installs should fail within the chosen provider unless the user
    # explicitly opts into cross-provider fallback.
    return os.getenv("V1_LOCAL_MODE", "false").strip().lower() not in {"1", "true", "yes", "on"}


def get_agent_model_overrides() -> dict[str, dict[str, str]]:
    raw = os.getenv(AGENT_MODEL_OVERRIDES_ENV, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    cleaned: dict[str, dict[str, str]] = {}
    for key, value in parsed.items():
        if not isinstance(value, dict):
            continue
        route = str(value.get("route") or "default").strip().lower()
        model = str(value.get("model") or "").strip()
        if route not in {"default", "openrouter", "local"}:
            continue
        cleaned[str(key).strip().lower()] = {"route": route, "model": model}
    return cleaned


def get_agent_route_context(
    *,
    default_model: str,
    agent_name: str | None = None,
) -> dict[str, Any]:
    overrides = get_agent_model_overrides()
    effective_agent = (agent_name or "sparkbot").strip().lower()
    override = overrides.get(effective_agent)

    route = str((override or {}).get("route") or "default").strip().lower()
    if route not in {"default", "openrouter", "local"}:
        route = "default"

    chosen_model = default_model
    if route == "openrouter":
        chosen_model = str((override or {}).get("model") or "").strip() or get_openrouter_default_model()
    elif route == "local":
        chosen_model = str((override or {}).get("model") or "").strip() or get_local_default_model()

    return {
        "agent_name": effective_agent,
        "route": route,
        "provider_locked": route in {"openrouter", "local"},
        "model": chosen_model,
        "requested_provider": model_provider(chosen_model),
        "cross_provider_fallback": (
            default_cross_provider_fallback_enabled()
            if route == "default"
            else False
        ),
    }


def model_provider(model: str) -> str:
    normalized = (model or "").strip()
    if normalized.startswith("openrouter/"):
        return "openrouter"
    if normalized.startswith("gpt-"):
        return "openai"
    if normalized.startswith("claude"):
        return "anthropic"
    if normalized.startswith("gemini/"):
        return "google"
    if normalized.startswith("groq/"):
        return "groq"
    if normalized.startswith("minimax/"):
        return "minimax"
    if normalized.startswith("ollama/"):
        return "ollama"
    return "other"


def model_is_configured(model: str) -> bool:
    provider = model_provider(model)
    if provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY", "").strip())
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    if provider == "google":
        return bool(os.getenv("GOOGLE_API_KEY", "").strip())
    if provider == "groq":
        return bool(os.getenv("GROQ_API_KEY", "").strip())
    if provider == "minimax":
        return bool(os.getenv("MINIMAX_API_KEY", "").strip())
    if provider == "ollama":
        # Ollama is always "configured" — it's local, no API key needed
        return True
    return bool((model or "").strip())


def get_model_stack() -> dict[str, str]:
    primary = _default_model()
    backup_1 = os.getenv(BACKUP_MODEL_1_ENV, "").strip()
    backup_2 = os.getenv(BACKUP_MODEL_2_ENV, "").strip()
    heavy_hitter = os.getenv(HEAVY_HITTER_MODEL_ENV, "").strip() or "gpt-4o"
    return {
        "primary": primary,
        "backup_1": backup_1,
        "backup_2": backup_2,
        "heavy_hitter": heavy_hitter,
    }


def set_model_stack(
    *,
    primary: str,
    backup_1: str,
    backup_2: str,
    heavy_hitter: str,
    user_id: str | None = None,
) -> dict[str, str]:
    stack = {
        "primary": (primary or "").strip(),
        "backup_1": (backup_1 or "").strip(),
        "backup_2": (backup_2 or "").strip(),
        "heavy_hitter": (heavy_hitter or "").strip(),
    }
    for key, model in stack.items():
        if model and not is_valid_model(model):
            raise ValueError(f"Unknown model '{model}' for {key}.")

    non_empty = [model for model in stack.values() if model]
    if len(non_empty) != len(set(non_empty)):
        raise ValueError("Primary, backup, and heavy hitter models must be distinct.")

    os.environ[PRIMARY_MODEL_ENV] = stack["primary"]
    os.environ[BACKUP_MODEL_1_ENV] = stack["backup_1"]
    os.environ[BACKUP_MODEL_2_ENV] = stack["backup_2"]
    os.environ[HEAVY_HITTER_MODEL_ENV] = stack["heavy_hitter"]

    if user_id:
        _user_models[user_id] = stack["primary"]

    return stack


def _annotate_route_payload(
    route_payload: dict[str, Any] | None,
    *,
    route_context: dict[str, Any],
    current_model: str,
    applied_model: str | None = None,
) -> dict[str, Any]:
    payload = dict(route_payload or {})
    payload["route"] = route_context["route"]
    payload["provider_locked"] = bool(route_context["provider_locked"])
    payload["requested_provider"] = route_context["requested_provider"]
    payload["requested_model"] = route_context["model"]
    payload["current_model"] = current_model
    resolved_applied = (applied_model or payload.get("applied_model") or current_model).strip()
    payload["applied_model"] = resolved_applied
    payload["applied_provider"] = model_provider(resolved_applied)
    return payload


def _locked_route_payload(
    *,
    message: str,
    route_context: dict[str, Any],
) -> dict[str, Any]:
    model_name = str(route_context["model"]).strip()
    return {
        "timestamp": _utc_now_iso(),
        "query": message,
        "classification": "forced_provider",
        "confidence": 1.0,
        "threshold": 1.0,
        "selected_model": model_name,
        "fallback_triggered": False,
        "fallback_reason": None,
        "optimization": None,
        "estimated_cost": 0.0,
        "status": "locked",
        "mode": "locked",
        "current_model": model_name,
        "estimated_tokens": None,
        "estimated_current_cost": 0.0,
        "estimated_savings": 0.0,
        "would_switch_models": False,
        "configured_models": [model_name],
        "allowed_live_models": [model_name],
        "live_ready": True,
        "selected_model_supported": is_valid_model(model_name),
        "selected_model_configured": model_is_configured(model_name),
        "selected_model_allowed": True,
        "candidate_models": [model_name],
        "applied_model": model_name,
        "applied_provider": route_context["requested_provider"],
        "live_routed": False,
        "route": route_context["route"],
        "provider_locked": True,
        "requested_provider": route_context["requested_provider"],
        "requested_model": model_name,
    }


def _provider_authoritative_route_payload(
    *,
    message: str,
    route_context: dict[str, Any],
) -> dict[str, Any]:
    model_name = str(route_context["model"]).strip()
    provider_name = str(route_context["requested_provider"]).strip()
    return {
        "timestamp": _utc_now_iso(),
        "query": message,
        "classification": "default_provider_authoritative",
        "confidence": 1.0,
        "threshold": 1.0,
        "selected_model": model_name,
        "fallback_triggered": False,
        "fallback_reason": None,
        "optimization": None,
        "estimated_cost": 0.0,
        "status": "provider_default",
        "mode": "provider_default",
        "current_model": model_name,
        "estimated_tokens": None,
        "estimated_current_cost": 0.0,
        "estimated_savings": 0.0,
        "would_switch_models": False,
        "configured_models": [model_name],
        "allowed_live_models": [model_name],
        "live_ready": True,
        "selected_model_supported": is_valid_model(model_name),
        "selected_model_configured": model_is_configured(model_name),
        "selected_model_allowed": True,
        "candidate_models": [model_name],
        "applied_model": model_name,
        "applied_provider": provider_name,
        "live_routed": False,
        "route": "default",
        "provider_locked": False,
        "requested_provider": provider_name,
        "requested_model": model_name,
        "cross_provider_fallback": bool(route_context.get("cross_provider_fallback")),
        "provider_authoritative": True,
    }


async def _ensure_locked_route_ready(route_context: dict[str, Any]) -> None:
    route = str(route_context.get("route") or "default").strip().lower()
    model_name = str(route_context.get("model") or "").strip()
    if route == "openrouter":
        if not os.getenv("OPENROUTER_API_KEY", "").strip():
            raise RuntimeError(
                "OpenRouter is forced for this agent, but no OpenRouter API key is saved in Controls."
            )
        return
    if route == "local":
        ollama_status = await get_ollama_status()
        if not ollama_status.get("reachable"):
            raise RuntimeError(
                f"Local Ollama is forced for this agent, but Ollama is not reachable at {ollama_status['base_url']}."
            )
        if model_name not in set(ollama_status.get("model_ids") or []):
            raise RuntimeError(
                f"Local Ollama is forced for this agent, but model '{model_name}' is not downloaded on this machine."
            )


def _format_locked_route_error(route_context: dict[str, Any], error: Exception) -> str:
    route = str(route_context.get("route") or "default").strip().lower()
    model_name = str(route_context.get("model") or "").strip()
    if route == "openrouter":
        return (
            f"OpenRouter is forced for this agent, but model '{model_name}' could not run. "
            f"Fix the OpenRouter setup or change this agent back to Use default. Details: {error}"
        )
    if route == "local":
        return (
            f"Local Ollama is forced for this agent, but model '{model_name}' could not run. "
            f"Make sure Ollama is running and the model is downloaded, or change this agent back to Use default. Details: {error}"
        )
    return str(error)


def _candidate_models(
    primary_model: str,
    route_payload: dict | None = None,
    route_context: dict[str, Any] | None = None,
) -> list[str]:
    if route_context and route_context.get("provider_locked"):
        return [primary_model]

    stack = get_model_stack()
    candidates: list[str] = []
    requested_provider = str((route_context or {}).get("requested_provider") or model_provider(primary_model)).strip()
    allow_cross_provider = bool((route_context or {}).get("cross_provider_fallback"))

    def add(model_name: str) -> None:
        normalized = (model_name or "").strip()
        if not normalized:
            return
        if not allow_cross_provider and model_provider(normalized) != requested_provider:
            return
        if normalized and is_valid_model(normalized) and normalized not in candidates:
            candidates.append(normalized)

    add(primary_model)
    classification = str((route_payload or {}).get("classification") or "").strip()
    if classification in _HEAVY_HITTER_CLASSIFICATIONS:
        add(stack["heavy_hitter"])
    add(stack["backup_1"])
    add(stack["backup_2"])
    if classification not in _HEAVY_HITTER_CLASSIFICATIONS:
        add(stack["heavy_hitter"])

    filtered = [candidate for candidate in candidates if model_is_configured(candidate)]
    if filtered:
        return filtered
    return [primary_model]


async def _acompletion_with_fallback(
    *,
    model: str,
    route_payload: dict | None = None,
    route_context: dict[str, Any] | None = None,
    **kwargs,
):
    last_error: Exception | None = None
    chosen_candidate = model
    errors: list[str] = []
    route_mode = str((route_context or {}).get("route") or "default")
    requested_provider = str((route_context or {}).get("requested_provider") or model_provider(model))
    candidates = _candidate_models(model, route_payload, route_context=route_context)
    log.info(
        "LLM route start: route=%s requested_provider=%s requested_model=%s cross_provider_fallback=%s candidates=%s",
        route_mode,
        requested_provider,
        model,
        bool((route_context or {}).get("cross_provider_fallback")),
        candidates,
    )
    for candidate in candidates:
        try:
            chosen_candidate = candidate
            response = await litellm.acompletion(model=candidate, **kwargs)
            log.info(
                "LLM route applied: route=%s requested_provider=%s requested_model=%s cross_provider_fallback=%s applied_provider=%s applied_model=%s",
                route_mode,
                requested_provider,
                model,
                bool((route_context or {}).get("cross_provider_fallback")),
                model_provider(candidate),
                candidate,
            )
            if candidate != model:
                log.warning(
                    "LLM fallback succeeded: requested=%s applied=%s prior_errors=%s",
                    model,
                    candidate,
                    errors,
                )
            return chosen_candidate, response
        except Exception as exc:
            last_error = exc
            errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
            if route_context and route_context.get("provider_locked"):
                friendly_error = _format_locked_route_error(route_context, exc)
                log.error(
                    "LLM locked route failed: route=%s requested_provider=%s requested_model=%s error=%s",
                    route_mode,
                    requested_provider,
                    model,
                    friendly_error,
                )
                raise RuntimeError(friendly_error) from exc
            continue
    if last_error is not None:
        log.error(
            "LLM completion failed for all candidates: requested=%s candidates=%s errors=%s",
            model,
            candidates,
            errors,
        )
        raise last_error
    chosen_candidate = model
    response = await litellm.acompletion(model=chosen_candidate, **kwargs)
    return chosen_candidate, response


def resolve_model_for_agent(
    *,
    default_model: str,
    agent_name: str | None = None,
) -> str:
    return get_agent_route_context(default_model=default_model, agent_name=agent_name)["model"]


def get_model(user_id: str | None = None, agent_name: str | None = None) -> str:
    if user_id and user_id in _user_models:
        base = _user_models[user_id]
    else:
        base = _default_model()
    return resolve_model_for_agent(default_model=base, agent_name=agent_name)


def set_model(user_id: str, model: str) -> str:
    """Set model preference for a user. Returns the model string."""
    if not is_valid_model(model):
        raise ValueError(f"Unknown model '{model}'. Available: {', '.join(AVAILABLE_MODELS)}")
    _user_models[user_id] = model
    return model


_WEB_SEARCH_HINT_RE = re.compile(
    r"\b("
    r"latest|recent|current|today|news|headline|price|pricing|cost|token cost|weather|look up|lookup|search the web|browse|google|"
    r"website|web page|url|docs?|documentation|release notes?|what changed"
    r")\b",
    re.IGNORECASE,
)
_FETCH_URL_HINT_RE = re.compile(
    r"(https?://\S+)"                                   # explicit URL in message
    r"|(\bgo to\b|\bvisit\b|\bopen\b|\bread\b|\bcheck\b|\bparticipate\b|\bfetch\b)"
    r".*\.(com|org|net|io|co|ai|app|dev|info|gov|edu)",
    re.IGNORECASE,
)
_SERVER_READ_HINT_RE = re.compile(
    r"\b("
    r"server|machine|local machine|droplet|system|service|journal|log|logs|memory|disk|cpu|process|"
    r"listener|listeners|port|socket|status|uptime|network|troubleshoot|debug|investigate|check itself|root"
    r")\b",
    re.IGNORECASE,
)


def _should_nudge_web_search(message: str) -> bool:
    return bool(_WEB_SEARCH_HINT_RE.search((message or "").strip()))


def _should_nudge_fetch_url(message: str) -> bool:
    return bool(_FETCH_URL_HINT_RE.search((message or "").strip()))


def _should_nudge_server_read(message: str) -> bool:
    return bool(_SERVER_READ_HINT_RE.search((message or "").strip()))


def _available_models_for_default_route(route_context: dict[str, Any]) -> set[str]:
    requested_provider = str(route_context.get("requested_provider") or "").strip()
    allow_cross_provider = bool(route_context.get("cross_provider_fallback"))
    dynamic_same_provider = {
        str(route_context.get("model") or "").strip(),
        _default_model(),
        get_openrouter_default_model(),
        get_local_default_model(),
        *get_model_stack().values(),
    }
    if allow_cross_provider:
        return {
            model_name
            for model_name in {*(set(AVAILABLE_MODELS)), *dynamic_same_provider}
            if model_name
        }
    return {
        model_name.strip()
        for model_name in {*(set(AVAILABLE_MODELS)), *dynamic_same_provider}
        if model_provider(model_name) == requested_provider
    }


async def stream_chat(
    messages: list[dict],
    user_id: str | None = None,
    model: str | None = None,
    agent_name: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat completion tokens. Yields text deltas."""
    base_model = model or get_model(user_id)
    route_context = get_agent_route_context(default_model=base_model, agent_name=agent_name)
    chosen = route_context["model"]
    if route_context["provider_locked"]:
        await _ensure_locked_route_ready(route_context)
    elif route_context["route"] == "default" and not route_context.get("cross_provider_fallback"):
        chosen = route_context["model"]
    _, response = await _acompletion_with_fallback(
        model=chosen,
        route_context=route_context,
        messages=messages,
        stream=True,
        temperature=0.2,
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


async def stream_chat_with_tools(
    messages: list[dict],
    user_id: str | None = None,
    model: str | None = None,
    db_session=None,
    room_id: str | None = None,
    agent_name: str | None = None,
    confirmed_ids: set[str] | None = None,
    room_execution_allowed: bool | None = None,
    is_operator: bool = False,
    is_privileged: bool = False,
) -> AsyncGenerator[dict, None]:
    """
    Tool-aware streaming. Yields typed event dicts:
      {"type": "routing",    "payload": {...}}
      {"type": "tool_start", "tool": "web_search", "input": {...}}
      {"type": "tool_done",  "tool": "web_search", "result": "..."}
      {"type": "token",      "token": "..."}

    Handles the tool-calling loop automatically (up to 5 rounds), then
    streams the final LLM response token-by-token.
    """
    from app.api.routes.chat.tools import (
        TOOL_DEFINITIONS,
        execute_tool,
        _email_configured_smtp,
        _google_configured,
    )
    from app.services.guardian.executive import exec_with_guard
    from app.services.guardian.policy import decide_tool_use
    from app.services.guardian.verifier import (
        format_verifier_note,
        should_verify_interactive_tool_run,
        verify_interactive_tool_run,
    )

    base_model = model or get_model(user_id)
    route_context = get_agent_route_context(default_model=base_model, agent_name=agent_name)
    chosen = route_context["model"]
    msgs = list(messages)
    latest_user_message = next(
        (
            str(msg.get("content", ""))
            for msg in reversed(msgs)
            if msg.get("role") == "user"
        ),
        "",
    )

    if latest_user_message:
        if route_context["provider_locked"]:
            await _ensure_locked_route_ready(route_context)
            route_payload = _locked_route_payload(
                message=latest_user_message,
                route_context=route_context,
            )
        else:
            available_models = _available_models_for_default_route(route_context)
            try:
                from app.services.guardian.token_guardian import route_model

                routed_model, route_payload = route_model(
                    latest_user_message,
                    chosen,
                    available_models=available_models,
                )
                chosen = routed_model
                route_payload = _annotate_route_payload(
                    route_payload,
                    route_context=route_context,
                    current_model=route_context["model"],
                    applied_model=chosen,
                )
                route_payload["cross_provider_fallback"] = bool(route_context.get("cross_provider_fallback"))
                route_payload["provider_authoritative"] = not bool(route_context.get("cross_provider_fallback"))
            except Exception:
                route_payload = _provider_authoritative_route_payload(
                    message=latest_user_message,
                    route_context=route_context,
                )
                chosen = route_context["model"]
    else:
        route_payload = None

    if route_payload is not None:
        yield {"type": "routing", "payload": route_payload}

    if latest_user_message:
        if _should_nudge_fetch_url(latest_user_message):
            msgs.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "The user wants you to visit or read a specific URL or website. "
                        "Use the fetch_url tool to retrieve the page content, then respond based on what you read. "
                        "You CAN and SHOULD fetch URLs — do not say you cannot visit websites."
                    ),
                },
            )
        if _should_nudge_web_search(latest_user_message):
            msgs.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "This request likely needs live external information. "
                        "Use the web_search tool unless the user explicitly asked for reasoning only."
                    ),
                },
            )
        if _should_nudge_server_read(latest_user_message):
            if room_execution_allowed:
                msgs.insert(
                    1,
                    {
                        "role": "system",
                        "content": (
                            "This request appears to be about the local machine or services. "
                            "Use read-only server tools for diagnostics before answering when relevant."
                        ),
                    },
                )
            else:
                msgs.insert(
                    1,
                    {
                        "role": "system",
                        "content": (
                            "This request appears to be about the local machine or services, "
                            "but the room execution gate is disabled. Explain that clearly instead of pretending the tools do not exist."
                        ),
                    },
                )

    if db_session is not None and user_id and room_id and route_payload:
        try:
            import uuid as _uuid
            from app.crud import create_audit_log

            mode = str(route_payload.get("mode") or "shadow")
            tool_name = "tokenguardian_live" if mode == "live" else "tokenguardian_shadow"
            create_audit_log(
                session=db_session,
                tool_name=tool_name,
                tool_input=json.dumps(
                    {
                        "query": latest_user_message[:500],
                        "current_model": route_payload.get("current_model", chosen),
                    }
                ),
                tool_result=json.dumps(route_payload)[:1000],
                user_id=_uuid.UUID(user_id),
                room_id=_uuid.UUID(room_id),
                agent_name=agent_name,
                model=chosen,
            )
        except Exception:
            pass

    tool_usage_counts: dict[str, int] = {}

    for _round in range(5):
        tool_choice: str = "auto"
        if tool_usage_counts.get("web_search", 0) >= 2:
            msgs.append(
                {
                    "role": "system",
                    "content": (
                        "You already have live search results. "
                        "Do not call web_search again. Synthesize the answer from the tool results you already received."
                    ),
                }
            )
            tool_choice = "none"

        # Non-streaming call to resolve any tool calls
        chosen, response = await _acompletion_with_fallback(
            model=chosen,
            route_payload=route_payload,
            route_context=route_context,
            messages=msgs,
            tools=TOOL_DEFINITIONS,
            tool_choice=tool_choice,
            temperature=0.2,
        )

        choice = response.choices[0]
        finish_reason = choice.finish_reason
        assistant_msg = choice.message

        if finish_reason == "tool_calls" and assistant_msg.tool_calls:
            # Append the assistant's tool-call turn
            msgs.append(assistant_msg.model_dump(exclude_none=True))

            for tc in assistant_msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except Exception:
                    tool_args = {}

                decision = decide_tool_use(
                    tool_name,
                    tool_args if isinstance(tool_args, dict) else {},
                    room_execution_allowed=room_execution_allowed,
                    is_operator=is_operator,
                    is_privileged=is_privileged,
                )

                if db_session is not None:
                    try:
                        import uuid as _uuid
                        from app.crud import create_audit_log

                        create_audit_log(
                            session=db_session,
                            tool_name="policy_decision",
                            tool_input=json.dumps(
                                {
                                    "tool_name": tool_name,
                                    "tool_args": json.loads(serialize_tool_args_for_audit(tool_name, tool_args)),
                                }
                            )[:2000],
                            tool_result=decision.to_json()[:1000],
                            user_id=_uuid.UUID(user_id) if user_id else None,
                            room_id=_uuid.UUID(room_id) if room_id else None,
                            agent_name=agent_name,
                            model=chosen,
                        )
                    except Exception:
                        pass

                if decision.action == "deny":
                    result = f"POLICY DENIED: {decision.reason}"
                    verification = None
                    if should_verify_interactive_tool_run(
                        action_type=decision.action_type,
                        high_risk=decision.high_risk,
                    ):
                        verification = verify_interactive_tool_run(
                            tool_name=tool_name,
                            output=result,
                            execution_status="denied",
                        )
                    yield {"type": "tool_start", "tool": tool_name, "input": tool_args}
                    tool_done_event = {"type": "tool_done", "tool": tool_name, "result": result[:300]}
                    if verification is not None:
                        tool_done_event["verification_status"] = verification.status
                        tool_done_event["confidence"] = verification.confidence
                        if verification.recommended_next_action:
                            tool_done_event["recommended_next_action"] = verification.recommended_next_action
                    yield tool_done_event
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": (
                            f"{result}\n\n{format_verifier_note(verification)}"
                            if verification is not None
                            else result
                        ),
                    })
                    continue

                if decision.action in ("privileged", "privileged_reveal"):
                    confirm_id = str(_uuid_module.uuid4())
                    _pending_ttl_cleanup()
                    pending_entry = {
                        "tool": tool_name,
                        "args": tool_args,
                        "user_id": user_id,
                        "room_id": room_id,
                        "created_at": time.time(),
                    }
                    _pending[confirm_id] = pending_entry
                    try:
                        from app.services.guardian.pending_approvals import store_pending_approval

                        store_pending_approval(
                            confirm_id=confirm_id,
                            tool_name=tool_name,
                            tool_args=tool_args if isinstance(tool_args, dict) else {},
                            user_id=user_id,
                            room_id=room_id,
                        )
                    except Exception:
                        pass
                    yield {
                        "type": "privileged_required",
                        "confirm_id": confirm_id,
                        "tool": tool_name,
                        "input": tool_args,
                        "risk": decision.reason,
                        "requires_confirm_after_auth": decision.action == "privileged_reveal",
                    }
                    return

                if decision.action == "confirm":
                    # Don't prompt for confirmation when email sending is unavailable.
                    # Let the tool return the concrete configuration error instead.
                    if tool_name == "email_send" and not _email_configured_smtp():
                        pass
                    elif tool_name in {"gmail_send", "drive_create_folder", "calendar_create_event"} and not _google_configured():
                        pass
                    else:
                        already_confirmed = confirmed_ids and any(
                            c for c in (confirmed_ids or set()) if c
                        )
                        if not already_confirmed:
                            confirm_id = str(_uuid_module.uuid4())
                            _pending_ttl_cleanup()
                            pending_entry = {
                                "tool": tool_name,
                                "args": tool_args,
                                "user_id": user_id,
                                "room_id": room_id,
                                "created_at": time.time(),
                            }
                            _pending[confirm_id] = pending_entry
                            try:
                                from app.services.guardian.pending_approvals import store_pending_approval

                                store_pending_approval(
                                    confirm_id=confirm_id,
                                    tool_name=tool_name,
                                    tool_args=tool_args if isinstance(tool_args, dict) else {},
                                    user_id=user_id,
                                    room_id=room_id,
                                )
                            except Exception:
                                pass
                            yield {
                                "type": "confirm_required",
                                "confirm_id": confirm_id,
                                "tool": tool_name,
                                "input": tool_args,
                            }
                            return

                yield {"type": "tool_start", "tool": tool_name, "input": tool_args}

                result = await exec_with_guard(
                    tool_name=tool_name,
                    action_type=decision.action_type,
                    expected_outcome=f"Successful tool execution for {tool_name}",
                    perform_fn=lambda: execute_tool(
                        tool_name,
                        tool_args,
                        user_id=user_id,
                        session=db_session,
                        room_id=room_id,
                    ),
                    metadata={
                        "room_id": room_id,
                        "user_id": user_id,
                        "scope": decision.scope,
                        "resource": decision.resource,
                    },
                )
                verification = None
                if should_verify_interactive_tool_run(
                    action_type=decision.action_type,
                    high_risk=decision.high_risk,
                ):
                    verification = verify_interactive_tool_run(
                        tool_name=tool_name,
                        output=str(result),
                        execution_status="success",
                    )

                # Vault-internal tools: mask plaintext in all outward-facing paths.
                # The full plaintext stays in `result` for the LLM context only.
                outward_result = mask_tool_result_for_external(tool_name, tool_args, result)
                tool_done_event = {"type": "tool_done", "tool": tool_name, "result": outward_result[:300]}
                if verification is not None:
                    tool_done_event["verification_status"] = verification.status
                    tool_done_event["confidence"] = verification.confidence
                    if verification.recommended_next_action:
                        tool_done_event["recommended_next_action"] = verification.recommended_next_action
                yield tool_done_event
                tool_usage_counts[tool_name] = tool_usage_counts.get(tool_name, 0) + 1

                # Audit log — best-effort, never let it break the chat stream
                if db_session is not None:
                    try:
                        import uuid as _uuid
                        from app.crud import create_audit_log
                        from app.services.guardian.memory import remember_tool_event
                        redacted_input, redacted_result = redact_tool_call_for_audit(
                            tool_name, tool_args, result
                        )
                        if verification is not None:
                            redacted_result = f"{redacted_result}\n\n{format_verifier_note(verification)}"
                        create_audit_log(
                            session=db_session,
                            tool_name=tool_name,
                            tool_input=redacted_input,
                            tool_result=redacted_result,
                            user_id=_uuid.UUID(user_id) if user_id else None,
                            room_id=_uuid.UUID(room_id) if room_id else None,
                            agent_name=agent_name,
                            model=chosen,
                        )
                        if user_id and room_id:
                            parsed_input = json.loads(redacted_input)
                            remember_tool_event(
                                user_id=user_id,
                                room_id=room_id,
                                tool_name=tool_name,
                                args=parsed_input if isinstance(parsed_input, dict) else {},
                                result=redacted_result,
                            )
                    except Exception:
                        pass  # never fail the stream because of logging

                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": (
                        f"{result}\n\n{format_verifier_note(verification)}"
                        if verification is not None
                        else result
                    ),  # full plaintext for LLM context only
                })
        else:
            # No more tool calls — stream the final answer
            chosen, stream = await _acompletion_with_fallback(
                model=chosen,
                route_payload=route_payload,
                route_context=route_context,
                messages=msgs,
                stream=True,
                temperature=0.2,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield {"type": "token", "token": delta}
            return

    # Safety: too many tool rounds
    yield {"type": "token", "token": "\n\n⚠️ Tool loop limit reached."}
