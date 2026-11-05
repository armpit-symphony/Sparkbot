"""
Roundtable seats — let outside agents and guest humans join a room.

Why: Sparkbot rooms already support members, roles, invites, meeting mode and
artifacts, but the only login is the single-passphrase ``sparkbot-user``. A
"seat" gives each outside participant (Codex, Claude, another person) their own
identity in a room without handing them the full app.

Flow:
1. A room OWNER/MOD creates a seat:   POST /chat/rooms/{room_id}/seats
   -> returns a one-time seat key (shown once, stored hashed).
2. The participant exchanges the key: POST /chat/seats/token
   -> returns a short-lived, room-scoped bearer token.
3. With that token the seat can only:
   GET  /chat/seats/me
   GET  /chat/seats/rooms/{room_id}/messages?after_id=...
   POST /chat/seats/rooms/{room_id}/messages

Safety boundaries (enforced, and covered by tests):
- Seat tokens carry scope ``roundtable_seat`` and are rejected by every regular
  chat dependency and by the websocket, so a seat cannot reach tools, settings,
  terminal, Vault, connectors or other rooms.
- Seat accounts are never Guardian operators (see guardian/auth.py).
- Posting a message never triggers model calls or tool execution; it is
  stored, labeled with the seat's identity, and broadcast to the room.
- Posts are rate limited per seat. Revoking a seat removes it from the room;
  a seat with no rooms left is deactivated and its key is wiped.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlmodel import col

from app.api.deps import CurrentChatUser, SessionDep
from app.core.config import settings
from app.core.security import (
    ALGORITHM,
    SEAT_TOKEN_SCOPE,
    SEAT_USERNAME_PREFIX,
    get_password_hash,
    verify_password,
)
from app.crud import (
    add_chat_room_member,
    create_audit_log,
    create_chat_message,
    get_chat_room_by_id,
    get_chat_room_member,
    get_chat_user_by_id,
)
from app.models import ChatMessage, ChatRoomMember, ChatUser, RoomRole, UserType
from app.services import roundtable_jobs

router = APIRouter(tags=["roundtable-seats"])

_SEAT_KEY_PREFIX = "rts"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
_MAX_CONTENT = 8000
_MANAGER_ROLES = {RoomRole.OWNER, RoomRole.MOD}

# In-process limits (same approach as chat login rate limiting).
_failed_key_attempts: dict[str, deque[float]] = defaultdict(deque)
_seat_posts: dict[str, deque[float]] = defaultdict(deque)
_KEY_MAX_FAILURES = 10
_KEY_WINDOW_SECONDS = 300


def _token_minutes() -> int:
    try:
        return max(5, int(os.getenv("SPARKBOT_SEAT_TOKEN_MINUTES", "720")))
    except ValueError:
        return 720


def _post_limit_per_minute(seat: ChatUser, room) -> int:
    if seat.type == UserType.BOT:
        if room is not None and room.meeting_mode_enabled:
            return max(1, int(room.meeting_mode_max_bot_msgs_per_min or 3))
        return int(os.getenv("SPARKBOT_SEAT_AGENT_MSGS_PER_MIN", "20"))
    return int(os.getenv("SPARKBOT_SEAT_HUMAN_MSGS_PER_MIN", "60"))


def is_seat_user(user: ChatUser | None) -> bool:
    return user is not None and (user.username or "").startswith(SEAT_USERNAME_PREFIX)


# ── Schemas ───────────────────────────────────────────────────────────────────


class SeatCreateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)
    slug: str = Field(description="Mention handle, e.g. 'codex' -> @codex")
    kind: Literal["agent", "human"] = "agent"


class SeatResponse(BaseModel):
    id: str
    slug: str
    display_name: str
    kind: Literal["agent", "human"]
    active: bool
    role: str | None = None
    created_at: datetime
    # Runner pilot: online / working / offline for agent seats.
    presence: str | None = None
    working_note: str | None = None
    pending_jobs: int = 0
    last_seen_at: datetime | None = None


class SeatCreatedResponse(SeatResponse):
    key: str = Field(
        description="Shown once. Store it in a password manager or env var."
    )


class SeatTokenRequest(BaseModel):
    key: str


class SeatTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    seat: SeatResponse


class SeatRoom(BaseModel):
    id: str
    name: str
    role: str
    meeting_mode_enabled: bool


class SeatMeResponse(BaseModel):
    seat: SeatResponse
    rooms: list[SeatRoom]


class SeatMessage(BaseModel):
    id: str
    room_id: str
    sender_id: str
    sender_type: str
    sender_name: str
    sender_slug: str | None = None
    content: str
    created_at: datetime
    reply_to_id: str | None = None


class SeatPostRequest(BaseModel):
    content: str = Field(min_length=1, max_length=_MAX_CONTENT)
    reply_to_id: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────


def _seat_response(user: ChatUser, role: RoomRole | None = None) -> SeatResponse:
    return SeatResponse(
        id=str(user.id),
        slug=user.bot_slug or user.username.removeprefix(SEAT_USERNAME_PREFIX),
        display_name=user.bot_display_name or user.username,
        kind="agent" if user.type == UserType.BOT else "human",
        active=bool(user.is_active),
        role=role.value if role is not None else None,
        created_at=user.created_at,
    )


def _new_key(user_id: uuid.UUID) -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    return f"{_SEAT_KEY_PREFIX}_{user_id.hex}_{secret}", get_password_hash(secret)


def _require_manager(session, room_id: uuid.UUID, user: ChatUser):
    room = get_chat_room_by_id(session, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    membership = get_chat_room_member(session, room_id, user.id)
    if not membership or membership.role not in _MANAGER_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Only the room owner or a moderator can manage seats",
        )
    return room


def _audit(session, action: str, *, actor_id, room_id, detail: dict) -> None:
    try:
        create_audit_log(
            session=session,
            tool_name=f"roundtable_seat_{action}",
            tool_input=json.dumps(detail),
            tool_result="ok",
            user_id=actor_id,
            room_id=room_id,
            agent_name="roundtable",
        )
    except Exception:
        pass


def _message_out(session, message: ChatMessage, cache: dict) -> SeatMessage:
    sender = cache.get(message.sender_id)
    if sender is None:
        sender = get_chat_user_by_id(session, message.sender_id)
        cache[message.sender_id] = sender
    if sender is None:
        name = "unknown"
    elif sender.bot_display_name:
        name = sender.bot_display_name
    elif sender.username == "sparkbot-user":
        name = "Owner"
    else:
        name = sender.username
    return SeatMessage(
        id=str(message.id),
        room_id=str(message.room_id),
        sender_id=str(message.sender_id),
        sender_type=getattr(message.sender_type, "value", str(message.sender_type)),
        sender_name=name,
        sender_slug=sender.bot_slug if sender else None,
        content=message.content,
        created_at=message.created_at,
        reply_to_id=str(message.reply_to_id) if message.reply_to_id else None,
    )


def _parse_reply_to(
    session, room_id: uuid.UUID, reply_to_id: str | None
) -> uuid.UUID | None:
    if not reply_to_id:
        return None
    try:
        parent = session.get(ChatMessage, uuid.UUID(reply_to_id))
    except ValueError:
        parent = None
    if not parent or parent.room_id != room_id:
        raise HTTPException(
            status_code=400, detail="reply_to_id is not a message in this room"
        )
    return parent.id


async def _store_and_broadcast(
    session,
    room_id: uuid.UUID,
    sender: ChatUser,
    content: str,
    reply_to: uuid.UUID | None,
    meta: dict[str, Any],
) -> SeatMessage:
    """Save a message and push it to the room's websocket listeners. Never calls a model."""
    message = create_chat_message(
        session=session,
        room_id=room_id,
        sender_id=sender.id,
        content=content,
        sender_type=sender.type.value,
        reply_to_id=reply_to,
        meta_json=meta,
    )
    out = _message_out(session, message, {sender.id: sender})
    if sender.type == UserType.HUMAN:
        try:
            roundtable_jobs.handle_human_message(session, message, sender)
        except Exception:  # never lose the message because job bookkeeping failed
            session.rollback()
    try:
        from app.api.routes.chat.websocket import ws_manager

        await ws_manager.broadcast(
            str(room_id),
            {
                "type": "message",
                "message": {
                    **out.model_dump(mode="json"),
                    "sender_username": sender.username,
                    "sender_display_name": sender.bot_display_name,
                },
            },
        )
    except Exception:
        pass
    return out


