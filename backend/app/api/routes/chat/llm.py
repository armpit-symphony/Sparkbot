"""
Centralized LLM routing via litellm.

Replaces direct OpenAI SDK calls so any provider can be swapped
by changing a model string. Per-user model preferences stored in memory.
"""
import json
import os
import re
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
    "For Gmail, Google Drive, email, search, Slack, GitHub, Notion, Confluence, and calendar requests, prefer using the corresponding tool. "
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
) -> AsyncGenerator[dict, None]:
    """
    Tool-aware streaming. Yields typed event dicts:
      {"type": "tool_start", "tool": "web_search", "input": {...}}
      {"type": "tool_done",  "tool": "web_search", "result": "..."}
      {"type": "token",      "token": "..."}

    Handles the tool-calling loop automatically (up to 5 rounds), then
    streams the final LLM response token-by-token.
    """
    from app.api.routes.chat.tools import TOOL_DEFINITIONS, execute_tool

    chosen = model or get_model(user_id)
    msgs = list(messages)

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

                yield {"type": "tool_start", "tool": tool_name, "input": tool_args}

                result = await execute_tool(tool_name, tool_args, user_id=user_id, session=db_session, room_id=room_id)

                yield {"type": "tool_done", "tool": tool_name, "result": result[:300]}

                # Audit log — best-effort, never let it break the chat stream
                if db_session is not None:
                    try:
                        import uuid as _uuid
                        from app.crud import create_audit_log
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
