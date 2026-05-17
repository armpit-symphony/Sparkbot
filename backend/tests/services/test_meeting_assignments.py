from __future__ import annotations

from sqlmodel import Session, SQLModel, create_engine

from app.models import ChatRoom, ChatUser, UserType
from app.services.guardian.meeting_assignments import (
    latest_meeting_assignments,
    parse_meeting_assignments,
    persist_meeting_assignments,
)


def _session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _seed_room(session: Session) -> tuple[ChatUser, ChatRoom]:
    user = ChatUser(username="sparkbot-user", type=UserType.HUMAN, hashed_password="")
    session.add(user)
    session.commit()
    session.refresh(user)

    room = ChatRoom(name="Round Table", created_by=user.id, meeting_mode_enabled=True)
    session.add(room)
    session.commit()
    session.refresh(room)
    return user, room


def test_parse_meeting_assignments_extracts_participant_jobs() -> None:
    assignments = parse_meeting_assignments(
        "@sparkbot: summarize the release blockers\n- researcher - inspect memory wiring\nhelper: ignore this",
        ["sparkbot", "researcher"],
    )

    assert assignments == [
        {"handle": "sparkbot", "assignment": "summarize the release blockers"},
        {"handle": "researcher", "assignment": "inspect memory wiring"},
    ]


def test_persist_meeting_assignments_survives_manifest_reload() -> None:
    with _session() as session:
        user, room = _seed_room(session)

        stored = persist_meeting_assignments(
            session=session,
            room_id=room.id,
            created_by_user_id=user.id,
            chair_handle="sparkbot",
            participant_handles=["sparkbot", "researcher"],
            assignment_text="@sparkbot: chair the next pass\n@researcher: verify backend persistence",
            meeting_phase="manager_assessment",
        )
        latest = latest_meeting_assignments(session=session, room_id=room.id)

    assert stored == latest
    assert latest[0]["assignment"] == "chair the next pass"
    assert latest[1]["assignment"] == "verify backend persistence"