# ── Seat authentication ───────────────────────────────────────────────────────

_seat_bearer = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/chat/seats/token", auto_error=False
)


def get_current_seat(
    session: SessionDep,
    token: Annotated[str | None, Depends(_seat_bearer)],
) -> ChatUser:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Seat token required"
        )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired seat token",
        )
    if payload.get("scope") != SEAT_TOKEN_SCOPE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not a seat token"
        )
    try:
        user = session.get(ChatUser, uuid.UUID(str(payload.get("sub"))))
    except (ValueError, TypeError):
        user = None
    if not user or not user.is_active or not is_seat_user(user):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Seat revoked or not found"
        )
    return user


CurrentSeat = Annotated[ChatUser, Depends(get_current_seat)]


def _require_seat_member(session, room_id: str, seat: ChatUser):
    try:
        room_uuid = uuid.UUID(room_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid room ID")
    membership = get_chat_room_member(session, room_uuid, seat.id)
    room = get_chat_room_by_id(session, room_uuid) if membership else None
    if not membership or not room:
        # Same answer for "no such room" and "not invited" — don't leak room ids.
        raise HTTPException(status_code=404, detail="Room not found")
    return room, membership


# ── Owner endpoints (normal chat login) ───────────────────────────────────────


@router.post(
    "/rooms/{room_id}/seats", response_model=SeatCreatedResponse, status_code=201
)
def create_seat(
    room_id: uuid.UUID,
    body: SeatCreateRequest,
    session: SessionDep,
    current_user: CurrentChatUser,
):
    room = _require_manager(session, room_id, current_user)
    slug = body.slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=422,
            detail="Slug must be 2-31 chars: lowercase letters, digits, dashes",
        )
    username = f"{SEAT_USERNAME_PREFIX}{slug}"
    taken = (
        session.execute(
            select(ChatUser).where(
                (col(ChatUser.username) == username) | (col(ChatUser.bot_slug) == slug)
            )
        )
        .scalars()
        .first()
    )
    if taken:
        raise HTTPException(status_code=409, detail=f"@{slug} is already taken")

    user = ChatUser(
        username=username,
        type=UserType.BOT if body.kind == "agent" else UserType.HUMAN,
        is_active=True,
        bot_display_name=body.display_name.strip(),
        bot_slug=slug,
        bot_auto_mode=False,
    )
    key, key_hash = _new_key(user.id)
    user.bot_service_key_hash = key_hash
    session.add(user)
    session.commit()
    session.refresh(user)
    role = RoomRole.BOT if body.kind == "agent" else RoomRole.MEMBER
    add_chat_room_member(session, room_id, user.id, role=role.value)
    if not room.meeting_mode_enabled:
        # A room with outside participants is a Roundtable meeting: this makes it
        # show in the meetings list and applies the room's bot rate cap to agents.
        room.meeting_mode_enabled = True
        room.updated_at = datetime.now(timezone.utc)
        session.add(room)
        session.commit()
    _audit(
        session,
        "create",
        actor_id=current_user.id,
        room_id=room_id,
        detail={"seat_id": str(user.id), "slug": slug, "kind": body.kind},
    )
    return SeatCreatedResponse(**_seat_response(user, role).model_dump(), key=key)


