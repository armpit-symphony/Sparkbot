# Sparkbot — Skill Author Guide

How to write, test, and ship a skill plugin for Sparkbot.

---

## Table of Contents

1. [What a skill is](#what-a-skill-is)
2. [Minimal skill template](#minimal-skill-template)
3. [Full skill template with all options](#full-skill-template-with-all-options)
4. [POLICY reference](#policy-reference)
5. [Multi-tool skills](#multi-tool-skills)
6. [Testing your skill locally](#testing-your-skill-locally)
7. [CI validation](#ci-validation)
8. [Common mistakes](#common-mistakes)
9. [Publishing a skill](#publishing-a-skill)

---

## What a skill is

A skill is a single `.py` file dropped into `backend/skills/`. On startup Sparkbot automatically discovers it, registers the tool with the LLM, and routes calls to your `execute()` function. No other files need editing — no router registration, no import changes.

Skills are called exactly like built-in tools — the LLM decides when to call them based on the `description` field. The same policy, audit, and confirmation system applies.

---

## Minimal skill template

Copy this and fill in the four marked fields. This is everything required.

```python
# backend/skills/my_tool.py
from __future__ import annotations

DEFINITION = {
    "name": "my_tool",                          # ← unique tool name (snake_case)
    "description": (                            # ← what the LLM reads to decide when to call this
        "One or two sentences describing what this tool does and when to use it. "
        "Be specific — the LLM uses this to decide when to call your tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {                          # ← rename/add parameters as needed
                "type": "string",
                "description": "The input to process.",
            },
        },
        "required": ["query"],
    },
}


async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    query = args.get("query", "").strip()
    if not query:
        return "Error: query is required."

    # ← your implementation here
    return f"Result for: {query}"
```

Drop it in `backend/skills/` and restart Sparkbot. The tool is live immediately.

---

## Full skill template with all options

```python
# backend/skills/example_full.py
"""
Sparkbot skill: example_full

Demonstrates every optional feature:
  - POLICY declaration
  - Custom timeout
  - Multiple return formats
  - Error handling patterns
  - Type hints
"""
from __future__ import annotations

import os
import logging

log = logging.getLogger(__name__)

# ── Tool definition (required) ─────────────────────────────────────────────────
# This is what the LLM sees. Write the description as if explaining to a smart
# colleague when they should use this tool.

DEFINITION = {
    "name": "example_full",
    "description": (
        "Example tool demonstrating all skill features. "
        "Use this as a template when writing new skills."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": "The text to process.",
            },
            "mode": {
                "type": "string",
                "enum": ["fast", "thorough"],
                "description": "Processing mode. Default: fast.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return (1–20). Default: 5.",
            },
        },
        "required": ["input"],
    },
}

# ── Policy (optional) ──────────────────────────────────────────────────────────
# Omit POLICY entirely to use the default: read/allow (safest).
# If your tool writes, sends, or executes anything, declare it here.
#
# IMPORTANT: use only these keys — 'category' and 'description' are NOT valid.
# See POLICY reference below for allowed values.

POLICY = {
    "scope": "read",                    # read | write | execute | admin
    "resource": "external",            # external | local_machine | system
    "default_action": "allow",         # allow | confirm | deny
    "action_type": "data_read",        # any descriptive string
    "high_risk": False,                # True → adds to executive guardian journal
    "requires_execution_gate": False,  # True → room must have execution gate enabled
}

# ── Optional: override the global skill timeout (seconds) ─────────────────────
# TIMEOUT = 30  # uncomment to set a custom timeout for this skill

# ── Executor (required) ────────────────────────────────────────────────────────
# - Must be async
# - Must accept (args, *, user_id=None, room_id=None, session=None)
# - Must return a str
# - Never raise — return an error string instead

async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    # Extract and validate args
    input_text = args.get("input", "").strip()
    if not input_text:
        return "Error: input is required."

    mode = args.get("mode", "fast")
    limit = min(int(args.get("limit", 5)), 20)

    log.debug("example_full called: mode=%s limit=%d user=%s", mode, limit, user_id)

    try:
        # Your implementation here
        result = f"Processed {limit} results for '{input_text}' in {mode} mode."
        return result
    except Exception as exc:
        log.exception("example_full failed: %s", exc)
        return f"Error: {exc}"
```

---

## POLICY reference

| Field | Type | Required | Allowed values |
|-------|------|----------|----------------|
| `scope` | str | yes | `"read"` `"write"` `"execute"` `"admin"` |
| `resource` | str | yes | `"external"` `"local_machine"` `"system"` `"workspace"` |
| `default_action` | str | yes | `"allow"` `"confirm"` `"deny"` |
| `action_type` | str | yes | any descriptive string (`"data_read"`, `"api_call"`, `"command_exec"`, `"code_exec"`) |
| `high_risk` | bool | no | default `False` |
| `requires_execution_gate` | bool | no | default `False` |

**Scope guidance:**

| What your tool does | scope |
|---------------------|-------|
| Reads data (web, files, APIs) | `"read"` |
| Writes, creates, or updates something | `"write"` |
| Runs a command, script, or program | `"execute"` |
| Manages system configuration | `"admin"` |

**Action guidance:**

| Use `default_action` | When |
|----------------------|------|
| `"allow"` | Read-only; reversible; low risk |
| `"confirm"` | Sends email, posts to Slack, writes files, creates calendar events |
| `"deny"` | Disabled by default; user must explicitly enable |

**DO NOT use these keys in POLICY** — they are not accepted by `ToolPolicy` and will crash skill loading:
- ❌ `"category"` — use `"scope"` instead
- ❌ `"description"` — use `"action_type"` instead

---

## Multi-tool skills

One `.py` file can register multiple tools using `_register_extra`:

```python
# backend/skills/my_multi_tool.py
from __future__ import annotations

# Primary tool (loaded automatically)
DEFINITION = {
    "name": "tool_one",
    "description": "First tool.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

POLICY = {
    "scope": "read", "resource": "external",
    "default_action": "allow", "action_type": "data_read",
    "high_risk": False, "requires_execution_gate": False,
}

async def execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return "tool_one result"


# Additional tools registered via _register_extra
_TOOL_TWO_DEFINITION = {
    "name": "tool_two",
    "description": "Second tool.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

_TOOL_TWO_POLICY = {
    "scope": "read", "resource": "external",
    "default_action": "allow", "action_type": "data_read",
    "high_risk": False, "requires_execution_gate": False,
}

async def _tool_two_execute(args: dict, *, user_id=None, room_id=None, session=None) -> str:
    return "tool_two result"


def _register_extra(registry) -> None:
    registry.definitions.append(_TOOL_TWO_DEFINITION)
    registry.executors["tool_two"] = _tool_two_execute
    registry.policies["tool_two"] = _TOOL_TWO_POLICY
```

---

## Testing your skill locally

### Quick import check

```bash
cd backend
python -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('skill', 'skills/my_tool.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('DEFINITION name:', mod.DEFINITION['name'])
print('execute is coroutine:', import_module_inspect_iscoroutine(mod.execute))
print('POLICY keys:', list(mod.POLICY.keys()) if hasattr(mod, 'POLICY') else 'default')
"
```

### Run the smoke test suite

```bash
# From repo root — tests all skills in backend/skills/
cd backend

# Windows
set DATABASE_TYPE=sqlite
set V1_LOCAL_MODE=true
set ENVIRONMENT=local
set PROJECT_NAME=Sparkbot
set SECRET_KEY=test-key
set FIRST_SUPERUSER=admin@example.com
set FIRST_SUPERUSER_PASSWORD=sparkbot-local
set SPARKBOT_PASSPHRASE=sparkbot-local
set BACKEND_CORS_ORIGINS=http://localhost:3000
set WORKSTATION_LIVE_TERMINAL_ENABLED=false
uv run python -m pytest tests/test_skills.py -v

# Linux / macOS
DATABASE_TYPE=sqlite V1_LOCAL_MODE=true ENVIRONMENT=local PROJECT_NAME=Sparkbot \
SECRET_KEY=test-key FIRST_SUPERUSER=admin@example.com \
FIRST_SUPERUSER_PASSWORD=sparkbot-local SPARKBOT_PASSPHRASE=sparkbot-local \
BACKEND_CORS_ORIGINS=http://localhost:3000 WORKSTATION_LIVE_TERMINAL_ENABLED=false \
uv run python -m pytest tests/test_skills.py -v
```

### Test execute() manually

```python
import asyncio

async def test():
    from skills.my_tool import execute
    result = await execute({"query": "hello"}, user_id="test", room_id="test")
    print(result)

asyncio.run(test())
```

### Test via Sparkbot chat

1. Drop your `.py` file into `backend/skills/`
2. Restart the backend
3. In chat: *"Use my_tool with input hello"*
4. Check `sparkbot-backend.log` for `Loaded skill: my_tool`

---

## CI validation

The `skill-tests.yml` workflow runs automatically on every push or PR that modifies files in `backend/skills/`. It validates:

| Check | What it catches |
|-------|----------------|
| Clean import | Syntax errors, missing dependencies |
| DEFINITION name | Missing or empty tool name |
| DEFINITION description | Missing description |
| DEFINITION parameters | Missing parameters block |
| `execute` is async | Forgot `async def` |
| `execute` signature | Missing `user_id`, `room_id`, `session` kwargs |
| POLICY key validity | `category`/`description` wrong keys crash skill loading |
| POLICY scope enum | Invalid scope string |
| POLICY default_action enum | Invalid action string |
| `_register_extra` safety | Multi-tool registration doesn't crash |

If CI fails, the error message tells you exactly which key or field is wrong and what to change it to.

---

## Common mistakes

**1. Using `category` or `description` as POLICY keys**
```python
# ❌ Wrong — crashes skill loading with TypeError
POLICY = {
    "category": "read",
    "description": "My tool",
    ...
}

# ✅ Correct
POLICY = {
    "scope": "read",
    "action_type": "data_read",
    ...
}
```

**2. `execute` is not async**
```python
# ❌ Wrong
def execute(args, *, user_id=None, room_id=None, session=None):
    return "result"

# ✅ Correct
async def execute(args, *, user_id=None, room_id=None, session=None):
    return "result"
```

**3. Raising exceptions instead of returning error strings**
```python
# ❌ Wrong — unhandled exception surfaces as "Skill error [name]: ..."
async def execute(args, *, user_id=None, room_id=None, session=None):
    raise ValueError("something failed")

# ✅ Correct — return a string the LLM can report back
async def execute(args, *, user_id=None, room_id=None, session=None):
    try:
        ...
    except Exception as exc:
        return f"Error: {exc}"
```

**4. Missing required keyword arguments**
```python
# ❌ Wrong — crashes at dispatch time
async def execute(args):
    ...

# ✅ Correct — all three kwargs required even if unused
async def execute(args, *, user_id=None, room_id=None, session=None):
    ...
```

**5. Blocking I/O in an async function**
```python
# ❌ Wrong — blocks the event loop; use httpx, not requests
import requests
async def execute(args, *, user_id=None, room_id=None, session=None):
    r = requests.get("https://example.com")   # blocks!

# ✅ Correct
import httpx
async def execute(args, *, user_id=None, room_id=None, session=None):
    async with httpx.AsyncClient() as client:
        r = await client.get("https://example.com")
```

---

## Publishing a skill

Skills are drop-in files — no PR to the main repo required for personal use. To share a skill:

1. Make sure `tests/test_skills.py` passes for your file
2. Ensure `POLICY` is correctly declared (CI will catch it if not)
3. Open a PR adding your `.py` file to `backend/skills/`
4. The `skill-tests.yml` workflow runs automatically and validates your skill

Skills added to the main repo become part of every Sparkbot install. Keep external API calls optional (check for missing env vars and return a helpful message if not configured).
