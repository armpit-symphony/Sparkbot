"""
Voice endpoints for Sparkbot chat.

Handles:
  - POST /rooms/{room_id}/voice  — audio → Whisper transcription → SSE stream (same protocol as /messages/stream)
  - POST /voice/tts              — text → audio/mpeg stream (OpenAI TTS)

Both endpoints require authentication (same cookie-first deps as all other routes).
Room membership is enforced on the per-room endpoint. All policy/tool/guardian
logic fires identically because transcribed text enters stream_chat_with_tools()
unchanged.
"""
import io
import json
import os
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentChatUser, SessionDep, get_db
from app.crud import create_chat_message, get_chat_messages, get_chat_room_member
from app.models import ChatUser, RoomRole, UserType

router = APIRouter(tags=["chat-voice"])

MAX_AUDIO_SIZE = 5 * 1024 * 1024  # 5 MB — audio recordings are small


class TTSRequest(BaseModel):
    text: str


async def _transcribe(audio_bytes: bytes, filename: str) -> str:
    """Send audio to Whisper and return the transcript."""
    import openai

    client = openai.AsyncOpenAI()
    buf = io.BytesIO(audio_bytes)
    buf.name = filename or "recording.webm"  # extension gives Whisper the format hint
    result = await client.audio.transcriptions.create(model="whisper-1", file=buf)
    return result.text


@router.post("/rooms/{room_id}/voice")
async def voice_message(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    audio: UploadFile = File(...),
):
    """Accept an audio recording, transcribe it, and stream the bot reply as SSE.

    SSE protocol (superset of /messages/stream):
      data: {"type": "transcription",  "text": "..."}          — voice-only, heard text
      data: {"type": "human_message",  "message_id": "..."}
      data: {"type": "token",          "token": "..."}
      data: {"type": "tool_start",     "tool": "...", "input": {...}}
      data: {"type": "tool_done",      "tool": "...", "result": "..."}
      data: {"type": "confirm_required", ...}
      data: {"type": "done",           "message_id": "..."}
      data: {"type": "error",          "error": "..."}
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot send voice messages")

    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(status_code=413, detail="Audio too large (max 5 MB)")
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty audio file")

    filename = audio.filename or "recording.webm"

    # Transcribe synchronously before opening the SSE stream so we have the text
    # to save as the human message and pass to the LLM.
    try:
        transcript = await _transcribe(audio_bytes, filename)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {e}")

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="No speech detected in audio")

    # Save human message with transcription as content
    human_msg = create_chat_message(
        session=session,
        room_id=room_id,
        sender_id=current_user.id,
        content=transcript.strip(),
        sender_type=current_user.type.value if hasattr(current_user.type, "value") else "HUMAN",
    )
    human_msg_id = str(human_msg.id)
    human_msg_uuid = human_msg.id

    # Build last-10-message history (same pattern as uploads.py / rooms.py)
    history_msgs, _, _ = get_chat_messages(session=session, room_id=room_id, limit=10)
    openai_history = []
    for m in history_msgs:
        if str(m.id) == human_msg_id:
            continue
        role = "assistant" if str(m.sender_type).upper() == "BOT" else "user"
        openai_history.append({"role": role, "content": m.content})
    # Append the just-saved human turn
    openai_history.append({"role": "user", "content": transcript.strip()})

    from app.api.routes.chat.llm import SYSTEM_PROMPT as LLM_SYSTEM_PROMPT
    from app.crud import get_user_memories

    memories = get_user_memories(session, current_user.id)
    if memories:
        mem_block = "\n".join(f"- {m.fact}" for m in memories)
        system_prompt = LLM_SYSTEM_PROMPT + f"\n\n## What you know about this user:\n{mem_block}"
    else:
        system_prompt = LLM_SYSTEM_PROMPT

    user_id_str = str(current_user.id)

    # Capture room execution_allowed before closing the route session
    from app.crud import get_chat_room_by_id
    room = get_chat_room_by_id(session, room_id)
    room_execution_allowed = room.execution_allowed if room else None

    async def event_stream():
        # Immediately tell the client what was heard
        yield f"data: {json.dumps({'type': 'transcription', 'text': transcript.strip()})}\n\n"
        yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"

        full_text = ""
        awaiting_confirmation = False
        try:
            from app.api.routes.chat.llm import stream_chat_with_tools

            db = next(get_db())
            async for event in stream_chat_with_tools(
                [{"role": "system", "content": system_prompt}] + openai_history,
                user_id=user_id_str,
                db_session=db,
                room_id=str(room_id),
                room_execution_allowed=room_execution_allowed,
            ):
                if event["type"] == "token":
                    full_text += event["token"]
                    yield f"data: {json.dumps({'type': 'token', 'token': event['token']})}\n\n"
                elif event["type"] in ("tool_start", "tool_done"):
                    yield f"data: {json.dumps(event)}\n\n"
                elif event["type"] == "confirm_required":
                    awaiting_confirmation = True
                    yield f"data: {json.dumps(event)}\n\n"
                    break
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            return

        if awaiting_confirmation:
            db.close()
            return

        # Save bot reply
        try:
            bot_user = db.exec(
                select(ChatUser).where(ChatUser.username == "sparkbot")
            ).scalar_one_or_none()
            if not bot_user:
                bot_user = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
                db.add(bot_user)
                db.commit()
                db.refresh(bot_user)
            bot_reply = create_chat_message(
                session=db,
                room_id=room_id,
                sender_id=bot_user.id,
                content=full_text,
                sender_type="BOT",
                reply_to_id=human_msg_uuid,
            )
            bot_reply_id = str(bot_reply.id)
            db.close()
            yield f"data: {json.dumps({'type': 'done', 'message_id': bot_reply_id})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Save failed: {e}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/voice/tts")
async def tts(body: TTSRequest, current_user: CurrentChatUser):
    """Convert text to speech using OpenAI TTS.

    Returns audio/mpeg stream. Configure voice/model via env vars:
      SPARKBOT_TTS_VOICE — alloy (default) | echo | fable | onyx | nova | shimmer
      SPARKBOT_TTS_MODEL — tts-1 (default, fast) | tts-1-hd (higher quality)
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not body.text or not body.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")

    import openai

    voice = os.getenv("SPARKBOT_TTS_VOICE", "alloy")
    model = os.getenv("SPARKBOT_TTS_MODEL", "tts-1")
    client = openai.AsyncOpenAI()

    try:
        response = await client.audio.speech.create(
            model=model,
            voice=voice,
            input=body.text.strip(),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")

    return StreamingResponse(response.iter_bytes(), media_type="audio/mpeg")
