"""Durable outcome scoring, workflow promotion, and route adaptation."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "improvement_loop"
_STORE_FILENAME = "outcomes.json"
_MAX_ROOM_PATTERNS = 12
_MAX_CONTEXT_PATTERNS = 3
_MAX_IMPROVEMENT_PROPOSALS = 50


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


def _outcome_window_days() -> int:
    try:
        return max(1, min(int(os.getenv("SPARKBOT_IMPROVEMENT_OUTCOME_WINDOW_DAYS", "90")), 3650))
    except ValueError:
        return 90


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _outcome_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=_outcome_window_days())


def _rebuild_bucket_from_recent(bucket: dict[str, Any]) -> None:
    recent = bucket.get("recent_outcomes")
    if not isinstance(recent, list):
        return
    cutoff = _outcome_cutoff()
    kept = []
    for item in recent:
        if not isinstance(item, dict):
            continue
        created_at = _parse_utc(item.get("created_at"))
        if created_at and created_at >= cutoff:
            kept.append(item)
    bucket["recent_outcomes"] = kept
    bucket["attempts"] = len(kept)
    bucket["successes"] = sum(1 for item in kept if bool(item.get("success")))
    bucket["failures"] = bucket["attempts"] - bucket["successes"]
    bucket["score_total"] = round(sum(float(item.get("score") or 0.0) for item in kept), 2)
    bucket["last_score"] = float(kept[-1].get("score") or 0.0) if kept else 0.0
    bucket["last_result_at"] = str(kept[-1].get("created_at") or "") if kept else ""
    bucket["last_error"] = str(kept[-1].get("error") or "")[:400] if kept and not kept[-1].get("success") else ""
    tool_totals: dict[str, int] = {}
    agent_successes: dict[str, int] = {}
    for item in kept:
        for tool_name, count in (item.get("tool_usage_counts") or {}).items():
            tool_totals[str(tool_name)] = int(tool_totals.get(str(tool_name)) or 0) + int(count or 0)
        if item.get("success") and item.get("agent_name"):
            agent_name = str(item.get("agent_name"))
            agent_successes[agent_name] = int(agent_successes.get(agent_name) or 0) + 1
    bucket["tool_totals"] = tool_totals
    bucket["agent_successes"] = agent_successes


def _prune_store_windows(store: dict[str, Any]) -> None:
    for class_bucket in (store.get("model_outcomes") or {}).values():
        if not isinstance(class_bucket, dict):
            continue
        for bucket in class_bucket.values():
            if isinstance(bucket, dict):
                _rebuild_bucket_from_recent(bucket)
    cutoff = _outcome_cutoff()
    workflow_root = store.get("workflow_patterns") or {}
    if isinstance(workflow_root, dict):
        for user_bucket in workflow_root.values():
            if not isinstance(user_bucket, dict):
                continue
            for room_bucket in user_bucket.values():
                patterns = room_bucket.get("patterns") if isinstance(room_bucket, dict) else None
                if isinstance(patterns, list):
                    room_bucket["patterns"] = [
                        item for item in patterns
                        if isinstance(item, dict)
                        and (_parse_utc(item.get("last_seen")) or datetime.now(timezone.utc)) >= cutoff
                    ]


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
    payload.setdefault("improvement_proposals", [])
    _prune_store_windows(payload)
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
    now_iso = _utc_now_iso()
    recent = model_bucket.setdefault("recent_outcomes", [])
    if not isinstance(recent, list):
        recent = []
        model_bucket["recent_outcomes"] = recent
    recent.append(
        {
            "created_at": now_iso,
            "score": score,
            "success": bool(success),
            "error": str(error or "").strip()[:400],
            "tool_usage_counts": normalized_tools,
            "agent_name": agent_name or "",
        }
    )
    _rebuild_bucket_from_recent(model_bucket)

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

    _prune_store_windows(store)
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
    _ = query
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


def _safe_summary(value: str, *, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def propose_improvement(
    *,
    user_id: str | None,
    room_id: str | None,
    summary: str,
    evidence: str = "",
    suggested_change: str = "",
    risk: str = "medium",
    source: str = "assistant",
) -> dict[str, Any] | None:
    """Record a governed self-improvement proposal for operator approval.

    This records intent only. Code, config, or workflow changes still need an
    explicit user approval before Sparkbot applies them with execution tools.
    """
    if not improvement_loop_enabled():
        return None

    cleaned_summary = _safe_summary(summary, limit=240)
    if not cleaned_summary:
        return None

    risk_value = str(risk or "medium").strip().lower()
    if risk_value not in {"low", "medium", "high"}:
        risk_value = "medium"

    proposal = {
        "id": f"improve-{uuid.uuid4().hex[:12]}",
        "status": "proposed",
        "approval_required": True,
        "summary": cleaned_summary,
        "evidence": _safe_summary(evidence, limit=800),
        "suggested_change": _safe_summary(suggested_change, limit=1200),
        "risk": risk_value,
        "source": _safe_summary(source, limit=80) or "assistant",
        "user_id": str(user_id or ""),
        "room_id": str(room_id or ""),
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }

    store = _load_store()
    proposals = store.setdefault("improvement_proposals", [])
    if not isinstance(proposals, list):
        proposals = []
        store["improvement_proposals"] = proposals
    proposals.insert(0, proposal)
    del proposals[_MAX_IMPROVEMENT_PROPOSALS:]
    _save_store(store)

    try:
        from app.services.guardian.spine import (
            SpineSourceReference,
            ingest_subsystem_event,
        )

        ingest_subsystem_event(
            event_type="improvement.proposed",
            subsystem="improvement",
            source=SpineSourceReference(source_kind="improvement", source_ref=proposal["id"], room_id=proposal["room_id"] or None),
            content=f"Improvement proposal needs approval: {cleaned_summary}",
            metadata={
                "title": cleaned_summary,
                "summary": suggested_change or cleaned_summary,
                "status": "awaiting_approval",
                "approval_required": True,
                "approval_state": "required",
                "confidence": 0.95,
                "tags": ["improvement", "approval"],
            },
        )
    except Exception:
        pass

    return proposal


def list_improvement_proposals(
    *,
    user_id: str | None = None,
    room_id: str | None = None,
    status: str | None = "proposed",
    limit: int = 10,
) -> list[dict[str, Any]]:
    if not improvement_loop_enabled():
        return []

    store = _load_store()
    proposals = store.get("improvement_proposals", [])
    if not isinstance(proposals, list):
        return []

    status_filter = str(status or "").strip().lower()
    room_filter = str(room_id or "").strip()
    user_filter = str(user_id or "").strip()
    rows: list[dict[str, Any]] = []
    for item in proposals:
        if not isinstance(item, dict):
            continue
        if status_filter and str(item.get("status") or "").strip().lower() != status_filter:
            continue
        if room_filter and str(item.get("room_id") or "") != room_filter:
            continue
        if user_filter and str(item.get("user_id") or "") != user_filter:
            continue
        rows.append(dict(item))
        if len(rows) >= max(1, min(int(limit or 10), 50)):
            break
    return rows
