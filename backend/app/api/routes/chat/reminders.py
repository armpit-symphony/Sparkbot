"""
Proactive reminders — background scheduler + REST API.

The scheduler runs as an asyncio background task started during FastAPI lifespan.
Every 60 s it checks for pending reminders whose fire_at <= now, writes a bot
message to the DB, broadcasts via WebSocket, then marks the reminder fired
(or reschedules it if it's recurring).

REST API:
  GET    /chat/rooms/{room_id}/reminders           — list pending reminders
  POST   /chat/rooms/{room_id}/reminders           — create a reminder
  DELETE /chat/rooms/{room_id}/reminders/{id}      — cancel a reminder
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlmodel import Session

from app.api.deps import CurrentChatUser, SessionDep, get_db
from app.crud import (
    cancel_reminder,
    create_chat_message,
    create_reminder,
    fire_reminder,
    get_chat_room_member,
    get_due_reminders,
    get_room_reminders,
)
from app.models import ChatUser, Reminder, ReminderRecurrence, ReminderStatus, UserType

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat-reminders"])

POLL_INTERVAL_SECONDS = 60


# ─── Background scheduler ─────────────────────────────────────────────────────

async def _fire_one(reminder: Reminder, session: Session) -> None:
    """Write the bot message to DB and broadcast via WebSocket."""
    try:
        # Find or create the sparkbot bot user
        bot_user = session.exec(
            select(ChatUser).where(ChatUser.username == "sparkbot")
        ).scalar_one_or_none()
        if not bot_user:
            bot_user = ChatUser(
                username="sparkbot",
                type=UserType.BOT,
                hashed_password="",
            )
            session.add(bot_user)
            session.commit()
            session.refresh(bot_user)

        msg = create_chat_message(
            session=session,
            room_id=reminder.room_id,
            sender_id=bot_user.id,
            content=f"⏰ **Reminder:** {reminder.message}",
            sender_type="BOT",
        )
        msg_id = str(msg.id)
        session.close()

        # Broadcast to any connected WebSocket clients
        try:
            from app.api.routes.chat.websocket import ws_manager
            await ws_manager.broadcast(
                str(reminder.room_id),
                {
                    "type": "message",
                    "payload": {
                        "id": msg_id,
                        "room_id": str(reminder.room_id),
                        "content": f"⏰ **Reminder:** {reminder.message}",
                        "sender_type": "BOT",
                        "sender": {"username": "sparkbot"},
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                },
            )
        except Exception as ws_err:
            logger.debug(f"[reminders] WS broadcast skipped: {ws_err}")

        logger.info(f"[reminders] Fired reminder {reminder.id}: {reminder.message[:60]}")
    except Exception as e:
        logger.error(f"[reminders] Failed to fire {reminder.id}: {e}")


async def reminder_scheduler() -> None:
    """Background asyncio task — polls DB every POLL_INTERVAL_SECONDS."""
    logger.info("[reminders] Scheduler started")
    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            now = datetime.now(timezone.utc)
            db = next(get_db())
            try:
                due = get_due_reminders(db, now)
                for reminder in due:
                    await _fire_one(reminder, next(get_db()))
                    # Reschedule or mark fired in a fresh session
                    mark_db = next(get_db())
                    fire_reminder(mark_db, reminder.id)
                    mark_db.close()
            finally:
                db.close()
        except asyncio.CancelledError:
            logger.info("[reminders] Scheduler stopped")
            return
        except Exception as e:
            logger.error(f"[reminders] Scheduler error: {e}")


# ─── REST API ──────────────────────────────────────────────────────────────────

class ReminderResponse(BaseModel):
    id: str
    room_id: str
    created_by: str
    message: str
    fire_at: str
    recurrence: str
    status: str
    created_at: str


def _fmt(r: Reminder) -> ReminderResponse:
    return ReminderResponse(
        id=str(r.id),
        room_id=str(r.room_id),
        created_by=str(r.created_by),
        message=r.message,
        fire_at=r.fire_at.isoformat(),
        recurrence=r.recurrence.value if hasattr(r.recurrence, "value") else str(r.recurrence),
        status=r.status.value if hasattr(r.status, "value") else str(r.status),
        created_at=r.created_at.isoformat(),
    )


class ReminderCreate(BaseModel):
    message: str
    fire_at: str           # ISO 8601 UTC datetime
    recurrence: str = "once"   # once | daily | weekly


@router.get("/rooms/{room_id}/reminders", response_model=dict)
def list_room_reminders(
    room_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    status: str = "pending",
) -> Any:
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    status_map = {
        "pending": ReminderStatus.PENDING,
        "fired": ReminderStatus.FIRED,
        "cancelled": ReminderStatus.CANCELLED,
        "all": None,
    }
    if status not in status_map:
        raise HTTPException(status_code=400, detail="status must be pending, fired, cancelled, or all")

    reminders = get_room_reminders(session, room_id, status=status_map[status])
    return {"reminders": [_fmt(r) for r in reminders], "count": len(reminders)}


@router.post("/rooms/{room_id}/reminders", response_model=ReminderResponse)
def create_room_reminder(
    room_id: uuid.UUID,
    reminder_in: ReminderCreate,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> Any:
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    try:
        dt = datetime.fromisoformat(reminder_in.fire_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid fire_at — use ISO 8601 format")

    rec_map = {
        "once": ReminderRecurrence.ONCE,
        "daily": ReminderRecurrence.DAILY,
        "weekly": ReminderRecurrence.WEEKLY,
    }
    recurrence = rec_map.get(reminder_in.recurrence, ReminderRecurrence.ONCE)

    reminder = create_reminder(
        session=session,
        room_id=room_id,
        created_by=current_user.id,
        message=reminder_in.message,
        fire_at=dt,
        recurrence=recurrence,
    )
    return _fmt(reminder)


@router.delete("/rooms/{room_id}/reminders/{reminder_id}")
def cancel_room_reminder(
    room_id: uuid.UUID,
    reminder_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> dict:
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    reminder = session.get(Reminder, reminder_id)
    if not reminder or reminder.room_id != room_id:
        raise HTTPException(status_code=404, detail="Reminder not found")

    cancel_reminder(session, reminder_id)
    return {"cancelled": str(reminder_id)}
