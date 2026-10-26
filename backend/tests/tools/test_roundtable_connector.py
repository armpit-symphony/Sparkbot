"""sparkbot-roundtable.py: CLI + MCP connector for Roundtable seats, run against the real API."""

import importlib.util
import io
import json
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.routes.chat import seats as seats_route
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
from tests.utils.utils import random_lower_string

_PATH = Path(__file__).resolve().parents[3] / "sparkbot-roundtable.py"
_spec = importlib.util.spec_from_file_location("sparkbot_roundtable", _PATH)
rt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rt)  # type: ignore[union-attr]

BASE = "http://sparkbot.test"


def _transport(client: TestClient):
    def call(method, url, body, headers):
        path = url.removeprefix(BASE)
        resp = client.request(method, path, json=body, headers=headers)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, resp.text

    return call


@pytest.fixture()
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUNDTABLE_HOME", str(tmp_path))
    for var in (
        "SPARKBOT_URL",
        "SPARKBOT_SEAT_KEY",
        "SPARKBOT_ROOM_ID",
        "ROUNDTABLE_PROFILE",
    ):
        monkeypatch.delenv(var, raising=False)
    seats_route._failed_key_attempts.clear()
    seats_route._seat_posts.clear()
    return tmp_path


def _owner_and_room(n_rooms: int = 1) -> tuple[UUID, list[UUID]]:
    with Session(engine) as db:
        owner = ChatUser(
            username=f"own-{random_lower_string()[:10]}",
            type=UserType.HUMAN,
            is_active=True,
        )
        db.add(owner)
        db.commit()
        db.refresh(owner)
        rooms = []
        for _ in range(n_rooms):
            room = ChatRoom(name=f"rt-{random_lower_string()[:6]}", created_by=owner.id)
            db.add(room)
            db.commit()
            db.refresh(room)
            db.add(
                ChatRoomMember(room_id=room.id, user_id=owner.id, role=RoomRole.OWNER)
            )
            db.commit()
            rooms.append(room.id)
        return owner.id, rooms


def _owner_headers(owner: UUID) -> dict:
    return {
        "Authorization": f"Bearer {create_access_token(subject=str(owner), expires_delta=timedelta(minutes=30))}"
    }


