"""Public-safe local AI provider helpers.

This module keeps local model-server configuration separate from provider
secrets. Ollama remains first-class through its native API; ``local/`` models
use an OpenAI-compatible endpoint such as LM Studio, llama.cpp, or a custom
local server.
"""

from __future__ import annotations

import os
from typing import Any

LOCAL_AI_ENABLED_ENV = "SPARKBOT_LOCAL_AI_ENABLED"
LOCAL_AI_RUNTIME_ENV = "SPARKBOT_LOCAL_AI_RUNTIME"
LOCAL_AI_BASE_URL_ENV = "SPARKBOT_LOCAL_AI_BASE_URL"
LOCAL_AI_MODEL_ENV = "SPARKBOT_LOCAL_AI_MODEL"
LOCAL_AI_DISPLAY_NAME_ENV = "SPARKBOT_LOCAL_AI_DISPLAY_NAME"
LOCAL_AI_AUTH_MODE_ENV = "SPARKBOT_LOCAL_AI_AUTH_MODE"
LOCAL_AI_API_KEY_ENV = "SPARKBOT_LOCAL_AI_API_KEY"

LOCAL_AI_RUNTIMES = {
    "ollama",
    "lmstudio",
    "llamacpp",
    "openai_compatible",
    "custom",
}

LOCAL_AI_RUNTIME_ALIASES = {
    "lm_studio": "lmstudio",
    "lm-studio": "lmstudio",
    "llama.cpp": "llamacpp",
    "llama_cpp": "llamacpp",
    "llama-cpp": "llamacpp",
    "llama_server": "llamacpp",
    "llama-server": "llamacpp",
    "openai-compatible": "openai_compatible",
    "openai compatible": "openai_compatible",
    "openai_compat": "openai_compatible",
    "custom_local": "custom",
    "local": "custom",
}

LOCAL_AI_DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
    "openai_compatible": "http://localhost:1234/v1",
    "custom": "http://localhost:1234/v1",
}


def normalize_local_runtime(value: str | None) -> str:
    raw = str(value or "").strip().lower().replace(" ", "_")
    raw = LOCAL_AI_RUNTIME_ALIASES.get(raw, raw)
    return raw if raw in LOCAL_AI_RUNTIMES else "openai_compatible"


def local_runtime_label(runtime: str | None) -> str:
    normalized = normalize_local_runtime(runtime)
    return {
        "ollama": "Ollama",
        "lmstudio": "LM Studio",
        "llamacpp": "llama.cpp / llama-server",
        "openai_compatible": "OpenAI-compatible local endpoint",
        "custom": "Custom local endpoint",
    }.get(normalized, "Local AI endpoint")


def local_default_base_url(runtime: str | None = None) -> str:
    normalized = normalize_local_runtime(runtime)
    return LOCAL_AI_DEFAULT_BASE_URLS.get(normalized, LOCAL_AI_DEFAULT_BASE_URLS["openai_compatible"])


def normalize_local_model_id(model: str | None) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return ""
    if normalized.startswith(("local/", "ollama/")):
        return normalized
    return f"local/{normalized}"


def local_model_slug(model: str | None) -> str:
    normalized = str(model or "").strip()
    if normalized.startswith("local/"):
        return normalized.removeprefix("local/")
    return normalized


def local_ai_litellm_model(model: str) -> str:
    slug = local_model_slug(model)
    if slug.startswith("openai/"):
        return slug
    return f"openai/{slug}"


def local_ai_config(
    *,
    base_url: str | None = None,
    runtime: str | None = None,
    model_id: str | None = None,
    display_name: str | None = None,
    auth_mode: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    normalized_runtime = normalize_local_runtime(runtime or os.getenv(LOCAL_AI_RUNTIME_ENV, ""))
    resolved_base_url = (
        str(base_url or "").strip()
        or os.getenv(LOCAL_AI_BASE_URL_ENV, "").strip()
        or local_default_base_url(normalized_runtime)
    ).rstrip("/")
    resolved_model = normalize_local_model_id(model_id or os.getenv(LOCAL_AI_MODEL_ENV, ""))
    resolved_auth_mode = str(auth_mode or os.getenv(LOCAL_AI_AUTH_MODE_ENV, "none")).strip().lower()
    if resolved_auth_mode not in {"none", "api_key"}:
        resolved_auth_mode = "none"
    explicit_enabled = str(os.getenv(LOCAL_AI_ENABLED_ENV, "")).strip().lower()
    resolved_enabled = (
        bool(enabled)
        if enabled is not None
        else explicit_enabled in {"1", "true", "yes", "on"}
        or bool(os.getenv(LOCAL_AI_BASE_URL_ENV, "").strip())
        or bool(os.getenv(LOCAL_AI_MODEL_ENV, "").strip())
    )
    return {
        "provider_type": "local",
        "provider": "local_ai",
        "local_runtime": normalized_runtime,
        "runtime_label": local_runtime_label(normalized_runtime),
        "base_url": resolved_base_url,
        "model_id": resolved_model,
        "display_name": str(display_name or os.getenv(LOCAL_AI_DISPLAY_NAME_ENV, "") or local_runtime_label(normalized_runtime)).strip(),
        "enabled": bool(resolved_enabled),
        "auth_mode": resolved_auth_mode,
        "supports_chat": True,
        "supports_embeddings": False,
        "supports_tools": False,
    }


def local_ai_enabled() -> bool:
    config = local_ai_config()
    return bool(config.get("enabled") and config.get("base_url") and config.get("model_id"))


def local_ai_api_key(value: str | None = None) -> str | None:
    return str(value or os.getenv(LOCAL_AI_API_KEY_ENV, "")).strip() or None


def local_ai_litellm_kwargs(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> dict[str, str]:
    config = local_ai_config(base_url=base_url)
    return {
        "api_base": str(config["base_url"]).rstrip("/"),
        "api_key": local_ai_api_key(api_key) or "local-ai",
    }


async def get_local_ai_status(
    *,
    base_url: str | None = None,
    runtime: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Check an OpenAI-compatible local endpoint and list models if available."""
    import httpx

    config = local_ai_config(base_url=base_url, runtime=runtime)
    explicitly_configured = bool(
        base_url
        or runtime
        or os.getenv(LOCAL_AI_BASE_URL_ENV, "").strip()
        or os.getenv(LOCAL_AI_MODEL_ENV, "").strip()
        or os.getenv(LOCAL_AI_ENABLED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}
    )
    if not explicitly_configured:
        return {
            **config,
            "reachable": False,
            "models": [],
            "model_ids": [],
            "models_available": False,
        }
    resolved_base_url = str(config["base_url"]).rstrip("/")
    headers: dict[str, str] = {}
    resolved_key = local_ai_api_key(api_key)
    if resolved_key:
        headers["Authorization"] = f"Bearer {resolved_key}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{resolved_base_url}/models", headers=headers)
            if response.status_code == 200:
                data = response.json()
                rows = data.get("data", []) if isinstance(data, dict) else []
                models: list[str] = []
                for item in rows:
                    if isinstance(item, dict):
                        model_id = str(item.get("id") or "").strip()
                    else:
                        model_id = str(item or "").strip()
                    if model_id:
                        models.append(model_id)
                model_ids = [normalize_local_model_id(model) for model in models]
                return {
                    **config,
                    "reachable": True,
                    "models": models,
                    "model_ids": model_ids,
                    "models_available": bool(model_ids),
                }
    except Exception:
        pass
    return {
        **config,
        "reachable": False,
        "models": [],
        "model_ids": [],
        "models_available": False,
    }
