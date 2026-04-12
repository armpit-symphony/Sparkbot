"""Durable outcome scoring, workflow promotion, and route adaptation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "improvement_loop"
_STORE_FILENAME = "outcomes.json"
_MAX_ROOM_PATTERNS = 12
_MAX_CONTEXT_PATTERNS = 3


def improvement_loop_enabled() -> bool:
    return os.getenv("SPARKBOT_IMPROVEMENT_LOOP_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _data_dir() -> Path:
    configured = os.getenv("SPARKBOT_IMPROVEMENT_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return _DEFAULT_DATA_DIR


def _store_path() -> Path:
    path = _data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path / _STORE_FILENAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"model_outcomes": {}, "workflow_patterns": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"model_outcomes": {}, "workflow_patterns": {}}
    if not isinstance(payload, dict):
        return {"model_outcomes": {}, "workflow_patterns": {}}
    payload.setdefault("model_outcomes", {})
    payload.setdefault("workflow_patterns", {})
    return payload


def _save_store(store: dict[str, Any]) -> None:
    path = _store_path()
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _normalize_classification(value: str | None) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_")
    return normalized or "general"


def _normalize_model(value: str | None) -> str:
    return str(value or "").strip()


def _normalize_tool_counts(tool_usage_counts: dict[str, int] | None) -> dict[str, int]:
    normalized: dict[str, int] = {}
    for name, count in (tool_usage_counts or {}).items():
        tool_name = str(name or "").strip()
        if not tool_name:
            continue
        try:
            parsed_count = max(int(count), 0)
        except Exception:
            parsed_count = 0
        if parsed_count:
            normalized[tool_name] = parsed_count
    return normalized


def score_outcome(
    *,
    success: bool,
    output_text: str = "",
    tool_usage_counts: dict[str, int] | None = None,
    route_payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> float:
    if not success:
        penalty = 1.5 + min(len((error or "").strip()) / 120.0, 0.75)
        return round(-penalty, 2)

    cleaned_output = str(output_text or "").strip()
    output_bonus = min(len(cleaned_output) / 320.0, 1.75)
    if cleaned_output and len(cleaned_output) < 24:
        output_bonus -= 0.35

    tools = _normalize_tool_counts(tool_usage_counts)
    tool_bonus = min(sum(min(count, 2) for count in tools.values()) * 0.22, 1.0)
    fallback_penalty = 0.25 if bool((route_payload or {}).get("fallback_triggered")) else 0.0
    learned_bonus = 0.15 if bool((route_payload or {}).get("learned_route_applied")) else 0.0
    return round(max(0.2, 1.0 + output_bonus + tool_bonus + learned_bonus - fallback_penalty), 2)


def _tool_label(tool_name: str) -> str:
    return tool_name.replace("_", " ")


def _pattern_summary(*, classification: str, model: str, tools: list[str], agent_name: str | None) -> list[dict[str, Any]]:
    label = classification.replace("_", " ")
    patterns = [
        {
            "key": f"model::{classification}::{model}",
            "summary": f"For {label} work in this room, {model} has produced reliable results.",
        }
    ]
    if tools:
        pretty_tools = ", ".join(_tool_label(tool_name) for tool_name in tools)
        patterns.append(
            {
                "key": f"tools::{classification}::{'|'.join(tools)}",
                "summary": f"Successful {label} runs here often use: {pretty_tools}.",
            }
        )
    if agent_name and agent_name not in {"", "sparkbot"}:
        patterns.append(
            {
                "key": f"agent::{classification}::{agent_name}",
                "summary": f"@{agent_name} has been effective for {label} work in this room.",
            }
        )
    return patterns


def _update_pattern_bucket(
    *,
    patterns: list[dict[str, Any]],
    summary: str,
    key: str,
    score: float,
    metadata: dict[str, Any],
) -> None:
    now = _utc_now_iso()
    existing = next((item for item in patterns if item.get("key") == key), None)
    if existing is None:
        existing = {
            "key": key,
            "summary": summary,
            "score_total": 0.0,
            "count": 0,
            "last_seen": now,
        }
        patterns.append(existing)
    existing["summary"] = summary
    existing["count"] = int(existing.get("count") or 0) + 1
    existing["score_total"] = round(float(existing.get("score_total") or 0.0) + score, 2)
    existing["last_seen"] = now
    existing.update(metadata)


def record_outcome(
    *,
    user_id: str | None,
    room_id: str | None,
    route_payload: dict[str, Any] | None,
    output_text: str = "",
    tool_usage_counts: dict[str, int] | None = None,
    success: bool,
    agent_name: str | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    if not improvement_loop_enabled():
        return None

    classification = _normalize_classification((route_payload or {}).get("classification"))
    model = _normalize_model(
        (route_payload or {}).get("applied_model")
        or (route_payload or {}).get("selected_model")
        or (route_payload or {}).get("requested_model")
    )
    if not model:
        return None

    normalized_tools = _normalize_tool_counts(tool_usage_counts)
    score = score_outcome(
        success=success,
        output_text=output_text,
        tool_usage_counts=normalized_tools,
        route_payload=route_payload,
        error=error,
    )

    store = _load_store()
    outcomes = store.setdefault("model_outcomes", {})
    model_bucket = outcomes.setdefault(classification, {}).setdefault(
        model,
        {
            "attempts": 0,
            "successes": 0,
            "failures": 0,
            "score_total": 0.0,
            "last_score": 0.0,
            "last_result_at": "",
            "last_error": "",
            "tool_totals": {},
            "agent_successes": {},
        },
    )
    model_bucket["attempts"] = int(model_bucket.get("attempts") or 0) + 1
    if success:
        model_bucket["successes"] = int(model_bucket.get("successes") or 0) + 1
    else:
        model_bucket["failures"] = int(model_bucket.get("failures") or 0) + 1
        model_bucket["last_error"] = str(error or "").strip()[:400]
    model_bucket["score_total"] = round(float(model_bucket.get("score_total") or 0.0) + score, 2)
    model_bucket["last_score"] = score
    model_bucket["last_result_at"] = _utc_now_iso()
    tool_totals = model_bucket.setdefault("tool_totals", {})
    for tool_name, count in normalized_tools.items():
        tool_totals[tool_name] = int(tool_totals.get(tool_name) or 0) + count
    if success and agent_name:
        agent_successes = model_bucket.setdefault("agent_successes", {})
        agent_successes[agent_name] = int(agent_successes.get(agent_name) or 0) + 1

    if success and user_id and room_id:
        workflow_root = store.setdefault("workflow_patterns", {})
        room_patterns = (
            workflow_root
            .setdefault(str(user_id), {})
            .setdefault(str(room_id), {"patterns": []})
            .setdefault("patterns", [])
        )
        tools = sorted(normalized_tools)
        pattern_metadata = {
            "classification": classification,
            "model": model,
            "tools": tools,
            "agent_name": agent_name or "",
        }
        for pattern in _pattern_summary(
            classification=classification,
            model=model,
            tools=tools,
            agent_name=agent_name,
        ):
            pattern_score = score + (0.25 * len(tools) if pattern["key"].startswith("tools::") else 0.0)
            _update_pattern_bucket(
                patterns=room_patterns,
                key=pattern["key"],
                summary=pattern["summary"],
                score=pattern_score,
                metadata=pattern_metadata,
            )
        room_patterns.sort(
            key=lambda item: (
                -float(item.get("score_total") or 0.0),
                -int(item.get("count") or 0),
                str(item.get("summary") or ""),
            )
        )
        del room_patterns[_MAX_ROOM_PATTERNS:]

    _save_store(store)
    return {
        "classification": classification,
        "model": model,
        "score": score,
        "success": success,
    }


def _ranking_score(item: dict[str, Any]) -> float:
    attempts = max(int(item.get("attempts") or 0), 0)
    successes = max(int(item.get("successes") or 0), 0)
    if attempts <= 0 or successes <= 0:
        return 0.0
    success_rate = successes / attempts
    avg_score = max(float(item.get("score_total") or 0.0), 0.0) / max(successes, 1)
    confidence = min(attempts / 4.0, 1.0)
    return round((success_rate * 0.55) + (min(avg_score / 3.0, 1.0) * 0.3) + (confidence * 0.15), 4)


def choose_best_model(
    *,
    classification: str,
    current_model: str,
    candidates: list[str] | tuple[str, ...] | set[str],
) -> tuple[str, str | None, list[dict[str, Any]]]:
    normalized_candidates = [candidate for candidate in [str(item).strip() for item in candidates] if candidate]
    if not improvement_loop_enabled() or not normalized_candidates:
        return current_model, None, []

    store = _load_store()
    outcomes = store.get("model_outcomes", {}).get(_normalize_classification(classification), {})
    ranking: list[dict[str, Any]] = []
    for index, candidate in enumerate(normalized_candidates):
        stats = outcomes.get(candidate, {})
        ranking.append(
            {
                "model": candidate,
                "score": _ranking_score(stats),
                "attempts": int(stats.get("attempts") or 0),
                "successes": int(stats.get("successes") or 0),
                "order": index,
            }
        )

    ranking.sort(key=lambda item: (-float(item["score"]), -item["successes"], item["order"]))
    top = ranking[0] if ranking else None
    baseline = next((item for item in ranking if item["model"] == current_model), None)
    baseline_score = float(baseline["score"]) if baseline else 0.0

    if not top or top["model"] == current_model:
        return current_model, None, ranking
    if top["attempts"] < 2 or top["successes"] < 2:
        return current_model, None, ranking
    if float(top["score"]) < baseline_score + 0.12:
        return current_model, None, ranking

    reason = (
        f"Outcome learning preferred {top['model']} for {_normalize_classification(classification).replace('_', ' ')} "
        f"work ({top['successes']}/{top['attempts']} successful runs, score {top['score']:.2f})."
    )
    return str(top["model"]), reason, ranking


def reorder_candidate_models(
    *,
    classification: str,
    candidates: list[str],
) -> list[str]:
    if not improvement_loop_enabled() or len(candidates) <= 1:
        return candidates
    chosen, _, ranking = choose_best_model(
        classification=classification,
        current_model=candidates[0],
        candidates=candidates,
    )
    if not ranking:
        return candidates
    preferred_order = [item["model"] for item in ranking if item["attempts"] >= 2 and item["successes"] >= 1]
    if not preferred_order:
        return candidates
    reordered = preferred_order + [candidate for candidate in candidates if candidate not in set(preferred_order)]
    if chosen in reordered:
        reordered.remove(chosen)
        reordered.insert(0, chosen)
    return reordered


def build_promoted_workflow_context(*, user_id: str, room_id: str, query: str = "") -> str:
    if not improvement_loop_enabled():
        return ""

    store = _load_store()
    room_patterns = (
        store.get("workflow_patterns", {})
        .get(str(user_id), {})
        .get(str(room_id), {})
        .get("patterns", [])
    )
    if not room_patterns:
        return ""

    top_patterns = sorted(
        room_patterns,
        key=lambda item: (
            -float(item.get("score_total") or 0.0),
            -int(item.get("count") or 0),
            str(item.get("last_seen") or ""),
        ),
    )[:_MAX_CONTEXT_PATTERNS]
    if not top_patterns:
        return ""
    lines = [f"- {item['summary']}" for item in top_patterns if str(item.get("summary") or "").strip()]
    if not lines:
        return ""
    return "## Promoted Workflow Patterns\n" + "\n".join(lines)
