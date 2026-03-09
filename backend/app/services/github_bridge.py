from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
from sqlalchemy import select
from sqlmodel import Session

from app.crud import (
    add_chat_room_member,
    create_audit_log,
    create_chat_message,
    create_chat_room,
    create_chat_user,
    get_chat_messages,
    get_chat_room_by_id,
    get_chat_user_by_id,
    get_chat_user_by_username,
    get_user_memories,
)
from app.models import ChatUser, UserType

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_DELIVERY_TTL_SECONDS = 300.0
_seen_deliveries: dict[str, float] = {}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS github_links (
  thread_key TEXT PRIMARY KEY,
  room_id TEXT NOT NULL,
  repo_full_name TEXT NOT NULL,
  issue_number INTEGER NOT NULL,
  thread_title TEXT,
  pending_confirm_id TEXT,
  pending_confirm_tool TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_github_links_room_id ON github_links(room_id);
CREATE INDEX IF NOT EXISTS idx_github_links_repo_issue ON github_links(repo_full_name, issue_number);
"""


@dataclass(frozen=True)
class GitHubLink:
    thread_key: str
    room_id: str
    repo_full_name: str
    issue_number: int
    thread_title: Optional[str]
    pending_confirm_id: Optional[str]
    pending_confirm_tool: Optional[str]
    created_at: str
    updated_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _enabled() -> bool:
    return _is_truthy(os.getenv("GITHUB_BRIDGE_ENABLED", "false"))


def _github_token() -> str:
    return os.getenv("GITHUB_TOKEN", "").strip()


def _webhook_secret() -> str:
    return os.getenv("GITHUB_WEBHOOK_SECRET", "").strip()


def _bot_login() -> str:
    return os.getenv("GITHUB_BOT_LOGIN", "sparkbot").strip() or "sparkbot"


def _default_repo() -> str:
    return os.getenv("GITHUB_DEFAULT_REPO", "").strip()


def _allowed_repos() -> set[str]:
    return {
        item.strip().lower()
        for item in os.getenv("GITHUB_ALLOWED_REPOS", "").split(",")
        if item.strip()
    }


def _configured() -> bool:
    return bool(_github_token() and _webhook_secret())


def _data_root() -> Path:
    root = os.getenv("SPARKBOT_GUARDIAN_DATA_DIR", "").strip()
    if root:
        return Path(root).expanduser()
    return Path(__file__).resolve().parents[2] / "data" / "guardian"


def _db_path() -> Path:
    path = _data_root() / "github_bridge.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _init_store() -> None:
    with _conn() as conn:
        conn.executescript(_SCHEMA)


def _thread_key(repo_full_name: str, issue_number: int) -> str:
    return f"{repo_full_name.strip().lower()}#{issue_number}"


def _get_link(thread_key: str) -> Optional[GitHubLink]:
    _init_store()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM github_links WHERE thread_key = ?",
            (thread_key,),
        ).fetchone()
    if not row:
        return None
    return GitHubLink(**dict(row))


def _linked_threads_for_room(room_id: str) -> list[GitHubLink]:
    _init_store()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM github_links WHERE room_id = ? ORDER BY created_at ASC",
            (room_id,),
        ).fetchall()
    return [GitHubLink(**dict(row)) for row in rows]


def _upsert_link(
    *,
    thread_key: str,
    room_id: str,
    repo_full_name: str,
    issue_number: int,
    thread_title: str | None,
) -> GitHubLink:
    _init_store()
    now = _now_iso()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO github_links (
              thread_key, room_id, repo_full_name, issue_number, thread_title,
              pending_confirm_id, pending_confirm_tool, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?)
            ON CONFLICT(thread_key) DO UPDATE SET
              room_id = excluded.room_id,
              repo_full_name = excluded.repo_full_name,
              issue_number = excluded.issue_number,
              thread_title = excluded.thread_title,
              updated_at = excluded.updated_at
            """,
            (
                thread_key,
                room_id,
                repo_full_name,
                issue_number,
                (thread_title or "").strip() or None,
                now,
                now,
            ),
        )
    link = _get_link(thread_key)
    if not link:
        raise RuntimeError("Failed to persist GitHub room link")
    return link


