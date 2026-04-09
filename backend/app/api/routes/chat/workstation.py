"""
Workstation overview endpoint.

GET /workstation/overview — consolidated dashboard data for the Workstation UI:
  - current model stack with friendly labels
  - all guardian tasks for the current user (across all rooms)
  - recent meeting rooms (meeting_mode_enabled=True)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentChatUser, SessionDep
from app.models import ChatRoom, ChatRoomMember
from app.services.guardian import task_guardian as tg
from app.api.routes.chat.llm import get_model_stack, model_label

router = APIRouter(tags=["workstation"])


@router.get("/workstation/overview")
def get_workstation_overview(
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict[str, Any]:
    """Return stack, guardian tasks, and recent meetings for the Workstation dashboard."""
    # Model stack + friendly labels
    stack = get_model_stack()
    stack_labels = {k: model_label(v) if v else "" for k, v in stack.items()}

    # All guardian tasks for this user across all rooms
    tasks = tg.list_tasks_by_user(user_id=str(current_user.id), limit=50)

    # Recent meeting rooms the user belongs to
    stmt = (
        select(ChatRoom)
        .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
        .where(ChatRoomMember.user_id == current_user.id)
        .where(ChatRoom.meeting_mode_enabled.is_(True))
        .order_by(ChatRoom.updated_at.desc())
        .limit(20)
    )
    meeting_rooms = list(session.execute(stmt).scalars().all())

    return {
        "stack": stack,
        "stack_labels": stack_labels,
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "tool_name": t.tool_name,
                "schedule": t.schedule,
                "enabled": bool(t.enabled),
                "room_id": t.room_id,
                "last_status": t.last_status,
                "last_run_at": t.last_run_at,
                "next_run_at": t.next_run_at,
                "last_message": t.last_message,
                "consecutive_failures": t.consecutive_failures or 0,
            }
            for t in tasks
        ],
        "meetings": [
            {
                "id": str(r.id),
                "name": r.name,
                "description": r.description,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in meeting_rooms
        ],
    }
