"""
Centralized LLM routing via litellm.

Replaces direct OpenAI SDK calls so any provider can be swapped
by changing a model string. Per-user model preferences stored in memory.
"""
import json
import logging
import os
import pathlib
import re
import time
import uuid as _uuid_module
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import litellm
from app.services.guardian import get_guardian_suite
from app.services.guardian import improvement as guardian_improvement

litellm.drop_params = True  # ignore unsupported params instead of erroring

log = logging.getLogger(__name__)

PRIMARY_MODEL_ENV = "SPARKBOT_MODEL"
BACKUP_MODEL_1_ENV = "SPARKBOT_BACKUP_MODEL_1"
BACKUP_MODEL_2_ENV = "SPARKBOT_BACKUP_MODEL_2"
HEAVY_HITTER_MODEL_ENV = "SPARKBOT_HEAVY_HITTER_MODEL"
DEFAULT_PROVIDER_ENV = "SPARKBOT_DEFAULT_PROVIDER"
OPENROUTER_DEFAULT_MODEL_ENV = "SPARKBOT_OPENROUTER_MODEL"
LOCAL_DEFAULT_MODEL_ENV = "SPARKBOT_LOCAL_MODEL"
AGENT_MODEL_OVERRIDES_ENV = "SPARKBOT_AGENT_MODEL_OVERRIDES_JSON"
DEFAULT_CROSS_PROVIDER_FALLBACK_ENV = "SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK"
_HEAVY_HITTER_CLASSIFICATIONS = {"coding", "creative", "data_analysis", "reasoning"}
_LLM_TOOL_LIMIT = 128
_TOOL_KEYWORD_PROMOTIONS: dict[str, set[str]] = {
    "youtube": {"youtube_transcript", "youtube_summarize"},
    "video": {"youtube_transcript", "youtube_summarize"},
    "timer": {"time_start", "time_stop", "time_status", "time_report", "time_log"},
    "time tracking": {"time_start", "time_stop", "time_status", "time_report", "time_log"},
    "spotify": {
        "spotify_play",
        "spotify_pause",
        "spotify_next",
        "spotify_previous",
        "spotify_now_playing",
        "spotify_search",
        "spotify_volume",
    },
    "portfolio": {"portfolio_add", "portfolio_view", "portfolio_remove", "stock_quote", "stock_history"},
    "stock": {"stock_quote", "stock_history", "portfolio_view"},
}
_CORE_TOOL_PRIORITY = {
    "remember_fact",
    "memory_recall",
    "web_search",
    "fetch_url",
    "browser_open",
    "browser_snapshot",
    "browser_click",
    "browser_fill_field",
    "browser_close",
    "terminal_list_sessions",
    "terminal_send",
    "get_datetime",
    "calculate",
    "create_task",
    "list_tasks",
    "complete_task",
    "github_list_prs",
    "github_get_pr",
    "github_create_issue",
    "gmail_search",
    "gmail_get_message",
    "gmail_send",
    "guardian_schedule_task",
    "guardian_list_tasks",
    "guardian_propose_improvement",
    "guardian_simulate_policy",
    "calendar_list_events",
    "calendar_create_event",
    "vault_list_secrets",
    "vault_use_secret",
    "shell_run",
    "run_code",
    "morning_briefing",
    "news_headlines",
    "send_alert",
}

# ─── System prompt ────────────────────────────────────────────────────────────
# Loaded from prompts/system.md (backend root) at startup.
# Override path via SPARKBOT_SYSTEM_PROMPT_FILE env var.
# Falls back to the hardcoded default below when the file is missing.

_SYSTEM_PROMPT_DEFAULT = (
    "You are Sparkbot — a capable, proactive AI workspace assistant built and operated by Sparkpit Labs. "
    "You serve the operator and their team directly: people who trust you to get real work done.\n\n"
    "## EXECUTION RULES (Highest Priority)\n"
    "RULE 1 — EXECUTE FIRST, EXPLAIN NEVER\n"
    "When a user gives you a task that requires a tool, use the tool IMMEDIATELY. "
    "Do not describe what you will do. Do not explain before acting. "
    "Bad: \"I'll check your calendar for today. Let me look that up for you.\" "
    "Good: [calls calendar tool] → streams result directly\n\n"
    "RULE 2 — CHAIN ACTIONS WITHOUT WAITING\n"
    "After completing one tool call, immediately identify the next logical action. "
    "Continue executing until the task is COMPLETE. "
    "Do not stop after one tool and ask \"would you like me to do anything else?\"\n\n"
    "RULE 3 — COMPLETE WORK AUTONOMOUSLY\n"
    "When given a multi-step task, execute ALL steps without asking for permission on each step. "
    "If you need a decision (e.g., who to email), make a reasonable default and note it. "
    "You are authorized to complete the work the user assigned.\n\n"
    "RULE 4 — RESULT-FIRST RESPONSE\n"
    "When a tool executes, lead with the result. Add brief context only if it changes behavior. "
    "Bad: \"I checked your calendar and found 3 events today: 9am standup, 2pm review...\" "
    "Good: \"📅 Today: 9am standup, 2pm review, 4pm 1:1\"\n\n"
    "## Identity\n"
    "You are not a generic chatbot. You are the operator's dedicated AI worker — opinionated, resourceful, and direct. "
    "You understand their stack, their tools, and their goals. You act with authority on tasks you've been given, "
    "and you escalate clearly when you hit a real blocker.\n\n"
    "## Collaboration\n"
    "Contribute new thinking only when it adds value. Never open a reply by restating what the user just said. "
    "Never summarize your previous response before adding new content. If the answer is already in the conversation, "
    "say so briefly and move on. Prioritize ACTION over explanation.\n\n"
    "## Proactivity\n"
    "Notice what's not being asked. If you see a gap, a risk, or a better path, surface it — briefly and confidently. "
    "Don't wait to be told every step. When given an open-ended goal, break it into concrete steps and EXECUTE them. "
    "Flag dependencies, missing config, or likely failure points before they bite — then keep working.\n\n"
    "## Quality\n"
    "Be thorough when it matters, concise when it doesn't. Prefer verified over guessed — reach for a tool when live data "
    "would make your answer more accurate. When you commit to an answer, stand behind it. "
    "If you're uncertain, say so clearly and explain why. Never invent results, statuses, or tool outputs.\n\n"
    "## Truth And Confidence\n"
    "No lying. If your confidence in a factual statement, status, diagnosis, or recommendation is below 90%, "
    "say what could be wrong and name the missing information or verification step. Do not present guesses as facts. "
    "Use tools to raise confidence when live data, logs, repo state, or external systems can answer the question. "
    "If you discover an earlier mistake, state the correction directly and what you learned from it.\n\n"
    "## Self-Improvement\n"
    "Always look for chances to improve Sparkbot's workflows, prompts, docs, tool routing, tests, and Guardian policies. "
    "When you see a repeated miss, uncertain behavior, missing capability, stale documentation, or a safer implementation path, "
    "record it with guardian_propose_improvement. Code, configuration, docs, scheduled jobs, and external write actions "
    "still require explicit operator approval before you apply them. After approval, make only the approved change, verify it, "
    "and report the evidence.\n\n"
    "## Boundaries\n"
    "Do not disclose raw secrets, API keys, vault contents, or hidden credentials. "
    "You may share safe operational runtime state (provider, model, routing, Ollama status, Token Guardian state, "
    "break-glass status) when explicitly asked. Never claim a write action succeeded unless the tool result explicitly "
    "confirms it. If a confirmation gate requires approval, wait — do not claim it already happened.\n\n"
    "## Tool Philosophy\n"
    "Tools are your first instinct for live data, external systems, and actions — not a fallback. "
    "For anything requiring current information, use web_search. "
    "For running shell commands, scripts, file operations, git, npm, pip, or any terminal task, use shell_run — "
    "it runs PowerShell on Windows and bash on Linux/macOS directly on the user's local machine. "
    "For interactive website tasks (register, login, navigate, fill forms, click, post, reply), use the browser tools — "
    "this is fully operator-authorized. "
    "For typing into a live terminal session, use terminal_list_sessions then terminal_send. "
    "For Gmail, GitHub, Notion, Confluence, Slack, calendar, and other integrations, use the matching tool. "
    "For server status, diagnostics, logs, and local-machine checks, use local tools when Computer Control is on or after break-glass PIN authorization. "
    "Never claim you cannot use a tool if it exists and is relevant — use it.\n\n"
    "## Tone\n"
    "Professional, direct, and action-oriented. No filler. No unnecessary apologies. No hedging when you know the answer. "
    "Prioritize completing the user's task over explaining your thinking."
)


