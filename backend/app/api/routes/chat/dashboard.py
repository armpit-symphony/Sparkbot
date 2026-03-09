from __future__ import annotations

import json
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentChatUser, SessionDep
from app.crud import create_audit_log, create_chat_message, get_chat_room_by_id, get_chat_room_member, get_user_chat_rooms
from app.models import AuditLog, ChatMeetingArtifact, ChatTask, Reminder, ReminderStatus, RoomRole, TaskStatus, ChatUser, UserType
from app.services.guardian.pending_approvals import get_pending_approval, list_pending_approvals
from app.services.guardian.task_guardian import TASK_GUARDIAN_ENABLED, list_tasks as list_guardian_tasks
from app.services.guardian.token_guardian import get_token_guardian_stats

router = APIRouter(tags=["chat-dashboard"])


class DashboardRoomItem(BaseModel):
    id: str
    name: str
    execution_allowed: bool
    updated_at: str


class DashboardReminderItem(BaseModel):
    id: str
    room_id: str
    room_name: str
    message: str
    fire_at: str
    recurrence: str


class DashboardTaskItem(BaseModel):
    id: str
    room_id: str
    room_name: str
    title: str
    status: str
    due_date: str | None
    assigned_to: str | None


class DashboardApprovalItem(BaseModel):
    id: str
    room_id: str | None
    room_name: str
    created_at: str
    expires_at: str
    tool_name: str
    reason: str
    tool_args_preview: str


class DashboardGuardianTaskItem(BaseModel):
    id: str
    room_id: str
    room_name: str
    name: str
    tool_name: str
    schedule: str
    enabled: bool
    next_run_at: str | None
    last_status: str | None


class DashboardMeetingItem(BaseModel):
    id: str
    room_id: str
    room_name: str
    type: str
    created_at: str
    excerpt: str


class DashboardInboxSummary(BaseModel):
    configured: bool
    source: str
    summary_text: str


class DashboardTokenGuardianSummary(BaseModel):
    mode: str
    live_ready: bool
    configured_models: list[str]
    allowed_live_models: list[str]
    total_tokens: int
    total_cost: float
    requests: int
    live_routes_24h: int
    suggested_switches_24h: int
    estimated_savings_24h: float
    top_models: list[dict[str, Any]]
    last_route: dict[str, Any] | None = None


class DashboardSummary(BaseModel):
    rooms_count: int
    execution_enabled_rooms: int
    open_tasks: int
    tasks_due_today: int
    pending_reminders: int
    reminders_due_today: int
    pending_approvals: int
    guardian_jobs: int
    guardian_jobs_enabled: int
    task_guardian_enabled: bool
    token_guardian_mode: str


class DashboardToday(BaseModel):
    rooms: list[DashboardRoomItem]
    upcoming_reminders: list[DashboardReminderItem]
    focus_tasks: list[DashboardTaskItem]
    approval_requests: list[DashboardApprovalItem]
    guardian_jobs: list[DashboardGuardianTaskItem]
    meetings: list[DashboardMeetingItem]
    inbox: DashboardInboxSummary
    token_guardian: DashboardTokenGuardianSummary


class DashboardSummaryResponse(BaseModel):
    generated_at: str
    summary: DashboardSummary
    today: DashboardToday


class ApprovalActionResponse(BaseModel):
    confirm_id: str
    status: str
    tool_name: str
    room_id: str | None = None
    result: str


