"""Runner pilot: @mention jobs for agent seats (docs/roundtable-runner.md v1)."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

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
    RoundtableJob,
    UserType,
)
from tests.utils.utils import random_lower_string

API = settings.API_V1_STR


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _owner_h(user_id: UUID) -> dict[str, str]:
    return _h(
        create_access_token(subject=str(user_id), expires_delta=timedelta(minutes=30))
    )


def _human() -> UUID:
    with Session(engine) as db:
        u = ChatUser(
            username=f"h-{random_lower_string()[:10]}",
            type=UserType.HUMAN,
            is_active=True,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id


def _room(owner: UUID) -> UUID:
    with Session(engine) as db:
        room = ChatRoom(name=f"rt-{random_lower_string()[:8]}", created_by=owner)
        db.add(room)
        db.commit()
        db.refresh(room)
        db.add(ChatRoomMember(room_id=room.id, user_id=owner, role=RoomRole.OWNER))
        db.commit()
        return room.id


def _seat(
    client: TestClient,
    room: UUID,
    owner: UUID,
    kind: str = "agent",
    name: str = "Atlas",
) -> dict:
    slug = f"a{random_lower_string()[:10]}"
    r = client.post(
        f"{API}/chat/rooms/{room}/seats",
        json={"display_name": name, "slug": slug, "kind": kind},
        headers=_owner_h(owner),
    )
    assert r.status_code == 201, r.text
    seat = r.json()
    tok = client.post(f"{API}/chat/seats/token", json={"key": seat["key"]}).json()[
        "access_token"
    ]
    seat["token"] = tok
    return seat


def _say(client: TestClient, room: UUID, owner: UUID, text: str) -> dict:
    r = client.post(
        f"{API}/chat/rooms/{room}/roundtable/messages",
        json={"content": text},
        headers=_owner_h(owner),
    )
    assert r.status_code == 201, r.text
    return r.json()


def _next(client: TestClient, seat: dict):
    return client.get(
        f"{API}/chat/seats/jobs/next", params={"wait": 0}, headers=_h(seat["token"])
    )


def _jobs(room: UUID) -> list[RoundtableJob]:
    with Session(engine) as db:
        return list(
            db.exec(select(RoundtableJob).where(RoundtableJob.room_id == room)).all()
        )


@pytest.fixture(autouse=True)
def _reset_limits(monkeypatch):
    seats_route._failed_key_attempts.clear()
    seats_route._seat_posts.clear()
    monkeypatch.delenv("SPARKBOT_RUNNER_JOBS_PER_HOUR", raising=False)


def test_mentions_create_jobs_only_for_mentioned_agent_seats(
    client: TestClient,
) -> None:
    owner = _human()
    room = _room(owner)
    atlas, meridian = (
        _seat(client, room, owner, name="Atlas"),
        _seat(client, room, owner, name="Meridian"),
    )
    guest = _seat(client, room, owner, kind="human", name="Dana")

    _say(client, room, owner, "no mention here")
    assert _jobs(room) == []

    _say(client, room, owner, f"@{atlas['slug']} please check, again @{atlas['slug']}")
    jobs = _jobs(room)
    assert [str(j.seat_id) for j in jobs] == [atlas["id"]] and jobs[
        0
    ].status == "pending"

    # A guest (human seat) can wake agents too; @all = every agent seat, never human seats.
    r = client.post(
        f"{API}/chat/seats/rooms/{room}/messages",
        json={"content": "@all ideas?"},
        headers=_h(guest["token"]),
    )
    assert r.status_code == 201
    all_jobs = [j for j in _jobs(room) if str(j.trigger_message_id) == r.json()["id"]]
    assert sorted(str(j.seat_id) for j in all_jobs) == sorted(
        [atlas["id"], meridian["id"]]
    )

    # Agents never wake agents.
    before = len(_jobs(room))
    client.post(
        f"{API}/chat/seats/rooms/{room}/messages",
        json={"content": f"@{meridian['slug']} over to you"},
        headers=_h(atlas["token"]),
    )
    assert len(_jobs(room)) == before


def test_claim_heartbeat_complete_is_atomic_and_idempotent(client: TestClient) -> None:
    owner = _human()
    room = _room(owner)
    atlas = _seat(client, room, owner)
    assert _next(client, atlas).status_code == 204

    trigger = _say(client, room, owner, f"@{atlas['slug']} status of RT-010?")
    r = _next(client, atlas)
    assert r.status_code == 200, r.text
    job = r.json()["job"]
    assert (
        job["status"] == "claimed"
        and job["attempt"] == 1
        and len(job["claim_token"]) > 20
    )
    assert (
        job["trigger"]["id"] == trigger["id"]
        and job["context"][-1]["id"] == trigger["id"]
    )
    assert job["room"]["id"] == str(room) and job["limits"]["max_reply_chars"] == 8000
    assert _next(client, atlas).status_code == 204  # already claimed

    base = f"{API}/chat/seats/jobs/{job['id']}"
    wrong = {"claim_token": "not-the-right-token"}
    assert (
        client.post(
            f"{base}/heartbeat", json=wrong, headers=_h(atlas["token"])
        ).status_code
        == 409
    )
    hb = client.post(
        f"{base}/heartbeat",
        json={"claim_token": job["claim_token"], "note": "reading"},
        headers=_h(atlas["token"]),
    )
    assert hb.status_code == 200

    body = {
        "claim_token": job["claim_token"],
        "content": "RT-010 is not started yet. Signed: Atlas",
    }
    first = client.post(f"{base}/complete", json=body, headers=_h(atlas["token"]))
    assert first.status_code == 200, first.text
    again = client.post(f"{base}/complete", json=body, headers=_h(atlas["token"]))
    assert again.status_code == 200
    assert first.json()["message"]["id"] == again.json()["message"]["id"]
    assert first.json()["job"]["status"] == "done"

    msg = first.json()["message"]
    assert msg["sender_type"] == "BOT" and msg["reply_to_id"] == trigger["id"]
    with Session(engine) as db:
        replies = db.exec(
            select(ChatMessage).where(ChatMessage.reply_to_id == UUID(trigger["id"]))
        ).all()
        assert len(replies) == 1  # never posted twice
    # Heartbeat on a finished job is a conflict.
    done_hb = client.post(
        f"{base}/heartbeat",
        json={"claim_token": job["claim_token"]},
        headers=_h(atlas["token"]),
    )
    assert done_hb.status_code == 409 and done_hb.json()["status"] == "done"


def test_fail_retry_then_new_claim_and_old_token_is_stale(client: TestClient) -> None:
    owner = _human()
    room = _room(owner)
    atlas = _seat(client, room, owner)
    _say(client, room, owner, f"@{atlas['slug']} hi")
    j1 = _next(client, atlas).json()["job"]
    r = client.post(
        f"{API}/chat/seats/jobs/{j1['id']}/fail",
        json={
            "claim_token": j1["claim_token"],
            "error": "codex crashed",
            "retry": True,
        },
        headers=_h(atlas["token"]),
    )
    assert r.json()["job"]["status"] == "pending"
    j2 = _next(client, atlas).json()["job"]
    assert (
        j2["id"] == j1["id"]
        and j2["attempt"] == 2
        and j2["claim_token"] != j1["claim_token"]
    )
    stale = client.post(
        f"{API}/chat/seats/jobs/{j1['id']}/complete",
        json={"claim_token": j1["claim_token"], "content": "late"},
        headers=_h(atlas["token"]),
    )
    assert stale.status_code == 409
    # Out of attempts: retry=True still ends as failed.
    r = client.post(
        f"{API}/chat/seats/jobs/{j2['id']}/fail",
        json={"claim_token": j2["claim_token"], "error": "again", "retry": True},
        headers=_h(atlas["token"]),
    )
    assert r.json()["job"]["status"] == "failed"


def test_expired_lease_is_retried_once_then_expires(client: TestClient) -> None:
    owner = _human()
    room = _room(owner)
    atlas = _seat(client, room, owner)
    _say(client, room, owner, f"@{atlas['slug']} hi")

    def _expire(job_id: str) -> None:
        with Session(engine) as db:
            job = db.get(RoundtableJob, UUID(job_id))
            job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)
            db.add(job)
            db.commit()

    j1 = _next(client, atlas).json()["job"]
    _expire(j1["id"])
    j2 = _next(client, atlas).json()["job"]
    assert j2["id"] == j1["id"] and j2["attempt"] == 2
    old = client.post(
        f"{API}/chat/seats/jobs/{j1['id']}/heartbeat",
        json={"claim_token": j1["claim_token"]},
        headers=_h(atlas["token"]),
    )
    assert old.status_code == 409
    _expire(j2["id"])
    assert _next(client, atlas).status_code == 204
    assert _jobs(room)[0].status == "expired"


def test_pause_cancels_pending_and_claimed_and_resume(client: TestClient) -> None:
    owner = _human()
    room = _room(owner)
    atlas, meridian = (
        _seat(client, room, owner),
        _seat(client, room, owner, name="Meridian"),
    )
    _say(client, room, owner, "@all go")
    claimed = _next(client, atlas).json()["job"]

    _say(client, room, owner, "/pause")
    assert {j.status for j in _jobs(room)} == {"cancelled"}
    hb = client.post(
        f"{API}/chat/seats/jobs/{claimed['id']}/heartbeat",
        json={"claim_token": claimed["claim_token"]},
        headers=_h(atlas["token"]),
    )
    assert hb.status_code == 409 and hb.json()["status"] == "cancelled"
    state = client.get(
        f"{API}/chat/rooms/{room}/roundtable/state", headers=_owner_h(owner)
    ).json()
    assert state == {"paused": True}

    _say(client, room, owner, f"@{meridian['slug']} still there?")
    assert all(j.status == "cancelled" for j in _jobs(room))  # no new job while paused

    r = client.post(
        f"{API}/chat/rooms/{room}/roundtable/pause",
        json={"paused": False},
        headers=_owner_h(owner),
    )
    assert r.json()["paused"] is False
    _say(client, room, owner, f"@{meridian['slug']} now?")
    assert _next(client, meridian).status_code == 200


def test_hourly_cap_skips(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("SPARKBOT_RUNNER_JOBS_PER_HOUR", "1")
    owner = _human()
    room = _room(owner)
    atlas = _seat(client, room, owner)
    _say(client, room, owner, f"@{atlas['slug']} one")
    _say(client, room, owner, f"@{atlas['slug']} two")
    statuses = sorted(j.status for j in _jobs(room))
    assert statuses == ["pending", "skipped"]


def test_only_agent_seats_run_jobs_and_owner_tokens_are_rejected(
    client: TestClient,
) -> None:
    owner = _human()
    room = _room(owner)
    guest = _seat(client, room, owner, kind="human", name="Dana")
    assert _next(client, guest).status_code == 403
    r = client.get(
        f"{API}/chat/seats/jobs/next", params={"wait": 0}, headers=_owner_h(owner)
    )
    assert r.status_code == 403  # owner token is not a seat token


def test_presence_shows_online_and_working(client: TestClient) -> None:
    owner = _human()
    room = _room(owner)
    atlas = _seat(client, room, owner)

    def presence() -> dict:
        rows = client.get(
            f"{API}/chat/rooms/{room}/seats", headers=_owner_h(owner)
        ).json()
        return next(r for r in rows if r["id"] == atlas["id"])

    assert presence()["presence"] == "offline"
    _next(client, atlas)
    assert presence()["presence"] == "online"
    _say(client, room, owner, f"@{atlas['slug']} work")
    job = _next(client, atlas).json()["job"]
    client.post(
        f"{API}/chat/seats/jobs/{job['id']}/heartbeat",
        json={"claim_token": job["claim_token"], "note": "thinking"},
        headers=_h(atlas["token"]),
    )
    p = presence()
    assert p["presence"] == "working" and p["working_note"] == "thinking"


def test_removed_seat_job_is_cancelled_and_reply_limits(client: TestClient) -> None:
    owner = _human()
    room = _room(owner)
    atlas = _seat(client, room, owner)
    _say(client, room, owner, f"@{atlas['slug']} hi")
    job = _next(client, atlas).json()["job"]
    too_long = client.post(
        f"{API}/chat/seats/jobs/{job['id']}/complete",
        json={"claim_token": job["claim_token"], "content": "x" * 8001},
        headers=_h(atlas["token"]),
    )
    assert too_long.status_code == 422

    second_room_owner = _human()
    room2 = _room(second_room_owner)
    meridian = _seat(client, room2, second_room_owner, name="Meridian")
    _say(client, room2, second_room_owner, f"@{meridian['slug']} hi")
    with Session(engine) as db:  # seat removed from the room before it claims
        m = db.exec(
            select(ChatRoomMember).where(
                ChatRoomMember.room_id == room2,
                ChatRoomMember.user_id == UUID(meridian["id"]),
            )
        ).first()
        db.delete(m)
        db.commit()
    assert _next(client, meridian).status_code in (204, 404)
    assert _jobs(room2)[0].status == "cancelled"