def _load_system_prompt() -> str:
    """Load system prompt from file, with fallback to hardcoded default.

    Resolution order:
    1. Path in SPARKBOT_SYSTEM_PROMPT_FILE env var
    2. <backend_root>/prompts/system.md
    3. Hardcoded _SYSTEM_PROMPT_DEFAULT
    """
    candidates = []
    env_path = os.getenv("SPARKBOT_SYSTEM_PROMPT_FILE", "").strip()
    if env_path:
        candidates.append(pathlib.Path(env_path))
    # backend root = 4 levels up from this file (chat/routes/api/app/backend)
    candidates.append(pathlib.Path(__file__).parents[4] / "prompts" / "system.md")
    for p in candidates:
        try:
            if p.is_file():
                content = p.read_text(encoding="utf-8").strip()
                if content:
                    log.debug("System prompt loaded from %s", p)
                    return content
        except Exception as exc:
            log.warning("Could not read system prompt file %s: %s", p, exc)
    return _SYSTEM_PROMPT_DEFAULT


SYSTEM_PROMPT = _load_system_prompt()
_GLOBAL_OPERATION_GUARDRAILS = (
    "Truth and confidence are mandatory: if confidence in a factual statement, status, diagnosis, "
    "or recommendation is below 90%, state what could be wrong and what information is missing. "
    "Never invent tool results. Watch for self-improvement opportunities; use guardian_propose_improvement "
    "for repeated failures, missing capabilities, stale docs, uncertain answer patterns, or safer workflow ideas. "
    "Do not apply code, config, docs, scheduled-job, or external write changes until the operator explicitly approves."
)

# Curated model list — only show what's actually usable given configured keys
AVAILABLE_MODELS: dict[str, str] = {
    # ── OpenRouter (proxy for any model) ───────────────────────────────────────
    "openrouter/openai/gpt-4o-mini":  "OpenRouter · GPT-4o Mini — easy cloud default",
    # ── OpenAI ─────────────────────────────────────────────────────────────────
    "gpt-4o-mini":      "GPT-4o Mini — fast, cost-effective",
    "gpt-4o":           "GPT-4o — flagship OpenAI model",
    "gpt-4.5":          "GPT-4.5 — advanced reasoning",
    "gpt-4.1":          "GPT-4.1 — long-context flagship",
    "gpt-4.1-mini":     "GPT-4.1 Mini — fast long-context",
    "gpt-4.1-nano":     "GPT-4.1 Nano — cheapest long-context",
    "gpt-5":            "GPT-5 — most capable OpenAI model",
    "gpt-5-mini":       "GPT-5 Mini — fast, cost-effective next-gen",
    "gpt-5-nano":       "GPT-5 Nano — ultra-fast next-gen",
    "gpt-5.4":          "GPT-5.4 — latest OpenAI flagship",
    "gpt-5.4-mini":     "GPT-5.4 Mini — fast 5.4 series",
    "gpt-5.4-nano":     "GPT-5.4 Nano — lightest 5.4 series",
    "codex-mini-latest": "Codex Mini Latest — OpenAI coding agent model",
    # ── Anthropic ──────────────────────────────────────────────────────────────
    "claude-haiku-4-5":          "Claude Haiku 4.5 — fastest Anthropic model",
    "claude-sonnet-4-5":         "Claude Sonnet 4.5 — balanced Anthropic model",
    "claude-sonnet-4-6":         "Claude Sonnet 4.6 — latest balanced Anthropic",
    "claude-opus-4-6":           "Claude Opus 4.6 — most capable Anthropic model",
    # ── Google ─────────────────────────────────────────────────────────────────
    "gemini/gemini-2.0-flash":       "Gemini 2.0 Flash — fast Google model",
    "gemini/gemini-3-flash":         "Gemini 3 Flash — fast Gemini 3 model",
    "gemini/gemini-3.1-flash-lite":  "Gemini 3.1 Flash Lite — lightest Gemini 3.1",
    "gemini/gemini-3.1-pro":         "Gemini 3.1 Pro — flagship Google model",
    # ── Groq ───────────────────────────────────────────────────────────────────
    "groq/llama-3.3-70b-versatile":  "Llama 3.3 70B via Groq — very fast",
    # ── MiniMax ────────────────────────────────────────────────────────────────
    "minimax/MiniMax-M2.5":  "MiniMax M2.5 — reasoning + tool calling",
    "minimax/MiniMax-M2.7":  "MiniMax M2.7 — latest MiniMax model",
    # ── xAI (Grok) ─────────────────────────────────────────────────────────────
    "xai/grok-4.20-0309-reasoning":      "Grok 4.20 Reasoning — xAI deep reasoning",
    "xai/grok-4.20-0309-non-reasoning":  "Grok 4.20 — xAI fast non-reasoning",
    "xai/grok-4.20-multi-agent-0309":    "Grok 4.20 Multi-Agent — xAI agentic mode",
    "xai/grok-4-1-fast-reasoning":       "Grok 4.1 Fast Reasoning — xAI balanced",
    "xai/grok-4-1-fast-non-reasoning":   "Grok 4.1 Fast — xAI cost-effective",
}

OLLAMA_MODELS: dict[str, str] = {
    "ollama/llama3.2:1b":    "Llama 3.2 1B — fastest, lowest memory (~1 GB)",
    "ollama/llama3.2:3b":    "Llama 3.2 3B — fast and balanced (~2 GB)",
    "ollama/phi4-mini":      "Phi-4 Mini — best default quality/speed balance (~2.5 GB)",
    "ollama/phi3.5":         "Phi 3.5 — reasoning-focused, efficient (~2 GB)",
    "ollama/gemma2:2b":      "Gemma 2 2B — compact quality (~1.6 GB)",
    "ollama/granite3.3:2b":  "Granite 3.3 2B — long-context, compact (~1.5 GB)",
    "ollama/mistral:7b":     "Mistral 7B — stronger quality (~4.1 GB)",
    "ollama/falcon3:1b":       "Falcon3 1B — ultra-light (~0.6 GB)",
    "ollama/falcon3:3b":       "Falcon3 3B — light and capable (~1.7 GB)",
    "ollama/falcon3:7b":       "Falcon3 7B — powerful, good reasoning (~4 GB)",
    "ollama/gemma2:9b":        "Gemma 2 9B — strong quality, larger model (~5.5 GB)",
    "ollama/granite3.3:8b":    "Granite 3.3 8B — long-context, stronger (~4.9 GB)",
}
# Merge into AVAILABLE_MODELS so model routing works
AVAILABLE_MODELS.update(OLLAMA_MODELS)

# In-memory per-user model preferences  {user_id: model_name}
# Resets on service restart — good enough until DB persistence is added
_user_models: dict[str, str] = {}

# Pending confirmations: confirm_id -> {tool, args, user_id, room_id, created_at}
_pending: dict[str, dict] = {}
_PENDING_TTL = 600  # 10 minutes


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _pending_ttl_cleanup() -> None:
    now = time.time()
    stale = [k for k, v in _pending.items() if now - v["created_at"] > _PENDING_TTL]
    for k in stale:
        _pending.pop(k, None)


def consume_pending(confirm_id: str) -> dict | None:
    """Pop and return a pending confirmation entry, or None if not found/expired."""
    entry = _pending.pop(confirm_id, None)
    if entry and time.time() - entry["created_at"] > _PENDING_TTL:
        try:
            get_guardian_suite().pending_approvals.discard_pending_approval(confirm_id)
        except Exception:
            pass
        return None
    if entry:
        try:
            get_guardian_suite().pending_approvals.discard_pending_approval(confirm_id)
        except Exception:
            pass
        return entry
    try:
        return get_guardian_suite().pending_approvals.consume_pending_approval(confirm_id)
    except Exception:
        return None


def discard_pending(confirm_id: str) -> None:
    _pending.pop(confirm_id, None)
    try:
        get_guardian_suite().pending_approvals.discard_pending_approval(confirm_id)
    except Exception:
        pass


# ── Per-model latency tracking ────────────────────────────────────────────────
# Stores the last 10 successful response times (seconds) per model string.
# Written by _acompletion_with_fallback; read by the /models endpoint.
from collections import deque

_MODEL_LATENCIES: dict[str, deque[float]] = {}
_LATENCY_WINDOW = 10  # keep last N samples per model


def record_latency(model: str, elapsed: float) -> None:
    if model not in _MODEL_LATENCIES:
        _MODEL_LATENCIES[model] = deque(maxlen=_LATENCY_WINDOW)
    _MODEL_LATENCIES[model].append(round(elapsed, 2))


def get_latency_stats(model: str) -> dict:
    samples = list(_MODEL_LATENCIES.get(model, []))
    if not samples:
        return {"samples": 0, "avg_s": None, "min_s": None, "max_s": None, "last_s": None}
    return {
        "samples": len(samples),
        "avg_s": round(sum(samples) / len(samples), 2),
        "min_s": round(min(samples), 2),
        "max_s": round(max(samples), 2),
        "last_s": samples[-1],
    }


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
    # Belt-and-suspenders: vault_reveal_secret output format "Value: <plaintext>"
    re.compile(r"(?i)^Value:\s+\S+", re.MULTILINE),
]

