from datetime import timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.routes.chat import users as chat_users_route
from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token, decode_token
from app.models import AuditLog, ChatRoom, ChatRoomMember, ChatUser, RoomRole, UserType
from tests.utils.utils import random_lower_string


def _chat_headers_for_user(user_id: UUID) -> dict[str, str]:
    token = create_access_token(subject=str(user_id), expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {token}"}


def _create_chat_user(prefix: str) -> UUID:
    with Session(engine) as db:
        user = ChatUser(
            username=f"{prefix}-{random_lower_string()[:10]}",
            type=UserType.HUMAN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _create_room_with_owner() -> tuple[UUID, UUID]:
    owner_id = _create_chat_user("owner")
    with Session(engine) as db:
        room = ChatRoom(name=f"room-{random_lower_string()[:8]}", created_by=owner_id)
        db.add(room)
        db.commit()
        db.refresh(room)

        membership = ChatRoomMember(room_id=room.id, user_id=owner_id, role=RoomRole.OWNER)
        db.add(membership)
        db.commit()
        return room.id, owner_id


def test_chat_login_creates_real_user_and_token_subject(client: TestClient) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/chat/users/login",
        json={"passphrase": settings.SPARKBOT_PASSPHRASE},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["access_token"]

    with Session(engine) as db:
        sparkbot_user = db.exec(
            select(ChatUser).where(ChatUser.username == "sparkbot-user")
        ).first()
        assert sparkbot_user is not None

        token_payload = decode_token(payload["access_token"])
        assert token_payload is not None
        assert token_payload.get("sub") == str(sparkbot_user.id)


def test_chat_login_rate_limit_blocks_repeated_failures(client: TestClient) -> None:
    chat_users_route._chat_login_attempts.clear()
    original_max_attempts = chat_users_route._CHAT_MAX_ATTEMPTS
    original_window = chat_users_route._CHAT_WINDOW_SECONDS

    try:
        chat_users_route._CHAT_MAX_ATTEMPTS = 1
        chat_users_route._CHAT_WINDOW_SECONDS = 60

        first = client.post(
            f"{settings.API_V1_STR}/chat/users/login",
            json={"passphrase": "wrong-passphrase"},
        )
        assert first.status_code == 401

        second = client.post(
            f"{settings.API_V1_STR}/chat/users/login",
            json={"passphrase": "wrong-passphrase"},
        )
        assert second.status_code == 429
    finally:
        chat_users_route._CHAT_MAX_ATTEMPTS = original_max_attempts
        chat_users_route._CHAT_WINDOW_SECONDS = original_window
        chat_users_route._chat_login_attempts.clear()


def test_room_and_upload_read_endpoints_require_membership(
    client: TestClient,
) -> None:
    room_id, owner_id = _create_room_with_owner()
    outsider_id = _create_chat_user("outsider")

    owner_headers = _chat_headers_for_user(owner_id)
    outsider_headers = _chat_headers_for_user(outsider_id)

    owner_room = client.get(f"{settings.API_V1_STR}/chat/rooms/{room_id}", headers=owner_headers)
    assert owner_room.status_code == 200

    outsider_room = client.get(
        f"{settings.API_V1_STR}/chat/rooms/{room_id}", headers=outsider_headers
    )
    assert outsider_room.status_code == 403

    outsider_members = client.get(
        f"{settings.API_V1_STR}/chat/rooms/{room_id}/members",
        headers=outsider_headers,
    )
    assert outsider_members.status_code == 403

    outsider_upload = client.get(
        f"{settings.API_V1_STR}/chat/rooms/{room_id}/uploads/file-123/test.txt",
        headers=outsider_headers,
    )
    assert outsider_upload.status_code == 403

    owner_messages = client.get(
        f"{settings.API_V1_STR}/chat/rooms/{room_id}/messages",
        headers=owner_headers,
    )
    assert owner_messages.status_code == 200

    outsider_messages = client.get(
        f"{settings.API_V1_STR}/chat/rooms/{room_id}/messages",
        headers=outsider_headers,
    )
    assert outsider_messages.status_code == 403

    unauth_messages = client.get(f"{settings.API_V1_STR}/chat/rooms/{room_id}/messages")
    assert unauth_messages.status_code in {401, 403}


def test_audit_endpoints_require_room_scope_and_membership(
    client: TestClient,
) -> None:
    room_id, owner_id = _create_room_with_owner()
    outsider_id = _create_chat_user("outsider")

    with Session(engine) as db:
        db.add(
            AuditLog(
                user_id=owner_id,
                room_id=room_id,
                tool_name="web_search",
                tool_input='{"query":"sparkbot"}',
                tool_result="ok",
                agent_name="researcher",
                model="gpt-4o-mini",
            )
        )
        db.commit()

    owner_headers = _chat_headers_for_user(owner_id)
    outsider_headers = _chat_headers_for_user(outsider_id)

    no_room = client.get(f"{settings.API_V1_STR}/chat/audit", headers=owner_headers)
    assert no_room.status_code == 400

    member_list = client.get(
        f"{settings.API_V1_STR}/chat/audit?room_id={room_id}",
        headers=owner_headers,
    )
    assert member_list.status_code == 200
    assert member_list.json()["total"] >= 1

    non_member_list = client.get(
        f"{settings.API_V1_STR}/chat/audit?room_id={room_id}",
        headers=outsider_headers,
    )
    assert non_member_list.status_code == 403
