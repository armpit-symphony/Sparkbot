from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import crud
from app.api.routes.chat import users as chat_users_route
from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token, decode_token
from app.models import AuditLog, ChatMessage, ChatRoom, ChatRoomMember, ChatUser, RoomRole, UserMemory, UserType
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


def _ensure_chat_user(username: str) -> UUID:
    with Session(engine) as db:
        user = db.exec(select(ChatUser).where(ChatUser.username == username)).first()
        if user:
            return user.id
        user = ChatUser(username=username, type=UserType.HUMAN, is_active=True)
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

    client.cookies.clear()


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

    client.cookies.clear()
    unauth_messages = client.get(f"{settings.API_V1_STR}/chat/rooms/{room_id}/messages")
    assert unauth_messages.status_code in {401, 403}


def test_memory_inspector_and_semantic_forget_are_user_scoped(client: TestClient) -> None:
    owner_id = _create_chat_user("memory-owner")
    outsider_id = _create_chat_user("memory-outsider")
    with Session(engine) as db:
        own_memory = crud.add_user_memory(db, owner_id, "I work at Google")
        other_memory = crud.add_user_memory(db, outsider_id, "I work at Meta")
        own_memory_id = own_memory.id
        other_memory_id = other_memory.id

    owner_headers = _chat_headers_for_user(owner_id)
    outsider_headers = _chat_headers_for_user(outsider_id)

    inspected = client.get(f"{settings.API_V1_STR}/chat/memory/inspect?limit=8", headers=owner_headers)
    assert inspected.status_code == 200
    facts = [item["fact"] for item in inspected.json()["memories"]]
    assert "I work at Google" in facts
    assert "I work at Meta" not in facts
    assert inspected.json()["memories"][0]["confidence"] is not None

    blocked_delete = client.delete(f"{settings.API_V1_STR}/chat/memory/{own_memory_id}", headers=outsider_headers)
    assert blocked_delete.status_code == 404

    forgotten = client.post(
        f"{settings.API_V1_STR}/chat/memory/forget",
        headers=owner_headers,
        json={"query": "forget that I work at Google"},
    )
    assert forgotten.status_code == 200
    assert forgotten.json()["deleted"] == str(own_memory_id)

    with Session(engine) as db:
        assert db.get(UserMemory, other_memory_id).lifecycle_state == "active"


def test_room_listing_and_message_lookup_require_auth_and_membership(
    client: TestClient,
) -> None:
    room_id, owner_id = _create_room_with_owner()
    outsider_id = _create_chat_user("outsider")

    with Session(engine) as db:
        message = ChatMessage(
            room_id=room_id,
            sender_id=owner_id,
            sender_type=UserType.HUMAN,
            content="private message",
        )
        db.add(message)
        db.commit()
        db.refresh(message)
        message_id = message.id

    owner_headers = _chat_headers_for_user(owner_id)
    outsider_headers = _chat_headers_for_user(outsider_id)

    owner_rooms = client.get(f"{settings.API_V1_STR}/chat/rooms/", headers=owner_headers)
    assert owner_rooms.status_code == 200
    assert any(room["id"] == str(room_id) for room in owner_rooms.json())

    outsider_rooms = client.get(f"{settings.API_V1_STR}/chat/rooms/", headers=outsider_headers)
    assert outsider_rooms.status_code == 200
    assert all(room["id"] != str(room_id) for room in outsider_rooms.json())

    client.cookies.clear()
    unauth_rooms = client.get(f"{settings.API_V1_STR}/chat/rooms/")
    assert unauth_rooms.status_code in {401, 403}

    owner_message = client.get(
        f"{settings.API_V1_STR}/chat/messages/{room_id}/message/{message_id}",
        headers=owner_headers,
    )
    assert owner_message.status_code == 200

    outsider_message = client.get(
        f"{settings.API_V1_STR}/chat/messages/{room_id}/message/{message_id}",
        headers=outsider_headers,
    )
    assert outsider_message.status_code == 403

    client.cookies.clear()
    unauth_message = client.get(
        f"{settings.API_V1_STR}/chat/messages/{room_id}/message/{message_id}"
    )
    assert unauth_message.status_code in {401, 403}


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


def test_models_config_requires_operator_identity(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_OPERATOR_USERNAMES", "sparkbot-user")
    operator_id = _ensure_chat_user("sparkbot-user")
    outsider_id = _create_chat_user("outsider")

    operator_headers = _chat_headers_for_user(operator_id)
    outsider_headers = _chat_headers_for_user(outsider_id)

    operator_response = client.get(
        f"{settings.API_V1_STR}/chat/models/config",
        headers=operator_headers,
    )
    assert operator_response.status_code == 200

    outsider_response = client.get(
        f"{settings.API_V1_STR}/chat/models/config",
        headers=outsider_headers,
    )
    assert outsider_response.status_code == 403


def test_sensitive_chat_controls_require_authentication(client: TestClient) -> None:
    client.cookies.clear()

    models_response = client.get(f"{settings.API_V1_STR}/chat/models/config")
    users_response = client.get(f"{settings.API_V1_STR}/chat/users/")
    dashboard_response = client.get(f"{settings.API_V1_STR}/chat/dashboard/summary")

    assert models_response.status_code in {401, 403}
    assert users_response.status_code in {401, 403}
    assert dashboard_response.status_code in {401, 403}


def test_models_config_update_requires_operator_identity(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARKBOT_OPERATOR_USERNAMES", "sparkbot-user")
    outsider_id = _create_chat_user("outsider")
    outsider_headers = _chat_headers_for_user(outsider_id)

    response = client.post(
        f"{settings.API_V1_STR}/chat/models/config",
        headers=outsider_headers,
        json={"token_guardian_mode": "shadow"},
    )
    assert response.status_code == 403


def test_comms_github_token_save_writes_vault_without_breakglass(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    from cryptography.fernet import Fernet

    from app.api.routes.chat import model as model_route
    from app.services.guardian.auth import close_privileged_session
    from app.services.guardian.vault import init_vault_db, vault_use

    guardian_dir = Path.cwd() / ".test-data" / f"guardian-{random_lower_string()[:10]}"
    monkeypatch.setenv("SPARKBOT_OPERATOR_USERNAMES", "sparkbot-user")
    monkeypatch.setenv("SPARKBOT_GUARDIAN_DATA_DIR", str(guardian_dir))
    monkeypatch.setenv("SPARKBOT_VAULT_KEY", Fernet.generate_key().decode("utf-8"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    init_vault_db()

    persisted_env: dict[str, str] = {}

    async def fake_ollama_status():
        return {"reachable": False, "models_available": False, "models": [], "model_ids": []}

    monkeypatch.setattr(model_route, "_write_env_updates", lambda updates: persisted_env.update(updates))
    monkeypatch.setattr(model_route, "get_ollama_status", fake_ollama_status)

    operator_id = _ensure_chat_user("sparkbot-user")
    close_privileged_session(str(operator_id))
    headers = _chat_headers_for_user(operator_id)

    response = client.post(
        f"{settings.API_V1_STR}/chat/models/config",
        headers=headers,
        json={
            "comms": {
                "github": {
                    "token": "ghp_controls_token",
                    "enabled": True,
                    "default_repo": "armpit-symphony/Sparkbot",
                }
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "GitHub token saved to Vault." in payload["notices"]
    assert vault_use("github_token", user_id="github_bridge", operator="system") == "ghp_controls_token"
    assert "GITHUB_TOKEN" not in persisted_env
    assert persisted_env["GITHUB_BRIDGE_ENABLED"] == "true"