# Tools whose plaintext result must never leave the LLM context boundary.
# Result is replaced with a placeholder in all outward-facing paths:
# SSE tool_done events, audit logs, memory, Telegram responses, chat DB.
_VAULT_INTERNAL_TOOLS: frozenset[str] = frozenset({"vault_use_secret"})
# Tools whose result must be masked in audit logs and memory but MAY appear in user-facing chat
# (e.g. vault_reveal_secret: operator sees plaintext in chat, but log stores only the alias).
_VAULT_AUDIT_MASK_TOOLS: frozenset[str] = frozenset({"vault_use_secret", "vault_reveal_secret"})
_VAULT_VALUE_ARG_TOOLS: frozenset[str] = frozenset({"vault_add_secret", "vault_update_secret"})


def _masked_vault_placeholder(tool_args: dict | None) -> str:
    alias = "secret"
    if isinstance(tool_args, dict):
        alias = str(tool_args.get("alias") or alias).strip() or alias
    return f"[vault:{alias}]"


def mask_tool_result_for_external(tool_name: str, tool_args: dict | None, result: object) -> str:
    """Mask result for user-visible outward paths (SSE, chat DB, Telegram)."""
    if tool_name in _VAULT_INTERNAL_TOOLS:
        return _masked_vault_placeholder(tool_args)
    return str(result)


def _mask_result_for_audit(tool_name: str, tool_args: dict | None, result: object) -> str:
    """Mask result for audit log and memory — broader than outward mask."""
    if tool_name in _VAULT_AUDIT_MASK_TOOLS:
        return _masked_vault_placeholder(tool_args)
    return str(result)


def _sanitize_tool_args_for_audit(tool_name: str, tool_args: dict | None) -> str:
    safe_args = dict(tool_args) if isinstance(tool_args, dict) else {}
    if tool_name in _VAULT_VALUE_ARG_TOOLS and "value" in safe_args:
        safe_args["value"] = "[REDACTED]"
    return json.dumps(safe_args)


def serialize_tool_args_for_audit(tool_name: str, tool_args: dict | None) -> str:
    return _sanitize_tool_args_for_audit(tool_name, tool_args)


def redact_tool_call_for_audit(
    tool_name: str,
    tool_args: dict | None,
    result: object,
) -> tuple[str, str]:
    audit_result = _mask_result_for_audit(tool_name, tool_args, result)
    return _redact_for_audit(_sanitize_tool_args_for_audit(tool_name, tool_args), audit_result)


_GENERIC_SECRET_PAIR_RE = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|credential|auth[_-]?token|passphrase|private[_-]?key)\b(\s*[:=]\s*)([^\s,;]+)"
)


def _redact_secret_like_text(text: str) -> str:
    return _GENERIC_SECRET_PAIR_RE.sub(r"\1\2[REDACTED]", text)


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
    tool_input = _redact_secret_like_text(tool_input)
    for pattern in _SECRET_VALUE_PATTERNS:
        tool_result = pattern.sub("[REDACTED]", tool_result)
    # Also redact secret-keyed fields if result is a JSON dict
    try:
        result_data = json.loads(tool_result)
        if isinstance(result_data, dict):
            for key in list(result_data.keys()):
                if _SECRET_KEY_RE.search(key):
                    result_data[key] = "[REDACTED]"
            tool_result = json.dumps(result_data)
    except Exception:
        pass
    tool_result = _redact_secret_like_text(tool_result)
    return tool_input, tool_result


async def get_ollama_status() -> dict:
    """Check Ollama server connectivity and list available local models."""
    import httpx
    base_url = os.environ.get("OLLAMA_API_BASE", "http://localhost:11434").rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                model_ids = [
                    name if name.startswith("ollama/") else f"ollama/{name}"
                    for name in models
                ]
                return {
                    "reachable": True,
                    "base_url": base_url,
                    "models": models,
                    "model_ids": model_ids,
                    "models_available": bool(model_ids),
                }
    except Exception:
        pass
    return {
        "reachable": False,
        "base_url": base_url,
        "models": [],
        "model_ids": [],
        "models_available": False,
    }


def is_valid_model(model: str) -> bool:
    normalized = (model or "").strip()
    if not normalized:
        return False
    if normalized in AVAILABLE_MODELS:
        return True
    if normalized.startswith("openrouter/"):
        return True
    if normalized.startswith("ollama/"):
        return True
    return False


def model_label(model: str) -> str:
    normalized = (model or "").strip()
    if normalized in AVAILABLE_MODELS:
        return AVAILABLE_MODELS[normalized]
    if normalized.startswith("openrouter/"):
        slug = normalized.removeprefix("openrouter/")
        return f"OpenRouter · {slug}"
    if normalized.startswith("ollama/"):
        slug = normalized.removeprefix("ollama/")
        return f"Local Ollama · {slug}"
    return normalized


def _default_model() -> str:
    return (
        os.getenv(PRIMARY_MODEL_ENV, os.getenv("OPENAI_MODEL", "gpt-4o-mini")).strip()
        or "gpt-4o-mini"
    )


def get_default_provider() -> str:
    explicit = os.getenv(DEFAULT_PROVIDER_ENV, "").strip().lower()
    if explicit:
        return explicit
    return model_provider(_default_model())


def get_openrouter_default_model() -> str:
    configured = os.getenv(OPENROUTER_DEFAULT_MODEL_ENV, "").strip()
    if configured:
        return configured
    primary = _default_model()
    if model_provider(primary) == "openrouter":
        return primary
    return "openrouter/openai/gpt-4o-mini"


def get_local_default_model() -> str:
    configured = os.getenv(LOCAL_DEFAULT_MODEL_ENV, "").strip()
    if configured:
        return configured
    primary = _default_model()
    if model_provider(primary) == "ollama":
        return primary
    return "ollama/phi4-mini"


