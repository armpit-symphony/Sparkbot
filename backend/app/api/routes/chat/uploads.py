"""
File upload route for Sparkbot chat.

Handles image and file uploads, stores them locally, and streams
AI vision analysis back as SSE (same protocol as /messages/stream).
"""
import json
import os
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
import litellm
from sqlalchemy import select

from app.api.deps import CurrentChatUser, SessionDep, get_db
from app.crud import create_chat_message, get_chat_messages, get_chat_room_member
from app.models import ChatUser, RoomRole, UserType
from app.services.image_vision import build_vision_user_message, detect_image_type, resolve_vision_model

router = APIRouter(tags=["chat-uploads"])

_upload_root = os.getenv("SPARKBOT_UPLOAD_DIR", "").strip()
if _upload_root:
    UPLOAD_DIR = Path(_upload_root).expanduser()
else:
    UPLOAD_DIR = Path(__file__).resolve().parents[5] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("/rooms/{room_id}/uploads/{file_id}/{filename}")
def serve_upload(
    room_id: UUID,
    file_id: str,
    filename: str,
    session: SessionDep,
    current_user: CurrentChatUser,
):
    """Serve a previously uploaded file."""
    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    # Validate file_id is a well-formed UUID to prevent path traversal.
    try:
        uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="File not found")

    safe_name = Path(filename).name  # strip any path traversal
    file_path = UPLOAD_DIR / file_id / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Determine content type from magic bytes, not the stored filename.
    with file_path.open("rb") as handle:
        raw = handle.read(16)
    detected_mime = detect_image_type(raw)

    if detected_mime:
        # Known image: serve inline so the browser can render it in chat.
        return FileResponse(
            file_path,
            media_type=detected_mime,
            headers={"Cache-Control": "private, max-age=3600"},
        )
    else:
        # Unknown / non-image: force download to prevent inline execution.
        return FileResponse(
            file_path,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "Cache-Control": "private, max-age=3600",
            },
        )


@router.post("/rooms/{room_id}/upload")
async def upload_file(
    room_id: UUID,
    session: SessionDep,
    current_user: CurrentChatUser,
    file: UploadFile = File(...),
    caption: str = Form(""),
):
    """Upload a file to a room.

    - Images → streamed AI vision analysis (SSE)
    - Other files → saved locally, acknowledgement SSE

    Same SSE protocol as /messages/stream:
      data: {"type": "human_message", "message_id": "..."}
      data: {"type": "token", "token": "..."}
      data: {"type": "done", "message_id": "..."}
      data: {"type": "error", "error": "..."}
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    membership = get_chat_room_member(session, room_id, current_user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    if membership.role == RoomRole.VIEWER:
        raise HTTPException(status_code=403, detail="VIEWERs cannot upload files")

    # Read and size-check file
    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    # Use magic bytes to determine image type — never trust the client Content-Type header.
    detected_mime = detect_image_type(data)
    is_image = detected_mime is not None
    # Use the server-verified MIME for downstream processing; fall back to octet-stream.
    content_type = detected_mime or "application/octet-stream"
    filename_safe = Path(file.filename or "upload").name

    # Save to disk
    file_id = str(uuid.uuid4())
    dest_dir = UPLOAD_DIR / file_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    (dest_dir / filename_safe).write_bytes(data)

    # Build public URL (served through nginx /api/ → 8091)
    file_url = f"/api/v1/chat/rooms/{room_id}/uploads/{file_id}/{filename_safe}"

    # Human message content: markdown image or file link + optional caption
    if is_image:
        human_content = f"![{filename_safe}]({file_url})"
        if caption.strip():
            human_content += f"\n\n{caption.strip()}"
    else:
        human_content = f"📎 [{filename_safe}]({file_url})"
        if caption.strip():
            human_content += f"\n\n{caption.strip()}"

    # Save human message
    human_msg = create_chat_message(
        session=session,
        room_id=room_id,
        sender_id=current_user.id,
        content=human_content,
        sender_type=current_user.type.value if hasattr(current_user.type, "value") else "HUMAN",
    )
    human_msg_id = str(human_msg.id)
    human_msg_uuid = human_msg.id

    # Build conversation history for context
    history_msgs, _, _ = get_chat_messages(session=session, room_id=room_id, limit=10)
    text_history = []
    for m in history_msgs:
        if str(m.id) == human_msg_id:
            continue
        role = "assistant" if str(m.sender_type).upper() == "BOT" else "user"
        text_history.append({"role": role, "content": m.content})

    async def event_stream():
        yield f"data: {json.dumps({'type': 'human_message', 'message_id': human_msg_id})}\n\n"

        full_text = ""
        try:
            from app.api.routes.chat.llm import SYSTEM_PROMPT as LLM_SYSTEM_PROMPT, get_model

            if is_image:
                vision_model = resolve_vision_model(get_model(str(current_user.id)))
                if not vision_model:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'No configured vision-capable model is available. Configure OpenAI, Gemini, Claude, or a vision OpenRouter model in Controls and try again.'})}\n\n"
                    return
                user_message: dict = build_vision_user_message(
                    data,
                    content_type,
                    caption.strip() or "Describe this image and note anything relevant.",
                )
            else:
                vision_model = get_model(str(current_user.id))
                user_message = {
                    "role": "user",
                    "content": f"I've uploaded a file: **{filename_safe}**. {caption.strip() or 'Please acknowledge the upload.'}",
                }

            messages = [{"role": "system", "content": LLM_SYSTEM_PROMPT}] + text_history + [user_message]

            response = await litellm.acompletion(
                model=vision_model,
                messages=messages,
                temperature=0.2,
                stream=True,
                max_tokens=500,
            )
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full_text += delta
                    yield f"data: {json.dumps({'type': 'token', 'token': delta})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
            return

        # Save bot reply
        try:
            db_gen = get_db()
            db = next(db_gen)
            try:
                bot_user = db.exec(select(ChatUser).where(ChatUser.username == "sparkbot")).scalar_one_or_none()
                if not bot_user:
                    bot_user = ChatUser(
                        username="sparkbot",
                        type=UserType.BOT,
                        is_active=True,
                        hashed_password=None,
                        bot_display_name="Sparkbot",
                        bot_slug="sparkbot",
                    )
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
            finally:
                db_gen.close()
            yield f"data: {json.dumps({'type': 'done', 'message_id': bot_reply_id, 'file_url': file_url})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': f'Save failed: {e}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
