"""Governed memory lifecycle hygiene for durable user memories."""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlmodel import Session

from app.crud import propose_delete_memory
from app.models import UserMemory
from app.services.guardian.memory_taxonomy import classify_memory_type

_PROTECTED_TYPES = {"identity", "preference", "project_decision", "relationship_note"}
_LOW_RISK_TYPES = {"debug_state", "temporary_context", "unknown", "project_context", "tool_pattern"}


@dataclass
class HygieneChange:
    memory_id: str
    old_state: str
    new_state: str
    reason: str


@dataclass
class HygieneReport:
    scanned_count: int = 0
    marked_stale_count: int = 0
    archived_count: int = 0
    proposed_delete_count: int = 0
    skipped_pinned_count: int = 0
    skipped_protected_count: int = 0
    conflicts_detected_count: int = 0
    errors: list[str] = field(default_factory=list)
    changed_memory_ids: list[HygieneChange] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scanned_count": self.scanned_count,
            "marked_stale_count": self.marked_stale_count,
            "archived_count": self.archived_count,
            "proposed_delete_count": self.proposed_delete_count,
            "skipped_pinned_count": self.skipped_pinned_count,
            "skipped_protected_count": self.skipped_protected_count,
            "conflicts_detected_count": self.conflicts_detected_count,
            "errors": list(self.errors),
            "changed_memory_ids": [change.__dict__ for change in self.changed_memory_ids],
        }


def _env_days(name: str, default: int) -> int:
    try:
        return max(1, min(int(os.getenv(name, str(default))), 3650))
    except ValueError:
        return default


def _policy_days(memory_type: str) -> tuple[int | None, int | None, int | None]:
    if memory_type == "debug_state":
        return (
            _env_days("SPARKBOT_MEMORY_STALE_DEBUG_DAYS", 7),
            _env_days("SPARKBOT_MEMORY_ARCHIVE_DEBUG_DAYS", 14),
            _env_days("SPARKBOT_MEMORY_PROPOSE_DELETE_DEBUG_DAYS", 45),
        )
    if memory_type == "temporary_context":
        return (
            _env_days("SPARKBOT_MEMORY_STALE_TEMP_DAYS", 14),
            _env_days("SPARKBOT_MEMORY_ARCHIVE_TEMP_DAYS", 30),
            _env_days("SPARKBOT_MEMORY_PROPOSE_DELETE_TEMP_DAYS", 90),
        )
    if memory_type == "project_context":
        return 90, 180, 365
    if memory_type == "tool_pattern":
        return 90, 180, 365
    if memory_type == "active_task":
        return 14, 30, 120
    if memory_type == "meeting_action":
        return 30, 90, 180
    if memory_type in _PROTECTED_TYPES:
        return None, None, None
    return (
        _env_days("SPARKBOT_MEMORY_STALE_UNKNOWN_DAYS", 90),
        _env_days("SPARKBOT_MEMORY_ARCHIVE_UNKNOWN_DAYS", 180),
        _env_days("SPARKBOT_MEMORY_PROPOSE_DELETE_UNKNOWN_DAYS", 365),
    )


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _last_activity(memory: UserMemory) -> datetime:
    values = [
        _aware(memory.last_used_at),
        _aware(memory.last_retrieved_at),
        _aware(memory.last_injected_at),
        _aware(memory.updated_at),
        _aware(memory.created_at),
    ]
    return max(dt for dt in values if dt is not None)


def _change(report: HygieneReport, memory: UserMemory, old: str, new: str, reason: str) -> None:
    report.changed_memory_ids.append(
        HygieneChange(memory_id=str(memory.id), old_state=old, new_state=new, reason=reason)
    )


_SUBJECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("work_at", re.compile(r"(?i)\b(?:i work at|my company is|i work for)\s+([A-Za-z0-9 ._-]{2,80})")),
    ("prefer", re.compile(r"(?i)\b(?:i prefer|user prefers|my preference is)\s+([^.;,\n]{2,100})")),
    ("role", re.compile(r"(?i)\b(?:my role is|i am a|i'm a)\s+([^.;,\n]{2,100})")),
    ("use", re.compile(r"(?i)\b(?:i use|user uses)\s+([^.;,\n]{2,100})")),
)


def _subject_key(text: str) -> tuple[str, str] | None:
    for key, pattern in _SUBJECT_PATTERNS:
        match = pattern.search(text or "")
        if match:
            return key, " ".join(match.group(1).lower().split())
    return None


