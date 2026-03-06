"""Sparkbot adapter for vendored Token Guardian shadow routing."""

from __future__ import annotations

import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from .tokenguardian.monitor import Monitor
from .tokenguardian.pipeline import RoutingDecision, UnifiedPipeline

_CONFIG_DIR = Path(__file__).resolve().parent / "tokenguardian" / "config"


def token_guardian_shadow_enabled() -> bool:
    return os.getenv("SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


@lru_cache(maxsize=1)
def _pipeline() -> UnifiedPipeline:
    return UnifiedPipeline(config_dir=str(_CONFIG_DIR), shadow_mode=True)


@lru_cache(maxsize=1)
def _monitor() -> Monitor:
    return Monitor(str(_CONFIG_DIR))


def _estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // 4 + 1)


def run_shadow_route(query: str, current_model: str) -> dict[str, Any] | None:
    if not token_guardian_shadow_enabled():
        return None

    prompt = " ".join((query or "").split()).strip()
    if not prompt:
        return None

    decision: RoutingDecision = _pipeline().process(prompt)
    estimated_tokens = _estimate_tokens(prompt)
    estimated_cost = _monitor()._estimate_cost_for_model(estimated_tokens, decision.selected_model)

    payload = asdict(decision)
    payload["current_model"] = current_model
    payload["estimated_tokens"] = estimated_tokens
    payload["estimated_cost"] = round(estimated_cost, 6)
    payload["would_switch_models"] = decision.selected_model != current_model
    return payload
