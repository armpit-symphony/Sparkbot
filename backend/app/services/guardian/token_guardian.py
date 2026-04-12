"""Sparkbot adapter for vendored Token Guardian routing."""

from __future__ import annotations

import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import improvement
from .tokenguardian.monitor import Monitor
from .tokenguardian.pipeline import RoutingDecision, UnifiedPipeline

_CONFIG_DIR = Path(__file__).resolve().parent / "tokenguardian" / "config"
_SUPPORTED_MODES = {"off", "shadow", "live"}


def token_guardian_mode() -> str:
    explicit = os.getenv("SPARKBOT_TOKEN_GUARDIAN_MODE", "").strip().lower()
    if explicit in _SUPPORTED_MODES:
        return explicit
    shadow_enabled = os.getenv("SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    return "shadow" if shadow_enabled else "off"


def token_guardian_shadow_enabled() -> bool:
    return token_guardian_mode() == "shadow"


def token_guardian_live_enabled() -> bool:
    return token_guardian_mode() == "live"


@lru_cache(maxsize=1)
def _pipeline() -> UnifiedPipeline:
    return UnifiedPipeline(config_dir=str(_CONFIG_DIR), shadow_mode=True)


@lru_cache(maxsize=1)
def _monitor() -> Monitor:
    return Monitor(str(_CONFIG_DIR))


@lru_cache(maxsize=1)
def _routing_config() -> dict[str, Any]:
    config_path = _CONFIG_DIR / "routing.yaml"
    if not config_path.exists():
        return {}
    try:
        return yaml.safe_load(config_path.read_text()) or {}
    except Exception:
        return {}


def _estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4 + 1)


def _build_route_payload(query: str, current_model: str, mode: str) -> dict[str, Any] | None:
    if mode not in {"shadow", "live"}:
        return None

    prompt = " ".join((query or "").split()).strip()
    if not prompt:
        return None

    decision: RoutingDecision = _pipeline().process(prompt)
    estimated_tokens = _estimate_tokens(prompt)
    estimated_cost = _monitor()._estimate_cost_for_model(estimated_tokens, decision.selected_model)
    current_estimated_cost = _monitor()._estimate_cost_for_model(estimated_tokens, current_model)

    payload = asdict(decision)
    payload["mode"] = mode
    payload["current_model"] = current_model
    payload["estimated_tokens"] = estimated_tokens
    payload["estimated_cost"] = round(estimated_cost, 6)
    payload["estimated_current_cost"] = round(current_estimated_cost, 6)
    payload["estimated_savings"] = round(max(0.0, current_estimated_cost - estimated_cost), 6)
    payload["would_switch_models"] = decision.selected_model != current_model
    return payload


def _env_or_vault_has(env_var: str, vault_alias: str) -> bool:
    """Return True if an API key is configured via env var OR Guardian Vault.

    Minimal integration: token_guardian continues to use env vars for runtime,
    but will treat vault-backed keys as "configured" for routing eligibility.

    NOTE: We do not automatically inject the vault secret into the process
    environment here to avoid surprising side effects.
    """
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


def _model_is_configured(model: str) -> bool:
    normalized = (model or "").strip()
    if not normalized:
        return False
    if normalized.startswith("gpt-"):
        return _env_or_vault_has("OPENAI_API_KEY", "api_key_openai")
    if normalized.startswith("claude"):
        return _env_or_vault_has("ANTHROPIC_API_KEY", "api_key_anthropic")
    if normalized.startswith("gemini/"):
        return _env_or_vault_has("GOOGLE_API_KEY", "api_key_google")
    if normalized.startswith("groq/"):
        return _env_or_vault_has("GROQ_API_KEY", "api_key_groq")
    if normalized.startswith("minimax/"):
        return _env_or_vault_has("MINIMAX_API_KEY", "api_key_minimax")
    if normalized.startswith("xai/"):
        return _env_or_vault_has("XAI_API_KEY", "api_key_xai")
    if normalized.startswith("openrouter/"):
        return _env_or_vault_has("OPENROUTER_API_KEY", "api_key_openrouter")
    return True


def _normalize_model_pool(models: set[str] | list[str] | tuple[str, ...] | None) -> list[str]:
    if not models:
        return []
    return sorted({str(model).strip() for model in models if str(model).strip()})


