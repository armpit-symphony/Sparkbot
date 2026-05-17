"""Public Invite Wing model-seat helpers.

Model seats are public configuration records. Credentials stay in Guardian
Vault and are referenced only by deterministic aliases derived from the seat id.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

MODEL_SEATS_ENV = "SPARKBOT_MODEL_SEATS_JSON"
MODEL_SEAT_AUTH_MODES = {"api_key", "oauth", "codex_sub"}
MODEL_SEAT_PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "claude_sub": "claude_sub",
    "claude-sub": "claude_sub",
    "google": "google",
    "gemini": "google",
    "groq": "groq",
    "minimax": "minimax",
    "ollama": "ollama",
    "openai": "openai",
    "openai_codex": "openai_codex",
    "openai-codex": "openai_codex",
    "codex": "openai_codex",
    "xai": "xai",
    "grok": "xai",
}
MODEL_SEAT_DEFAULTS: list[dict[str, Any]] = [
    {
        "id": "invite-gpt",
        "label": "Codex / OpenAI",
        "company": "OpenAI",
        "provider": "openai_codex",
        "auth_mode": "codex_sub",
        "model_id": "openai-codex/gpt-5.3-codex",
        "enabled": True,
        "show_in_round_table": True,
        "show_in_specialty_wing": True,
        "notes": "Default Codex/OpenAI model seat for Round Table and Specialty Wing.",
    },
    {
        "id": "invite-claude",
        "label": "Claude / Anthropic",
        "company": "Anthropic",
        "provider": "anthropic",
        "auth_mode": "api_key",
        "model_id": "claude-sonnet-4-6",
        "enabled": True,
        "show_in_round_table": True,
        "show_in_specialty_wing": True,
        "notes": "Default Claude model seat for long-context reasoning.",
    },
    {
        "id": "invite-custom",
        "label": "Grok / xAI",
        "company": "xAI",
        "provider": "xai",
        "auth_mode": "api_key",
        "model_id": "xai/grok-4.20-multi-agent-0309",
        "enabled": True,
        "show_in_round_table": True,
        "show_in_specialty_wing": True,
        "notes": "Default Grok model seat for agentic reasoning.",
    },
]


def model_seat_secret_alias(seat_id: str) -> str:
    safe_id = re.sub(r"[^a-z0-9_]+", "_", seat_id.strip().lower()).strip("_")
    return f"model_seat_{safe_id}_credential"


def load_model_seat_overrides() -> dict[str, dict[str, Any]]:
    raw = os.getenv(MODEL_SEATS_ENV, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, list):
        return {}
    items: dict[str, dict[str, Any]] = {}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        seat_id = str(item.get("id") or "").strip().lower()
        if not seat_id:
            continue
        items[seat_id] = item
    return items


def normalize_model_seat_provider(
    provider: str | None,
    model_id: str | None = None,
    *,
    model_provider_func: Callable[[str], str] | None = None,
) -> str:
    raw_provider = str(provider or "").strip().lower().replace(" ", "_")
    if raw_provider in MODEL_SEAT_PROVIDER_ALIASES:
        return MODEL_SEAT_PROVIDER_ALIASES[raw_provider]
    if model_id and model_provider_func:
        resolved = model_provider_func(model_id)
        if resolved:
            return resolved
    return "openrouter"


def merged_model_seats(
    *,
    model_provider_func: Callable[[str], str] | None = None,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {
        str(item["id"]): dict(item)
        for item in MODEL_SEAT_DEFAULTS
    }
    for seat_id, override in load_model_seat_overrides().items():
        base = dict(merged.get(seat_id, {"id": seat_id}))
        for key in (
            "label",
            "company",
            "provider",
            "auth_mode",
            "model_id",
            "enabled",
            "show_in_round_table",
            "show_in_specialty_wing",
            "notes",
        ):
            if key in override:
                base[key] = override[key]
        base["provider"] = normalize_model_seat_provider(
            str(base.get("provider") or ""),
            str(base.get("model_id") or ""),
            model_provider_func=model_provider_func,
        )
        merged[seat_id] = base
    return list(merged.values())


def model_seat_by_id(
    seat_id: str,
    *,
    model_provider_func: Callable[[str], str] | None = None,
) -> dict[str, Any] | None:
    normalized = str(seat_id or "").strip().lower()
    for seat in merged_model_seats(model_provider_func=model_provider_func):
        if str(seat.get("id") or "").strip().lower() == normalized:
            return seat
    return None
