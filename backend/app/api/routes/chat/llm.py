"""
Centralized LLM routing via litellm.

Replaces direct OpenAI SDK calls so any provider can be swapped
by changing a model string. Per-user model preferences stored in memory.
"""
import json
import os
import re
import time
import uuid as _uuid_module
from typing import AsyncGenerator

import litellm

litellm.drop_params = True  # ignore unsupported params instead of erroring

DEFAULT_MODEL = os.getenv("SPARKBOT_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

SYSTEM_PROMPT = (
    "You are Sparkbot, the assistant for Sparkpit Labs. "
    "Do not disclose internal model names/versions. "
    "If asked what model you are, say: 'I'm Sparkbot, your Sparkpit assistant.' "
    "Use available tools whenever they are relevant. "
    "Do not claim you lack the ability to access external systems if a matching tool is available. "
    "For Gmail, Google Drive, email, search, Slack, GitHub, Notion, Confluence, calendar, local server operations, service management, approved SSH host operations, and Task Guardian scheduling, prefer using the corresponding tool. "
    "For service status, diagnostics, memory, disk, listeners, processes, and logs, use read-only server tools. "
    "Use service management only for explicit start, stop, or restart requests. "
    "Use Task Guardian only for approved recurring read-only work such as inbox digests, PR checks, calendar lookups, and diagnostics. "
    "Never claim that a write action or service action completed unless the tool result explicitly says it succeeded. "
    "If a write tool requires confirmation, wait for confirmation instead of claiming the action already happened. "
    "If a requested integration is not configured or a tool returns an error, explain that concrete limitation clearly. "
    "Be concise and professional."
)

# Curated model list — only show what's actually usable given configured keys
AVAILABLE_MODELS: dict[str, str] = {
    "gpt-4o-mini":                   "GPT-4o Mini — fast, cost-effective (default)",
    "gpt-4o":                        "GPT-4o — most capable OpenAI model",
    "claude-3-5-haiku-20241022":     "Claude Haiku — fast Anthropic model",
    "claude-sonnet-4-5":             "Claude Sonnet — balanced Anthropic model",
    "gemini/gemini-2.0-flash":       "Gemini Flash — fast Google model",
    "groq/llama-3.3-70b-versatile":  "Llama 3.3 70B via Groq — very fast",
    "minimax/MiniMax-M2.5":          "MiniMax M2.5 — reasoning + tool calling (MINIMAX_API_KEY)",
}

# In-memory per-user model preferences  {user_id: model_name}
# Resets on service restart — good enough until DB persistence is added
_user_models: dict[str, str] = {}

# Pending confirmations: confirm_id -> {tool, args, user_id, room_id, created_at}
_pending: dict[str, dict] = {}
_PENDING_TTL = 600  # 10 minutes


def _pending_ttl_cleanup() -> None:
    now = time.time()
    stale = [k for k, v in _pending.items() if now - v["created_at"] > _PENDING_TTL]
    for k in stale:
        _pending.pop(k, None)


def consume_pending(confirm_id: str) -> dict | None:
    """Pop and return a pending confirmation entry, or None if not found/expired."""
    entry = _pending.pop(confirm_id, None)
    if entry and time.time() - entry["created_at"] > _PENDING_TTL:
        return None
    return entry


# ── Audit log redaction ───────────────────────────────────────────────────────

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|secret|token|api_key|apikey|access_key|credential|auth_token|passphrase|private_key)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"xoxb-[A-Za-z0-9\-]+"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"AKIA[A-Z0-9]{16}"),
    re.compile(r"secret_[A-Za-z0-9]{40,}"),
]


def _redact_for_audit(tool_input: str, tool_result: str) -> tuple[str, str]:
    """Redact sensitive values from audit log entries."""
    try:
        data = json.loads(tool_input)
        for key in list(data.keys()):
            if _SECRET_KEY_RE.search(key):
                data[key] = "[REDACTED]"
        tool_input = json.dumps(data)
    except Exception:
        pass
    for pattern in _SECRET_VALUE_PATTERNS:
        tool_result = pattern.sub("[REDACTED]", tool_result)
    return tool_input, tool_result


def get_model(user_id: str | None = None) -> str:
    if user_id and user_id in _user_models:
        return _user_models[user_id]
    return DEFAULT_MODEL


def set_model(user_id: str, model: str) -> str:
    """Set model preference for a user. Returns the model string."""
    if model not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown model '{model}'. Available: {', '.join(AVAILABLE_MODELS)}")
    _user_models[user_id] = model
    return model