def default_cross_provider_fallback_enabled() -> bool:
    raw = os.getenv(DEFAULT_CROSS_PROVIDER_FALLBACK_ENV, "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    # Local installs should fail within the chosen provider unless the user
    # explicitly opts into cross-provider fallback.
    return os.getenv("V1_LOCAL_MODE", "false").strip().lower() not in {"1", "true", "yes", "on"}


# Runtime store for invite-seat custom API keys and model IDs.
# Populated via POST /agents/{name}/invite-route; cleared on process restart.
_invite_agent_configs: dict[str, dict[str, str]] = {}


def set_invite_agent_config(
    agent_name: str,
    *,
    model: str | None,
    api_key: str | None,
    auth_mode: str | None = None,
) -> None:
    key = agent_name.strip().lower()
    if not model and not api_key:
        _invite_agent_configs.pop(key, None)
        return
    normalized_auth = (auth_mode or "").strip().lower()
    if normalized_auth not in {"api_key", "oauth", "codex_sub"}:
        normalized_auth = "api_key"
    entry: dict[str, str] = {}
    if model:
        entry["model"] = model.strip()
    if api_key:
        entry["api_key"] = api_key.strip()
        entry["auth_mode"] = normalized_auth
    _invite_agent_configs[key] = entry


def get_invite_agent_config(agent_name: str) -> dict[str, str]:
    return _invite_agent_configs.get(agent_name.strip().lower(), {})


def get_agent_model_overrides() -> dict[str, dict[str, str]]:
    raw = os.getenv(AGENT_MODEL_OVERRIDES_ENV, "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    cleaned: dict[str, dict[str, str]] = {}
    for key, value in parsed.items():
        if not isinstance(value, dict):
            continue
        route = str(value.get("route") or "default").strip().lower()
        model = str(value.get("model") or "").strip()
        if route not in {"default", "openrouter", "local"}:
            continue
        cleaned[str(key).strip().lower()] = {"route": route, "model": model}
    return cleaned


def get_agent_route_context(
    *,
    default_model: str,
    agent_name: str | None = None,
) -> dict[str, Any]:
    overrides = get_agent_model_overrides()
    effective_agent = (agent_name or "sparkbot").strip().lower()
    override = overrides.get(effective_agent)
    workstation_stack_slots = {
        "workstation_backup_1": "backup_1",
        "workstation_backup_2": "backup_2",
        "workstation_heavy_hitter": "heavy_hitter",
    }
    if effective_agent in workstation_stack_slots:
        slot_model = str(get_model_stack().get(workstation_stack_slots[effective_agent]) or "").strip()
        chosen_model = slot_model or default_model
        return {
            "agent_name": effective_agent,
            "route": "default",
            "provider_locked": True,
            "model": chosen_model,
            "requested_provider": model_provider(chosen_model),
            "cross_provider_fallback": False,
        }

    invite_conf = get_invite_agent_config(effective_agent)
    invite_model = invite_conf.get("model", "").strip()
    invite_api_key = invite_conf.get("api_key", "").strip()
    invite_auth_mode = invite_conf.get("auth_mode", "api_key").strip().lower() or "api_key"

    route = str((override or {}).get("route") or "default").strip().lower()
    if route not in {"default", "openrouter", "local"}:
        route = "default"

    override_model = invite_model or str((override or {}).get("model") or "").strip()
    chosen_model = default_model
    if route == "openrouter":
        chosen_model = override_model or get_openrouter_default_model()
    elif route == "local":
        chosen_model = override_model or get_local_default_model()
    elif override_model:
        chosen_model = override_model

    provider_locked = route in {"openrouter", "local"} or bool(override_model)

    ctx: dict[str, Any] = {
        "agent_name": effective_agent,
        "route": route,
        "provider_locked": provider_locked,
        "model": chosen_model,
        "requested_provider": model_provider(chosen_model),
        "cross_provider_fallback": (
            default_cross_provider_fallback_enabled()
            if route == "default" and not provider_locked
            else False
        ),
    }
    if invite_api_key:
        ctx["invite_api_key"] = invite_api_key
        ctx["invite_auth_mode"] = invite_auth_mode
    return ctx


def model_provider(model: str) -> str:
    normalized = (model or "").strip()
    if normalized.startswith("openrouter/"):
        return "openrouter"
    if normalized.startswith("gpt-") or normalized.startswith("codex-"):
        return "openai"
    if normalized.startswith("claude"):
        return "anthropic"
    if normalized.startswith("gemini/"):
        return "google"
    if normalized.startswith("groq/"):
        return "groq"
    if normalized.startswith("minimax/"):
        return "minimax"
    if normalized.startswith("xai/"):
        return "xai"
    if normalized.startswith("ollama/"):
        return "ollama"
    return "other"


def model_is_configured(model: str) -> bool:
    provider = model_provider(model)
    if provider == "openrouter":
        return bool(os.getenv("OPENROUTER_API_KEY", "").strip())
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY", "").strip())
    if provider == "anthropic":
        return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    if provider == "google":
        return bool(os.getenv("GOOGLE_API_KEY", "").strip())
    if provider == "groq":
        return bool(os.getenv("GROQ_API_KEY", "").strip())
    if provider == "minimax":
        return bool(os.getenv("MINIMAX_API_KEY", "").strip())
    if provider == "xai":
        return bool(os.getenv("XAI_API_KEY", "").strip())
    if provider == "ollama":
        # Ollama is always "configured" — it's local, no API key needed
        return True
    return bool((model or "").strip())


def _global_provider_auth_config(provider: str) -> tuple[str | None, str]:
    normalized = (provider or "").strip().lower()
    if normalized == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip() or None
        auth_mode = os.getenv("ANTHROPIC_AUTH_MODE", "").strip().lower()
        if auth_mode not in {"api_key", "oauth"}:
            auth_mode = "api_key"
        return api_key, auth_mode
    if normalized == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip() or None
        auth_mode = os.getenv("OPENAI_AUTH_MODE", "").strip().lower()
        if auth_mode not in {"api_key", "codex_sub"}:
            auth_mode = "api_key"
        return api_key, auth_mode
    return None, "api_key"


def get_model_stack() -> dict[str, str]:
    primary = _default_model()
    backup_1 = os.getenv(BACKUP_MODEL_1_ENV, "").strip()
    backup_2 = os.getenv(BACKUP_MODEL_2_ENV, "").strip()
    heavy_hitter = os.getenv(HEAVY_HITTER_MODEL_ENV, "").strip() or "gpt-4o"
    return {
        "primary": primary,
        "backup_1": backup_1,
        "backup_2": backup_2,
        "heavy_hitter": heavy_hitter,
    }


def get_model_stack_display() -> dict[str, str]:
    """Like get_model_stack() but returns empty strings for values that were
    never explicitly set by the user — used only for the settings config response
    so the UI shows a clean slate on first launch."""
    return {
        "primary": os.getenv(PRIMARY_MODEL_ENV, "").strip(),
        "backup_1": os.getenv(BACKUP_MODEL_1_ENV, "").strip(),
        "backup_2": os.getenv(BACKUP_MODEL_2_ENV, "").strip(),
        "heavy_hitter": os.getenv(HEAVY_HITTER_MODEL_ENV, "").strip(),
    }


def set_model_stack(
    *,
    primary: str,
    backup_1: str,
    backup_2: str,
    heavy_hitter: str,
    user_id: str | None = None,
) -> dict[str, str]:
    stack = {
        "primary": (primary or "").strip(),
        "backup_1": (backup_1 or "").strip(),
        "backup_2": (backup_2 or "").strip(),
        "heavy_hitter": (heavy_hitter or "").strip(),
    }
    for key, model in stack.items():
        if model and not is_valid_model(model):
            raise ValueError(f"Unknown model '{model}' for {key}.")

    os.environ[PRIMARY_MODEL_ENV] = stack["primary"]
    os.environ[BACKUP_MODEL_1_ENV] = stack["backup_1"]
    os.environ[BACKUP_MODEL_2_ENV] = stack["backup_2"]
    os.environ[HEAVY_HITTER_MODEL_ENV] = stack["heavy_hitter"]

    if user_id:
        _user_models[user_id] = stack["primary"]

    return stack


def _annotate_route_payload(
    route_payload: dict[str, Any] | None,
    *,
    route_context: dict[str, Any],
    current_model: str,
    applied_model: str | None = None,
) -> dict[str, Any]:
    payload = dict(route_payload or {})
    payload["route"] = route_context["route"]
    payload["provider_locked"] = bool(route_context["provider_locked"])
    payload["requested_provider"] = route_context["requested_provider"]
    payload["requested_model"] = route_context["model"]
    payload["current_model"] = current_model
    resolved_applied = (applied_model or payload.get("applied_model") or current_model).strip()
    payload["applied_model"] = resolved_applied
    payload["applied_provider"] = model_provider(resolved_applied)
    return payload


def _locked_route_payload(
    *,
    message: str,
    route_context: dict[str, Any],
) -> dict[str, Any]:
    model_name = str(route_context["model"]).strip()
    return {
        "timestamp": _utc_now_iso(),
        "query": message,
        "classification": "forced_provider",
        "confidence": 1.0,
        "threshold": 1.0,
        "selected_model": model_name,
        "fallback_triggered": False,
        "fallback_reason": None,
        "optimization": None,
        "estimated_cost": 0.0,
        "status": "locked",
        "mode": "locked",
        "current_model": model_name,
        "estimated_tokens": None,
        "estimated_current_cost": 0.0,
        "estimated_savings": 0.0,
        "would_switch_models": False,
        "configured_models": [model_name],
        "allowed_live_models": [model_name],
        "live_ready": True,
        "selected_model_supported": is_valid_model(model_name),
        "selected_model_configured": model_is_configured(model_name),
        "selected_model_allowed": True,
        "candidate_models": [model_name],
        "applied_model": model_name,
        "applied_provider": route_context["requested_provider"],
        "live_routed": False,
        "route": route_context["route"],
        "provider_locked": True,
        "requested_provider": route_context["requested_provider"],
        "requested_model": model_name,
    }


def _provider_authoritative_route_payload(
    *,
    message: str,
    route_context: dict[str, Any],
) -> dict[str, Any]:
    model_name = str(route_context["model"]).strip()
    provider_name = str(route_context["requested_provider"]).strip()
    return {
        "timestamp": _utc_now_iso(),
        "query": message,
        "classification": "default_provider_authoritative",
        "confidence": 1.0,
        "threshold": 1.0,
        "selected_model": model_name,
        "fallback_triggered": False,
        "fallback_reason": None,
        "optimization": None,
        "estimated_cost": 0.0,
        "status": "provider_default",
        "mode": "provider_default",
        "current_model": model_name,
        "estimated_tokens": None,
        "estimated_current_cost": 0.0,
        "estimated_savings": 0.0,
        "would_switch_models": False,
        "configured_models": [model_name],
        "allowed_live_models": [model_name],
        "live_ready": True,
        "selected_model_supported": is_valid_model(model_name),
        "selected_model_configured": model_is_configured(model_name),
        "selected_model_allowed": True,
        "candidate_models": [model_name],
        "applied_model": model_name,
        "applied_provider": provider_name,
        "live_routed": False,
        "route": "default",
        "provider_locked": False,
        "requested_provider": provider_name,
        "requested_model": model_name,
        "cross_provider_fallback": bool(route_context.get("cross_provider_fallback")),
        "provider_authoritative": True,
    }


async def _ensure_locked_route_ready(route_context: dict[str, Any]) -> None:
    model_name = str(route_context.get("model") or "").strip()
    locked_provider = model_provider(model_name) if route_context.get("provider_locked") else ""
    if locked_provider == "openrouter":
        if not os.getenv("OPENROUTER_API_KEY", "").strip():
            raise RuntimeError(
                "OpenRouter is forced for this agent, but no OpenRouter API key is saved in Controls."
            )
        return
    if locked_provider == "ollama":
        ollama_status = await get_ollama_status()
        if not ollama_status.get("reachable"):
            raise RuntimeError(
                f"Local Ollama is forced for this agent, but Ollama is not reachable at {ollama_status['base_url']}."
            )
        if model_name not in set(ollama_status.get("model_ids") or []):
            raise RuntimeError(
                f"Local Ollama is forced for this agent, but model '{model_name}' is not downloaded on this machine."
            )


def _format_locked_route_error(route_context: dict[str, Any], error: Exception) -> str:
    model_name = str(route_context.get("model") or "").strip()
    locked_provider = model_provider(model_name) if route_context.get("provider_locked") else ""
    if locked_provider == "openrouter":
        return (
            f"OpenRouter is forced for this agent, but model '{model_name}' could not run. "
            f"Fix the OpenRouter setup or change this agent back to Use default. Details: {error}"
        )
    if locked_provider == "ollama":
        return (
            f"Local Ollama is forced for this agent, but model '{model_name}' could not run. "
            f"Make sure Ollama is running and the model is downloaded, or change this agent back to Use default. Details: {error}"
        )
    return str(error)


def _candidate_models(
    primary_model: str,
    route_payload: dict | None = None,
    route_context: dict[str, Any] | None = None,
) -> list[str]:
    if route_context and route_context.get("provider_locked"):
        return [primary_model]

    stack = get_model_stack()
    candidates: list[str] = []
    requested_provider = str((route_context or {}).get("requested_provider") or model_provider(primary_model)).strip()
    allow_cross_provider = bool((route_context or {}).get("cross_provider_fallback"))

    def add(model_name: str) -> None:
        normalized = (model_name or "").strip()
        if not normalized:
            return
        if not allow_cross_provider and model_provider(normalized) != requested_provider:
            return
        if normalized and is_valid_model(normalized) and normalized not in candidates:
            candidates.append(normalized)

    add(primary_model)
    classification = str((route_payload or {}).get("classification") or "").strip()
    if classification in _HEAVY_HITTER_CLASSIFICATIONS:
        add(stack["heavy_hitter"])
    add(stack["backup_1"])
    add(stack["backup_2"])
    if classification not in _HEAVY_HITTER_CLASSIFICATIONS:
        add(stack["heavy_hitter"])

    filtered = [candidate for candidate in candidates if model_is_configured(candidate)]
    classification = str((route_payload or {}).get("classification") or "").strip() or "general"
    filtered = guardian_improvement.reorder_candidate_models(
        classification=classification,
        candidates=filtered,
    )
    if filtered:
        return filtered
    return [primary_model]


async def _retry_plain_text_without_tools(
    *,
    chosen: str,
    route_payload: dict | None,
    route_context: dict[str, Any],
    messages: list[dict],
    temperature: float,
) -> str:
    retry_kwargs = {
        "messages": messages,
        "temperature": temperature,
    }
    retry_model, retry_response = await _acompletion_with_fallback(
        model=chosen,
        route_payload=route_payload,
        route_context=route_context,
        **retry_kwargs,
    )
    retry_choice = retry_response.choices[0]
    retry_text = _assistant_message_text(retry_choice.message)
    if retry_text:
        log.warning(
            "LLM empty tool response recovered without tools: requested=%s applied=%s provider=%s",
            chosen,
            retry_model,
            model_provider(retry_model),
        )
    return retry_text


async def _stream_text_with_fallback(
    *,
    model: str,
    route_payload: dict | None,
    route_context: dict[str, Any],
    messages: list[dict],
    temperature: float,
) -> AsyncGenerator[str, None]:
    streamed_any = False
    try:
        _, response = await _acompletion_with_fallback(
            model=model,
            route_payload=route_payload,
            route_context=route_context,
            messages=messages,
            stream=True,
            temperature=temperature,
        )
        async for chunk in response:
            delta = _assistant_message_text(chunk.choices[0].delta)
            if delta:
                streamed_any = True
                yield delta
    except Exception as exc:
        if streamed_any:
            raise
        log.warning(
            "streaming completion failed before tokens for %s; retrying non-streaming: %s",
            model,
            exc,
        )

    if streamed_any:
        return

    retry_model, retry_response = await _acompletion_with_fallback(
        model=model,
        route_payload=route_payload,
        route_context=route_context,
        messages=messages,
        stream=False,
        temperature=temperature,
    )
    retry_text = _assistant_message_text(retry_response.choices[0].message)
    if retry_text:
        log.warning(
            "streaming completion produced no tokens; retried non-streaming successfully: requested=%s applied=%s provider=%s",
            model,
            retry_model,
            model_provider(retry_model),
        )
        yield retry_text


def _assistant_message_text(message: Any) -> str:
    text = _extract_text_content(getattr(message, "content", None))
    if text:
        return text
    if hasattr(message, "model_dump"):
        try:
            dumped = message.model_dump(exclude_none=False)
        except Exception:
            dumped = {}
        if isinstance(dumped, dict):
            return _extract_text_content(dumped.get("content"))
        return _extract_text_content(dumped)
    return ""


def _looks_like_placeholder_text(text: str) -> bool:
    normalized = " ".join((text or "").split()).strip()
    if not normalized:
        return True
    return normalized in {"{}", "[]", "null", '""', "```json {} ```", "```json\n{}\n```"}


def _extract_text_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_extract_text_content(item) for item in value]
        return "".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("text", "content", "value"):
            text = _extract_text_content(value.get(key))
            if text:
                return text
        return ""
    if hasattr(value, "text"):
        text = _extract_text_content(getattr(value, "text", None))
        if text:
            return text
    if hasattr(value, "content"):
        text = _extract_text_content(getattr(value, "content", None))
        if text:
            return text
    if hasattr(value, "model_dump"):
        try:
            return _extract_text_content(value.model_dump(exclude_none=False))
        except Exception:
            return ""
    return ""


def _tool_name(tool: dict[str, Any]) -> str:
    function = tool.get("function")
    if not isinstance(function, dict):
        return ""
    return str(function.get("name") or "")


def _select_tool_definitions(
    tool_definitions: list[dict[str, Any]],
    *,
    latest_user_message: str = "",
    max_tools: int = _LLM_TOOL_LIMIT,
) -> list[dict[str, Any]]:
    """Keep tool payloads within provider limits while preserving relevant tools."""
    by_name: dict[str, dict[str, Any]] = {}
    ordered_names: list[str] = []
    for tool in tool_definitions:
        name = _tool_name(tool)
        if not name or name in by_name:
            continue
        by_name[name] = tool
        ordered_names.append(name)

    deduped = [by_name[name] for name in ordered_names]
    if len(deduped) <= max_tools:
        return deduped

    text = (latest_user_message or "").lower()
    promoted: set[str] = set()
    for keyword, names in _TOOL_KEYWORD_PROMOTIONS.items():
        if keyword in text:
            promoted.update(names)

    def priority(name: str) -> int:
        if name in promoted:
            return 0
        if name in _CORE_TOOL_PRIORITY:
            return 1
        return 2

    indexed = [(idx, name, by_name[name]) for idx, name in enumerate(ordered_names)]
    selected = sorted(indexed, key=lambda item: (priority(item[1]), item[0]))[:max_tools]
    return [tool for _, _, tool in sorted(selected, key=lambda item: item[0])]


def _latest_user_message_from_call_kwargs(kwargs: dict[str, Any]) -> str:
    messages = kwargs.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        return _extract_text_content(content)
    return ""


def _normalize_tool_call_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Defensively enforce provider tool-count limits at the LiteLLM boundary."""
    tools = kwargs.get("tools")
    if not isinstance(tools, list):
        return kwargs

    latest_user_message = _latest_user_message_from_call_kwargs(kwargs)
    selected_tools = _select_tool_definitions(
        tools,
        latest_user_message=latest_user_message,
    )
    if len(selected_tools) < len(tools):
        log.warning(
            "LLM tool payload trimmed before provider call: original=%s selected=%s latest_user_message_len=%s",
            len(tools),
            len(selected_tools),
            len(latest_user_message),
        )
        normalized = dict(kwargs)
        normalized["tools"] = selected_tools
        return normalized
    return kwargs


def _should_retry_without_tools(error: Exception, candidate: str, kwargs: dict[str, Any]) -> bool:
    if "tools" not in kwargs:
        return False
    text = str(error).lower()
    if "tool_choice" in text:
        return True
    provider = model_provider(candidate)
    if provider in {"ollama", "minimax"} and any(
        token in text for token in ("bad_request_error", "invalid", "unsupported", "tool", "function")
    ):
        return True
    return False


def _should_retry_minimax_safe(error: Exception, candidate: str) -> bool:
    if model_provider(candidate) != "minimax":
        return False
    text = str(error).lower()
    return "invalid chat setting" in text or "bad_request_error" in text


def _minimax_safe_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    stripped = dict(kwargs)
    for key in (
        "tools",
        "tool_choice",
        "temperature",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
        "reasoning_effort",
        "thinking",
        "reasoning_split",
    ):
        stripped.pop(key, None)
    return stripped


async def _acompletion_with_fallback(
    *,
    model: str,
    route_payload: dict | None = None,
    route_context: dict[str, Any] | None = None,
    **kwargs,
):
    kwargs = _normalize_tool_call_kwargs(kwargs)
    last_error: Exception | None = None
    chosen_candidate = model
    errors: list[str] = []
    route_mode = str((route_context or {}).get("route") or "default")
    requested_provider = str((route_context or {}).get("requested_provider") or model_provider(model))
    candidates = _candidate_models(model, route_payload, route_context=route_context)
    log.info(
        "LLM route start: route=%s requested_provider=%s requested_model=%s cross_provider_fallback=%s candidates=%s",
        route_mode,
        requested_provider,
        model,
        bool((route_context or {}).get("cross_provider_fallback")),
        candidates,
    )
    invite_api_key = str((route_context or {}).get("invite_api_key") or "").strip() or None
    invite_auth_mode = str((route_context or {}).get("invite_auth_mode") or "api_key").strip().lower()
    for candidate in candidates:
        try:
            chosen_candidate = candidate
            call_kwargs = dict(kwargs)
            candidate_provider = model_provider(candidate)
            provider_api_key: str | None = None
            provider_auth_mode = "api_key"
            if invite_api_key:
                provider_api_key = invite_api_key
                provider_auth_mode = invite_auth_mode
            else:
                provider_api_key, provider_auth_mode = _global_provider_auth_config(candidate_provider)
            if provider_api_key:
                call_kwargs["api_key"] = provider_api_key
                # Claude Pro/Max subscription tokens (sk-ant-oat01-…) authenticate
                # via Authorization: Bearer plus the oauth beta header — the same
                # mechanism openclaw and Hermes use to drive subscription quota
                # from the Messages API. Litellm forwards extra_headers verbatim;
                # Anthropic accepts Bearer auth when the oauth beta is opted into.
                if provider_auth_mode == "oauth" and candidate_provider == "anthropic":
                    prior_headers = dict(call_kwargs.get("extra_headers") or {})
                    prior_headers.setdefault("Authorization", f"Bearer {provider_api_key}")
                    prior_headers.setdefault("anthropic-beta", "oauth-2025-04-20")
                    call_kwargs["extra_headers"] = prior_headers
            _t0 = time.perf_counter()
            response = await litellm.acompletion(model=candidate, **call_kwargs)
            record_latency(candidate, time.perf_counter() - _t0)
            log.info(
                "LLM route applied: route=%s requested_provider=%s requested_model=%s cross_provider_fallback=%s applied_provider=%s applied_model=%s latency_s=%.2f",
                route_mode,
                requested_provider,
                model,
                bool((route_context or {}).get("cross_provider_fallback")),
                model_provider(candidate),
                candidate,
                time.perf_counter() - _t0,
            )
            if candidate != model:
                log.warning(
                    "LLM fallback succeeded: requested=%s applied=%s prior_errors=%s",
                    model,
                    candidate,
                    errors,
                )
            return chosen_candidate, response
        except Exception as exc:
            last_error = exc
            errors.append(f"{candidate}: {type(exc).__name__}: {exc}")
            # OpenRouter returns 404 "No endpoints found that support the provided
            # 'tool_choice' value" when the selected model/provider doesn't support
            # function calling.  litellm.drop_params=True only strips params that
            # litellm itself knows about — it can't suppress a router-level 404.
            # Retry this candidate without tools so the model can still give a
            # plain-text answer rather than crashing the whole request.
            if _should_retry_without_tools(exc, candidate, kwargs):
                try:
                    no_tool_kwargs = {k: v for k, v in call_kwargs.items()
                                      if k not in ("tools", "tool_choice")}
                    _t0 = time.perf_counter()
                    response = await litellm.acompletion(model=candidate, **no_tool_kwargs)
                    record_latency(candidate, time.perf_counter() - _t0)
                    log.warning(
                        "tool-enabled request rejected by %s — retried without tools successfully",
                        candidate,
                    )
                    return chosen_candidate, response
                except Exception as exc2:
                    last_error = exc2
                    errors.append(f"{candidate}(no-tools): {type(exc2).__name__}: {exc2}")
                    exc = exc2
            if _should_retry_minimax_safe(exc, candidate):
                try:
                    safe_kwargs = _minimax_safe_kwargs(call_kwargs)
                    _t0 = time.perf_counter()
                    response = await litellm.acompletion(model=candidate, **safe_kwargs)
                    record_latency(candidate, time.perf_counter() - _t0)
                    log.warning(
                        "MiniMax rejected chat settings for %s; retried with safe text-only settings successfully",
                        candidate,
                    )
                    return chosen_candidate, response
                except Exception as exc3:
                    last_error = exc3
                    errors.append(f"{candidate}(minimax-safe): {type(exc3).__name__}: {exc3}")
                    exc = exc3
            if route_context and route_context.get("provider_locked"):
                friendly_error = _format_locked_route_error(route_context, exc)
                log.error(
                    "LLM locked route failed: route=%s requested_provider=%s requested_model=%s error=%s",
                    route_mode,
                    requested_provider,
                    model,
                    friendly_error,
                )
                raise RuntimeError(friendly_error) from exc
            continue
    if last_error is not None:
        log.error(
            "LLM completion failed for all candidates: requested=%s candidates=%s errors=%s",
            model,
            candidates,
            errors,
        )
        raise last_error
    chosen_candidate = model
    response = await litellm.acompletion(model=chosen_candidate, **kwargs)
    return chosen_candidate, response


def resolve_model_for_agent(
    *,
    default_model: str,
    agent_name: str | None = None,
) -> str:
    return get_agent_route_context(default_model=default_model, agent_name=agent_name)["model"]


def get_model(user_id: str | None = None, agent_name: str | None = None) -> str:
    if user_id and user_id in _user_models:
        base = _user_models[user_id]
    else:
        base = _default_model()
    return resolve_model_for_agent(default_model=base, agent_name=agent_name)


def set_model(user_id: str, model: str) -> str:
    """Set model preference for a user. Returns the model string."""
    if not is_valid_model(model):
        raise ValueError(f"Unknown model '{model}'. Available: {', '.join(AVAILABLE_MODELS)}")
    _user_models[user_id] = model
    return model


_WEB_SEARCH_HINT_RE = re.compile(
    r"\b("
    r"latest|recent|current|today|news|headline|price|pricing|cost|token cost|weather|look up|lookup|search the web|browse|google|"
    r"website|web page|url|docs?|documentation|release notes?|what changed"
    r")\b",
    re.IGNORECASE,
)
_FETCH_URL_HINT_RE = re.compile(
    r"(https?://\S+)"                                   # explicit URL in message
    r"|(\bgo to\b|\bvisit\b|\bopen\b|\bread\b|\bcheck\b|\bfetch\b)"
    r".*\.(com|org|net|io|co|ai|app|dev|info|gov|edu)",
    re.IGNORECASE,
)
_BROWSER_INTERACTION_HINT_RE = re.compile(
    r"\b("
    r"register|sign up|signup|log in|login|navigate|click|fill|form|submit|reply|respond|comment|post|"
    r"interact|complete the form|enter the site"
    r")\b",
    re.IGNORECASE,
)
_SERVER_READ_HINT_RE = re.compile(
    r"\b("
    r"server|machine|local machine|droplet|system|service|journal|log|logs|memory|disk|cpu|process|"
    r"listener|listeners|port|socket|status|uptime|network|troubleshoot|debug|investigate|check itself|root"
    r")\b",
    re.IGNORECASE,
)

_SHELL_RUN_HINT_RE = re.compile(
    r"\b("
    r"run|execute|shell|terminal|command|cmd|powershell|bash|script|"
    r"dir|ls|cd|mkdir|rm|del|copy|move|pip|npm|git|python|node|"
    r"install|uninstall|start|stop|restart|kill|open|launch|type into"
    r")\b",
    re.IGNORECASE,
)


def _should_nudge_web_search(message: str) -> bool:
    return bool(_WEB_SEARCH_HINT_RE.search((message or "").strip()))


def _should_nudge_fetch_url(message: str) -> bool:
    return bool(_FETCH_URL_HINT_RE.search((message or "").strip()))


def _should_nudge_browser_interaction(message: str) -> bool:
    msg = (message or "").strip()
    return bool(_BROWSER_INTERACTION_HINT_RE.search(msg))


def _should_nudge_server_read(message: str) -> bool:
    return bool(_SERVER_READ_HINT_RE.search((message or "").strip()))


def _available_models_for_default_route(route_context: dict[str, Any]) -> set[str]:
    requested_provider = str(route_context.get("requested_provider") or "").strip()
    allow_cross_provider = bool(route_context.get("cross_provider_fallback"))
    dynamic_same_provider = {
        str(route_context.get("model") or "").strip(),
        _default_model(),
        get_openrouter_default_model(),
        get_local_default_model(),
        *get_model_stack().values(),
    }
    if allow_cross_provider:
        return {
            model_name
            for model_name in {*(set(AVAILABLE_MODELS)), *dynamic_same_provider}
            if model_name
        }
    return {
        model_name.strip()
        for model_name in {*(set(AVAILABLE_MODELS)), *dynamic_same_provider}
        if model_provider(model_name) == requested_provider
    }


async def stream_chat(
    messages: list[dict],
    user_id: str | None = None,
    model: str | None = None,
    agent_name: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream chat completion tokens. Yields text deltas."""
    base_model = model or get_model(user_id)
    route_context = get_agent_route_context(default_model=base_model, agent_name=agent_name)
    chosen = route_context["model"]
    if route_context["provider_locked"]:
        await _ensure_locked_route_ready(route_context)
    elif route_context["route"] == "default" and not route_context.get("cross_provider_fallback"):
        chosen = route_context["model"]
    guarded_messages = list(messages)
    if guarded_messages and guarded_messages[0].get("role") == "system":
        guarded_messages.insert(1, {"role": "system", "content": _GLOBAL_OPERATION_GUARDRAILS})
    else:
        guarded_messages.insert(0, {"role": "system", "content": _GLOBAL_OPERATION_GUARDRAILS})
    async for delta in _stream_text_with_fallback(
        model=chosen,
        route_payload=None,
        route_context=route_context,
        messages=guarded_messages,
        temperature=0.2,
    ):
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
    is_operator: bool = False,
    is_privileged: bool = False,
) -> AsyncGenerator[dict, None]:
    """
    Tool-aware streaming. Yields typed event dicts:
      {"type": "routing",    "payload": {...}}
      {"type": "tool_start", "tool": "web_search", "input": {...}}
      {"type": "tool_done",  "tool": "web_search", "result": "..."}
      {"type": "token",      "token": "..."}

    Handles the tool-calling loop automatically (up to SPARKBOT_MAX_TOOL_ROUNDS, default 20), then
    streams the final LLM response token-by-token.
    """
    from app.api.routes.chat.tools import (
        TOOL_DEFINITIONS,
        execute_tool,
        _email_configured_smtp,
        _google_configured,
    )
    guardian_suite = get_guardian_suite()

    base_model = model or get_model(user_id)
    route_context = get_agent_route_context(default_model=base_model, agent_name=agent_name)
    chosen = route_context["model"]
    msgs = list(messages)
    if msgs and msgs[0].get("role") == "system":
        msgs.insert(1, {"role": "system", "content": _GLOBAL_OPERATION_GUARDRAILS})
    else:
        msgs.insert(0, {"role": "system", "content": _GLOBAL_OPERATION_GUARDRAILS})
    latest_user_message = next(
        (
            str(msg.get("content", ""))
            for msg in reversed(msgs)
            if msg.get("role") == "user"
        ),
        "",
    )
    selected_tool_definitions = _select_tool_definitions(
        TOOL_DEFINITIONS,
        latest_user_message=latest_user_message,
    )
    if len(selected_tool_definitions) < len(TOOL_DEFINITIONS):
        log.info(
            "LLM tool manifest trimmed: original=%s selected=%s latest_user_message_len=%s",
            len(TOOL_DEFINITIONS),
            len(selected_tool_definitions),
            len(latest_user_message),
        )

    if latest_user_message:
        if route_context["provider_locked"]:
            await _ensure_locked_route_ready(route_context)
            route_payload = _locked_route_payload(
                message=latest_user_message,
                route_context=route_context,
            )
        else:
            available_models = _available_models_for_default_route(route_context)
            try:
                routed_model, route_payload = guardian_suite.token_guardian.route_model(
                    latest_user_message,
                    chosen,
                    available_models=available_models,
                )
                chosen = routed_model
                route_payload = _annotate_route_payload(
                    route_payload,
                    route_context=route_context,
                    current_model=route_context["model"],
                    applied_model=chosen,
                )
                route_payload["cross_provider_fallback"] = bool(route_context.get("cross_provider_fallback"))
                route_payload["provider_authoritative"] = not bool(route_context.get("cross_provider_fallback"))
            except Exception as _tg_err:
                log.debug("Token Guardian route_model raised: %s", _tg_err, exc_info=True)
                route_payload = _provider_authoritative_route_payload(
                    message=latest_user_message,
                    route_context=route_context,
                )
                chosen = route_context["model"]
    else:
        route_payload = None

    if route_payload is not None:
        yield {"type": "routing", "payload": route_payload}

    if latest_user_message:
        wants_browser_interaction = _should_nudge_browser_interaction(latest_user_message)
        if wants_browser_interaction:
            msgs.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "The user is asking for interactive website actions. "
                        "You are authorized to perform all web automation: open browsers, navigate pages, fill forms, click buttons, register accounts, post and reply to content. "
                        "Use browser_open first, then browser_snapshot to see the page, then browser_fill_field and browser_click to interact. "
                        "Do NOT refuse or claim you cannot register, navigate, or post — just do it using the browser tools and report what happened."
                    ),
                },
            )
        if _should_nudge_fetch_url(latest_user_message) and not wants_browser_interaction:
            msgs.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "The user wants you to visit or read a specific URL or website. "
                        "Use the fetch_url tool to retrieve the page content, then respond based on what you read. "
                        "You CAN and SHOULD fetch URLs — do not say you cannot visit websites."
                    ),
                },
            )
        if _should_nudge_web_search(latest_user_message):
            msgs.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "This request likely needs live external information. "
                        "Use the web_search tool unless the user explicitly asked for reasoning only."
                    ),
                },
            )
        if _SHELL_RUN_HINT_RE.search(latest_user_message):
            msgs.insert(
                1,
                {
                    "role": "system",
                    "content": (
                        "You have a shell_run tool that runs PowerShell (Windows) or bash commands "
                        "directly on the user's local machine. Use it immediately for any task involving "
                        "running commands, scripts, file operations, git, npm, pip, or anything terminal-related. "
                        "Do NOT say you cannot run commands — use shell_run and report the output."
                    ),
                },
            )
        if _should_nudge_server_read(latest_user_message):
            if room_execution_allowed:
                msgs.insert(
                    1,
                    {
                        "role": "system",
                        "content": (
                            "This request appears to be about the local machine or services. "
                            "Use read-only server tools for diagnostics before answering when relevant."
                        ),
                    },
                )
            else:
                msgs.insert(
                    1,
                    {
                        "role": "system",
                        "content": (
                            "This request appears to be about the local machine or services, "
                            "but Computer Control is off. Ask for break-glass PIN authorization instead of pretending the tools do not exist."
                        ),
                    },
                )

    if db_session is not None and user_id and room_id and route_payload:
        try:
            import uuid as _uuid
            from app.crud import create_audit_log

            mode = str(route_payload.get("mode") or "shadow")
            tool_name = "tokenguardian_live" if mode == "live" else "tokenguardian_shadow"
            create_audit_log(
                session=db_session,
                tool_name=tool_name,
                tool_input=json.dumps(
                    {
                        "query": latest_user_message[:500],
                        "current_model": route_payload.get("current_model", chosen),
                    }
                ),
                tool_result=json.dumps(route_payload)[:8000],
                user_id=_uuid.UUID(user_id),
                room_id=_uuid.UUID(room_id),
                agent_name=agent_name,
                model=chosen,
            )
        except Exception:
            pass

    tool_usage_counts: dict[str, int] = {}
    _max_tool_rounds = max(5, min(int(os.getenv("SPARKBOT_MAX_TOOL_ROUNDS", "20")), 50))
    final_output_text = ""
    selected_provider = model_provider(chosen)

    try:
        for _round in range(_max_tool_rounds):
            tool_choice: str = "auto"
            if tool_usage_counts.get("web_search", 0) >= 2:
                msgs.append(
                    {
                        "role": "system",
                        "content": (
                            "You already have live search results. "
                            "Do not call web_search again. Synthesize the answer from the tool results you already received."
                        ),
                    }
                )
                tool_choice = "none"

            if tool_usage_counts.get("shell_run", 0) >= 2:
                msgs.append(
                    {
                        "role": "system",
                        "content": (
                            "You already have shell_run output. "
                            "Do not call shell_run again. Respond directly using the output you already received."
                        ),
                    }
                )
                tool_choice = "none"

            if tool_usage_counts.get("browser_open", 0) >= 1 and tool_usage_counts.get("browser_snapshot", 0) >= 1:
                msgs.append(
                    {
                        "role": "system",
                        "content": (
                            "You have already opened the browser and taken a snapshot. "
                            "Do not call browser_open or browser_snapshot again. Respond with what you found."
                        ),
                    }
                )
                tool_choice = "none"

            # Non-streaming call to resolve any tool calls
            chosen, response = await _acompletion_with_fallback(
                model=chosen,
                route_payload=route_payload,
                route_context=route_context,
                messages=msgs,
                tools=selected_tool_definitions,
                tool_choice=tool_choice,
                temperature=0.2,
            )

            choice = response.choices[0]
            finish_reason = choice.finish_reason
            assistant_msg = choice.message

            # If the model returned plain text (tool_choice rejected and retried
            # without tools, or the model simply chose not to call a tool), stream
            # the content directly and exit the loop.
            if finish_reason != "tool_calls" or not getattr(assistant_msg, "tool_calls", None):
                text = _assistant_message_text(assistant_msg)
                if (selected_provider in {"ollama", "minimax"} and _looks_like_placeholder_text(text)) or not text:
                    text = await _retry_plain_text_without_tools(
                        chosen=chosen,
                        route_payload=route_payload,
                        route_context=route_context,
                        messages=msgs,
                        temperature=0.2,
                    )
                if text:
                    final_output_text += text
                    yield {"type": "token", "token": text}
                    guardian_improvement.record_outcome(
                        user_id=user_id,
                        room_id=room_id,
                        route_payload=route_payload,
                        output_text=final_output_text,
                        tool_usage_counts=tool_usage_counts,
                        success=True,
                        agent_name=agent_name,
                    )
                else:
                    guardian_improvement.record_outcome(
                        user_id=user_id,
                        room_id=room_id,
                        route_payload=route_payload,
                        output_text="",
                        tool_usage_counts=tool_usage_counts,
                        success=False,
                        agent_name=agent_name,
                        error="empty or placeholder assistant response",
                    )
                return

            if finish_reason == "tool_calls" and assistant_msg.tool_calls:
                # Append the assistant's tool-call turn
                msgs.append(assistant_msg.model_dump(exclude_none=True))

                for tc in assistant_msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        tool_args = json.loads(tc.function.arguments)
                    except Exception:
                        tool_args = {}

                    decision = guardian_suite.policy.decide_tool_use(
                        tool_name,
                        tool_args if isinstance(tool_args, dict) else {},
                        room_execution_allowed=room_execution_allowed,
                        is_operator=is_operator,
                        is_privileged=is_privileged,
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
                                        "tool_args": json.loads(serialize_tool_args_for_audit(tool_name, tool_args)),
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
                        verification = None
                        if guardian_suite.verifier.should_verify_interactive_tool_run(
                            action_type=decision.action_type,
                            high_risk=decision.high_risk,
                        ):
                            verification = guardian_suite.verifier.verify_interactive_tool_run(
                                tool_name=tool_name,
                                output=result,
                                execution_status="denied",
                            )
                        yield {"type": "tool_start", "tool": tool_name, "input": tool_args}
                        tool_done_event = {"type": "tool_done", "tool": tool_name, "result": result[:300]}
                        if verification is not None:
                            tool_done_event["verification_status"] = verification.status
                            tool_done_event["confidence"] = verification.confidence
                            if verification.recommended_next_action:
                                tool_done_event["recommended_next_action"] = verification.recommended_next_action
                        yield tool_done_event
                        msgs.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": (
                                f"{result}\n\n{guardian_suite.verifier.format_verifier_note(verification)}"
                                if verification is not None
                                else result
                            ),
                        })
                        continue

                    if decision.action in ("privileged", "privileged_reveal"):
                        confirm_id = str(_uuid_module.uuid4())
                        _pending_ttl_cleanup()
                        pending_entry = {
                            "tool": tool_name,
                            "args": tool_args,
                            "user_id": user_id,
                            "room_id": room_id,
                            "created_at": time.time(),
                        }
                        _pending[confirm_id] = pending_entry
                        try:
                            guardian_suite.pending_approvals.store_pending_approval(
                                confirm_id=confirm_id,
                                tool_name=tool_name,
                                tool_args=tool_args if isinstance(tool_args, dict) else {},
                                user_id=user_id,
                                room_id=room_id,
                            )
                        except Exception:
                            pass
                        yield {
                            "type": "privileged_required",
                            "confirm_id": confirm_id,
                            "tool": tool_name,
                            "input": tool_args,
                            "risk": decision.reason,
                            "requires_confirm_after_auth": decision.action == "privileged_reveal",
                        }
                        return

                    if decision.action == "confirm":
                        # Don't prompt for confirmation when email sending is unavailable.
                        # Let the tool return the concrete configuration error instead.
                        if tool_name == "email_send" and not _email_configured_smtp():
                            pass
                        elif tool_name in {"gmail_send", "drive_create_folder", "calendar_create_event"} and not _google_configured():
                            pass
                        else:
                            already_confirmed = confirmed_ids and any(
                                c for c in (confirmed_ids or set()) if c
                            )
                            if not already_confirmed:
                                confirm_id = str(_uuid_module.uuid4())
                                _pending_ttl_cleanup()
                                pending_entry = {
                                    "tool": tool_name,
                                    "args": tool_args,
                                    "user_id": user_id,
                                    "room_id": room_id,
                                    "created_at": time.time(),
                                }
                                _pending[confirm_id] = pending_entry
                                try:
                                    guardian_suite.pending_approvals.store_pending_approval(
                                        confirm_id=confirm_id,
                                        tool_name=tool_name,
                                        tool_args=tool_args if isinstance(tool_args, dict) else {},
                                        user_id=user_id,
                                        room_id=room_id,
                                    )
                                except Exception:
                                    pass
                                yield {
                                    "type": "confirm_required",
                                    "confirm_id": confirm_id,
                                    "tool": tool_name,
                                    "input": tool_args,
                                }
                                return

                    yield {"type": "tool_start", "tool": tool_name, "input": tool_args}

                    result = await guardian_suite.executive.exec_with_guard(
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
                    output_guardrail = guardian_suite.tool_guardrails.validate_tool_output(
                        tool_name,
                        str(result),
                        high_risk=decision.high_risk,
                    )
                    if not output_guardrail.allowed:
                        result = f"TOOL GUARDRAIL REJECTED: {output_guardrail.reason}"
                    verification = None
                    if guardian_suite.verifier.should_verify_interactive_tool_run(
                        action_type=decision.action_type,
                        high_risk=decision.high_risk,
                    ):
                        verification = guardian_suite.verifier.verify_interactive_tool_run(
                            tool_name=tool_name,
                            output=str(result),
                            execution_status="success" if output_guardrail.allowed else "rejected",
                        )

                    # Vault-internal tools: mask plaintext in all outward-facing paths.
                    # The full plaintext stays in `result` for the LLM context only.
                    outward_result = mask_tool_result_for_external(tool_name, tool_args, result)
                    tool_done_event = {"type": "tool_done", "tool": tool_name, "result": outward_result[:300]}
                    if verification is not None:
                        tool_done_event["verification_status"] = verification.status
                        tool_done_event["confidence"] = verification.confidence
                        if verification.recommended_next_action:
                            tool_done_event["recommended_next_action"] = verification.recommended_next_action
                    yield tool_done_event
                    tool_usage_counts[tool_name] = tool_usage_counts.get(tool_name, 0) + 1

                    # Audit log — best-effort, never let it break the chat stream
                    if db_session is not None:
                        try:
                            import uuid as _uuid
                            from app.crud import create_audit_log
                            redacted_input, redacted_result = redact_tool_call_for_audit(
                                tool_name, tool_args, result
                            )
                            if verification is not None:
                                redacted_result = f"{redacted_result}\n\n{guardian_suite.verifier.format_verifier_note(verification)}"
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
                                guardian_suite.memory.remember_tool_event(
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
                        "content": (
                            f"{result}\n\n{guardian_suite.verifier.format_verifier_note(verification)}"
                            if verification is not None
                            else result
                        ),
                    })
                    # Continue working directive - only if task likely incomplete
                    if _round < _max_tool_rounds - 2:
                        pass
            else:
                async for delta in _stream_text_with_fallback(
                    model=chosen,
                    route_payload=route_payload,
                    route_context=route_context,
                    messages=msgs,
                    temperature=0.2,
                ):
                    final_output_text += delta
                    yield {"type": "token", "token": delta}
                guardian_improvement.record_outcome(
                    user_id=user_id,
                    room_id=room_id,
                    route_payload=route_payload,
                    output_text=final_output_text,
                    tool_usage_counts=tool_usage_counts,
                    success=bool(final_output_text.strip()),
                    agent_name=agent_name,
                    error="" if final_output_text.strip() else "empty final streaming response",
                )
                return
    except Exception as exc:
        guardian_improvement.record_outcome(
            user_id=user_id,
            room_id=room_id,
            route_payload=route_payload,
            output_text=final_output_text,
            tool_usage_counts=tool_usage_counts,
            success=False,
            agent_name=agent_name,
            error=str(exc),
        )
        raise

    guardian_improvement.record_outcome(
        user_id=user_id,
        room_id=room_id,
        route_payload=route_payload,
        output_text=final_output_text,
        tool_usage_counts=tool_usage_counts,
        success=False,
        agent_name=agent_name,
        error="tool loop limit reached",
    )
    yield {"type": "token", "token": "\n\n⚠️ Tool loop limit reached."}
