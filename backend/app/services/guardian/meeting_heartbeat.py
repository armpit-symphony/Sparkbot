from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Optional

from sqlmodel import Session, select

from app.crud import (
    create_chat_meeting_artifact,
    create_chat_message,
    get_chat_meeting_artifacts,
    get_chat_messages,
    get_chat_room_by_id,
    get_chat_user_by_id,
    get_user_memories,
)
from app.models import ChatRoom, ChatUser, UserType
from app.services.guardian import get_guardian_suite
from app.services.guardian.meeting_recorder import generate_meeting_notes


MEETING_MANIFEST_SOURCE = "meeting_manifest"
MEETING_HEARTBEAT_SOURCE = "meeting_heartbeat"
HEARTBEAT_TOOL_NAME = "meeting_heartbeat"
DEFAULT_HEARTBEAT_SCHEDULE = "every:3600"
TERMINAL_MEETING_STATUSES = {
    "needs_user_input",
    "needs_approval",
    "recommendation_ready",
    "solved",
    "blocked",
    "looping",
}
MEETING_TURN_RETRY_ATTEMPTS = max(1, int(os.getenv("SPARKBOT_MEETING_TURN_RETRY_ATTEMPTS", "3")))
MEETING_TURN_RETRY_DELAY_SECONDS = max(0.1, float(os.getenv("SPARKBOT_MEETING_TURN_RETRY_DELAY_SECONDS", "1.5")))


def _is_retryable_meeting_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    retry_markers = (
        "network",
        "connection",
        "connect",
        "timeout",
        "timed out",
        "temporarily",
        "rate limit",
        "overloaded",
        "service unavailable",
        "bad gateway",
        "gateway timeout",
        "http 429",
        "http 500",
        "http 502",
        "http 503",
        "http 504",
    )
    return any(marker in text for marker in retry_markers)


def _chunk_text(text: str, size: int = 80) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] if text else []


def _agent_label(agent_name: str, agent_info: Optional[dict[str, Any]] = None) -> str:
    info = agent_info or {}
    emoji = str(info.get("emoji") or "")
    display = "Sparkbot" if agent_name == "sparkbot" else agent_name.replace("_", " ").title()
    return f"{emoji} {display}".strip() if emoji else display


def _meeting_role_instruction(agent_name: str, *, chair: bool) -> str:
    normalized = agent_name.lower()
    if chair:
        return (
            "You are the meeting chair and facilitator. Frame the objective, keep the room moving, "
            "synthesize distinct inputs, and decide whether another round adds value. Treat the human "
            "as the owner and approver, not as a required speaker between turns. Do not ask who should "
            "speak next or say 'next speaker'."
        )
    if "research" in normalized:
        return (
            "You are the researcher. Contribute evidence, relevant patterns, concrete options, and any "
            "missing facts worth checking. Add new information only; do not paraphrase prior speakers."
        )
    if "analyst" in normalized:
        return (
            "You are the analyst. Focus on tradeoffs, bottlenecks, risks, and decision logic. Challenge "
            "weak assumptions and clarify what would make a recommendation strong."
        )
    if normalized in {"coder", "builder", "engineer", "developer"} or any(
        token in normalized for token in ("build", "code", "engineer", "implement")
    ):
        return (
            "You are the implementation voice. Turn ideas into an operating model, execution plan, or "
            "practical build path. Be concrete about sequence, ownership, and feasibility."
        )
    return (
        "You provide an alternate expert angle. Add distinct value, propose a concrete path forward, "
        "and avoid repeating the prior speaker."
    )


def _parse_meeting_status(raw_text: str, default_status: str) -> tuple[str, str]:
    import json
    import re

    text = (raw_text or "").strip()
    if not text:
        return default_status, ""

    fenced_match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        text = fenced_match.group(1).strip()

    try:
        data = json.loads(text)
    except Exception:
        data = None

    if isinstance(data, dict):
        status = str(data.get("status") or default_status).strip().lower()
        message = str(data.get("message") or "").strip()
        if status not in TERMINAL_MEETING_STATUSES | {"continue"}:
            status = default_status
        return status, message or raw_text.strip()

    status_match = re.search(r"(?im)^status\s*:\s*([a-z_]+)\s*$", text)
    message_match = re.search(r"(?ims)^message\s*:\s*(.+)$", text)
    status = status_match.group(1).strip().lower() if status_match else default_status
    if status not in TERMINAL_MEETING_STATUSES | {"continue"}:
        status = default_status

    if message_match:
        message = message_match.group(1).strip()
    else:
        message = re.sub(r"(?im)^status\s*:\s*[a-z_]+\s*$", "", text).strip()
        message = re.sub(r"(?im)^message\s*:\s*", "", message).strip()
    return status, message