def _configured_models(available_models: set[str] | list[str] | tuple[str, ...] | None = None) -> list[str]:
    pool = _normalize_model_pool(available_models)
    return [model for model in pool if _model_is_configured(model)]


def _live_allowlist(available_models: set[str] | list[str] | tuple[str, ...] | None = None) -> list[str]:
    configured_env = [
        item.strip()
        for item in os.getenv("SPARKBOT_TOKEN_GUARDIAN_LIVE_MODELS", "").split(",")
        if item.strip()
    ]
    pool = _normalize_model_pool(available_models)
    if configured_env:
        allowed = sorted({model for model in configured_env if not pool or model in pool})
        return allowed
    return pool


def _classification_candidates(classification: str, current_model: str) -> list[str]:
    config = _routing_config()
    routing_rules = config.get("routing_rules") or {}
    rule = routing_rules.get(classification) or {}
    safe_fallback = str((config.get("safe_fallback") or {}).get("model") or "").strip()

    candidates: list[str] = []
    for candidate in [rule.get("preferred"), *(rule.get("alternatives") or []), current_model, safe_fallback]:
        normalized = str(candidate or "").strip()
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _known_routable_models() -> list[str]:
    config = _routing_config()
    routing_rules = config.get("routing_rules") or {}
    discovered: list[str] = []

    for rule in routing_rules.values():
        for candidate in [rule.get("preferred"), *(rule.get("alternatives") or [])]:
            normalized = str(candidate or "").strip()
            if normalized and normalized not in discovered:
                discovered.append(normalized)

    safe_fallback = str((config.get("safe_fallback") or {}).get("model") or "").strip()
    if safe_fallback and safe_fallback not in discovered:
        discovered.append(safe_fallback)
    return discovered


def _select_live_model(
    *,
    requested_model: str,
    classification: str,
    current_model: str,
    allowed_models: list[str],
    configured_models: list[str],
) -> tuple[str, str | None, list[str]]:
    allowed_set = set(allowed_models)
    configured_set = set(configured_models)
    candidate_models = _classification_candidates(classification, current_model)

    for candidate in candidate_models:
        if candidate not in allowed_set:
            continue
        if candidate not in configured_set:
            continue
        if candidate == requested_model:
            return candidate, None, candidate_models
        return candidate, f"Requested model '{requested_model}' was unavailable; applied '{candidate}' instead.", candidate_models

    if current_model in configured_set and current_model in allowed_set:
        return current_model, f"No live-routable Token Guardian target was available; stayed on '{current_model}'.", candidate_models

    usable_fallbacks = [model for model in configured_models if model in allowed_set]
    if usable_fallbacks:
        fallback = usable_fallbacks[0]
        return fallback, f"No classified candidate was available; fell back to first configured model '{fallback}'.", candidate_models

    return current_model, "No configured models are available for live Token Guardian routing.", candidate_models


def _emit_token_guardian_event(event_type: str, content: str, payload: dict) -> None:
    """Emit a spine event for a token guardian action. Non-blocking — never raises."""
    try:
        from app.services.guardian import spine
        spine.ingest_subsystem_event(
            event=spine.SpineSubsystemEvent(
                event_type=event_type,
                subsystem="token_guardian",
                actor_kind="system",
                source=spine.SpineSourceReference(
                    source_kind="token_guardian",
                    source_ref=event_type,
                ),
                content=content,
                payload=payload,
            ),
        )
    except Exception:
        pass


def _record_route_usage(payload: dict[str, Any], applied_model: str) -> None:
    try:
        _monitor().record_usage(
            int(payload.get("estimated_tokens") or 0),
            applied_model,
            action=f"token_guardian_{payload.get('mode') or 'unknown'}",
        )
    except Exception:
        pass


def run_shadow_route(query: str, current_model: str) -> dict[str, Any] | None:
    if not token_guardian_shadow_enabled():
        return None
    return _build_route_payload(query, current_model, "shadow")