@router.get("/rooms/{room_id}/seats", response_model=list[SeatResponse])
def list_seats(room_id: uuid.UUID, session: SessionDep, current_user: CurrentChatUser):
    if not get_chat_room_member(session, room_id, current_user.id):
        raise HTTPException(status_code=403, detail="Not a member of this room")
    rows = session.execute(
        select(ChatRoomMember, ChatUser)
        .join(ChatUser, col(ChatUser.id) == col(ChatRoomMember.user_id))
        .where(
            col(ChatRoomMember.room_id) == room_id,
            col(ChatUser.username).startswith(SEAT_USERNAME_PREFIX),
        )
        .order_by(col(ChatRoomMember.joined_at))
    ).all()
    seats = [_seat_response(user, member.role) for member, user in rows]
    status = roundtable_jobs.seat_presence(
        session, room_id, [user.id for _, user in rows]
    )
    for seat in seats:
        info = status.get(uuid.UUID(seat.id), {})
        if seat.kind == "agent":
            seat.presence = info.get("presence")
            seat.working_note = info.get("working_note")
            seat.pending_jobs = info.get("pending_jobs", 0)
            seat.last_seen_at = info.get("last_seen_at")
    return seats


def _get_room_seat(
    session, room_id: uuid.UUID, seat_id: uuid.UUID
) -> tuple[ChatUser, ChatRoomMember]:
    seat = session.get(ChatUser, seat_id)
    membership = get_chat_room_member(session, room_id, seat_id) if seat else None
    if not seat or not is_seat_user(seat) or not membership:
        raise HTTPException(status_code=404, detail="Seat not found in this room")
    return seat, membership


