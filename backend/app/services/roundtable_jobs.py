"""Roundtable runner pilot: jobs that wake outside agents on @mentions.

Contract: docs/roundtable-runner.md (v1). A human message that @mentions an
agent seat (or @all) creates one job per seat. A runner on the machine where
that agent is logged in claims the job with the seat token, runs the agent,
and completes it; the backend posts exactly one reply as the seat.

Rules that keep the room safe:
- Only HUMAN messages create jobs; agent replies never wake agents.
- One job per (seat, trigger message); per-seat hourly cap.
- "/pause" stops new jobs and cancels pending + claimed ones; "/resume" undoes.
- Every claim gets a fresh opaque claim token (stored hashed). Stale claims,
  cancelled or finished jobs answer 409 so a runner knows to stop.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlmodel import Session, col

from app.models import (
    ChatMessage,
    ChatRoomMember,
    ChatUser,
    RoundtableJob,
    RoundtableRoomState,
    RoundtableSeatPresence,
    UserType,
)

SEAT_PREFIX = "seat-"
LEASE_SECONDS = 600
MAX_ATTEMPTS = 2
CONTEXT_MESSAGES = 30
CONTEXT_MESSAGE_CHARS = 4000
MAX_REPLY_CHARS = 8000
ONLINE_WINDOW_SECONDS = 90

_MENTION_RE = re.compile(
    r"(?<![\w@])@([a-z0-9][a-z0-9-]{1,30})(?![\w-])", re.IGNORECASE
)
ACTIVE = ("pending", "claimed")


class JobConflict(Exception):
    """Stale or wrong claim, or the job is no longer workable (-> HTTP 409)."""

    def __init__(self, detail: str, status: str):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def jobs_per_hour() -> int:
    try:
        return max(1, int(os.getenv("SPARKBOT_RUNNER_JOBS_PER_HOUR", "12")))
    except ValueError:
        return 12


# ── Room state ────────────────────────────────────────────────────────────────


def is_paused(session: Session, room_id: uuid.UUID) -> bool:
    state = session.get(RoundtableRoomState, room_id)
    return bool(state and state.paused)


def set_paused(
    session: Session, room_id: uuid.UUID, paused: bool, by: uuid.UUID | None
) -> int:
    """Pause or resume. Pausing cancels pending and claimed jobs; returns how many."""
    state = session.get(RoundtableRoomState, room_id) or RoundtableRoomState(
        room_id=room_id
    )
    state.paused = paused
    state.changed_by = by
    state.updated_at = now()
    session.add(state)
    cancelled = 0
    if paused:
        result = session.execute(
            update(RoundtableJob)
            .where(
                col(RoundtableJob.room_id) == room_id,
                col(RoundtableJob.status).in_(ACTIVE),
            )
            .values(
                status="cancelled",
                reason="room paused",
                claim_token_hash=None,
                updated_at=now(),
                finished_at=now(),
            )
        )
        cancelled = getattr(result, "rowcount", 0) or 0
    session.commit()
    return cancelled


# ── Job creation ──────────────────────────────────────────────────────────────


def agent_seats_in_room(session: Session, room_id: uuid.UUID) -> list[ChatUser]:
    rows = session.execute(
        select(ChatUser)
        .join(ChatRoomMember, col(ChatRoomMember.user_id) == col(ChatUser.id))
        .where(
            col(ChatRoomMember.room_id) == room_id,
            col(ChatUser.username).startswith(SEAT_PREFIX),
            col(ChatUser.type) == UserType.BOT,
            col(ChatUser.is_active).is_(True),
        )
    ).scalars()
    return list(rows)


def mentioned_slugs(content: str) -> set[str]:
    return {m.lower() for m in _MENTION_RE.findall(content or "")}


def handle_human_message(
    session: Session, message: ChatMessage, sender: ChatUser
) -> dict[str, Any]:
    """Called after a message is stored. Applies /pause, /resume and @mention jobs."""
    if sender.type != UserType.HUMAN:
        return {"jobs": 0}
    text = (message.content or "").strip()
    command = text.lower()
    if command in ("/pause", "/resume"):
        cancelled = set_paused(session, message.room_id, command == "/pause", sender.id)
        return {"paused": command == "/pause", "cancelled": cancelled, "jobs": 0}
    if is_paused(session, message.room_id):
        return {"jobs": 0, "paused": True}

    slugs = mentioned_slugs(text)
    if not slugs:
        return {"jobs": 0}
    seats = agent_seats_in_room(session, message.room_id)
    targets = (
        seats
        if "all" in slugs
        else [s for s in seats if (s.bot_slug or "").lower() in slugs]
    )
    created = 0
    hour_ago = now() - timedelta(hours=1)
    cap = jobs_per_hour()
    for seat in targets:
        exists = session.execute(
            select(col(RoundtableJob.id)).where(
                col(RoundtableJob.seat_id) == seat.id,
                col(RoundtableJob.trigger_message_id) == message.id,
            )
        ).first()
        if exists:
            continue
        recent = session.execute(
            select(func.count())
            .select_from(RoundtableJob)
            .where(
                col(RoundtableJob.seat_id) == seat.id,
                col(RoundtableJob.created_at) >= hour_ago,
                col(RoundtableJob.status) != "skipped",
            )
        ).scalar_one()
        over_cap = recent >= cap
        session.add(
            RoundtableJob(
                room_id=message.room_id,
                seat_id=seat.id,
                trigger_message_id=message.id,
                status="skipped" if over_cap else "pending",
                reason=f"hourly cap ({cap}) reached" if over_cap else None,
            )
        )
        created += 0 if over_cap else 1
    session.commit()
    return {"jobs": created}


# ── Runner side ───────────────────────────────────────────────────────────────


def touch_presence(session: Session, seat_id: uuid.UUID) -> None:
    row = session.get(RoundtableSeatPresence, seat_id) or RoundtableSeatPresence(
        seat_id=seat_id
    )
    row.last_seen_at = now()
    session.add(row)
    session.commit()


def _expire_stale_claims(session: Session, seat_id: uuid.UUID) -> None:
    stale = session.execute(
        select(RoundtableJob).where(
            col(RoundtableJob.seat_id) == seat_id,
            col(RoundtableJob.status) == "claimed",
        )
    ).scalars()
    changed = False
    for job in stale:
        lease = aware(job.lease_expires_at)
        if lease and lease < now():
            job.claim_token_hash = None
            job.updated_at = now()
            if job.attempts < MAX_ATTEMPTS:
                job.status, job.reason = "pending", "lease expired; retrying"
            else:
                job.status, job.reason, job.finished_at = (
                    "expired",
                    "lease expired twice",
                    now(),
                )
            session.add(job)
            changed = True
    if changed:
        session.commit()


def claim_next(session: Session, seat: ChatUser) -> tuple[RoundtableJob, str] | None:
    """Claim the oldest pending job for this seat in an unpaused room."""
    _expire_stale_claims(session, seat.id)
    candidates = session.execute(
        select(RoundtableJob)
        .where(
            col(RoundtableJob.seat_id) == seat.id,
            col(RoundtableJob.status) == "pending",
        )
        .order_by(col(RoundtableJob.created_at))
    ).scalars()
    for job in candidates:
        if is_paused(session, job.room_id):
            continue
        # Still a member of that room? (seat may have been removed)
        member = session.execute(
            select(col(ChatRoomMember.id)).where(
                col(ChatRoomMember.room_id) == job.room_id,
                col(ChatRoomMember.user_id) == seat.id,
            )
        ).first()
        if not member:
            job.status, job.reason, job.finished_at = (
                "cancelled",
                "seat removed from room",
                now(),
            )
            session.add(job)
            session.commit()
            continue
        token = secrets.token_urlsafe(24)
        claimed_at = now()
        result = session.execute(
            update(RoundtableJob)
            .where(
                col(RoundtableJob.id) == job.id, col(RoundtableJob.status) == "pending"
            )
            .values(
                status="claimed",
                claim_token_hash=_hash(token),
                lease_expires_at=claimed_at + timedelta(seconds=LEASE_SECONDS),
                attempts=job.attempts + 1,
                claimed_at=claimed_at,
                updated_at=claimed_at,
                reason=None,
            )
        )
        session.commit()
        if getattr(result, "rowcount", 0):  # we won the claim
            session.refresh(job)
            return job, token
    return None


def _check_claim(
    session: Session, seat: ChatUser, job_id: uuid.UUID, token: str
) -> RoundtableJob:
    job = session.get(RoundtableJob, job_id)
    if not job or job.seat_id != seat.id:
        raise JobConflict("No such job for this seat", "missing")
    if not job.claim_token_hash or not secrets.compare_digest(
        job.claim_token_hash, _hash(token)
    ):
        raise JobConflict("Stale or wrong claim token", job.status)
    return job


def _require_live_claim(job: RoundtableJob) -> None:
    if job.status != "claimed":
        raise JobConflict(f"Job is {job.status}", job.status)
    lease = aware(job.lease_expires_at)
    if lease and lease < now():
        raise JobConflict("Lease expired", "expired")


def heartbeat(
    session: Session, seat: ChatUser, job_id: uuid.UUID, token: str, note: str | None
) -> RoundtableJob:
    job = _check_claim(session, seat, job_id, token)
    _require_live_claim(job)
    job.lease_expires_at = now() + timedelta(seconds=LEASE_SECONDS)
    job.note = (note or "")[:200] or job.note
    job.updated_at = now()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def find_existing_reply(session: Session, job: RoundtableJob) -> ChatMessage | None:
    """A reply this seat already posted for this job (crash between post and commit)."""
    if job.reply_message_id:
        return session.get(ChatMessage, job.reply_message_id)
    since = aware(job.claimed_at) or aware(job.created_at)
    rows = session.execute(
        select(ChatMessage)
        .where(
            col(ChatMessage.room_id) == job.room_id,
            col(ChatMessage.sender_id) == job.seat_id,
            col(ChatMessage.reply_to_id) == job.trigger_message_id,
        )
        .order_by(col(ChatMessage.created_at))
    ).scalars()
    for message in rows:
        if (message.meta_json or {}).get("job_id") == str(job.id):
            return message
        created = aware(message.created_at)
        if (
            since
            and created
            and created >= since
            and (message.meta_json or {}).get("via") == "roundtable_runner"
        ):
            return message
    return None


def begin_complete(
    session: Session, seat: ChatUser, job_id: uuid.UUID, token: str
) -> tuple[RoundtableJob, ChatMessage | None]:
    """Validate a completion. Returns (job, existing_reply). existing_reply set = idempotent repeat."""
    job = _check_claim(session, seat, job_id, token)
    if job.status == "done":
        return job, find_existing_reply(session, job)
    _require_live_claim(job)
    existing = find_existing_reply(session, job)
    if existing:
        mark_done(session, job, existing.id)
    return job, existing


def mark_done(
    session: Session, job: RoundtableJob, reply_message_id: uuid.UUID
) -> RoundtableJob:
    job.status = "done"
    job.reply_message_id = reply_message_id
    job.finished_at = now()
    job.updated_at = now()
    job.lease_expires_at = None
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def fail(
    session: Session,
    seat: ChatUser,
    job_id: uuid.UUID,
    token: str,
    error: str,
    retry: bool,
) -> RoundtableJob:
    job = _check_claim(session, seat, job_id, token)
    _require_live_claim(job)
    job.error = (error or "")[:500]
    job.claim_token_hash = None
    job.lease_expires_at = None
    job.updated_at = now()
    if retry and job.attempts < MAX_ATTEMPTS:
        job.status, job.reason = "pending", "runner asked to retry"
    else:
        job.status, job.finished_at = "failed", now()
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def context_messages(
    session: Session, room_id: uuid.UUID, upto: ChatMessage
) -> list[ChatMessage]:
    """Up to CONTEXT_MESSAGES messages ending at the trigger, oldest first."""
    rows = session.execute(
        select(ChatMessage)
        .where(
            col(ChatMessage.room_id) == room_id,
            col(ChatMessage.created_at) <= upto.created_at,
        )
        .order_by(col(ChatMessage.created_at).desc())
        .limit(CONTEXT_MESSAGES)
    ).scalars()
    return list(reversed(list(rows)))


# ── Room view (presence for the People panel) ─────────────────────────────────


def seat_presence(
    session: Session, room_id: uuid.UUID, seat_ids: list[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for seat_id in seat_ids:
        seen = session.get(RoundtableSeatPresence, seat_id)
        last = aware(seen.last_seen_at) if seen else None
        working = session.execute(
            select(col(RoundtableJob.note)).where(
                col(RoundtableJob.room_id) == room_id,
                col(RoundtableJob.seat_id) == seat_id,
                col(RoundtableJob.status) == "claimed",
            )
        ).first()
        waiting = session.execute(
            select(func.count())
            .select_from(RoundtableJob)
            .where(
                col(RoundtableJob.room_id) == room_id,
                col(RoundtableJob.seat_id) == seat_id,
                col(RoundtableJob.status) == "pending",
            )
        ).scalar_one()
        online = bool(last and (now() - last).total_seconds() <= ONLINE_WINDOW_SECONDS)
        out[seat_id] = {
            "presence": "working" if working else ("online" if online else "offline"),
            "working_note": working[0] if working else None,
            "pending_jobs": waiting,
            "last_seen_at": last,
        }
    return out
