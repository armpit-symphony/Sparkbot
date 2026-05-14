import os
from collections.abc import Iterator
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.core.security import create_access_token
from app.models import ChatUser, UserType


@pytest.fixture(autouse=True)
def _restore_security_env() -> Iterator[None]:
    keys = [
        "SPARKBOT_DATA_DIR",
        "SPARKBOT_OPERATOR_PIN_HASH",
        "SPARKBOT_OPERATOR_USERNAMES",
        "SPARKBOT_PASSPHRASE",
    ]
    original = {key: os.environ.get(key) for key in keys}
    yield
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


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


def _headers(user_id: UUID) -> dict[str, str]:
    token = create_access_token(subject=str(user_id), expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {token}"}


def test_security_status_reports_operator_posture(client: TestClient, monkeypatch, tmp_path) -> None:
    user_id = _ensure_chat_user("security-owner")
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SPARKBOT_PASSPHRASE", "weak")
    monkeypatch.delenv("SPARKBOT_OPERATOR_USERNAMES", raising=False)

    response = client.get(f"{settings.API_V1_STR}/chat/security/status", headers=_headers(user_id))

    assert response.status_code == 200
    payload = response.json()
    assert payload["operator"]["mode"] == "open"
    assert payload["passphrase"]["weak_default"] is True
    assert "frontend_headers" in payload
    assert payload["security_modes"][0]["id"] == "prototype"


def test_security_writes_require_breakglass(client: TestClient, monkeypatch, tmp_path) -> None:
    user_id = _ensure_chat_user("security-locked")
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path))

    response = client.post(
        f"{settings.API_V1_STR}/chat/security/passphrase",
        headers=_headers(user_id),
        json={"passphrase": "correct horse battery staple 123"},
    )

    assert response.status_code == 403
    assert "break-glass" in response.json()["detail"]


def test_security_can_create_pin_then_update_passphrase_and_operator_users(
    client: TestClient,
    monkeypatch,
    tmp_path,
) -> None:
    from app.services.guardian import auth as auth_module

    auth_module._PRIVILEGED_SESSIONS.clear()
    user_id = _ensure_chat_user("security-operator")
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SPARKBOT_OPERATOR_PIN_HASH", raising=False)
    monkeypatch.delenv("SPARKBOT_OPERATOR_USERNAMES", raising=False)

    pin_response = client.post(
        f"{settings.API_V1_STR}/chat/security/operator-pin",
        headers=_headers(user_id),
        json={"pin": "123456", "pin_confirm": "123456"},
    )
    assert pin_response.status_code == 200
    assert pin_response.json()["pin_configured"] is True

    auth_module.open_privileged_session(str(user_id), "security-operator")
    passphrase_response = client.post(
        f"{settings.API_V1_STR}/chat/security/passphrase",
        headers=_headers(user_id),
        json={"passphrase": "correct horse battery staple 123"},
    )
    assert passphrase_response.status_code == 200
    env_file = tmp_path / ".env"
    assert "SPARKBOT_PASSPHRASE=correct horse battery staple 123" in env_file.read_text()
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"

    operators_response = client.post(
        f"{settings.API_V1_STR}/chat/security/operator-users",
        headers=_headers(user_id),
        json={"usernames": ["security-operator"]},
    )
    assert operators_response.status_code == 200
    assert operators_response.json()["usernames"] == ["security-operator"]
    assert "SPARKBOT_OPERATOR_USERNAMES=security-operator" in env_file.read_text()


def test_fix_permissions_only_changes_accessible_env_files(
    client: TestClient,
    monkeypatch,
    tmp_path,
) -> None:
    from app.services.guardian import auth as auth_module

    auth_module._PRIVILEGED_SESSIONS.clear()
    user_id = _ensure_chat_user("security-perms")
    env_file = tmp_path / ".env"
    env_file.write_text("SPARKBOT_PASSPHRASE=unsafe\n")
    env_file.chmod(0o664)
    monkeypatch.setenv("SPARKBOT_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SPARKBOT_OPERATOR_USERNAMES", raising=False)
    auth_module.open_privileged_session(str(user_id), "security-perms")

    response = client.post(
        f"{settings.API_V1_STR}/chat/security/fix-permissions",
        headers=_headers(user_id),
    )

    assert response.status_code == 200
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"
    assert any(item["path"] == str(env_file) for item in response.json()["changed"])