@router.post(
    "/rooms/{room_id}/seats/{seat_id}/rotate", response_model=SeatCreatedResponse
)
def rotate_seat_key(
    room_id: uuid.UUID,
    seat_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
):
    _require_manager(session, room_id, current_user)
    seat, membership = _get_room_seat(session, room_id, seat_id)
    key, key_hash = _new_key(seat.id)
    seat.bot_service_key_hash = key_hash
    seat.is_active = True
    seat.updated_at = datetime.now(timezone.utc)
    session.add(seat)
    session.commit()
    session.refresh(seat)
    _audit(
        session,
        "rotate",
        actor_id=current_user.id,
        room_id=room_id,
        detail={"seat_id": str(seat.id)},
    )
    return SeatCreatedResponse(
        **_seat_response(seat, membership.role).model_dump(), key=key
    )


@router.delete("/rooms/{room_id}/seats/{seat_id}")
def revoke_seat(
    room_id: uuid.UUID,
    seat_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
):
    _require_manager(session, room_id, current_user)
    seat, membership = _get_room_seat(session, room_id, seat_id)
    session.delete(membership)
    session.commit()
    remaining = (
        session.execute(
            select(ChatRoomMember).where(col(ChatRoomMember.user_id) == seat.id)
        )
        .scalars()
        .first()
    )
    if remaining is None:
        seat.is_active = False
        seat.bot_service_key_hash = None
        seat.updated_at = datetime.now(timezone.utc)
        session.add(seat)
        session.commit()
    _audit(
        session,
        "revoke",
        actor_id=current_user.id,
        room_id=room_id,
        detail={"seat_id": str(seat.id), "deactivated": remaining is None},
    )
    return {"revoked": True, "deactivated": remaining is None}


# ── Seat endpoints (seat token only) ──────────────────────────────────────────


