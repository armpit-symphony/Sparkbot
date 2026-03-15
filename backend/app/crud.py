"""
CRUD operations for the application.

Includes base template CRUD and chat-specific operations.
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select
from sqlmodel import Session, delete

from app.core.security import get_password_hash, verify_password
from app.models import (
    AuditLog,
    ChatMeetingArtifact,
    ChatMessage,
    ChatRoom,
    ChatRoomInvite,
    ChatRoomMember,
    ChatTask,
    ChatUser,
    Item,
    ItemCreate,
    MeetingArtifactType,
    Reminder,
    ReminderRecurrence,
    ReminderStatus,
    RoomRole,
    TaskStatus,
    User,
    UserCreate,
    UserMemory,
    UserUpdate,
    UserType,
)


# ============== Base Template CRUD ==============

def create_user(*, session: Session, user_create: UserCreate) -> User:
    db_obj = User.model_validate(
        user_create, update={"hashed_password": get_password_hash(user_create.password)}
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.execute(statement).scalar_one_or_none()
    return session_user


# Dummy hash to use for timing attack prevention when user is not found
# This is an Argon2 hash of a random password, used to ensure constant-time comparison
DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        # Prevent timing attacks by running password verification even when user doesn't exist
        # This ensures the response time is similar whether or not the email exists
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, db_user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        db_user.hashed_password = updated_password_hash
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    return db_user


def create_item(*, session: Session, item_in: ItemCreate, owner_id: uuid.UUID) -> Item:
    db_item = Item.model_validate(item_in, update={"owner_id": owner_id})
    session.add(db_item)
    session.commit()
    session.refresh(db_item)
    return db_item


# ============== Chat User CRUD ==============

def get_chat_user_by_id(session: Session, user_id: uuid.UUID) -> Optional[ChatUser]:
    return session.get(ChatUser, user_id)


def get_chat_user_by_username(session: Session, username: str) -> Optional[ChatUser]:
    return session.execute(select(ChatUser).where(ChatUser.username == username)).scalar_one_or_none()


def get_chat_user_by_slug(session: Session, slug: str) -> Optional[ChatUser]:
    return session.execute(select(ChatUser).where(ChatUser.bot_slug == slug)).scalar_one_or_none()


def create_chat_user(
    session: Session,
    username: str,
    password: Optional[str] = None,
    user_type: str = "HUMAN",
    **kwargs,
) -> ChatUser:
    user = ChatUser(
        username=username,
        hashed_password=get_password_hash(password) if password else None,
        type=user_type,
        **kwargs,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def create_chat_bot_user(
    session: Session,
    username: str,
    slug: str,
    display_name: str,
    service_key: str,
    **kwargs,
) -> ChatUser:
    user = ChatUser(
        username=username,
        hashed_password=None,  # Bots use service key auth
        type="BOT",
        bot_slug=slug,
        bot_display_name=display_name,
        bot_service_key_hash=get_password_hash(service_key),
        **kwargs,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_chat_user(session: Session, username: str, password: str) -> Optional[ChatUser]:
    user = get_chat_user_by_username(session, username)
    if not user:
        return None
    if not user.hashed_password:
        return None
    verified, _ = verify_password(password, user.hashed_password)
    if not verified:
        return None
    return user


# ============== Chat Room CRUD ==============

def get_chat_room_by_id(session: Session, room_id: uuid.UUID) -> Optional[ChatRoom]:
    return session.get(ChatRoom, room_id)


def default_dm_execution_allowed(room_name: str) -> bool:
    name = (room_name or "").strip().lower()
    if name != "sparkbot dm":
        return False
    return os.getenv("SPARKBOT_DM_EXECUTION_DEFAULT", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def create_chat_room(
    session: Session,
    name: str,
    created_by: uuid.UUID,
    description: Optional[str] = None,
) -> ChatRoom:
    room = ChatRoom(
        name=name,
        description=description,
        created_by=created_by,
        execution_allowed=default_dm_execution_allowed(name),
    )
    session.add(room)
    session.commit()
    session.refresh(room)
    
    # Auto-add creator as OWNER
    add_chat_room_member(session, room.id, created_by, role="OWNER")

    try:
        from app.services.guardian.spine import emit_room_lifecycle_event

        emit_room_lifecycle_event(
            room_id=str(room.id),
            actor_id=str(created_by),
            event_type="room.created",
            room_name=room.name,
            description=room.description,
        )
    except Exception:
        pass
    
    return room


def get_user_chat_rooms(session: Session, user_id: uuid.UUID) -> list[ChatRoom]:
    statement = (
        select(ChatRoom)
        .join(ChatRoomMember, ChatRoomMember.room_id == ChatRoom.id)
        .where(ChatRoomMember.user_id == user_id)
        .order_by(ChatRoom.updated_at.desc())
    )
    return list(session.execute(statement).scalars().all())


# ============== Chat Room Member CRUD ==============

def add_chat_room_member(
    session: Session,
    room_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str = "MEMBER",
) -> ChatRoomMember:
    # Check if already a member
    existing = get_chat_room_member(session, room_id, user_id)
    if existing:
        return existing
    
    member = ChatRoomMember(
        room_id=room_id,
        user_id=user_id,
        role=RoomRole(role),
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return member


def get_chat_room_member(session: Session, room_id: uuid.UUID, user_id: uuid.UUID) -> Optional[ChatRoomMember]:
    # Use scalars().first() instead of scalar_one_or_none() to be robust against
    # any duplicate rows that may exist from a prior double-insert bug.
    return session.execute(
        select(ChatRoomMember)
        .where(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
    ).scalars().first()


def get_chat_room_members(session: Session, room_id: uuid.UUID) -> list[ChatRoomMember]:
    return list(
        session.execute(
            select(ChatRoomMember)
            .where(ChatRoomMember.room_id == room_id)
            .order_by(ChatRoomMember.joined_at)
        ).scalars().all()
    )


def remove_chat_room_member(session: Session, room_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Remove a member from a chat room. Returns True if removed, False if not found."""
    member = session.execute(
        select(ChatRoomMember)
        .where(ChatRoomMember.room_id == room_id, ChatRoomMember.user_id == user_id)
    ).scalar_one_or_none()
    
    if member:
        session.delete(member)
        session.commit()
        return True
    return False


