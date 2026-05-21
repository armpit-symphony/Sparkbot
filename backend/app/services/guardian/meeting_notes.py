from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

MEETING_NOTE_SOURCE_DEFAULT = "meeting_manager"
MEETING_NOTE_TAGS = ["meeting_notes", "roundtable", "shared_company_memory"]

_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "summary": ("discussion summary", "summary", "outcome", "purpose"),
    "decisions": ("key decisions", "decisions"),
    "action_items": ("action items", "actions"),
    "next_steps": ("next steps",),
    "open_questions": ("open questions", "questions"),
    "participants": ("participants", "seats"),
}


def _clean(value: Any, limit: int = 4000) -> str:
    text = " ".join(str(value or "").replace("\r", "\n").split())
    return text[:limit]


def _extract_sections(markdown: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = "body"
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            current = re.sub(r"[^a-z0-9]+", "_", stripped[3:].strip().lower()).strip("_") or "section"
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def structured_note_fields(markdown: str) -> dict[str, str]:
    sections = _extract_sections(markdown)
    result: dict[str, str] = {}
    for field, aliases in _SECTION_ALIASES.items():
        for alias in aliases:
            key = re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_")
            if sections.get(key):
                result[field] = _clean(sections[key], limit=1800)
                break
        result.setdefault(field, "")
    if not result["summary"]:
        result["summary"] = _clean(sections.get("body", ""), limit=1200)
    return result


def normalize_meeting_note_meta(
    *,
    room_id: Any,
    artifact_id: Any | None = None,
    room_name: str = "",
    created_by: Any | None = None,
    updated_by: Any | None = None,
    source: str | None = None,
    content_markdown: str = "",
    existing: dict[str, Any] | None = None,
    draft: bool | None = None,
    memory_rollup: bool | None = None,
) -> dict[str, Any]:
    meta = dict(existing or {})
    now = datetime.now(timezone.utc).isoformat()
    is_draft = bool(meta.get("draft", False) if draft is None else draft)
    rollup = bool((not is_draft) if memory_rollup is None else memory_rollup)
    note_fields = structured_note_fields(content_markdown)
    meta.update(
        {
            "meeting_id": str(room_id),
            "title": str(meta.get("title") or room_name or "Round Table Meeting")[:200],
            "source": str(source or meta.get("source") or MEETING_NOTE_SOURCE_DEFAULT),
            "updated_at": now,
            "updated_by": str(updated_by or meta.get("updated_by") or created_by or ""),
            "memory_rollup": rollup,
            "draft": is_draft,
            "tags": list(dict.fromkeys([*(meta.get("tags") or []), *MEETING_NOTE_TAGS]))[:12],
            "summary": note_fields.get("summary", ""),
            "decisions": note_fields.get("decisions", ""),
            "action_items": note_fields.get("action_items", ""),
            "next_steps": note_fields.get("next_steps", ""),
            "open_questions": note_fields.get("open_questions", ""),
            "participants": note_fields.get("participants", ""),
        }
    )
    if artifact_id:
        meta["artifact_id"] = str(artifact_id)
    if created_by and not meta.get("created_by"):
        meta["created_by"] = str(created_by)
    if not meta.get("created_at"):
        meta["created_at"] = now
    return meta