@router.post("/seats/token", response_model=SeatTokenResponse)
def exchange_seat_key(body: SeatTokenRequest, request: Request, session: SessionDep):
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _failed_key_attempts[ip]
    while attempts and now - attempts[0] > _KEY_WINDOW_SECONDS:
        attempts.popleft()
    if len(attempts) >= _KEY_MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail="Too many failed seat key attempts. Try again later.",
        )

    def _fail() -> HTTPException:
        attempts.append(now)
        return HTTPException(status_code=401, detail="Invalid seat key")

    parts = body.key.strip().split("_", 2)
    if len(parts) != 3 or parts[0] != _SEAT_KEY_PREFIX:
        raise _fail()
    try:
        seat_id = uuid.UUID(hex=parts[1])
    except ValueError:
        raise _fail()
    seat = session.get(ChatUser, seat_id)
    if (
        not seat
        or not seat.is_active
        or not is_seat_user(seat)
        or not seat.bot_service_key_hash
    ):
        raise _fail()
    ok, _ = verify_password(parts[2], seat.bot_service_key_hash)
    if not ok:
        raise _fail()

    minutes = _token_minutes()
    token = jwt.encode(
        {
            "sub": str(seat.id),
            "scope": SEAT_TOKEN_SCOPE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return SeatTokenResponse(
        access_token=token, expires_in=minutes * 60, seat=_seat_response(seat)
    )


@router.get("/seats/me", response_model=SeatMeResponse)
def seat_me(session: SessionDep, seat: CurrentSeat):
    from app.models import ChatRoom

    rows = session.execute(
        select(ChatRoomMember, ChatRoom)
        .join(ChatRoom, col(ChatRoom.id) == col(ChatRoomMember.room_id))
        .where(col(ChatRoomMember.user_id) == seat.id)
        .order_by(col(ChatRoomMember.joined_at))
    ).all()
    return SeatMeResponse(
        seat=_seat_response(seat),
        rooms=[
            SeatRoom(
                id=str(room.id),
                name=room.name,
                role=member.role.value,
                meeting_mode_enabled=bool(room.meeting_mode_enabled),
            )
            for member, room in rows
        ],
    )


@router.get("/seats/rooms/{room_id}/messages", response_model=list[SeatMessage])
def seat_read_messages(
    room_id: str,
    session: SessionDep,
    seat: CurrentSeat,
    after_id: str | None = None,
    limit: int = 50,
):
    """Oldest-first. Pass the last id you saw as ``after_id`` to poll for new messages."""
    room, _ = _require_seat_member(session, room_id, seat)
    limit = max(1, min(limit, 200))
    query = select(ChatMessage).where(col(ChatMessage.room_id) == room.id)
    if after_id:
        try:
            anchor = session.get(ChatMessage, uuid.UUID(after_id))
        except ValueError:
            anchor = None
        if not anchor or anchor.room_id != room.id:
            raise HTTPException(
                status_code=400, detail="after_id is not a message in this room"
            )
        query = (
            query.where(
                (col(ChatMessage.created_at) > anchor.created_at)
                | (
                    (col(ChatMessage.created_at) == anchor.created_at)
                    & (col(ChatMessage.id) != anchor.id)
                )
            )
            .order_by(col(ChatMessage.created_at).asc())
            .limit(limit)
        )
        messages = list(session.execute(query).scalars().all())
    else:
        latest = query.order_by(col(ChatMessage.created_at).desc()).limit(limit)
        messages = list(reversed(session.execute(latest).scalars().all()))
    cache: dict = {}
    return [_message_out(session, m, cache) for m in messages]


@router.post(
    "/seats/rooms/{room_id}/messages", response_model=SeatMessage, status_code=201
)
async def seat_post_message(
    room_id: str, body: SeatPostRequest, session: SessionDep, seat: CurrentSeat
):
    room, membership = _require_seat_member(session, room_id, seat)
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="This seat can read but not post")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message is empty")

    limit = _post_limit_per_minute(seat, room)
    now = time.monotonic()
    window = _seat_posts[str(seat.id)]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=429, detail=f"Seat rate limit: {limit} messages per minute"
        )

    reply_to = _parse_reply_to(session, room.id, body.reply_to_id)
    out = await _store_and_broadcast(
        session,
        room.id,
        seat,
        content,
        reply_to,
        {"via": "roundtable_seat", "seat_slug": seat.bot_slug},
    )
    window.append(now)
    return out


# ── Room members: talk in a Roundtable without starting a model turn ─────────