def route_model(
    query: str,
    current_model: str,
    *,
    available_models: set[str] | list[str] | tuple[str, ...] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    import logging as _logging
    _log = _logging.getLogger(__name__)

    mode = token_guardian_mode()
    if mode == "off":
        return current_model, None

    try:
        payload = _build_route_payload(query, current_model, mode)
    except Exception as _pipe_err:
        _log.debug("Token Guardian pipeline error (route_model): %s", _pipe_err, exc_info=True)
        # Pipeline failed — count the attempt but don't block the request
        try:
            _monitor().record_usage(
                _estimate_tokens(query),
                current_model,
                action=f"token_guardian_{mode}_pipeline_error",
            )
        except Exception:
            pass
        return current_model, None

    if not payload:
        return current_model, None

    configured_models = _configured_models(available_models)
    allowed_models = _live_allowlist(available_models)
    payload["configured_models"] = configured_models
    payload["allowed_live_models"] = allowed_models
    payload["live_ready"] = bool(set(configured_models) & set(allowed_models))
    payload["selected_model_supported"] = not available_models or str(payload.get("selected_model") or "") in set(available_models)
    payload["selected_model_configured"] = str(payload.get("selected_model") or "") in set(configured_models)
    payload["selected_model_allowed"] = str(payload.get("selected_model") or "") in set(allowed_models)
    payload.setdefault("fallback_reason", None)

    chosen_model = current_model
    if mode == "live":
        requested_model = str(payload.get("selected_model") or current_model)
        chosen_model, live_fallback_reason, candidate_models = _select_live_model(
            requested_model=requested_model,
            classification=str(payload.get("classification") or "general"),
            current_model=current_model,
            allowed_models=allowed_models,
            configured_models=configured_models,
        )
        payload["candidate_models"] = candidate_models
        if live_fallback_reason:
            payload["fallback_reason"] = live_fallback_reason
    candidate_pool = _normalize_model_pool(
        allowed_models if mode == "live" else (available_models or configured_models or [chosen_model])
    )
    if chosen_model and chosen_model not in candidate_pool:
        candidate_pool.insert(0, chosen_model)
    learned_model, learned_reason, learned_ranking = improvement.choose_best_model(
        classification=str(payload.get("classification") or "general"),
        current_model=chosen_model,
        candidates=candidate_pool,
    )
    payload["learned_route_candidates"] = learned_ranking
    payload["learned_route_applied"] = False
    if learned_reason and learned_model != chosen_model:
        payload["classifier_selected_model"] = payload.get("selected_model") or chosen_model
        payload["selected_model"] = learned_model
        payload["learned_route_applied"] = True
        payload["learned_route_reason"] = learned_reason
        chosen_model = learned_model
    payload["applied_model"] = chosen_model
    payload["live_routed"] = mode == "live" and chosen_model != current_model
    _record_route_usage(payload, chosen_model)
    if mode == "live" and payload.get("live_routed"):
        _emit_token_guardian_event(
            "token_guardian.quota_event",
            f"Token Guardian routed {current_model!r} → {chosen_model!r}",
            {
                "from_model": current_model,
                "to_model": chosen_model,
                "estimated_tokens": payload.get("estimated_tokens"),
                "classification": payload.get("classification"),
                "fallback_reason": payload.get("fallback_reason"),
            },
        )
    return chosen_model, payload


def _user_stack_models() -> list[str]:
    """Return the user's configured model stack (primary + backups) as a flat list."""
    try:
        from app.api.routes.chat.llm import get_model_stack, _default_model
        stack = get_model_stack()
        primary = _default_model()
        all_models = [primary] + [v for v in stack.values() if v and v != primary]
        return [m for m in all_models if m]
    except Exception:
        return []


def get_token_guardian_stats() -> dict[str, Any]:
    stats = _monitor().get_stats()
    stats["mode"] = token_guardian_mode()
    stats["shadow_enabled"] = token_guardian_shadow_enabled()
    stats["live_enabled"] = token_guardian_live_enabled()
    # Merge routing.yaml model pool with user's actual stack so OpenRouter users
    # see their models as "configured" even if routing.yaml uses direct-provider IDs.
    routing_pool = _known_routable_models()
    stack_pool = _user_stack_models()
    model_pool = list(dict.fromkeys(routing_pool + stack_pool))  # deduped, order preserved
    configured_models = _configured_models(model_pool)
    allowed_models = _live_allowlist(model_pool)
    stats["configured_models"] = configured_models
    stats["allowed_live_models"] = allowed_models
    stats["live_ready"] = bool(set(configured_models) & set(allowed_models))
    return stats
