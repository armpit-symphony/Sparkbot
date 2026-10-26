"""Roundtable seats: outside agents and guest humans join a room with their own identity."""

import asyncio
from datetime import timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.routes.chat import seats as seats_route
from app.api.routes.chat.websocket import get_current_chat_user_from_token
from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.models import (
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
    ChatUser,
    RoomRole,
    UserType,
)
from app.services.guardian.auth import is_operator_identity
from tests.utils.utils import random_lower_string

API = settings.API_V1_STR


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _user_headers(user_id: UUID) -> dict[str, str]:
    return _headers(
        create_access_token(subject=str(user_id), expires_delta=timedelta(minutes=30))
    )


def _human(prefix: str = "h") -> UUID:
    with Session(engine) as db:
        u = ChatUser(
            username=f"{prefix}-{random_lower_string()[:10]}",
            type=UserType.HUMAN,
            is_active=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id


def _room(owner_id: UUID, **kw) -> UUID:
    with Session(engine) as db:
        room = ChatRoom(
            name=f"rt-{random_lower_string()[:8]}", created_by=owner_id, **kw
        )
        db.add(room)
        db.commit()
        db.refresh(room)
        db.add(ChatRoomMember(room_id=room.id, user_id=owner_id, role=RoomRole.OWNER))
        db.commit()
        return room.id


def _slug() -> str:
    return f"a{random_lower_string()[:10]}"


def _create_seat(client, room_id, owner_id, kind="agent", slug=None, name="Codex"):
    r = client.post(
        f"{API}/chat/rooms/{room_id}/seats",
        json={"display_name": name, "slug": slug or _slug(), "kind": kind},
        headers=_user_headers(owner_id),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _seat_token(client, key) -> str:
    r = client.post(f"{API}/chat/seats/token", json={"key": key})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _reset_limits():
    seats_route._failed_key_attempts.clear()
    seats_route._seat_posts.clear()


def test_owner_creates_agent_seat_and_agent_joins_conversation(
    client: TestClient,
) -> None:
    _reset_limits()
    owner = _human("owner")
    room = _room(owner)
    seat = _create_seat(client, room, owner, kind="agent")
    assert (
        seat["key"].startswith("rts_")
        and seat["kind"] == "agent"
        and seat["role"] == "BOT"
    )

    # Key is stored hashed, never in plain text.
    with Session(engine) as db:
        stored = db.get(ChatUser, UUID(seat["id"]))
        assert (
            stored.bot_service_key_hash
            and seat["key"] not in stored.bot_service_key_hash
        )

    listed = client.get(
        f"{API}/chat/rooms/{room}/seats", headers=_user_headers(owner)
    ).json()
    assert [s["id"] for s in listed] == [seat["id"]] and "key" not in listed[0]

    # Owner says hello through the normal app path.
    with Session(engine) as db:
        db.add(
            ChatMessage(
                room_id=room,
                sender_id=owner,
                sender_type=UserType.HUMAN,
                content="hi team",
            )
        )
        db.commit()

    tok = _seat_token(client, seat["key"])
    me = client.get(f"{API}/chat/seats/me", headers=_headers(tok)).json()
    assert me["seat"]["slug"] == seat["slug"] and [r["id"] for r in me["rooms"]] == [
        str(room)
    ]

    msgs = client.get(
        f"{API}/chat/seats/rooms/{room}/messages", headers=_headers(tok)
    ).json()
    assert [m["content"] for m in msgs] == ["hi team"]

    posted = client.post(
        f"{API}/chat/seats/rooms/{room}/messages",
        json={"content": "Codex here, taking RT-002", "reply_to_id": msgs[0]["id"]},
        headers=_headers(tok),
    )
    assert posted.status_code == 201, posted.text
    body = posted.json()
    assert (
        body["sender_type"] == "BOT"
        and body["sender_name"] == "Codex"
        and body["reply_to_id"] == msgs[0]["id"]
    )

    # Poll only what's new.
    newer = client.get(
        f"{API}/chat/seats/rooms/{room}/messages",
        params={"after_id": msgs[0]["id"]},
        headers=_headers(tok),
    ).json()
    assert [m["content"] for m in newer] == ["Codex here, taking RT-002"]

    with Session(engine) as db:
        saved = db.get(ChatMessage, UUID(body["id"]))
        assert (
            saved.sender_id == UUID(seat["id"])
            and saved.meta_json["via"] == "roundtable_seat"
        )


def test_human_seat_is_human_but_never_an_operator(client: TestClient) -> None:
    _reset_limits()
    owner = _human("owner")
    room = _room(owner)
    seat = _create_seat(client, room, owner, kind="human", name="Dana")
    assert seat["kind"] == "human" and seat["role"] == "MEMBER"
    tok = _seat_token(client, seat["key"])
    r = client.post(
        f"{API}/chat/seats/rooms/{room}/messages",
        json={"content": "hello"},
        headers=_headers(tok),
    )
    assert r.json()["sender_type"] == "HUMAN"

    with Session(engine) as db:
        u = db.get(ChatUser, UUID(seat["id"]))
        assert is_operator_identity(username=u.username, user_type=u.type) is False


def test_seat_token_cannot_reach_rest_of_app_or_websocket(client: TestClient) -> None:
    _reset_limits()
    owner = _human("owner")
    room = _room(owner)
    tok = _seat_token(client, _create_seat(client, room, owner)["key"])

    for method, path in [
        ("get", f"{API}/chat/rooms/"),
        ("get", f"{API}/chat/rooms/{room}/messages"),
        ("get", f"{API}/chat/rooms/{room}/seats"),
        ("post", f"{API}/chat/rooms/{room}/seats"),
        ("get", f"{API}/chat/users/"),
    ]:
        if method == "post":
            r = client.post(
                path, headers=_headers(tok), json={"display_name": "x", "slug": _slug()}
            )
        else:
            r = client.get(path, headers=_headers(tok))
        assert r.status_code == 403, (path, r.status_code, r.text)

    with Session(engine) as db:
        assert asyncio.run(get_current_chat_user_from_token(tok, db)) is None


def test_regular_login_token_is_not_a_seat_token(client: TestClient) -> None:
    owner = _human("owner")
    r = client.get(f"{API}/chat/seats/me", headers=_user_headers(owner))
    assert r.status_code == 403
    assert client.get(f"{API}/chat/seats/me").status_code == 401


def test_seat_cannot_see_rooms_it_was_not_invited_to(client: TestClient) -> None:
    _reset_limits()
    owner = _human("owner")
    room_a, room_b = _room(owner), _room(owner)
    tok = _seat_token(client, _create_seat(client, room_a, owner)["key"])
    assert (
        client.get(
            f"{API}/chat/seats/rooms/{room_b}/messages", headers=_headers(tok)
        ).status_code
        == 404
    )
    r = client.post(
        f"{API}/chat/seats/rooms/{room_b}/messages",
        json={"content": "x"},
        headers=_headers(tok),
    )
    assert r.status_code == 404


def test_only_owner_or_mod_manages_seats(client: TestClient) -> None:
    owner, member = _human("owner"), _human("member")
    room = _room(owner)
    with Session(engine) as db:
        db.add(ChatRoomMember(room_id=room, user_id=member, role=RoomRole.MEMBER))
        db.commit()
    r = client.post(
        f"{API}/chat/rooms/{room}/seats",
        json={"display_name": "X", "slug": _slug(), "kind": "agent"},
        headers=_user_headers(member),
    )
    assert r.status_code == 403


def test_slug_rules(client: TestClient) -> None:
    owner = _human("owner")
    room = _room(owner)
    slug = _slug()
    _create_seat(client, room, owner, slug=slug)
    dup = client.post(
        f"{API}/chat/rooms/{room}/seats",
        json={"display_name": "X", "slug": slug},
        headers=_user_headers(owner),
    )
    assert dup.status_code == 409
    bad = client.post(
        f"{API}/chat/rooms/{room}/seats",
        json={"display_name": "X", "slug": "Bad Slug!"},
        headers=_user_headers(owner),
    )
    assert bad.status_code == 422


def test_bad_keys_rejected_and_rate_limited(client: TestClient) -> None:
    _reset_limits()
    owner = _human("owner")
    seat = _create_seat(client, _room(owner), owner)
    wrong = seat["key"][:-4] + "zzzz"
    for bad in ["nonsense", "rts_nothex_abc", wrong]:
        assert (
            client.post(f"{API}/chat/seats/token", json={"key": bad}).status_code == 401
        )
    original = seats_route._KEY_MAX_FAILURES
    try:
        seats_route._KEY_MAX_FAILURES = 3
        assert (
            client.post(
                f"{API}/chat/seats/token", json={"key": seat["key"]}
            ).status_code
            == 429
        )
    finally:
        seats_route._KEY_MAX_FAILURES = original
        _reset_limits()


def test_post_rate_limit_follows_meeting_mode(client: TestClient) -> None:
    _reset_limits()
    owner = _human("owner")
    room = _room(owner, meeting_mode_enabled=True, meeting_mode_max_bot_msgs_per_min=2)
    tok = _seat_token(client, _create_seat(client, room, owner)["key"])
    codes = [
        client.post(
            f"{API}/chat/seats/rooms/{room}/messages",
            json={"content": f"m{i}"},
            headers=_headers(tok),
        ).status_code
        for i in range(3)
    ]
    assert codes == [201, 201, 429]


def test_viewer_seat_can_read_not_post(client: TestClient) -> None:
    _reset_limits()
    owner = _human("owner")
    room = _room(owner)
    seat = _create_seat(client, room, owner, kind="human")
    with Session(engine) as db:
        m = (
            db.query(ChatRoomMember)
            .filter_by(room_id=room, user_id=UUID(seat["id"]))
            .first()
        )
        m.role = RoomRole.VIEWER
        db.add(m)
        db.commit()
    tok = _seat_token(client, seat["key"])
    assert (
        client.get(
            f"{API}/chat/seats/rooms/{room}/messages", headers=_headers(tok)
        ).status_code
        == 200
    )
    r = client.post(
        f"{API}/chat/seats/rooms/{room}/messages",
        json={"content": "x"},
        headers=_headers(tok),
    )
    assert r.status_code == 403


def test_rotate_and_revoke(client: TestClient) -> None:
    _reset_limits()
    owner = _human("owner")
    room = _room(owner)
    seat = _create_seat(client, room, owner)
    old_tok = _seat_token(client, seat["key"])

    rotated = client.post(
        f"{API}/chat/rooms/{room}/seats/{seat['id']}/rotate",
        headers=_user_headers(owner),
    )
    assert rotated.status_code == 200
    assert (
        client.post(f"{API}/chat/seats/token", json={"key": seat["key"]}).status_code
        == 401
    )
    new_tok = _seat_token(client, rotated.json()["key"])

    r = client.delete(
        f"{API}/chat/rooms/{room}/seats/{seat['id']}", headers=_user_headers(owner)
    )
    assert r.json() == {"revoked": True, "deactivated": True}
    for tok in (old_tok, new_tok):
        assert (
            client.get(f"{API}/chat/seats/me", headers=_headers(tok)).status_code == 401
        )
    assert (
        client.post(
            f"{API}/chat/seats/token", json={"key": rotated.json()["key"]}
        ).status_code
        == 401
    )
    _reset_limits()
