from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


EXECUTIVE_GUARDIAN_ENABLED = os.getenv("SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

HIGH_RISK_ACTIONS = {
    "write_external",
    "service_control",
    "command_exec",
    "ssh_exec",
    "scheduler_write",
}


def _guardian_root() -> Path:
    root = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    if root:
        return Path(root).expanduser()
    return Path(__file__).resolve().parents[4] / "data" / "guardian"


def _decision_log_path() -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = _guardian_root() / "executive" / "decisions" / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _emit_spine_decision(payload: dict[str, Any]) -> None:
    try:
        from app.services.guardian.spine import SpineProjectInput, SpineTaskInput, ingest_executive_decision

        metadata = payload.get("metadata") or {}
        room_id = metadata.get("room_id")
        project = None
        if metadata.get("project_id") and metadata.get("project_name"):
            project = SpineProjectInput(
                project_id=str(metadata["project_id"]),
                display_name=str(metadata["project_name"]),
                summary=str(metadata.get("project_summary") or payload.get("expected_outcome") or ""),
                status=str(metadata.get("project_status") or "active"),
                room_id=str(room_id) if room_id else None,
                tags=list(metadata.get("project_tags") or []),
                parent_project_id=metadata.get("parent_project_id"),
            )
        task = None
        if metadata.get("task_title"):
            task = SpineTaskInput(
                task_id=metadata.get("task_id"),
                title=str(metadata["task_title"]),
                summary=str(metadata.get("task_summary") or payload.get("expected_outcome") or ""),
                project_id=str(metadata["project_id"]) if metadata.get("project_id") else None,
                type=str(metadata.get("task_type") or "ops"),
                priority=str(metadata.get("task_priority") or "normal"),
                status=str(metadata.get("task_status") or "open"),
                owner_kind=str(metadata.get("owner_kind") or "unassigned"),
                owner_id=metadata.get("owner_id"),
                parent_task_id=metadata.get("parent_task_id"),
                depends_on=list(metadata.get("depends_on") or []),
                related_task_ids=list(metadata.get("related_task_ids") or []),
                approval_required=bool(metadata.get("approval_required")),
                approval_state=str(metadata.get("approval_state") or ("required" if metadata.get("approval_required") else "not_required")),
                confidence=float(metadata.get("confidence") or 0.95),
                tags=list(metadata.get("task_tags") or ["executive"]),
            )
        ingest_executive_decision(
            room_id=str(room_id) if room_id else None,
            source_ref=str(payload.get("decision_id") or payload.get("started_at") or "executive-decision"),
            decision_summary=str(payload.get("expected_outcome") or ""),
            task=task,
            project=project,
            metadata={
                "tool_name": payload.get("tool_name"),
                "action_type": payload.get("action_type"),
                "outcome": payload.get("outcome"),
                "validation_tier": payload.get("validation_tier"),
                "validation_note": payload.get("validation_note"),
                **metadata,
            },
        )
    except Exception:
        pass


def _looks_like_failure(result: Any) -> tuple[bool, str]:
    text = str(result or "").strip()
    lowered = text.lower()
    failure_markers = (
        "failed:",
        "unknown tool:",
        "unsupported ",
        "not configured",
        "not allowed",
        "missing required field",
        "error:",
        "command timed out",
        "command failed",
    )
    for marker in failure_markers:
        if marker in lowered:
            return True, marker
    return False, "success"


def get_status() -> dict[str, Any]:
    return {
        "enabled": EXECUTIVE_GUARDIAN_ENABLED,
        "high_risk_actions": sorted(HIGH_RISK_ACTIONS),
        "log_root": str(_guardian_root()),
    }


async def exec_with_guard(
    *,
    tool_name: str,
    action_type: str,
    expected_outcome: str,
    perform_fn: Callable[[], Any],
    metadata: dict[str, Any] | None = None,
) -> Any:
    if (not EXECUTIVE_GUARDIAN_ENABLED) or action_type not in HIGH_RISK_ACTIONS:
        result = perform_fn()
        if hasattr(result, "__await__"):
            result = await result
        return result

    decision_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "decision_id": decision_id,
        "tool_name": tool_name,
        "action_type": action_type,
        "expected_outcome": expected_outcome,
        "started_at": started_at,
        "metadata": metadata or {},
    }

    try:
        result = perform_fn()
        if hasattr(result, "__await__"):
            result = await result
        failed, validation_note = _looks_like_failure(result)
        payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        payload["outcome"] = "fail" if failed else "success"
        payload["validation_tier"] = "FAIL" if failed else "SUCCESS"
        payload["validation_note"] = validation_note
        payload["result_excerpt"] = str(result)[:500]
        _append_jsonl(_decision_log_path(), payload)
        _emit_spine_decision(payload)
        return result
    except Exception as exc:
        payload["finished_at"] = datetime.now(timezone.utc).isoformat()
        payload["outcome"] = "error"
        payload["validation_tier"] = "FAIL"
        payload["validation_note"] = str(exc)
        _append_jsonl(_decision_log_path(), payload)
        _emit_spine_decision(payload)
        raise