# ============== Chat Message CRUD ==============

def create_chat_message(
    session: Session,
    room_id: uuid.UUID,
    sender_id: uuid.UUID,
    content: str,
    sender_type: str = "HUMAN",
    reply_to_id: Optional[uuid.UUID] = None,
    meta_json: Optional[dict] = None,
) -> ChatMessage:
    message = ChatMessage(
        room_id=room_id,
        sender_id=sender_id,
        sender_type=UserType(sender_type),
        content=content,
        reply_to_id=reply_to_id,
        meta_json=meta_json,
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    
    # Update room's updated_at
    room = get_chat_room_by_id(session, room_id)
    if room:
        room.updated_at = datetime.now(timezone.utc)
        session.add(room)
        session.commit()

    try:
        from app.services.guardian.spine import capture_message, emit_worker_status_event

        sender = get_chat_user_by_id(session, sender_id)
        capture_message(
            session=session,
            message=message,
            room_name=room.name if room else str(room_id),
            sender_username=sender.username if sender else None,
        )
        if sender and sender.type == UserType.BOT and sender.username and sender.username.startswith("agent_"):
            emit_worker_status_event(
                room_id=str(room_id),
                actor_id=str(sender_id),
                worker_name=sender.username.removeprefix("agent_"),
                source_ref=f"room-{room_id}-msg-{message.id}",
                status_text=content,
                session=session,
            )
    except Exception:
        pass
    
    return message


def get_chat_messages(
    session: Session,
    room_id: uuid.UUID,
    before: Optional[datetime] = None,
    limit: int = 50,
) -> tuple[list[ChatMessage], int, bool]:
    """Get messages for a room, optionally paginated."""
    # Build query
    query = select(ChatMessage).where(ChatMessage.room_id == room_id)
    
    if before:
        query = query.where(ChatMessage.created_at < before)
    
    # Get total count - properly extract integer from row
    count_result = session.execute(select(func.count()).select_from(query.subquery())).one()
    total = int(count_result[0]) if count_result else 0
    
    # Get messages with proper ORM mapping
    messages = list(
        session.execute(
            query.order_by(ChatMessage.created_at.desc())
            .limit(limit + 1)  # Fetch one extra to check has_more
        ).scalars().all()
    )
    
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]
    
    # Reverse to get chronological order
    messages.reverse()
    
    return messages, total, has_more


