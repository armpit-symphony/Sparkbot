# Sparkbot error handling

Sparkbot is built so that no single failing layer can take the whole app
down. Every boundary that talks to the outside world (model providers,
HTTP, shell, OAuth-backed comms, file I/O) is wrapped in a try/except,
and the failure is converted into either a fallback path or a short,
user-actionable string before it reaches the chat surface.

This document maps every error path you can hit in a normal Sparkbot
session, where the exception is caught, what the user sees, and where
the full traceback is logged.

## Layered error model

Sparkbot has four error boundaries, each with its own recovery strategy.

```
┌────────────────────────────────────────────────────────────────────┐
│  UI / SSE stream                                                   │
│  rooms.py, uploads.py, messages.py                                 │
│  Surfaces: {"type":"error","error":<friendly>,"detail":<raw>}      │
└──────────────────────────▲─────────────────────────────────────────┘
                           │ humanise_chat_error()
┌──────────────────────────┴─────────────────────────────────────────┐
│  LLM router  (llm._acompletion_with_fallback)                      │
│  Strategy: retry next candidate, retry without tools, trim tools,  │
│            retry with MiniMax-safe params                          │
└──────────────────────────▲─────────────────────────────────────────┘
                           │ raises after all candidates fail
┌──────────────────────────┴─────────────────────────────────────────┐
│  Tool execution  (executive.exec_with_guard → tools.execute_tool)  │
│  Strategy: caught per-tool, returns "TOOL ERROR: <reason>" string  │
│            to the LLM so it can recover; no exception escapes      │
└──────────────────────────▲─────────────────────────────────────────┘
                           │
┌──────────────────────────┴─────────────────────────────────────────┐
│  Background loops  (Spine, scheduler, watchers)                    │
│  Strategy: log + continue. Failures never crash the loop.          │
└────────────────────────────────────────────────────────────────────┘
```

## What the user sees

When something goes wrong inside the chat path the SSE stream emits a
single event with shape:

```
data: {"type":"error","error":"<short, actionable>","detail":"<raw, truncated>"}
```

`humanise_chat_error()` (in `backend/app/api/routes/chat/llm.py`)
recognises the most common provider failures and rewrites them:

| Raw error contains                       | User sees                                                                                                       |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `tools': array too long`                 | "The tool catalogue is larger than this provider allows. The router is shrinking it and retrying — try again." |
| `rate_limit`, `429`                      | "Provider is rate-limiting us right now. Wait and retry, or switch model in Controls."                          |
| `insufficient_quota`, `quota exceeded`   | "Provider quota exhausted. Add credits or rotate the key in Controls → Comms / API keys."                       |
| `authentication`, `invalid api key`, 401 | "Provider rejected our credentials. Re-enter the API key in Controls."                                          |
| `context length`, `context_window`       | "Conversation too long for this model's context. Start a new room or switch to a larger model."                 |
| `model_not_found`, `no such model`       | "Selected model not available. Pick a different model in Controls → Stack."                                     |
| `timeout`, `timed out`                   | "Model timed out. Retry, or pick a faster model."                                                               |
| `ssl`, `connection`                      | "Network error reaching the provider. Check connectivity and retry."                                            |
| anything else                            | The raw message, with the leading `litellm.<Class>:` framing stripped.                                          |

The full original exception still goes to the backend log via
`log.exception(...)` so diagnostics aren't lost.

## Tool-level errors

Tool calls run inside `guardian_suite.executive.exec_with_guard`, which
itself runs inside a try/except in the chat tool loop. If a tool raises,
the round emits a normal `tool_done` event with content
`"TOOL ERROR: <humanised reason>"`. The LLM sees this in the next round
and can either retry, pick a different tool, or apologise to the user —
the chat itself never aborts.

Tool latency and error counts are recorded by `record_tool_call(...)`.
Read them via the `/perf` slash command or `GET /api/v1/chat/performance`.

## Tool catalogue safety

The chat router applies two layers of defense around the OpenAI 128-tool
limit:

1. **Pre-flight trim** — `_select_tool_definitions()` deduplicates by
   name, then keeps the first 128 tools, prioritising tools the latest
   user message hints at (`youtube*` for "video", `time_*` for "timer",
   `spotify_*` for "spotify", etc.) and a fixed core list.
2. **Trim-and-retry** — if a provider still rejects the call with an
   "array too long" error (different limit than 128), the router halves
   the trimmed list and retries automatically. This kicks in for niche
   providers with stricter limits.

Duplicate tool names are also rejected at registration time; the native
definitions in `tools.py` win over same-named skills, and a warning is
logged for diagnostic purposes.

## LLM router recovery

`_acompletion_with_fallback` walks the candidate list (primary →
backups → heavy-hitter, filtered by configured providers) and recovers
from these failure modes per candidate:

| Failure                                                                  | Recovery                                                              |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| `tool_choice` not supported                                              | Retry the same candidate without `tools`/`tool_choice`                |
| Ollama / MiniMax tool refusal                                            | Retry the same candidate without `tools`/`tool_choice`                |
| Tools array too long                                                     | Trim to len-16 (capped at 120) and retry                              |
| MiniMax "invalid chat setting"                                           | Retry with stripped sampling params (`_minimax_safe_kwargs`)          |
| Locked route (`provider_locked` agent) failure                           | Raise a friendly RuntimeError with provider-specific guidance         |
| Anything else                                                            | Move to the next candidate in the list                                |

Per-candidate latency and error counts are recorded so the `/perf`
command can show which model is flaking.

## Comms bridges

Outbound bridges (Telegram, Discord, Slack, Gmail, Google Calendar,
Outlook) wrap their HTTP calls in try/except and either:

- Return a string starting with `"<provider>_send failed: ..."` for
  surface in chat, or
- Log and skip silently when the failure happens in a background loop
  (e.g. the Telegram poll catching up after a reconnect).

A failed comms send never aborts the chat round it was triggered from.

## Guardian suite

Each guardian (Policy, Token, Task, Memory, Vault, Executive) wraps
public methods in try/except and returns either a default-deny decision
or an empty result on failure. This means:

- `policy.decide_tool_use` returning `deny` on a thrown exception is the
  safe path; the user gets `"POLICY DENIED: <reason>"`.
- `memory.remember_*` and `memory.recall_*` swallow exceptions and log;
  a corrupted ledger never aborts the chat round.
- `executive.exec_with_guard` wraps the actual tool call and is itself
  wrapped at the chat layer — see "Tool-level errors" above.

## Background loops

Three background workers run for the lifetime of the backend:

- **Task Guardian scheduler** — fires scheduled tools on cadence
- **Process watcher** — monitors local CPU / memory and throttles
- **Telegram bridge** (when configured) — long-poll loop

Each worker runs inside an `asyncio` task with a top-level
`while True: try: ... except Exception: log.exception(...); await sleep`
shape. A single failed iteration is logged and skipped; the loop keeps
ticking.

## Where to look when something breaks

- `%APPDATA%\Sparkbot\backend.log` — full backend traceback
- `/perf` slash command — model + tool error counts and last error
- `GET /api/v1/chat/audit?limit=20` — tool execution audit trail
- `%APPDATA%\Sparkbot\guardian\decisions.jsonl` — policy decisions
- `%APPDATA%\Sparkbot\guardian\executive.jsonl` — executive guard chain

If the chat itself is silent (no error event), open devtools, switch to
the Network tab, and inspect the `messages/stream` SSE stream — the
JSON event payload always carries enough to diagnose.