def _meeting_artifact_markdown(objective: str, status: str, content: str) -> str:
    heading = {
        "needs_user_input": "Owner Input Needed",
        "needs_approval": "Approval Needed",
        "recommendation_ready": "Recommendation",
        "solved": "Resolution",
        "blocked": "Blocker",
        "looping": "Loop Detected",
    }.get(status, "Meeting Update")
    return (
        f"# {heading}\n\n"
        f"## Objective\n{objective.strip() or '(none noted)'}\n\n"
        f"## Outcome\n{content.strip() or '(none noted)'}\n"
    )


def _get_or_create_agent_bot_user(db: Session, agent_name: str) -> ChatUser:
    from app.api.routes.chat.agents import get_agent as _get_agent

    username = "sparkbot" if agent_name == "sparkbot" else f"agent_{agent_name}"
    bot_user = db.exec(select(ChatUser).where(ChatUser.username == username)).scalar_one_or_none()
    if not bot_user:
        agent_info = _get_agent(agent_name) or {}
        emoji = str(agent_info.get("emoji") or "")
        display_name = f"{emoji} {agent_name.title()}".strip() if emoji else agent_name.title()
        bot_user = ChatUser(username=username, type=UserType.BOT, hashed_password="", bot_display_name=display_name)
        db.add(bot_user)
        db.commit()
        db.refresh(bot_user)
    return bot_user


def load_meeting_manifest(session: Session, room_id: uuid.UUID) -> dict[str, Any] | None:
    for artifact in get_chat_meeting_artifacts(session=session, room_id=room_id, limit=20):
        meta = artifact.meta_json or {}
        if isinstance(meta, dict) and meta.get("source") == MEETING_MANIFEST_SOURCE:
            return meta
    return None


def _latest_meeting_status(session: Session, room_id: uuid.UUID) -> str | None:
    for artifact in get_chat_meeting_artifacts(session=session, room_id=room_id, limit=20):
        meta = artifact.meta_json or {}
        if not isinstance(meta, dict):
            continue
        status = str(meta.get("meeting_status") or "").strip().lower()
        if status:
            return status
    return None


def _latest_owner_objective(session: Session, room_id: uuid.UUID, fallback: str) -> str:
    messages, _, _ = get_chat_messages(session=session, room_id=room_id, limit=80)
    for message in reversed(messages):
        if str(message.sender_type).upper() != "HUMAN":
            continue
        content = (message.content or "").strip()
        if not content or content.startswith("/"):
            continue
        if message.meta_json and message.meta_json.get("breakglass_pin_submission"):
            continue
        return content
    return fallback