def get_chat_message_by_id(session: Session, message_id: uuid.UUID) -> Optional[ChatMessage]:
    return session.get(ChatMessage, message_id)


# ============== Chat Room Invite CRUD ==============

def create_chat_room_invite(
    session: Session,
    room_id: uuid.UUID,
    created_by: uuid.UUID,
    role: str = "MEMBER",
    usage_limit: Optional[int] = None,
    expires_at: Optional[datetime] = None,
) -> tuple[ChatRoomInvite, str]:
    # Generate token and hash it
    import secrets
    token = secrets.token_urlsafe(32)
    token_hash = get_password_hash(token)
    
    invite = ChatRoomInvite(
        room_id=room_id,
        token_hash=token_hash,
        created_by=created_by,
        role=RoomRole(role),
        usage_limit=usage_limit,
        expires_at=expires_at,
    )
    session.add(invite)
    session.commit()
    session.refresh(invite)
    
    # Return invite with the raw token (only time it's available)
    return invite, token


def validate_chat_invite_token(
    session: Session,
    room_id: uuid.UUID,
    token: str,
) -> Optional[ChatRoomInvite]:
    invites = list(
        session.execute(
            select(ChatRoomInvite)
            .where(ChatRoomInvite.room_id == room_id)
            .where(ChatRoomInvite.used_count < (ChatRoomInvite.usage_limit or 999999))
            .where(
                (ChatRoomInvite.expires_at.is_(None)) | 
                (ChatRoomInvite.expires_at > datetime.now(timezone.utc))
            )
        ).scalars().all()
    )
    
    for invite in invites:
        verified, _ = verify_password(token, invite.token_hash)
        if verified:
            return invite
    
    return None


def use_chat_invite(session: Session, invite: ChatRoomInvite) -> bool:
    """Increment usage count if within limits."""
    if invite.usage_limit and invite.used_count >= invite.usage_limit:
        return False
    
    invite.used_count += 1
    session.add(invite)
    session.commit()
    return True


def delete_expired_chat_invites(session: Session) -> int:
    """Delete expired invites and return count."""
    result = session.execute(
        delete(ChatRoomInvite).where(
            and_(
                ChatRoomInvite.expires_at.isnot(None),
                ChatRoomInvite.expires_at < datetime.now(timezone.utc),
            )
        )
    )
    session.commit()
    return result.rowcount


# ============== Chat Meeting Artifact CRUD ==============

def create_chat_meeting_artifact(
    session: Session,
    room_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    type: str,
    content_markdown: str,
    window_start_ts: Optional[datetime] = None,
    window_end_ts: Optional[datetime] = None,
    meta_json: Optional[dict] = None,
) -> ChatMeetingArtifact:
    artifact = ChatMeetingArtifact(
        room_id=room_id,
        created_by_user_id=created_by_user_id,
        type=MeetingArtifactType(type),
        content_markdown=content_markdown,
        window_start_ts=window_start_ts,
        window_end_ts=window_end_ts,
        meta_json=meta_json,
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)
    try:
        from app.services.guardian.spine import capture_meeting_artifact
        from app.services.guardian.spine import emit_meeting_output_event

        room = get_chat_room_by_id(session, room_id)
        creator = get_chat_user_by_id(session, created_by_user_id)
        capture_meeting_artifact(
            session=session,
            artifact=artifact,
            room_name=room.name if room else str(room_id),
            created_by_username=creator.username if creator else None,
        )
        emit_meeting_output_event(
            room_id=str(room_id),
            actor_id=str(created_by_user_id),
            artifact_type=type,
            artifact_id=str(artifact.id),
            content_markdown=content_markdown,
            session=session,
        )
    except Exception:
        pass
    return artifact


