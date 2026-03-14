"""
meeting_recorder.py — Guardian-backed meeting notes generator.

Fetches the recent transcript for a room, calls the configured LLM to
produce structured markdown notes, and persists the result as a
ChatMeetingArtifact.  All errors are caught so the endpoint always
returns something useful even when the LLM is unavailable.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session


# ── helpers ───────────────────────────────────────────────────────────────────

def _build_transcript(session: Session, room_id: uuid.UUID, limit: int = 60) -> tuple[str, list[str]]:
    """
    Return (transcript_text, unique_sender_names).

    Messages are fetched newest-first and reversed to chronological order
    (matching what get_chat_messages already does).
    """
    from app.crud import get_chat_messages
    from app.models import ChatUser

    messages, _total, _has_more = get_chat_messages(
        session=session,
        room_id=room_id,
        limit=limit,
    )

    lines: list[str] = []
    senders: list[str] = []

    for msg in messages:
        sender = session.get(ChatUser, msg.sender_id)
        name = (sender.username if sender else "unknown")
        ts = msg.created_at.strftime("%H:%M") if msg.created_at else "??"
        line = f"[{ts}] {name}: {msg.content}"
        lines.append(line)
        if name not in senders:
            senders.append(name)

    transcript = "\n".join(lines) if lines else "(no messages yet)"
    return transcript, senders


def _notes_prompt(transcript: str, senders: list[str], ts_label: str) -> str:
    participants_block = "\n".join(f"- {s}" for s in senders) if senders else "- (unknown)"
    return f"""You are Sparkbot, a meeting recorder. Given the following room transcript, produce concise structured meeting notes in the exact markdown format below. Fill every section — if information is absent write "(none noted)". Do not add extra sections.

---

# Roundtable Meeting — {ts_label}

## Purpose
<inferred from first bot message or "Roundtable session">

## Participants
{participants_block}

## Discussion Summary
<summary>

## Key Decisions
- ...

## Action Items
- [ ] Task — Owner — Status

## Open Questions
- ...

## Next Steps
- ...

---

TRANSCRIPT:
{transcript}

Produce the completed notes now, replacing the angle-bracket placeholders with real content. Keep each section tight."""


# ── public entry point ────────────────────────────────────────────────────────

async def generate_meeting_notes(
    *,
    session: Session,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    model: str,
    window_end_ts: datetime | None = None,
    transcript_limit: int = 60,
) -> dict[str, Any]:
    """
    Generate structured meeting notes for *room_id* and persist them.

    Returns a dict that is JSON-serialisable and matches MeetingArtifactResponse.
    Never raises — on LLM failure a minimal transcript-only artifact is saved.
    """
    from app.crud import create_chat_meeting_artifact
    from app.services.guardian.executive import (
        _append_jsonl,
        _decision_log_path,
    )

    window_end = window_end_ts or datetime.now(timezone.utc)
    ts_label = window_end.strftime("%Y-%m-%d %H:%M UTC")

    # ── 1. build transcript ───────────────────────────────────────────────────
    try:
        transcript, senders = _build_transcript(session, room_id, limit=transcript_limit)
    except Exception as exc:
        transcript = f"(error fetching transcript: {exc})"
        senders = []

    # ── 2. call LLM ───────────────────────────────────────────────────────────
    notes_md: str
    llm_ok = False
    try:
        import litellm  # type: ignore

        prompt = _notes_prompt(transcript, senders, ts_label)
        resp = litellm.completion(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are Sparkbot meeting recorder. Follow the exact template provided.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
        notes_md = (resp.choices[0].message.content or "").strip()
        if not notes_md:
            raise RuntimeError("LLM returned empty content")
        llm_ok = True
    except Exception as llm_err:
        # Graceful fallback: save raw transcript so something is always recorded
        notes_md = (
            f"# Roundtable Meeting — {ts_label}\n\n"
            f"_Notes could not be generated automatically ({llm_err})._\n\n"
            f"## Raw Transcript\n\n```\n{transcript}\n```"
        )

    # ── 3. log to executive guardian JSONL ────────────────────────────────────
    try:
        _append_jsonl(
            _decision_log_path(),
            {
                "tool_name": "generate_meeting_notes",
                "action_type": "read_internal",
                "room_id": str(room_id),
                "user_id": str(user_id),
                "model": model,
                "llm_ok": llm_ok,
                "ts": window_end.isoformat(),
            },
        )
    except Exception:
        pass  # never block on log failure

    # ── 4. persist artifact ───────────────────────────────────────────────────
    artifact = create_chat_meeting_artifact(
        session=session,
        room_id=room_id,
        created_by_user_id=user_id,
        type="notes",
        content_markdown=notes_md,
        window_end_ts=window_end,
        meta_json={"model": model, "llm_ok": llm_ok, "senders": senders},
    )

    return {
        "id": str(artifact.id),
        "room_id": str(artifact.room_id),
        "created_at": artifact.created_at.isoformat(),
        "created_by_user_id": str(artifact.created_by_user_id),
        "type": artifact.type.value,
        "window_start_ts": artifact.window_start_ts.isoformat() if artifact.window_start_ts else None,
        "window_end_ts": artifact.window_end_ts.isoformat() if artifact.window_end_ts else None,
        "content_markdown": artifact.content_markdown,
        "meta_json": artifact.meta_json,
    }