async def run_meeting_heartbeat(
    *,
    session: Session,
    room_id: str,
    user_id: str,
) -> dict[str, Any]:
    from app.api.routes.chat.agents import get_agent as _get_agent_info
    from app.api.routes.chat.llm import SYSTEM_PROMPT as LLM_SYSTEM_PROMPT
    from app.api.routes.chat.llm import get_model, stream_chat_with_tools

    room_uuid = uuid.UUID(room_id)
    user_uuid = uuid.UUID(user_id)
    room = get_chat_room_by_id(session, room_uuid)
    current_user = get_chat_user_by_id(session, user_uuid)
    if not room or not current_user:
        return {
            "tool": HEARTBEAT_TOOL_NAME,
            "heartbeat_status": "blocked",
            "summary": "Meeting heartbeat could not run because the room or owner could not be loaded.",
            "terminal": True,
        }

    if not room.meeting_mode_enabled:
        return {
            "tool": HEARTBEAT_TOOL_NAME,
            "heartbeat_status": "solved",
            "summary": "Meeting heartbeat stopped because meeting mode is disabled for this room.",
            "terminal": True,
        }

    manifest = load_meeting_manifest(session, room_uuid) or {}
    participant_records = list(manifest.get("participants") or [])
    participants = [
        str(item.get("handle") or "").strip().lower()
        for item in participant_records
        if isinstance(item, dict) and str(item.get("handle") or "").strip()
    ]
    participants = [p for index, p in enumerate(participants) if p and participants.index(p) == index]
    if not participants:
        return {
            "tool": HEARTBEAT_TOOL_NAME,
            "heartbeat_status": "blocked",
            "summary": "Meeting heartbeat stopped because no persisted participant handles were found for this room.",
            "terminal": True,
        }

    latest_status = _latest_meeting_status(session, room_uuid)
    if latest_status in TERMINAL_MEETING_STATUSES:
        return {
            "tool": HEARTBEAT_TOOL_NAME,
            "heartbeat_status": latest_status,
            "summary": f"Meeting heartbeat stopped because the latest room status is already `{latest_status}`.",
            "terminal": True,
        }

    objective = _latest_owner_objective(
        session,
        room_uuid,
        fallback=str(manifest.get("room_name") or room.name or "Roundtable"),
    )
    history_msgs, _, _ = get_chat_messages(session=session, room_id=room_uuid, limit=40)
    discussion_history: list[dict[str, str]] = []
    for message in history_msgs:
        role = "assistant" if str(message.sender_type).upper() == "BOT" else "user"
        discussion_history.append({"role": role, "content": message.content})

    memories = get_user_memories(session, current_user.id)
    guardian_suite = get_guardian_suite()
    try:
        memory_context = guardian_suite.memory.build_memory_context(
            user_id=str(current_user.id),
            room_id=str(room_uuid),
            query=objective,
        )
    except Exception:
        memory_context = ""

    user_is_operator = guardian_suite.auth.is_operator_identity(
        username=current_user.username,
        user_type=current_user.type,
    )
    user_is_privileged = guardian_suite.auth.is_operator_privileged(str(current_user.id))

    kickoff_user = _get_or_create_agent_bot_user(session, "sparkbot")
    kickoff_message = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=kickoff_user.id,
        content="Hourly heartbeat: continuing the autonomous meeting from the current state.",
        sender_type="BOT",
        meta_json={"meeting_heartbeat": True, "source": MEETING_HEARTBEAT_SOURCE},
    )

    def _lookup_agent_info(agent_handle: str) -> Optional[dict[str, Any]]:
        if agent_handle == "sparkbot":
            return {"emoji": "🤖", "system_prompt": LLM_SYSTEM_PROMPT}
        return _get_agent_info(agent_handle)

    async def _run_agent_turn(
        *,
        participant_handle: str,
        phase_prompt: str,
        chair_handle: str,
        parse_status: bool = False,
        default_status: str = "recommendation_ready",
    ) -> dict[str, Any]:
        agent_info = _lookup_agent_info(participant_handle)
        if not agent_info:
            return {"content": "", "status": None, "halted": False, "failed": True}

        p_base = str(agent_info.get("system_prompt") or LLM_SYSTEM_PROMPT)
        if room.persona and room.persona.strip():
            p_base = room.persona.strip() + "\n\n" + p_base
        role_instruction = _meeting_role_instruction(participant_handle, chair=participant_handle == chair_handle)
        p_base += (
            "\n\n## Autonomous roundtable protocol\n"
            "This is an autonomous meeting room. Continue the discussion without waiting for the owner "
            "between turns. One participant speaks at a time, but the handoff is automatic. Avoid filler, "
            "avoid generic agreement, and do not ask for the next speaker.\n\n"
            f"## Your role\n{role_instruction}"
        )
        if memories:
            mem_block = "\n".join(f"- {m.fact}" for m in memories)
            p_system = p_base + f"\n\n## What you know about this user:\n{mem_block}"
        else:
            p_system = p_base
        if memory_context:
            p_system += f"\n\n{memory_context}"

        agent_full_text = ""
        agent_routing_payload = None
        stop_event = None
        turn_messages = [{"role": "system", "content": p_system}] + discussion_history + [
            {
                "role": "user",
                "content": (
                    f"Meeting objective from the owner:\n{objective.strip()}\n\n"
                    f"{phase_prompt}"
                ).strip(),
            }
        ]
        last_error: Exception | None = None
        for attempt in range(MEETING_TURN_RETRY_ATTEMPTS):
            try:
                async for event in stream_chat_with_tools(
                    turn_messages,
                    user_id=str(current_user.id),
                    db_session=session,
                    room_id=str(room_uuid),
                    agent_name=participant_handle,
                    room_execution_allowed=room.execution_allowed,
                    is_operator=user_is_operator,
                    is_privileged=user_is_privileged,
                ):
                    if event["type"] == "token":
                        agent_full_text += event["token"]
                    elif event["type"] == "routing":
                        agent_routing_payload = event.get("payload")
                    elif event["type"] in ("confirm_required", "privileged_required"):
                        stop_event = event
                        break
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if agent_full_text or not _is_retryable_meeting_error(exc) or attempt >= MEETING_TURN_RETRY_ATTEMPTS - 1:
                    break
                await asyncio.sleep(MEETING_TURN_RETRY_DELAY_SECONDS * (attempt + 1))
        if last_error is not None:
            return {"content": "", "status": "blocked", "halted": False, "failed": True}

        if stop_event:
            return {"content": "", "status": "needs_approval", "halted": True}

        public_text = agent_full_text.strip()
        meeting_status = None
        if parse_status:
            meeting_status, public_text = _parse_meeting_status(agent_full_text, default_status=default_status)

        if not public_text:
            return {"content": "", "status": meeting_status, "halted": False, "failed": True}

        label = _agent_label(participant_handle, agent_info)
        bot_user = _get_or_create_agent_bot_user(session, participant_handle)
        meta_json: dict[str, Any] = {"agent": participant_handle, "source": MEETING_HEARTBEAT_SOURCE}
        if agent_routing_payload:
            meta_json["token_guardian"] = agent_routing_payload
        if meeting_status:
            meta_json["meeting_status"] = meeting_status
        create_chat_message(
            session=session,
            room_id=room_uuid,
            sender_id=bot_user.id,
            content=public_text,
            sender_type="BOT",
            reply_to_id=kickoff_message.id,
            meta_json=meta_json,
        )
        try:
            guardian_suite.memory.remember_chat_message(
                user_id=str(current_user.id),
                room_id=str(room_uuid),
                role="assistant",
                content=public_text,
            )
        except Exception:
            pass
        if meeting_status and meeting_status != "continue":
            try:
                create_chat_meeting_artifact(
                    session=session,
                    room_id=room_uuid,
                    created_by_user_id=current_user.id,
                    type="notes",
                    content_markdown=_meeting_artifact_markdown(objective, meeting_status, public_text),
                    meta_json={
                        "source": MEETING_HEARTBEAT_SOURCE,
                        "agent": participant_handle,
                        "meeting_status": meeting_status,
                    },
                )
            except Exception:
                pass
        discussion_history.append({"role": "assistant", "content": f"{label}: {public_text}"})
        return {"content": public_text, "status": meeting_status, "halted": False, "failed": False}

    chair_handle = "sparkbot" if "sparkbot" in participants else participants[0]
    specialists = [handle for handle in participants if handle != chair_handle]
    minimum_turns = 2 if not specialists else min(10, max(4, (len(participants) * 2) + 1))
    room_cap = max(int(room.meeting_mode_max_bot_msgs_per_min or 0), 0)
    max_bot_turns = min(10, max(minimum_turns, room_cap))
    turns_used = 0

    opening_result = await _run_agent_turn(
        participant_handle=chair_handle,
        phase_prompt=(
            "Current phase: heartbeat framing.\n"
            "Pick up from the current room state, state what changed or remains open, and set the next decision focus. "
            "Keep it concise and actionable. Do not ask for the next speaker."
        ),
        chair_handle=chair_handle,
    )
    turns_used += 1
    if opening_result.get("halted"):
        return {
            "tool": HEARTBEAT_TOOL_NAME,
            "heartbeat_status": opening_result.get("status") or "needs_approval",
            "summary": "Meeting heartbeat paused because a privileged or confirm-required action needs the owner.",
            "terminal": True,
            "participants": participants,
        }

    for participant_handle in specialists:
        if turns_used >= max_bot_turns - 1:
            break
        gather_result = await _run_agent_turn(
            participant_handle=participant_handle,
            phase_prompt=(
                "Current phase: heartbeat perspective gathering.\n"
                "Contribute the most useful new view from your role based on the current room state. "
                "Add only distinct evidence, tradeoffs, or execution detail. End with a concrete takeaway."
            ),
            chair_handle=chair_handle,
        )
        turns_used += 1
        if gather_result.get("halted"):
            return {
                "tool": HEARTBEAT_TOOL_NAME,
                "heartbeat_status": gather_result.get("status") or "needs_approval",
                "summary": "Meeting heartbeat paused because a privileged or confirm-required action needs the owner.",
                "terminal": True,
                "participants": participants,
            }

    synthesis_result = await _run_agent_turn(
        participant_handle=chair_handle,
        phase_prompt=(
            "Current phase: heartbeat synthesis.\n"
            "Assess whether the room should continue or stop. Return exactly in this format:\n"
            "STATUS: <continue|needs_user_input|needs_approval|recommendation_ready|solved|blocked|looping>\n"
            "MESSAGE:\n"
            "## Recommendation\n"
            "<one clear recommendation>\n\n"
            "## Action Plan\n"
            "- [ ] <step 1>\n"
            "- [ ] <step 2>\n"
            "- [ ] <step 3>\n\n"
            "## Owner Input Or Approval\n"
            "- <single approval, decision, or 'none'>\n\n"
            "## Stop Reason\n"
            "- <why continue or stop now>\n"
        ),
        chair_handle=chair_handle,
        parse_status=True,
        default_status="recommendation_ready",
    )
    turns_used += 1
    if synthesis_result.get("halted"):
        final_status = synthesis_result.get("status") or "needs_approval"
        final_text = "Meeting heartbeat paused because a privileged or confirm-required action needs the owner."
    else:
        final_status = synthesis_result.get("status") or "recommendation_ready"
        final_text = synthesis_result.get("content") or opening_result.get("content") or "Heartbeat completed."

    if final_status == "continue" and specialists and turns_used < max_bot_turns:
        for participant_handle in specialists:
            if turns_used >= max_bot_turns - 1:
                break
            refine_result = await _run_agent_turn(
                participant_handle=participant_handle,
                phase_prompt=(
                    "Current phase: heartbeat refinement.\n"
                    "Challenge weak assumptions, missing constraints, or better alternatives in the current direction. "
                    "Add only non-duplicative value and keep it tight."
                ),
                chair_handle=chair_handle,
            )
            turns_used += 1
            if refine_result.get("halted"):
                final_status = refine_result.get("status") or "needs_approval"
                final_text = "Meeting heartbeat paused because a privileged or confirm-required action needs the owner."
                break

        if final_status == "continue":
            final_result = await _run_agent_turn(
                participant_handle=chair_handle,
                phase_prompt=(
                    "Current phase: final heartbeat synthesis.\n"
                    "Return exactly in this format:\n"
                    "STATUS: <needs_user_input|needs_approval|recommendation_ready|solved|blocked|looping>\n"
                    "MESSAGE:\n"
                    "## Recommendation\n"
                    "<best recommendation>\n\n"
                    "## Action Plan\n"
                    "- [ ] <specific next action>\n"
                    "- [ ] <specific next action>\n"
                    "- [ ] <specific next action>\n\n"
                    "## Owners\n"
                    "- <owner> — <responsibility>\n\n"
                    "## Open Questions / Approval Needed\n"
                    "- <item or 'none'>\n\n"
                    "## Stop Reason\n"
                    "- <why the room is stopping>\n"
                ),
                chair_handle=chair_handle,
                parse_status=True,
                default_status="recommendation_ready",
            )
            final_status = final_result.get("status") or "recommendation_ready"
            final_text = final_result.get("content") or final_text

    notes: dict[str, Any] = {}
    try:
        notes = await generate_meeting_notes(
            session=session,
            room_id=room_uuid,
            user_id=current_user.id,
            model=get_model(str(current_user.id)),
        )
    except Exception:
        notes = {}
    summary = (
        f"Hourly meeting heartbeat completed with status `{final_status}`.\n\n"
        f"{final_text.strip() or '(no summary produced)'}"
    )
    return {
        "tool": HEARTBEAT_TOOL_NAME,
        "heartbeat_status": final_status,
        "summary": summary,
        "terminal": final_status in TERMINAL_MEETING_STATUSES,
        "participants": participants,
        "turns_used": turns_used,
        "notes_artifact_id": notes.get("id"),
    }