def get_chat_meeting_artifacts(
    session: Session,
    room_id: uuid.UUID,
    type: Optional[str] = None,
    limit: int = 50,
) -> list[ChatMeetingArtifact]:
    query = select(ChatMeetingArtifact).where(ChatMeetingArtifact.room_id == room_id)
    
    if type:
        query = query.where(ChatMeetingArtifact.type == MeetingArtifactType(type))
    
    return list(
        session.execute(
            query.order_by(ChatMeetingArtifact.created_at.desc())
            .limit(limit)
        ).scalars().all()
    )


# ─── User Memory CRUD ─────────────────────────────────────────────────────────

def get_user_memories(session: Session, user_id: uuid.UUID) -> list[UserMemory]:
    return list(
        session.execute(
            select(UserMemory)
            .where(UserMemory.user_id == user_id)
            .order_by(UserMemory.created_at.asc())
        ).scalars().all()
    )


def add_user_memory(session: Session, user_id: uuid.UUID, fact: str) -> UserMemory:
    mem = UserMemory(user_id=user_id, fact=fact.strip())
    session.add(mem)
    session.commit()
    session.refresh(mem)
    return mem


def delete_user_memory(session: Session, memory_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    mem = session.get(UserMemory, memory_id)
    if not mem or mem.user_id != user_id:
        return False
    session.delete(mem)
    session.commit()
    return True


def clear_user_memories(session: Session, user_id: uuid.UUID) -> int:
    mems = get_user_memories(session, user_id)
    count = len(mems)
    for m in mems:
        session.delete(m)
    session.commit()
    return count


# ─── Task CRUD ─────────────────────────────────────────────────────────────────

def create_task(
    session: Session,
    room_id: uuid.UUID,
    created_by: uuid.UUID,
    title: str,
    description: Optional[str] = None,
    assigned_to: Optional[uuid.UUID] = None,
    due_date: Optional[datetime] = None,
) -> ChatTask:
    task = ChatTask(
        room_id=room_id,
        created_by=created_by,
        title=title.strip(),
        description=description.strip() if description else None,
        assigned_to=assigned_to,
        due_date=due_date,
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    # Canonical task lifecycle writes should go through the Spine-backed adapter.
    from app.services.guardian.task_master_adapter import task_master_spine

    task_master_spine.register_created_task(
        session=session,
        task=task,
        actor_id=str(created_by),
        summary=description or title,
    )
    return task


def get_tasks(
    session: Session,
    room_id: uuid.UUID,
    status: Optional[TaskStatus] = None,
) -> list[ChatTask]:
    q = select(ChatTask).where(ChatTask.room_id == room_id)
    if status is not None:
        q = q.where(ChatTask.status == status)
    q = q.order_by(ChatTask.created_at.asc())
    return list(session.execute(q).scalars().all())


def get_task(session: Session, task_id: uuid.UUID) -> Optional[ChatTask]:
    return session.get(ChatTask, task_id)


def complete_task(session: Session, task_id: uuid.UUID) -> Optional[ChatTask]:
    task = session.get(ChatTask, task_id)
    if not task:
        return None
    from app.services.guardian.task_master_adapter import task_master_spine

    task = task_master_spine.complete_task(
        session=session,
        task=task,
        actor_id=str(task.created_by),
        summary=task.description or task.title,
    )
    return task


def assign_task(
    session: Session, task_id: uuid.UUID, assigned_to: Optional[uuid.UUID]
) -> Optional[ChatTask]:
    task = session.get(ChatTask, task_id)
    if not task:
        return None
    from app.services.guardian.task_master_adapter import task_master_spine

    task = task_master_spine.assign_existing_task(
        session=session,
        task=task,
        assigned_to=assigned_to,
        actor_id=str(task.created_by),
        summary=task.description or task.title,
    )
    return task


def delete_task(session: Session, task_id: uuid.UUID, *, actor_id: uuid.UUID | None = None) -> bool:
    task = session.get(ChatTask, task_id)
    if not task:
        return False
    from app.services.guardian.task_master_adapter import task_master_spine

    task_master_spine.archive_deleted_task(
        session=session,
        task=task,
        actor_id=str(actor_id or task.created_by),
        summary=task.description or task.title,
    )
    session.delete(task)
    session.commit()
    return True


# ─── Reminder CRUD ─────────────────────────────────────────────────────────────

def create_reminder(
    session: Session,
    room_id: uuid.UUID,
    created_by: uuid.UUID,
    message: str,
    fire_at: datetime,
    recurrence: ReminderRecurrence = ReminderRecurrence.ONCE,
) -> Reminder:
    reminder = Reminder(
        room_id=room_id,
        created_by=created_by,
        message=message.strip(),
        fire_at=fire_at,
        recurrence=recurrence,
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder


def get_room_reminders(
    session: Session,
    room_id: uuid.UUID,
    status: Optional[ReminderStatus] = ReminderStatus.PENDING,
) -> list[Reminder]:
    q = select(Reminder).where(Reminder.room_id == room_id)
    if status is not None:
        q = q.where(Reminder.status == status)
    q = q.order_by(Reminder.fire_at.asc())
    return list(session.execute(q).scalars().all())


def get_due_reminders(session: Session, now: datetime) -> list[Reminder]:
    """Return all pending reminders whose fire_at is at or before now."""
    return list(
        session.execute(
            select(Reminder)
            .where(Reminder.status == ReminderStatus.PENDING)
            .where(Reminder.fire_at <= now)
            .order_by(Reminder.fire_at.asc())
        ).scalars().all()
    )


def fire_reminder(session: Session, reminder_id: uuid.UUID) -> Optional[Reminder]:
    """Mark a reminder fired. Reschedule if recurring, else mark done."""
    from datetime import timedelta
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        return None

    if reminder.recurrence == ReminderRecurrence.DAILY:
        reminder.fire_at = reminder.fire_at + timedelta(days=1)
        # keep status PENDING for next fire
    elif reminder.recurrence == ReminderRecurrence.WEEKLY:
        reminder.fire_at = reminder.fire_at + timedelta(weeks=1)
    else:
        reminder.status = ReminderStatus.FIRED

    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder


def cancel_reminder(session: Session, reminder_id: uuid.UUID) -> bool:
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        return False
    reminder.status = ReminderStatus.CANCELLED
    session.add(reminder)
    session.commit()
    return True


# ─── Audit log CRUD ───────────────────────────────────────────────────────────

def create_audit_log(
    session: Session,
    tool_name: str,
    tool_input: str,
    tool_result: str,
    user_id: Optional[uuid.UUID] = None,
    room_id: Optional[uuid.UUID] = None,
    agent_name: Optional[str] = None,
    model: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        room_id=room_id,
        tool_name=tool_name,
        tool_input=tool_input[:2000],
        tool_result=tool_result[:1000],
        agent_name=agent_name,
        model=model,
    )
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def get_audit_logs(
    session: Session,
    limit: int = 20,
    offset: int = 0,
    tool_name: Optional[str] = None,
    user_id: Optional[uuid.UUID] = None,
    room_id: Optional[uuid.UUID] = None,
) -> tuple[list[AuditLog], int]:
    stmt = select(AuditLog)
    if tool_name:
        stmt = stmt.where(AuditLog.tool_name == tool_name)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if room_id:
        stmt = stmt.where(AuditLog.room_id == room_id)

    total: int = session.exec(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = session.execute(
        stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return list(rows), int(total)