@router.post(
    "/rooms/{room_id}/roundtable/messages", response_model=SeatMessage, status_code=201
)
async def post_roundtable_message(
    room_id: uuid.UUID,
    body: SeatPostRequest,
    session: SessionDep,
    current_user: CurrentChatUser,
) -> SeatMessage:
    """Post as a signed-in room member. Unlike /messages and /messages/stream this
    never calls a Sparkbot model, so it works with no provider keys configured;
    the room's seated agents and guests answer instead."""
    room = get_chat_room_by_id(session, room_id)
    membership = (
        get_chat_room_member(session, room_id, current_user.id) if room else None
    )
    if not room or not membership:
        raise HTTPException(status_code=404, detail="Room not found")
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot send messages")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Message is empty")
    reply_to = _parse_reply_to(session, room.id, body.reply_to_id)
    return await _store_and_broadcast(
        session, room.id, current_user, content, reply_to, {"via": "roundtable_room"}
    )


# ── Connector download (so an invited agent can fetch the client) ────────────


def _connector_path():
    from pathlib import Path

    candidates = [os.getenv("SPARKBOT_ROUNDTABLE_CONNECTOR", "")]
    here = Path(__file__).resolve()
    if len(here.parents) > 5:
        candidates.append(str(here.parents[5] / "sparkbot-roundtable.py"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


@router.get("/seats/connector.py", include_in_schema=False)
def download_connector():
    """The open-source Roundtable connector (stdlib-only Python). Public: it holds no secrets."""
    from fastapi.responses import FileResponse

    path = _connector_path()
    if path is None:
        raise HTTPException(
            status_code=404, detail="Connector not bundled with this install"
        )
    return FileResponse(
        path, media_type="text/x-python", filename="sparkbot-roundtable.py"
    )


# ── Runner pilot: jobs for agent seats (docs/roundtable-runner.md v1) ─────────


class JobClaimBody(BaseModel):
    claim_token: str = Field(min_length=8, max_length=200)


class JobHeartbeatBody(JobClaimBody):
    note: str | None = Field(default=None, max_length=200)


class JobCompleteBody(JobClaimBody):
    content: str = Field(min_length=1, max_length=roundtable_jobs.MAX_REPLY_CHARS)


class JobFailBody(JobClaimBody):
    error: str = Field(default="", max_length=500)
    retry: bool = False


def _job_out(job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "room_id": str(job.room_id),
        "status": job.status,
        "attempt": job.attempts,
        "reply_message_id": str(job.reply_message_id) if job.reply_message_id else None,
        "lease_expires_at": roundtable_jobs.aware(job.lease_expires_at),
    }


def _conflict(err: roundtable_jobs.JobConflict):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=409, content={"detail": err.detail, "status": err.status}
    )


def _parse_job_id(job_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="No such job")


@router.get("/seats/jobs/next")
async def runner_next_job(session: SessionDep, seat: CurrentSeat, wait: int = 25):
    """Long-poll for this seat's next job. 204 = nothing yet; 200 = claimed job."""
    import asyncio

    from fastapi import Response

    if seat.type != UserType.BOT:
        raise HTTPException(status_code=403, detail="Only agent seats run jobs")
    wait = max(0, min(wait, 30))
    deadline = time.monotonic() + wait
    roundtable_jobs.touch_presence(session, seat.id)
    while True:
        claimed = roundtable_jobs.claim_next(session, seat)
        if claimed:
            break
        if time.monotonic() >= deadline:
            roundtable_jobs.touch_presence(session, seat.id)
            return Response(status_code=204)
        await asyncio.sleep(1.0)
    job, token = claimed
    room = get_chat_room_by_id(session, job.room_id)
    trigger = session.get(ChatMessage, job.trigger_message_id)
    if room is None or trigger is None:  # deleted under us; the job can't be answered
        roundtable_jobs.fail(
            session, seat, job.id, token, "room or message deleted", retry=False
        )
        return Response(status_code=204)
    cache: dict = {}
    context = []
    for message in roundtable_jobs.context_messages(session, job.room_id, trigger):
        item = _message_out(session, message, cache).model_dump(mode="json")
        item["content"] = item["content"][: roundtable_jobs.CONTEXT_MESSAGE_CHARS]
        keep = (
            "id",
            "sender_name",
            "sender_slug",
            "sender_type",
            "content",
            "created_at",
            "reply_to_id",
        )
        context.append({k: item[k] for k in keep})
    trigger_out = next((m for m in context if m["id"] == str(trigger.id)), None)
    return {
        "job": {
            **_job_out(job),
            "claim_token": token,
            "room": {"id": str(room.id), "name": room.name},
            "trigger": trigger_out,
            "context": context,
            "limits": {
                "max_reply_chars": roundtable_jobs.MAX_REPLY_CHARS,
                "lease_seconds": roundtable_jobs.LEASE_SECONDS,
                "context_messages": roundtable_jobs.CONTEXT_MESSAGES,
                "context_message_chars": roundtable_jobs.CONTEXT_MESSAGE_CHARS,
            },
        }
    }


@router.post("/seats/jobs/{job_id}/heartbeat")
def runner_heartbeat(
    job_id: str, body: JobHeartbeatBody, session: SessionDep, seat: CurrentSeat
):
    roundtable_jobs.touch_presence(session, seat.id)
    try:
        job = roundtable_jobs.heartbeat(
            session, seat, _parse_job_id(job_id), body.claim_token, body.note
        )
    except roundtable_jobs.JobConflict as err:
        return _conflict(err)
    return {"job": _job_out(job)}


@router.post("/seats/jobs/{job_id}/complete")
async def runner_complete(
    job_id: str, body: JobCompleteBody, session: SessionDep, seat: CurrentSeat
):
    """Atomic + idempotent: one reply per job; repeating the call returns the same reply."""
    roundtable_jobs.touch_presence(session, seat.id)
    try:
        job, existing = roundtable_jobs.begin_complete(
            session, seat, _parse_job_id(job_id), body.claim_token
        )
    except roundtable_jobs.JobConflict as err:
        return _conflict(err)
    if existing is not None:
        return {
            "job": _job_out(job),
            "message": _message_out(session, existing, {seat.id: seat}),
        }
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=422, detail="Reply is empty")
    out = await _store_and_broadcast(
        session,
        job.room_id,
        seat,
        content,
        job.trigger_message_id,
        {"via": "roundtable_runner", "job_id": str(job.id), "seat_slug": seat.bot_slug},
    )
    job = roundtable_jobs.mark_done(session, job, uuid.UUID(out.id))
    return {"job": _job_out(job), "message": out}