def _set_pending_confirmation(thread_key: str, confirm_id: str, tool_name: str) -> None:
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE github_links
            SET pending_confirm_id = ?, pending_confirm_tool = ?, updated_at = ?
            WHERE thread_key = ?
            """,
            (confirm_id, tool_name, _now_iso(), thread_key),
        )


def _clear_pending_confirmation(thread_key: str) -> None:
    _init_store()
    with _conn() as conn:
        conn.execute(
            """
            UPDATE github_links
            SET pending_confirm_id = NULL, pending_confirm_tool = NULL, updated_at = ?
            WHERE thread_key = ?
            """,
            (_now_iso(), thread_key),
        )


def get_status() -> dict[str, Any]:
    _init_store()
    with _conn() as conn:
        count_row = conn.execute("SELECT COUNT(*) FROM github_links").fetchone()
    allowed = sorted(_allowed_repos())
    return {
        "configured": _configured(),
        "enabled": _enabled(),
        "bot_login": _bot_login(),
        "default_repo": _default_repo(),
        "allowed_repos": allowed,
        "allowed_repos_count": len(allowed),
        "linked_threads": int(count_row[0]) if count_row else 0,
        "webhook_path": "/api/v1/chat/github/events",
        "data_path": str(_db_path()),
    }


def verify_signature(body: bytes, signature: str) -> bool:
    secret = _webhook_secret()
    if not secret:
        return False
    if not signature.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def mark_delivery_seen(delivery_id: str) -> bool:
    if not delivery_id:
        return True
    now = time.time()
    stale = [key for key, seen_at in _seen_deliveries.items() if now - seen_at > _DELIVERY_TTL_SECONDS]
    for key in stale:
        _seen_deliveries.pop(key, None)
    if delivery_id in _seen_deliveries:
        return False
    _seen_deliveries[delivery_id] = now
    return True


def _repo_allowed(repo_full_name: str) -> bool:
    allowed = _allowed_repos()
    if not allowed:
        return True
    return repo_full_name.strip().lower() in allowed


def _github_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {_github_token()}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def _post_issue_comment(repo_full_name: str, issue_number: int, text: str) -> None:
    content = (text or "").strip()
    if not content or not _github_token():
        return
    if len(content) > 60000:
        content = content[:59900].rstrip() + "\n\n[truncated]"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{_GITHUB_API}/repos/{repo_full_name}/issues/{issue_number}/comments",
                headers=_github_headers(),
                json={"body": content},
            )
            response.raise_for_status()
    except Exception as exc:
        logger.warning(
            "[github] failed to post comment to %s#%s: %s",
            repo_full_name,
            issue_number,
            exc,
        )


async def _broadcast_room_message(
    room_id: str,
    message_id: str,
    content: str,
    sender_username: str,
    sender_type: str,
) -> None:
    try:
        from app.api.routes.chat.websocket import ws_manager

        await ws_manager.broadcast(
            room_id,
            {
                "type": "message",
                "payload": {
                    "id": message_id,
                    "room_id": room_id,
                    "content": content,
                    "sender_type": sender_type,
                    "sender": {"username": sender_username},
                    "created_at": _now_iso(),
                },
            },
        )
    except Exception:
        pass


def _find_or_create_bot_user(session: Session) -> ChatUser:
    bot_user = session.exec(select(ChatUser).where(ChatUser.username == "sparkbot")).scalar_one_or_none()
    if bot_user:
        return bot_user
    bot_user = ChatUser(username="sparkbot", type=UserType.BOT, hashed_password="")
    session.add(bot_user)
    session.commit()
    session.refresh(bot_user)
    return bot_user


def _github_username(login: str) -> str:
    normalized = re.sub(r"[^a-z0-9_.-]+", "-", (login or "").strip().lower()).strip("-")
    return f"github__{normalized or 'user'}"[:100]


def _safe_room_name(repo_full_name: str, issue_number: int, title: str) -> str:
    label = f"GitHub {repo_full_name} #{issue_number}"
    suffix = (title or "").strip()
    if not suffix:
        return label[:180]
    room_name = f"{label} - {suffix}"
    return room_name[:180]


def _find_or_create_github_user(session: Session, login: str) -> ChatUser:
    username = _github_username(login)
    user = get_chat_user_by_username(session, username)
    if user:
        return user
    return create_chat_user(session, username=username, user_type="HUMAN")


def _ensure_linked_room(
    session: Session,
    repo_full_name: str,
    issue_number: int,
    thread_title: str,
    actor_login: str,
) -> tuple[GitHubLink, ChatUser]:
    key = _thread_key(repo_full_name, issue_number)
    github_user = _find_or_create_github_user(session, actor_login)
    existing = _get_link(key)
    if existing:
        add_chat_room_member(session, uuid.UUID(existing.room_id), github_user.id, role="MEMBER")
        return (
            _upsert_link(
                thread_key=key,
                room_id=existing.room_id,
                repo_full_name=repo_full_name,
                issue_number=issue_number,
                thread_title=thread_title,
            ),
            github_user,
        )

    room = create_chat_room(
        session,
        name=_safe_room_name(repo_full_name, issue_number, thread_title),
        created_by=github_user.id,
        description=f"GitHub bridge thread for {repo_full_name}#{issue_number}",
    )
    return (
        _upsert_link(
            thread_key=key,
            room_id=str(room.id),
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            thread_title=thread_title,
        ),
        github_user,
    )


def _open_db_session(get_db: Callable[[], Any]) -> tuple[Session, Any]:
    db_gen = get_db()
    session = next(db_gen)
    return session, db_gen


def _close_db_session(db_gen: Any) -> None:
    try:
        db_gen.close()
    except Exception:
        pass


def _extract_command(body: str) -> tuple[str | None, str]:
    text = (body or "").strip()
    lower = text.lower()
    if lower in {"approve", "/approve"}:
        return "approve", ""
    if lower in {"deny", "cancel", "/deny", "/cancel"}:
        return "deny", ""

    bot_login = _bot_login().lower()
    prefixes = [
        "/sparkbot",
        "sparkbot:",
        f"@{bot_login}",
        f"{bot_login}:",
    ]
    for prefix in prefixes:
        if lower.startswith(prefix):
            prompt = text[len(prefix):].lstrip(" :,\n\t")
            return ("help", "") if not prompt else ("prompt", prompt)
    return None, ""


def _help_text() -> str:
    bot_login = _bot_login()
    return (
        "Sparkbot GitHub bridge commands:\n\n"
        f"- `/{bot_login}` is not required; use `/sparkbot your request` or `@{bot_login} your request`\n"
        "- `approve` confirms a pending tool action\n"
        "- `deny` cancels a pending tool action"
    )


async def _run_room_prompt(
    session: Session,
    room_id: str,
    user_id: str,
    content: str,
    *,
    thread_key: str,
    repo_full_name: str,
    issue_number: int,
    comment_url: str,
    actor_login: str,
) -> dict[str, Any]:
    from app.api.routes.chat.agents import get_agent, resolve_agent_from_message
    from app.api.routes.chat.llm import SYSTEM_PROMPT, stream_chat_with_tools
    from app.services.guardian.memory import build_memory_context, remember_chat_message

    room_uuid = uuid.UUID(room_id)
    user_uuid = uuid.UUID(user_id)
    room = get_chat_room_by_id(session, room_uuid)
    user = get_chat_user_by_id(session, user_uuid)
    if not room or not user:
        raise RuntimeError("Linked GitHub room or user no longer exists.")

    human_message = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=user_uuid,
        content=content,
        sender_type="HUMAN",
        meta_json={
            "source": "github",
            "github_thread_key": thread_key,
            "github_repo": repo_full_name,
            "github_issue_number": issue_number,
            "github_comment_url": comment_url,
            "github_actor": actor_login,
        },
    )
    await _broadcast_room_message(room_id, str(human_message.id), content, user.username, "HUMAN")

    agent_name, agent_content = resolve_agent_from_message(content)
    try:
        remember_chat_message(user_id=user_id, room_id=room_id, role="user", content=agent_content)
    except Exception:
        pass

    history_msgs, _, _ = get_chat_messages(session=session, room_id=room_uuid, limit=20)
    openai_history: list[dict[str, str]] = []
    for msg in history_msgs:
        if str(msg.id) == str(human_message.id):
            continue
        role = "assistant" if str(msg.sender_type).upper() == "BOT" else "user"
        openai_history.append({"role": role, "content": msg.content})
    openai_history.append({"role": "user", "content": agent_content})

    base_prompt = SYSTEM_PROMPT
    if agent_name:
        agent = get_agent(agent_name)
        if agent and agent.get("system_prompt"):
            base_prompt = agent["system_prompt"]

    memories = get_user_memories(session, user_uuid)
    if memories:
        mem_block = "\n".join(f"- {m.fact}" for m in memories)
        system_prompt = base_prompt + f"\n\n## What you know about this user:\n{mem_block}"
    else:
        system_prompt = base_prompt

    try:
        memory_context = build_memory_context(user_id=user_id, room_id=room_id, query=agent_content)
    except Exception:
        memory_context = ""
    if memory_context:
        system_prompt += f"\n\n{memory_context}"

    from app.services.guardian.auth import is_operator_privileged, is_operator_user_id
    full_text = ""
    async for event in stream_chat_with_tools(
        [{"role": "system", "content": system_prompt}] + openai_history,
        user_id=user_id,
        db_session=session,
        room_id=room_id,
        agent_name=agent_name,
        room_execution_allowed=room.execution_allowed,
        is_operator=is_operator_user_id(session, user_id),
        is_privileged=is_operator_privileged(user_id),
    ):
        event_type = event.get("type")
        if event_type == "token":
            full_text += str(event.get("token", ""))
        elif event_type == "confirm_required":
            confirm_id = str(event.get("confirm_id", ""))
            tool_name = str(event.get("tool", "tool"))
            _set_pending_confirmation(thread_key, confirm_id, tool_name)
            text = (
                f"Approval required for `{tool_name}`.\n\n"
                "Reply `approve` to continue or `deny` to cancel."
            )
            bot_user = _find_or_create_bot_user(session)
            bot_msg = create_chat_message(
                session=session,
                room_id=room_uuid,
                sender_id=bot_user.id,
                content=text,
                sender_type="BOT",
                meta_json={
                    "source": "github",
                    "github_thread_key": thread_key,
                    "github_repo": repo_full_name,
                    "github_issue_number": issue_number,
                    "confirm_required": True,
                },
            )
            await _broadcast_room_message(room_id, str(bot_msg.id), text, bot_user.username, "BOT")
            return {"kind": "confirm", "text": text, "confirm_id": confirm_id, "tool_name": tool_name}

    final_text = full_text.strip() or "I did not generate a response."
    bot_user = _find_or_create_bot_user(session)
    bot_msg = create_chat_message(
        session=session,
        room_id=room_uuid,
        sender_id=bot_user.id,
        content=final_text,
        sender_type="BOT",
        meta_json={
            "source": "github",
            "github_thread_key": thread_key,
            "github_repo": repo_full_name,
            "github_issue_number": issue_number,
        },
    )
    try:
        remember_chat_message(user_id=user_id, room_id=room_id, role="assistant", content=final_text)
    except Exception:
        pass
    await _broadcast_room_message(room_id, str(bot_msg.id), final_text, bot_user.username, "BOT")
    return {"kind": "reply", "text": final_text, "message_id": str(bot_msg.id)}


async def _execute_pending_confirmation(
    session: Session,
    room_id: str,
    user_id: str,
    confirm_id: str,
    *,
    thread_key: str,
) -> str:
    from app.api.routes.chat.llm import (
        consume_pending,
        mask_tool_result_for_external,
        redact_tool_call_for_audit,
        serialize_tool_args_for_audit,
    )
    from app.api.routes.chat.tools import execute_tool
    from app.services.guardian.auth import is_operator_privileged, is_operator_user_id
    from app.services.guardian.executive import exec_with_guard
    from app.services.guardian.memory import remember_tool_event
    from app.services.guardian.policy import decide_tool_use

    pending = consume_pending(confirm_id)
    if not pending:
        _clear_pending_confirmation(thread_key)
        return "Approval expired or is no longer valid."

    tool_name = str(pending.get("tool", ""))
    tool_args = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    room = get_chat_room_by_id(session, uuid.UUID(room_id))
    if not room:
        return "Linked room not found."

    decision = decide_tool_use(
        tool_name,
        tool_args,
        room_execution_allowed=room.execution_allowed,
        is_operator=is_operator_user_id(session, user_id),
        is_privileged=is_operator_privileged(user_id),
    )
    create_audit_log(
        session=session,
        tool_name="policy_decision",
        tool_input=json.dumps(
            {
                "tool_name": tool_name,
                "tool_args": json.loads(serialize_tool_args_for_audit(tool_name, tool_args)),
                "confirmed": True,
            }
        ),
        tool_result=decision.to_json(),
        user_id=uuid.UUID(user_id),
        room_id=uuid.UUID(room_id),
        model=None,
    )
    if decision.action == "deny":
        result = f"POLICY DENIED: {decision.reason}"
    else:
        result = await exec_with_guard(
            tool_name=tool_name,
            action_type=decision.action_type,
            expected_outcome=f"Confirmed GitHub execution for {tool_name}",
            perform_fn=lambda: execute_tool(
                tool_name,
                tool_args,
                user_id=user_id,
                session=session,
                room_id=room_id,
            ),
            metadata={"room_id": room_id, "user_id": user_id, "confirmed": True, "source": "github"},
        )

    result_text = mask_tool_result_for_external(tool_name, tool_args, result)
    redacted_input, redacted_result = redact_tool_call_for_audit(tool_name, tool_args, result)
    create_audit_log(
        session=session,
        tool_name=tool_name,
        tool_input=redacted_input,
        tool_result=redacted_result,
        user_id=uuid.UUID(user_id),
        room_id=uuid.UUID(room_id),
        model=None,
    )
    try:
        remember_tool_event(
            user_id=user_id,
            room_id=room_id,
            tool_name=tool_name,
            args=tool_args,
            result=redacted_result,
        )
    except Exception:
        pass

    bot_user = _find_or_create_bot_user(session)
    bot_msg = create_chat_message(
        session=session,
        room_id=uuid.UUID(room_id),
        sender_id=bot_user.id,
        content=result_text,
        sender_type="BOT",
        meta_json={"source": "github", "github_thread_key": thread_key, "confirmed": True},
    )
    await _broadcast_room_message(room_id, str(bot_msg.id), result_text, bot_user.username, "BOT")
    _clear_pending_confirmation(thread_key)
    return result_text


def _is_bot_sender(sender: dict[str, Any]) -> bool:
    login = str(sender.get("login", "")).strip().lower()
    sender_type = str(sender.get("type", "")).strip().lower()
    return sender_type == "bot" or (login and login == _bot_login().lower())


async def _handle_thread_command(
    *,
    get_db: Callable[[], Any],
    repo_full_name: str,
    issue_number: int,
    thread_title: str,
    actor_login: str,
    body: str,
    comment_url: str,
) -> None:
    if not _repo_allowed(repo_full_name):
        logger.info("[github] ignoring disallowed repo %s", repo_full_name)
        return

    action, prompt = _extract_command(body)
    if action is None:
        return

    session: Session
    db_gen: Any
    session, db_gen = _open_db_session(get_db)
    try:
        link, github_user = _ensure_linked_room(
            session,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            thread_title=thread_title,
            actor_login=actor_login,
        )
        if action == "help":
            await _post_issue_comment(repo_full_name, issue_number, _help_text())
            return
        if action == "deny":
            from app.api.routes.chat.llm import discard_pending

            if not link.pending_confirm_id:
                await _post_issue_comment(repo_full_name, issue_number, "There is no pending approval for this thread.")
                return
            discard_pending(link.pending_confirm_id)
            _clear_pending_confirmation(link.thread_key)
            await _post_issue_comment(repo_full_name, issue_number, "Pending approval denied.")
            return
        if action == "approve":
            if not link.pending_confirm_id:
                await _post_issue_comment(repo_full_name, issue_number, "There is no pending approval for this thread.")
                return
            result = await _execute_pending_confirmation(
                session,
                link.room_id,
                str(github_user.id),
                link.pending_confirm_id,
                thread_key=link.thread_key,
            )
            await _post_issue_comment(repo_full_name, issue_number, result)
            return

        result = await _run_room_prompt(
            session,
            link.room_id,
            str(github_user.id),
            prompt,
            thread_key=link.thread_key,
            repo_full_name=repo_full_name,
            issue_number=issue_number,
            comment_url=comment_url,
            actor_login=actor_login,
        )
        await _post_issue_comment(repo_full_name, issue_number, str(result.get("text", "")))
    finally:
        _close_db_session(db_gen)


async def handle_github_event(
    *,
    event_name: str,
    payload: dict[str, Any],
    get_db: Callable[[], Any],
) -> None:
    if not _enabled():
        return
    if not _configured():
        logger.warning("[github] bridge enabled but missing token or webhook secret")
        return

    try:
        if event_name == "issue_comment" and payload.get("action") == "created":
            comment = payload.get("comment") or {}
            issue = payload.get("issue") or {}
            repository = payload.get("repository") or {}
            sender = payload.get("sender") or {}
            if _is_bot_sender(sender):
                return
            await _handle_thread_command(
                get_db=get_db,
                repo_full_name=str(repository.get("full_name", "")).strip(),
                issue_number=int(issue.get("number") or 0),
                thread_title=str(issue.get("title", "")).strip(),
                actor_login=str(sender.get("login", "")).strip(),
                body=str(comment.get("body", "")),
                comment_url=str(comment.get("html_url", "")),
            )
            return

        if event_name == "pull_request_review_comment" and payload.get("action") == "created":
            comment = payload.get("comment") or {}
            pull_request = payload.get("pull_request") or {}
            repository = payload.get("repository") or {}
            sender = payload.get("sender") or {}
            if _is_bot_sender(sender):
                return
            await _handle_thread_command(
                get_db=get_db,
                repo_full_name=str(repository.get("full_name", "")).strip(),
                issue_number=int(pull_request.get("number") or 0),
                thread_title=str(pull_request.get("title", "")).strip(),
                actor_login=str(sender.get("login", "")).strip(),
                body=str(comment.get("body", "")),
                comment_url=str(comment.get("html_url", "")),
            )
            return
    except Exception as exc:
        logger.exception("[github] bridge event processing failed: %s", exc)


async def send_room_notification(room_id: str, text: str) -> None:
    for link in _linked_threads_for_room(room_id):
        await _post_issue_comment(link.repo_full_name, int(link.issue_number), text)