def _seat(client, owner, room, name="Codex") -> dict:
    r = client.post(
        f"{settings.API_V1_STR}/chat/rooms/{room}/seats",
        json={
            "display_name": name,
            "slug": f"a{random_lower_string()[:10]}",
            "kind": "agent",
        },
        headers=_owner_headers(owner),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _owner_says(room: UUID, owner: UUID, text: str) -> None:
    with Session(engine) as db:
        db.add(
            ChatMessage(
                room_id=room, sender_id=owner, sender_type=UserType.HUMAN, content=text
            )
        )
        db.commit()


def _profile(home: Path, name: str, key: str, **extra) -> None:
    (home / f"roundtable-{name}.json").write_text(
        json.dumps({"url": BASE, "key": key, **extra})
    )


def test_session_reads_only_new_and_posts(client: TestClient, home: Path) -> None:
    owner, (room,) = _owner_and_room()
    seat = _seat(client, owner, room)
    _profile(home, "codex", seat["key"])
    _owner_says(room, owner, "kickoff: who takes RT-002?")

    s = rt.Session("codex", transport=_transport(client))
    rid, msgs = s.read()
    assert rid == str(room) and [m["content"] for m in msgs] == [
        "kickoff: who takes RT-002?"
    ]
    assert s.read()[1] == []  # nothing new

    posted = s.post("Codex: I'll take RT-002", reply_to_id=msgs[0]["id"])
    assert posted["sender_type"] == "BOT"
    _owner_says(room, owner, "great, thanks")
    new = [m["content"] for m in s.read()[1]]
    assert new == ["Codex: I'll take RT-002", "great, thanks"]

    text = rt.format_messages(s.read(only_new=False)[1], s.client.seat["id"])
    assert (
        "(you)" in text
        and "[agent]" in text
        and "[human]" in text
        and f"id={msgs[0]['id']}" in text
    )

    state = json.loads((home / "roundtable-codex-state.json").read_text())
    assert state["last_seen"][str(room)]


def test_profiles_are_separate_seats(client: TestClient, home: Path) -> None:
    owner, (room,) = _owner_and_room()
    _profile(home, "codex", _seat(client, owner, room, "Codex")["key"])
    _profile(home, "claude", _seat(client, owner, room, "Claude")["key"])
    a = rt.Session("codex", transport=_transport(client))
    b = rt.Session("claude", transport=_transport(client))
    a.post("hi from codex")
    got = b.read()[1]
    assert [(m["sender_name"], m["content"]) for m in got] == [
        ("Codex", "hi from codex")
    ]


def test_room_choice(client: TestClient, home: Path) -> None:
    owner, (r1, r2) = _owner_and_room(2)
    seat = _seat(client, owner, r1)
    with Session(engine) as db:
        db.add(ChatRoomMember(room_id=r2, user_id=UUID(seat["id"]), role=RoomRole.BOT))
        db.commit()
    _profile(home, "p", seat["key"])
    s = rt.Session("p", transport=_transport(client))
    with pytest.raises(rt.RoundtableError, match="several rooms"):
        s.room()
    assert s.room(str(r2)) == str(r2)
    _profile(home, "p", seat["key"], room_id=str(r1))
    assert rt.Session("p", transport=_transport(client)).room() == str(r1)


def test_token_is_refreshed_after_rotation_is_refused(
    client: TestClient, home: Path
) -> None:
    owner, (room,) = _owner_and_room()
    seat = _seat(client, owner, room)
    _profile(home, "p", seat["key"])
    s = rt.Session("p", transport=_transport(client))
    s.client.me()
    s.client._token = "garbage"  # simulate an expired token
    s.client._token_exp = 9e18
    assert s.client.me()["seat"]["id"] == seat["id"]  # re-exchanged the key

    client.post(
        f"{settings.API_V1_STR}/chat/rooms/{room}/seats/{seat['id']}/rotate",
        headers=_owner_headers(owner),
    )
    s.client._token = None
    with pytest.raises(rt.RoundtableError) as exc:
        s.client.me()
    assert exc.value.status == 401


@pytest.mark.usefixtures("home")
def test_missing_key_is_a_clear_error() -> None:
    with pytest.raises(rt.RoundtableError, match="login"):
        rt.Session("nobody")


def _rpc(server, *msgs) -> list[dict]:
    stdin = io.BytesIO(b"".join((json.dumps(m) + "\n").encode() for m in msgs))
    out = io.BytesIO()
    server.serve(stdin, out)
    return [json.loads(line) for line in out.getvalue().decode().splitlines()]


def test_mcp_server_end_to_end(client: TestClient, home: Path) -> None:
    owner, (room,) = _owner_and_room()
    _profile(home, "claude", _seat(client, owner, room, "Claude")["key"])
    _owner_says(room, owner, "Claude, status?")
    server = rt.McpServer(
        lambda: rt.Session("claude", transport=_transport(client)), wait_interval=0.05
    )

    replies = _rpc(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "roundtable_whoami", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "roundtable_read", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "roundtable_post",
                "arguments": {"content": "Claude: seats PR is up"},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "roundtable_wait", "arguments": {"timeout_seconds": 1}},
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        },
        {"jsonrpc": "2.0", "id": 8, "method": "bogus/method"},
    )
    by_id = {r["id"]: r for r in replies}
    assert set(by_id) == {1, 2, 3, 4, 5, 6, 7, 8}  # notification got no reply
    assert by_id[1]["result"]["protocolVersion"] == "2025-06-18"
    assert by_id[1]["result"]["capabilities"] == {"tools": {}}
    names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert names == {
        "roundtable_whoami",
        "roundtable_read",
        "roundtable_post",
        "roundtable_wait",
    }
    assert "Claude" in by_id[3]["result"]["content"][0]["text"]
    assert "Claude, status?" in by_id[4]["result"]["content"][0]["text"]
    assert by_id[5]["result"]["isError"] is False
    # Our own post is the only new message; it's labeled as ours.
    wait_text = by_id[6]["result"]["content"][0]["text"]
    assert "Claude: seats PR is up" in wait_text and "(you)" in wait_text
    assert by_id[7]["error"]["code"] == -32602
    assert by_id[8]["error"]["code"] == -32601


@pytest.mark.usefixtures("home")
def test_mcp_reports_errors_without_crashing(client: TestClient) -> None:
    server = rt.McpServer(lambda: rt.Session("missing", transport=_transport(client)))
    replies = _rpc(
        server,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "roundtable_read", "arguments": {}},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
    )
    assert (
        replies[0]["result"]["isError"] is True
        and "login" in replies[0]["result"]["content"][0]["text"]
    )
    assert replies[1]["result"] == {}


def test_wait_times_out_quietly(client: TestClient, home: Path) -> None:
    owner, (room,) = _owner_and_room()
    _profile(home, "p", _seat(client, owner, room)["key"])
    s = rt.Session("p", transport=_transport(client))
    s.read()
    assert s.wait(timeout=0.2, interval=0.05)[1] == []


def test_cli_post_and_read(client: TestClient, home: Path, monkeypatch, capsys) -> None:
    owner, (room,) = _owner_and_room()
    _profile(home, "cli", _seat(client, owner, room)["key"])
    real_session = rt.Session
    monkeypatch.setattr(
        rt,
        "Session",
        lambda profile=None: real_session(profile, transport=_transport(client)),
    )
    assert rt.main(["post", "--profile", "cli", "hello", "room"]) == 0
    assert "Posted as Codex" in capsys.readouterr().out
    assert rt.main(["read", "--profile", "cli"]) == 0
    assert "hello room" in capsys.readouterr().out
    assert rt.main(["read", "--profile", "cli"]) == 0
    assert "(no new messages)" in capsys.readouterr().out
    assert rt.main(["logout", "--profile", "cli"]) == 0
    assert not (home / "roundtable-cli.json").exists()