@router.post("/seats/jobs/{job_id}/fail")
def runner_fail(job_id: str, body: JobFailBody, session: SessionDep, seat: CurrentSeat):
    roundtable_jobs.touch_presence(session, seat.id)
    try:
        job = roundtable_jobs.fail(
            session,
            seat,
            _parse_job_id(job_id),
            body.claim_token,
            body.error,
            body.retry,
        )
    except roundtable_jobs.JobConflict as err:
        return _conflict(err)
    return {"job": _job_out(job)}


class RoomPauseBody(BaseModel):
    paused: bool


@router.get("/rooms/{room_id}/roundtable/state")
def roundtable_state(
    room_id: uuid.UUID, session: SessionDep, current_user: CurrentChatUser
):
    if not get_chat_room_member(session, room_id, current_user.id):
        raise HTTPException(status_code=404, detail="Room not found")
    return {"paused": roundtable_jobs.is_paused(session, room_id)}


@router.post("/rooms/{room_id}/roundtable/pause")
def roundtable_pause(
    room_id: uuid.UUID,
    body: RoomPauseBody,
    session: SessionDep,
    current_user: CurrentChatUser,
):
    """Same effect as posting /pause or /resume in the room."""
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=404, detail="Room not found")
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot pause the room")
    cancelled = roundtable_jobs.set_paused(
        session, room_id, body.paused, current_user.id
    )
    return {"paused": body.paused, "cancelled_jobs": cancelled}