def _detect_conflicts(memories: list[UserMemory], report: HygieneReport) -> None:
    seen: dict[tuple[str, str, str, str], UserMemory] = {}
    for memory in sorted(memories, key=lambda item: item.created_at):
        subject = _subject_key(memory.fact)
        if not subject:
            continue
        subject_kind, value = subject
        key = (
            str(memory.user_id),
            memory.scope_type or "user",
            memory.scope_id or "",
            f"{memory.memory_type}:{subject_kind}",
        )
        older = seen.get(key)
        if older and _subject_key(older.fact) and _subject_key(older.fact)[1] != value:
            report.conflicts_detected_count += 1
            if not older.pinned and older.lifecycle_state == "active":
                older.lifecycle_state = "stale"
                older.stale_reason = f"Possible conflict with memory {memory.id}"
                older.deprecated_by = str(memory.id)
                older.deprecated_reason = "Potential conflict detected by conservative memory hygiene"
                older.updated_at = datetime.now(timezone.utc)
                _change(report, older, "active", "stale", older.stale_reason)
            continue
        seen[key] = memory


def run_memory_hygiene(
    session: Session,
    *,
    now: datetime | None = None,
    dry_run: bool = False,
    scope: dict[str, Any] | None = None,
) -> HygieneReport:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    report = HygieneReport()
    stmt = select(UserMemory)
    if scope:
        if scope.get("user_id"):
            stmt = stmt.where(UserMemory.user_id == scope["user_id"])
        if scope.get("scope_type"):
            stmt = stmt.where(UserMemory.scope_type == str(scope["scope_type"]))
        if scope.get("scope_id"):
            stmt = stmt.where(UserMemory.scope_id == str(scope["scope_id"]))
    memories = list(session.execute(stmt).scalars().all())
    report.scanned_count = len(memories)

    try:
        _detect_conflicts(memories, report)
        for memory in memories:
            if memory.lifecycle_state == "soft_deleted":
                continue
            if not memory.memory_type or memory.memory_type == "unknown":
                memory.memory_type = classify_memory_type(memory.fact, {"source": "durable.user_memory"})
            if memory.memory_type in {"secret_blocked", "do_not_store"}:
                old = memory.lifecycle_state
                memory.lifecycle_state = "delete_proposed"
                memory.delete_proposed_at = now
                memory.delete_proposed_reason = "Unsafe memory type discovered during hygiene"
                memory.updated_at = now
                report.proposed_delete_count += 1
                _change(report, memory, old, "delete_proposed", memory.delete_proposed_reason)
                continue
            if memory.pinned:
                report.skipped_pinned_count += 1
                continue
            if memory.memory_type in _PROTECTED_TYPES and not memory.deprecated_by:
                report.skipped_protected_count += 1
                continue
            stale_days, archive_days, propose_days = _policy_days(memory.memory_type or "unknown")
            last_activity = _last_activity(memory)
            unused_days = (now - last_activity).days
            if memory.lifecycle_state == "active" and stale_days is not None and unused_days >= stale_days:
                old = memory.lifecycle_state
                memory.lifecycle_state = "stale"
                memory.stale_reason = f"Unused for {unused_days} days"
                memory.updated_at = now
                report.marked_stale_count += 1
                _change(report, memory, old, "stale", memory.stale_reason)
            if memory.lifecycle_state == "stale" and archive_days is not None and unused_days >= archive_days:
                old = memory.lifecycle_state
                memory.lifecycle_state = "archived"
                memory.archived_at = now
                memory.updated_at = now
                report.archived_count += 1
                _change(report, memory, old, "archived", f"Unused for {unused_days} days")
            archive_age = (now - _aware(memory.archived_at)).days if memory.archived_at else unused_days
            if (
                memory.lifecycle_state == "archived"
                and propose_days is not None
                and memory.memory_type in _LOW_RISK_TYPES
                and archive_age >= propose_days
            ):
                old = memory.lifecycle_state
                reason = f"Archived and unused for {archive_age} days"
                memory.lifecycle_state = "delete_proposed"
                memory.delete_proposed_at = now
                memory.delete_proposed_reason = reason
                memory.updated_at = now
                report.proposed_delete_count += 1
                _change(report, memory, old, "delete_proposed", reason)
        if dry_run:
            session.rollback()
        else:
            session.add_all(memories)
            session.commit()
            for change in report.changed_memory_ids:
                if change.new_state == "delete_proposed":
                    try:
                        propose_delete_memory(
                            session,
                            memory_id=uuid.UUID(change.memory_id),
                            reason=change.reason,
                        )
                    except Exception:
                        pass
    except Exception as exc:
        session.rollback()
        report.errors.append(str(exc))
    return report


def run_weekly_memory_hygiene_job(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    report = run_memory_hygiene(session, now=now, dry_run=False)
    return {"cadence": "weekly", **report.as_dict()}


def run_monthly_memory_cleanup_proposal_job(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    report = run_memory_hygiene(session, now=now, dry_run=False)
    return {"cadence": "monthly", **report.as_dict()}