def _day_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _iso_from_epoch(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _excerpt(text: str, limit: int = 240) -> str:
    clean = " ".join((text or "").split()).strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "..."


def _approval_preview(tool_args_json: str) -> str:
    try:
        payload = json.loads(tool_args_json or "{}")
    except Exception:
        payload = tool_args_json
    if isinstance(payload, dict):
        parts = [f"{key}={value}" for key, value in payload.items()]
        return _excerpt(", ".join(parts), 180)
    return _excerpt(str(payload), 180)


def _ensure_approval_access(session: SessionDep, confirm_id: str, current_user: CurrentChatUser):
    pending = get_pending_approval(confirm_id)
    if not pending:
        return None, None, None
    if not pending.room_id:
        return pending, None, None
    try:
        room_uuid = uuid.UUID(pending.room_id)
    except Exception:
        return pending, None, None
    room = get_chat_room_by_id(session, room_uuid)
    membership = get_chat_room_member(session, room_uuid, current_user.id)
    if not room or not membership:
        return pending, room, None
    return pending, room, membership


async def _execute_dashboard_approval(
    *,
    session: SessionDep,
    current_user: CurrentChatUser,
    confirm_id: str,
) -> ApprovalActionResponse:
    from app.api.routes.chat.llm import (
        consume_pending,
        mask_tool_result_for_external,
        redact_tool_call_for_audit,
        serialize_tool_args_for_audit,
    )
    from app.api.routes.chat.tools import execute_tool
    from app.services.guardian.auth import is_operator_identity, is_operator_privileged
    from app.services.guardian.executive import exec_with_guard
    from app.services.guardian.memory import remember_tool_event
    from app.services.guardian.policy import decide_tool_use

    pending = consume_pending(confirm_id)
    if not pending:
        return ApprovalActionResponse(
            confirm_id=confirm_id,
            status="missing",
            tool_name="unknown",
            result="Confirmation expired or invalid.",
        )

    tool_name = str(pending.get("tool") or "unknown")
    tool_args = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    room_id = str(pending.get("room_id") or "")
    room_uuid = None
    if room_id:
        try:
            room_uuid = uuid.UUID(room_id)
        except Exception:
            room_uuid = None
    user_id_str = str(current_user.id)

    room = get_chat_room_by_id(session, room_uuid) if room_uuid else None
    decision = decide_tool_use(
        tool_name,
        tool_args,
        room_execution_allowed=room.execution_allowed if room else None,
        is_operator=is_operator_identity(username=current_user.username, user_type=current_user.type),
        is_privileged=is_operator_privileged(user_id_str),
    )
    create_audit_log(
        session=session,
        tool_name="policy_decision",
        tool_input=json.dumps(
            {
                "tool_name": tool_name,
                "tool_args": json.loads(serialize_tool_args_for_audit(tool_name, tool_args)),
                "confirmed": True,
                "source": "dashboard",
            }
        ),
        tool_result=decision.to_json(),
        user_id=current_user.id,
        room_id=room_uuid,
        model=None,
    )

    if decision.action == "deny":
        result = f"POLICY DENIED: {decision.reason}"
    else:
        result = await exec_with_guard(
            tool_name=tool_name,
            action_type=decision.action_type,
            expected_outcome=f"Confirmed dashboard execution for {tool_name}",
            perform_fn=lambda: execute_tool(
                tool_name,
                tool_args,
                user_id=user_id_str,
                session=session,
                room_id=room_id,
            ),
            metadata={"room_id": room_id, "user_id": user_id_str, "confirmed": True, "source": "dashboard"},
        )

    outward_result = mask_tool_result_for_external(tool_name, tool_args, result)
    redacted_input, redacted_result = redact_tool_call_for_audit(tool_name, tool_args, result)
    create_audit_log(
        session=session,
        tool_name=tool_name,
        tool_input=redacted_input,
        tool_result=redacted_result,
        user_id=current_user.id,
        room_id=room_uuid,
        model=None,
    )
    if room_uuid:
        try:
            remember_tool_event(
                user_id=user_id_str,
                room_id=room_id,
                tool_name=tool_name,
                args=tool_args,
                result=redacted_result,
            )
        except Exception:
            pass

        bot_user = session.exec(
            select(ChatUser).where(ChatUser.username == "sparkbot")
        ).scalar_one_or_none()
        if not bot_user:
            bot_user = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
            session.add(bot_user)
            session.commit()
            session.refresh(bot_user)
        create_chat_message(
            session=session,
            room_id=room_uuid,
            sender_id=bot_user.id,
            content=outward_result,
            sender_type="BOT",
            meta_json={"source": "dashboard", "approved_confirm_id": confirm_id},
        )

    return ApprovalActionResponse(
        confirm_id=confirm_id,
        status="approved",
        tool_name=tool_name,
        room_id=room_id or None,
        result=outward_result,
    )


async def _load_inbox_summary() -> DashboardInboxSummary:
    from app.api.routes.chat.tools import (
        _email_configured_imap,
        _email_fetch_inbox,
        _gmail_fetch_inbox,
        _google_configured,
    )

    try:
        if _google_configured():
            summary = await _gmail_fetch_inbox(max_emails=4, unread_only=True)
            return DashboardInboxSummary(
                configured=True,
                source="gmail",
                summary_text=_excerpt(summary, 1200),
            )
        if _email_configured_imap():
            summary = await _email_fetch_inbox(max_emails=4, unread_only=True)
            return DashboardInboxSummary(
                configured=True,
                source="imap",
                summary_text=_excerpt(summary, 1200),
            )
    except Exception as exc:
        return DashboardInboxSummary(
            configured=True,
            source="error",
            summary_text=f"Inbox widget error: {exc}",
        )

    return DashboardInboxSummary(
        configured=False,
        source="none",
        summary_text="Inbox integrations are not configured yet.",
    )


def _build_token_guardian_summary(session: SessionDep, room_ids: list[Any], now: datetime) -> DashboardTokenGuardianSummary:
    stats = get_token_guardian_stats()
    audit_window = now - timedelta(hours=24)
    routing_entries = list(
        session.execute(
            select(AuditLog)
            .where(AuditLog.room_id.in_(room_ids))
            .where(AuditLog.tool_name.in_(("tokenguardian_shadow", "tokenguardian_live")))
            .where(AuditLog.created_at >= audit_window)
            .order_by(AuditLog.created_at.desc())
            .limit(200)
        ).scalars().all()
    )

    live_routes_24h = 0
    suggested_switches_24h = 0
    estimated_savings_24h = 0.0
    last_route: dict[str, Any] | None = None
    for entry in routing_entries:
        try:
            payload = json.loads(entry.tool_result or "{}")
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            continue
        if last_route is None:
            last_route = {
                "created_at": entry.created_at.isoformat(),
                "classification": payload.get("classification"),
                "current_model": payload.get("current_model"),
                "selected_model": payload.get("selected_model"),
                "applied_model": payload.get("applied_model"),
                "fallback_reason": payload.get("fallback_reason"),
                "live_routed": bool(payload.get("live_routed")),
                "would_switch_models": bool(payload.get("would_switch_models")),
            }
        if payload.get("would_switch_models"):
            suggested_switches_24h += 1
        if payload.get("live_routed"):
            live_routes_24h += 1
        try:
            estimated_savings_24h += float(payload.get("estimated_savings") or 0.0)
        except Exception:
            pass

    top_models = sorted(
        (
            {"model": model, "tokens": tokens}
            for model, tokens in (stats.get("by_model") or {}).items()
        ),
        key=lambda item: item["tokens"],
        reverse=True,
    )[:5]

    return DashboardTokenGuardianSummary(
        mode=str(stats.get("mode") or "off"),
        live_ready=bool(stats.get("live_ready")),
        configured_models=list(stats.get("configured_models") or []),
        allowed_live_models=list(stats.get("allowed_live_models") or []),
        total_tokens=int(stats.get("total_tokens") or 0),
        total_cost=round(float(stats.get("total_cost") or 0.0), 6),
        requests=int(stats.get("requests") or 0),
        live_routes_24h=live_routes_24h,
        suggested_switches_24h=suggested_switches_24h,
        estimated_savings_24h=round(estimated_savings_24h, 6),
        top_models=top_models,
        last_route=last_route,
    )


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary(
    session: SessionDep,
    current_user: CurrentChatUser,
) -> DashboardSummaryResponse:
    now = datetime.now(timezone.utc)
    _, end_of_day = _day_bounds(now)

    rooms = get_user_chat_rooms(session, current_user.id)
    room_ids = [room.id for room in rooms]
    room_id_strings = [str(room.id) for room in rooms]
    room_name_map = {str(room.id): room.name for room in rooms}

    room_items = [
        DashboardRoomItem(
            id=str(room.id),
            name=room.name,
            execution_allowed=bool(room.execution_allowed),
            updated_at=room.updated_at.isoformat(),
        )
        for room in rooms[:6]
    ]

    if not room_ids:
        token_guardian = DashboardTokenGuardianSummary(
            mode=get_token_guardian_stats().get("mode", "off"),
            live_ready=bool(get_token_guardian_stats().get("live_ready")),
            configured_models=list(get_token_guardian_stats().get("configured_models") or []),
            allowed_live_models=list(get_token_guardian_stats().get("allowed_live_models") or []),
            total_tokens=0,
            total_cost=0.0,
            requests=0,
            live_routes_24h=0,
            suggested_switches_24h=0,
            estimated_savings_24h=0.0,
            top_models=[],
            last_route=None,
        )
        session.close()
        inbox = await _load_inbox_summary()
        return DashboardSummaryResponse(
            generated_at=now.isoformat(),
            summary=DashboardSummary(
                rooms_count=0,
                execution_enabled_rooms=0,
                open_tasks=0,
                tasks_due_today=0,
                pending_reminders=0,
                reminders_due_today=0,
                pending_approvals=0,
                guardian_jobs=0,
                guardian_jobs_enabled=0,
                task_guardian_enabled=TASK_GUARDIAN_ENABLED,
                token_guardian_mode=token_guardian.mode,
            ),
            today=DashboardToday(
                rooms=[],
                upcoming_reminders=[],
                focus_tasks=[],
                approval_requests=[],
                guardian_jobs=[],
                meetings=[],
                inbox=inbox,
                token_guardian=token_guardian,
            ),
        )

    open_tasks_count_row = session.exec(
        select(func.count())
        .select_from(ChatTask)
        .where(ChatTask.room_id.in_(room_ids))
        .where(ChatTask.status == TaskStatus.OPEN)
    ).one()
    open_tasks_count = int(open_tasks_count_row[0] if isinstance(open_tasks_count_row, tuple) or hasattr(open_tasks_count_row, "__getitem__") else open_tasks_count_row)
    tasks_due_today_count_row = session.exec(
        select(func.count())
        .select_from(ChatTask)
        .where(ChatTask.room_id.in_(room_ids))
        .where(ChatTask.status == TaskStatus.OPEN)
        .where(ChatTask.due_date.is_not(None))
        .where(ChatTask.due_date < end_of_day)
    ).one()
    tasks_due_today_count = int(tasks_due_today_count_row[0] if isinstance(tasks_due_today_count_row, tuple) or hasattr(tasks_due_today_count_row, "__getitem__") else tasks_due_today_count_row)
    pending_reminders_count_row = session.exec(
        select(func.count())
        .select_from(Reminder)
        .where(Reminder.room_id.in_(room_ids))
        .where(Reminder.status == ReminderStatus.PENDING)
    ).one()
    pending_reminders_count = int(pending_reminders_count_row[0] if isinstance(pending_reminders_count_row, tuple) or hasattr(pending_reminders_count_row, "__getitem__") else pending_reminders_count_row)
    reminders_due_today_count_row = session.exec(
        select(func.count())
        .select_from(Reminder)
        .where(Reminder.room_id.in_(room_ids))
        .where(Reminder.status == ReminderStatus.PENDING)
        .where(Reminder.fire_at < end_of_day)
    ).one()
    reminders_due_today_count = int(reminders_due_today_count_row[0] if isinstance(reminders_due_today_count_row, tuple) or hasattr(reminders_due_today_count_row, "__getitem__") else reminders_due_today_count_row)

    upcoming_reminders = session.exec(
        select(Reminder)
        .where(Reminder.room_id.in_(room_ids))
        .where(Reminder.status == ReminderStatus.PENDING)
        .order_by(Reminder.fire_at.asc())
        .limit(5)
    ).all()
    focus_tasks = session.exec(
        select(ChatTask)
        .where(ChatTask.room_id.in_(room_ids))
        .where(ChatTask.status == TaskStatus.OPEN)
        .order_by(ChatTask.due_date.is_(None), ChatTask.due_date.asc(), ChatTask.created_at.asc())
        .limit(6)
    ).all()
    meeting_artifacts = session.exec(
        select(ChatMeetingArtifact)
        .where(ChatMeetingArtifact.room_id.in_(room_ids))
        .order_by(ChatMeetingArtifact.created_at.desc())
        .limit(5)
    ).all()

    pending_approvals = list_pending_approvals(
        room_ids=room_id_strings,
        limit=8,
    )

    approval_items = [
        DashboardApprovalItem(
            id=item.confirm_id,
            room_id=item.room_id,
            room_name=room_name_map.get(item.room_id or "", "Unknown room"),
            created_at=_iso_from_epoch(item.created_at),
            expires_at=_iso_from_epoch(item.expires_at),
            tool_name=item.tool_name,
            reason="Confirmation required before Sparkbot can execute this action.",
            tool_args_preview=_approval_preview(item.tool_args_json),
        )
        for item in pending_approvals
    ]

    guardian_jobs: list[DashboardGuardianTaskItem] = []
    guardian_jobs_total = 0
    guardian_jobs_enabled = 0
    for room in rooms:
        room_tasks = list_guardian_tasks(room_id=str(room.id), limit=4)
        guardian_jobs_total += len(room_tasks)
        guardian_jobs_enabled += sum(1 for task in room_tasks if bool(task.enabled))
        for task in room_tasks[:2]:
            guardian_jobs.append(
                DashboardGuardianTaskItem(
                    id=task.id,
                    room_id=str(room.id),
                    room_name=room.name,
                    name=task.name,
                    tool_name=task.tool_name,
                    schedule=task.schedule,
                    enabled=bool(task.enabled),
                    next_run_at=task.next_run_at,
                    last_status=task.last_status,
                )
            )
    guardian_jobs = guardian_jobs[:6]

    token_guardian = _build_token_guardian_summary(session, room_ids, now)
    summary = DashboardSummary(
        rooms_count=len(rooms),
        execution_enabled_rooms=sum(1 for room in rooms if room.execution_allowed),
        open_tasks=open_tasks_count,
        tasks_due_today=tasks_due_today_count,
        pending_reminders=pending_reminders_count,
        reminders_due_today=reminders_due_today_count,
        pending_approvals=len(approval_items),
        guardian_jobs=guardian_jobs_total,
        guardian_jobs_enabled=guardian_jobs_enabled,
        task_guardian_enabled=TASK_GUARDIAN_ENABLED,
        token_guardian_mode=token_guardian.mode,
    )
    today = DashboardToday(
        rooms=room_items,
        upcoming_reminders=[
            DashboardReminderItem(
                id=str(reminder.id),
                room_id=str(reminder.room_id),
                room_name=room_name_map.get(str(reminder.room_id), "Unknown room"),
                message=reminder.message,
                fire_at=reminder.fire_at.isoformat(),
                recurrence=reminder.recurrence.value,
            )
            for reminder in upcoming_reminders
        ],
        focus_tasks=[
            DashboardTaskItem(
                id=str(task.id),
                room_id=str(task.room_id),
                room_name=room_name_map.get(str(task.room_id), "Unknown room"),
                title=task.title,
                status=task.status.value,
                due_date=task.due_date.isoformat() if task.due_date else None,
                assigned_to=str(task.assigned_to) if task.assigned_to else None,
            )
            for task in focus_tasks
        ],
        approval_requests=approval_items,
        guardian_jobs=guardian_jobs,
        meetings=[
            DashboardMeetingItem(
                id=str(item.id),
                room_id=str(item.room_id),
                room_name=room_name_map.get(str(item.room_id), "Unknown room"),
                type=item.type.value,
                created_at=item.created_at.isoformat(),
                excerpt=_excerpt(item.content_markdown),
            )
            for item in meeting_artifacts
        ],
        inbox=DashboardInboxSummary(
            configured=False,
            source="loading",
            summary_text="Loading inbox summary...",
        ),
        token_guardian=token_guardian,
    )
    session.close()
    today.inbox = await _load_inbox_summary()

    return DashboardSummaryResponse(
        generated_at=now.isoformat(),
        summary=summary,
        today=today,
    )


@router.post("/dashboard/approvals/{confirm_id}/approve", response_model=ApprovalActionResponse)
async def approve_dashboard_action(
    confirm_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> ApprovalActionResponse:
    pending, room, membership = _ensure_approval_access(session, confirm_id, current_user)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending approval not found")
    if pending.room_id and not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    if membership and membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot approve actions")
    return await _execute_dashboard_approval(
        session=session,
        current_user=current_user,
        confirm_id=confirm_id,
    )


@router.post("/dashboard/approvals/{confirm_id}/deny", response_model=ApprovalActionResponse)
async def deny_dashboard_action(
    confirm_id: str,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> ApprovalActionResponse:
    from app.api.routes.chat.llm import discard_pending

    pending, room, membership = _ensure_approval_access(session, confirm_id, current_user)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending approval not found")
    if pending.room_id and not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    if membership and membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot deny actions")

    discard_pending(confirm_id)
    if room and pending.room_id:
        room_uuid = uuid.UUID(pending.room_id)
        bot_user = session.exec(
            select(ChatUser).where(ChatUser.username == "sparkbot")
        ).scalar_one_or_none()
        if not bot_user:
            bot_user = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
            session.add(bot_user)
            session.commit()
            session.refresh(bot_user)
        create_chat_message(
            session=session,
            room_id=room_uuid,
            sender_id=bot_user.id,
            content=f"Pending action for {pending.tool_name} was denied from the dashboard.",
            sender_type="BOT",
            meta_json={"source": "dashboard", "denied_confirm_id": confirm_id},
        )
    return ApprovalActionResponse(
        confirm_id=confirm_id,
        status="denied",
        tool_name=pending.tool_name,
        room_id=pending.room_id,
        result="Pending action cancelled.",
    )