async def stream_chat(
    messages: list[dict],
    user_id: str | None = None,
    model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat completion tokens. Yields text deltas."""
    chosen = model or get_model(user_id)
    response = await litellm.acompletion(
        model=chosen,
        messages=messages,
        stream=True,
        temperature=0.2,
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content or ""
        if delta:
            yield delta


async def stream_chat_with_tools(
    messages: list[dict],
    user_id: str | None = None,
    model: str | None = None,
    db_session=None,
    room_id: str | None = None,
    agent_name: str | None = None,
    confirmed_ids: set[str] | None = None,
    room_execution_allowed: bool | None = None,
) -> AsyncGenerator[dict, None]:
    """
    Tool-aware streaming. Yields typed event dicts:
      {"type": "tool_start", "tool": "web_search", "input": {...}}
      {"type": "tool_done",  "tool": "web_search", "result": "..."}
      {"type": "token",      "token": "..."}

    Handles the tool-calling loop automatically (up to 5 rounds), then
    streams the final LLM response token-by-token.
    """
    from app.api.routes.chat.tools import (
        TOOL_DEFINITIONS,
        execute_tool,
        _email_configured_smtp,
        _google_configured,
    )
    from app.services.guardian.executive import exec_with_guard
    from app.services.guardian.policy import decide_tool_use

    chosen = model or get_model(user_id)
    msgs = list(messages)

    if db_session is not None and user_id and room_id:
        try:
            import uuid as _uuid
            from app.crud import create_audit_log
            from app.services.guardian.token_guardian import run_shadow_route

            latest_user_message = next(
                (
                    str(msg.get("content", ""))
                    for msg in reversed(msgs)
                    if msg.get("role") == "user"
                ),
                "",
            )
            shadow = run_shadow_route(latest_user_message, chosen)
            if shadow:
                create_audit_log(
                    session=db_session,
                    tool_name="tokenguardian_shadow",
                    tool_input=json.dumps(
                        {
                            "query": latest_user_message[:500],
                            "current_model": chosen,
                        }
                    ),
                    tool_result=json.dumps(shadow)[:1000],
                    user_id=_uuid.UUID(user_id),
                    room_id=_uuid.UUID(room_id),
                    agent_name=agent_name,
                    model=chosen,
                )
        except Exception:
            pass

    for _round in range(5):
        # Non-streaming call to resolve any tool calls
        response = await litellm.acompletion(
            model=chosen,
            messages=msgs,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            temperature=0.2,
        )

        choice = response.choices[0]
        finish_reason = choice.finish_reason
        assistant_msg = choice.message

        if finish_reason == "tool_calls" and assistant_msg.tool_calls:
            # Append the assistant's tool-call turn
            msgs.append(assistant_msg.model_dump(exclude_none=True))

            for tc in assistant_msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except Exception:
                    tool_args = {}

                decision = decide_tool_use(
                    tool_name,
                    tool_args if isinstance(tool_args, dict) else {},
                    room_execution_allowed=room_execution_allowed,
                )

                if db_session is not None:
                    try:
                        import uuid as _uuid
                        from app.crud import create_audit_log

                        create_audit_log(
                            session=db_session,
                            tool_name="policy_decision",
                            tool_input=json.dumps(
                                {
                                    "tool_name": tool_name,
                                    "tool_args": tool_args,
                                }
                            )[:2000],
                            tool_result=decision.to_json()[:1000],
                            user_id=_uuid.UUID(user_id) if user_id else None,
                            room_id=_uuid.UUID(room_id) if room_id else None,
                            agent_name=agent_name,
                            model=chosen,
                        )
                    except Exception:
                        pass

                if decision.action == "deny":
                    result = f"POLICY DENIED: {decision.reason}"
                    yield {"type": "tool_start", "tool": tool_name, "input": tool_args}
                    yield {"type": "tool_done", "tool": tool_name, "result": result[:300]}
                    msgs.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                    continue

                if decision.action == "confirm":
                    # Don't prompt for confirmation when email sending is unavailable.
                    # Let the tool return the concrete configuration error instead.
                    if tool_name == "email_send" and not _email_configured_smtp():
                        pass
                    elif tool_name in {"gmail_send", "drive_create_folder"} and not _google_configured():
                        pass
                    else:
                        already_confirmed = confirmed_ids and any(
                            c for c in (confirmed_ids or set()) if c
                        )
                        if not already_confirmed:
                            confirm_id = str(_uuid_module.uuid4())
                            _pending_ttl_cleanup()
                            _pending[confirm_id] = {
                                "tool": tool_name,
                                "args": tool_args,
                                "user_id": user_id,
                                "room_id": room_id,
                                "created_at": time.time(),
                            }
                            yield {
                                "type": "confirm_required",
                                "confirm_id": confirm_id,
                                "tool": tool_name,
                                "input": tool_args,
                            }
                            return

                yield {"type": "tool_start", "tool": tool_name, "input": tool_args}

                result = await exec_with_guard(
                    tool_name=tool_name,
                    action_type=decision.action_type,
                    expected_outcome=f"Successful tool execution for {tool_name}",
                    perform_fn=lambda: execute_tool(
                        tool_name,
                        tool_args,
                        user_id=user_id,
                        session=db_session,
                        room_id=room_id,
                    ),
                    metadata={
                        "room_id": room_id,
                        "user_id": user_id,
                        "scope": decision.scope,
                        "resource": decision.resource,
                    },
                )

                yield {"type": "tool_done", "tool": tool_name, "result": result[:300]}

                # Audit log — best-effort, never let it break the chat stream
                if db_session is not None:
                    try:
                        import uuid as _uuid
                        from app.crud import create_audit_log
                        from app.services.guardian.memory import remember_tool_event
                        redacted_input, redacted_result = _redact_for_audit(
                            tc.function.arguments, result
                        )
                        create_audit_log(
                            session=db_session,
                            tool_name=tool_name,
                            tool_input=redacted_input,
                            tool_result=redacted_result,
                            user_id=_uuid.UUID(user_id) if user_id else None,
                            room_id=_uuid.UUID(room_id) if room_id else None,
                            agent_name=agent_name,
                            model=chosen,
                        )
                        if user_id and room_id:
                            parsed_input = json.loads(redacted_input)
                            remember_tool_event(
                                user_id=user_id,
                                room_id=room_id,
                                tool_name=tool_name,
                                args=parsed_input if isinstance(parsed_input, dict) else {},
                                result=redacted_result,
                            )
                    except Exception:
                        pass  # never fail the stream because of logging

                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            # No more tool calls — stream the final answer
            stream = await litellm.acompletion(
                model=chosen,
                messages=msgs,
                stream=True,
                temperature=0.2,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    yield {"type": "token", "token": delta}
            return

    # Safety: too many tool rounds
    yield {"type": "token", "token": "\n\n⚠️ Tool loop limit reached."}
