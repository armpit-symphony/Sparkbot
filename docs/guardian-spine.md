# Guardian Suite ↔ Spine: how they interact in the background

The **Guardian Suite** is Sparkbot's set of policy/audit/scheduler
modules. The **Spine** is the canonical task ledger that everything in
the system writes against. This page explains how they wire together,
which loops run in the background, what each loop reads and writes, and
how to observe the whole pipeline.

If you've ever wondered "where does a Telegram message become a
trackable task," this is the page.

## The pieces

| Module                                            | Role                                                                                       |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `guardian/auth.py`                                | Operator identity, break-glass mode, session gating                                        |
| `guardian/policy.py`                              | Tool-use decision engine (`decide_tool_use`)                                               |
| `guardian/executive.py`                           | Wraps tool execution in a journaled `exec_with_guard`                                      |
| `guardian/verifier.py`                            | Confidence verification on high-risk tool runs                                             |
| `guardian/token_guardian.py`                      | LLM model routing (live or shadow)                                                         |
| `guardian/task_guardian.py`                       | Cron-style scheduler for guardian-allowed tools                                            |
| `guardian/memory.py` + `memory_os/`               | Hybrid FTS + embedding memory ledger                                                       |
| `guardian/vault.py`                               | Encrypted secret store                                                                     |
| `guardian/improvement.py`                         | Outcome learning, route adaptation                                                         |
| `guardian/meeting_recorder.py`                    | Meeting → notes / action items                                                             |
| `guardian/pending_approvals.py`                   | Confirmation-gated action storage                                                          |
| `guardian/tool_guardrails.py`                     | Output validation for risky tools                                                          |
| `guardian/spine.py`                               | Canonical task / project / event ledger (SQLite)                                           |
| `guardian/project_executive.py`                   | Promotes Spine candidates to active tasks                                                  |
| `guardian/task_master_adapter.py`                 | External task-tracker adapter surface                                                      |
| `guardian/meeting_heartbeat.py`                   | Background meeting tick driver                                                             |

The Spine is one SQLite database (`%APPDATA%\Sparkbot\guardian\spine.sqlite`)
with these tables:

```
guardian_spine_tasks         (canonical task ledger)
guardian_spine_events        (immutable event chain)
guardian_spine_handoffs      (cross-room ownership transfers)
guardian_spine_links         (duplicate/related/dependency edges)
guardian_spine_projects      (multi-task buckets)
guardian_spine_project_events
guardian_spine_approvals     (mirror of pending approvals)
```

## Data flow

```
┌────────────┐                                     ┌────────────────────┐
│ Chat user  │── message ─────────────────────────►│  rooms.py / llm.py │
└────────────┘                                     └─────────┬──────────┘
                                                             │
                                                             ▼
                                                   ┌──────────────────┐
                                                   │ token_guardian   │ ◄─── shadow/live
                                                   │ .route_model()   │      routing
                                                   └─────────┬────────┘
                                                             ▼
                                                   ┌──────────────────┐
                                                   │ litellm call     │
                                                   │ (with tools[])   │
                                                   └─────────┬────────┘
                                                             ▼
                              tool_call requested            │
                                                             ▼
                                                   ┌──────────────────┐
                                                   │ policy.decide_   │
                                                   │ tool_use()       │
                                                   └─────┬─────┬──────┘
                                          allow    │     │     │ deny / confirm
                                                   │     │     │
                                                   ▼     │     ▼
                                        ┌─────────────┐  │  pending_approvals
                                        │ executive.  │  │  → user prompt
                                        │ exec_with_  │  │
                                        │ guard()     │  │
                                        └──────┬──────┘  │
                                               │         │
                                               ▼         │
                                        tools.execute_   │
                                        tool()           │
                                               │         │
              ┌────────────────────────────────┘         │
              │  (success or failure both audited)       │
              ▼                                          ▼
     ┌────────────────┐                          ┌──────────────────┐
     │ memory.        │                          │ executive jsonl  │
     │ remember_tool_ │                          │ (decisions)      │
     │ event()        │                          └──────────────────┘
     └───────┬────────┘
             │
             ▼
   ┌───────────────────────┐
   │ spine.ingest_*()      │ ◄── meeting recorder, executive,
   │ — promotes candidate  │     improvement loop, meeting
   │   tasks               │     heartbeat all call here
   └───────────┬───────────┘
               ▼
       ┌────────────────┐
       │ spine.sqlite   │ — canonical task ledger
       └────────────────┘
```

## Background loops

Three asyncio loops run for the lifetime of the backend process. Each
has the same defensive shape (`try ... except: log; await sleep`) so a
single bad iteration never kills the loop.

### 1. Task Guardian scheduler

Source: `guardian/task_guardian.py`. Reads scheduled jobs from the local
SQLite (`task_guardian.db`), fires their tools at the configured cadence,
records each run, and feeds successful runs back to
`spine.ingest_task_guardian_result(...)` so finished output appears in
the Spine ledger.

Allowed tools are restricted to `ALLOWED_TASK_TOOLS` (see
`task_guardian.py`). Failures increment the run's error counter; the
job stays scheduled.

### 2. Meeting heartbeat

Source: `guardian/meeting_heartbeat.py`. When a room has
`meeting_mode_enabled=true`, this loop fires the next agent turn at the
configured cadence. Every turn writes a Spine event so the meeting
artifact (notes + action items + decisions) ends up in
`guardian_spine_events` with a meeting source ref. The recorder then
calls `spine.ingest_*` to promote action items to candidate tasks.

### 3. Process watcher

Source: `services/process_watcher.py`. Monitors the local CPU/memory
footprint of the Sparkbot processes; throttles when a backup model is
overloading the host. Read state via `GET /api/v1/chat/system/watcher`.

## Guardian writes that land in the Spine

Most Guardian modules don't talk to the Spine directly — they call
through one of these well-known ingest functions in `guardian/spine.py`:

| Caller                                       | Spine ingest function           | What it produces                      |
| -------------------------------------------- | ------------------------------- | ------------------------------------- |
| `executive.exec_with_guard` after a tool run | `ingest_executive_decision`     | An event keyed to the tool decision   |
| `meeting_recorder.generate_meeting_notes`    | `ingest_subsystem_event`        | Candidate tasks for action items      |
| `improvement.record_outcome`                 | `ingest_subsystem_event`        | Self-improvement signals              |
| `memory.remember_tool_event`                 | `ingest_memory_signal`          | Background memory writes              |
| `task_guardian.run_scheduled`                | `ingest_task_guardian_result`   | Job result events                     |
| `auth.open_breakglass`                       | `emit_breakglass_event`         | Audit-grade authority change          |

Spine itself decides whether each ingest is auto-promoted to an active
task (confidence ≥ `AUTO_CREATE_THRESHOLD`, default 0.85), kept as a
candidate awaiting review (confidence ≥ `REVIEW_THRESHOLD`, default
0.60), or dropped. Tune via env vars
`SPARKBOT_GUARDIAN_SPINE_AUTO_CREATE_THRESHOLD` and
`SPARKBOT_GUARDIAN_SPINE_REVIEW_THRESHOLD`.

## Spine reads that the UI uses

Read endpoints are in `backend/app/api/routes/chat/spine.py`:

| Endpoint                                                       | Returns                                            |
| -------------------------------------------------------------- | -------------------------------------------------- |
| `GET /api/v1/chat/spine/overview`                              | Counts by status, last activity, recent events     |
| `GET /api/v1/chat/spine/tasks?status=open`                     | Filtered task list                                 |
| `GET /api/v1/chat/spine/tasks/{id}`                            | Task detail + linked events                        |
| `GET /api/v1/chat/spine/projects`                              | Multi-task project buckets                         |
| `GET /api/v1/chat/spine/handoffs`                              | Cross-room ownership transfers                     |
| `GET /api/v1/chat/spine/approvals`                             | Mirror of pending guardian approvals               |
| `GET /api/v1/chat/spine/events`                                | Raw event stream                                   |

Workstation and the chat UI both consume these to render the task list,
project board, and audit timeline.

## Observability

Each layer has a different vantage point — pick the right one for the
question you're asking:

| Question                             | Where to look                                                  |
| ------------------------------------ | -------------------------------------------------------------- |
| Why was a tool denied?               | `GET /api/v1/chat/audit?tool=policy_decision&limit=10`         |
| What ran in the last hour?           | `GET /api/v1/chat/audit?limit=50`                              |
| Which model is slow / flaking?       | `/perf` slash command, `GET /api/v1/chat/performance`          |
| What's in the Spine queue?           | `GET /api/v1/chat/spine/overview`                              |
| Why is the scheduler not firing?     | `GET /api/v1/chat/rooms/{id}/guardian/runs?limit=10`           |
| What did Spine ingest from a meeting?| `GET /api/v1/chat/spine/events?source_kind=meeting`            |
| Is the process watcher throttling?   | `GET /api/v1/chat/system/watcher`                              |

## Lifecycle of one tool call (worked example)

A user types `@coder fix the failing test in foo.py` in a room.

1. `rooms.stream_room_message` builds the SSE stream and calls
   `llm.stream_chat_with_tools`.
2. `_select_tool_definitions` trims the 133-tool catalogue to 128 and
   prioritises tools the message hints at.
3. `token_guardian.route_model` picks the candidate model for the
   "coding" classification. The candidate list is built in
   `_candidate_models`.
4. `_acompletion_with_fallback` calls litellm. The model returns a
   `tool_calls` finish reason requesting `shell_run`.
5. `policy.decide_tool_use("shell_run", ...)` returns either `allow`,
   `confirm` (yields a `confirm_required` event), or `deny`.
6. On allow, `executive.exec_with_guard` wraps the actual
   `tools.execute_tool` call. Latency is recorded via
   `record_tool_call`. Errors become `"TOOL ERROR: <reason>"`.
7. `mask_tool_result_for_external` redacts vault output. The
   `tool_done` SSE event goes to the user.
8. The audit log row is written. `memory.remember_tool_event` indexes
   the event into both FTS and the embedding store.
9. `executive.ingest_executive_decision` posts a Spine event. If the
   action looked like a discrete piece of work, the project executive
   promotes it to a candidate task in `guardian_spine_tasks`.
10. The chat round continues for up to `SPARKBOT_MAX_TOOL_ROUNDS=20`
    rounds, then streams the final assistant response.
11. `improvement.record_outcome` records whether the round produced
    output, what tools fired, and what error (if any) terminated it.
    This feeds back into route adaptation for similar future requests.

Every step writes to a different observability surface, so when
something goes wrong you can answer "where in the chain did it break"
without having to add print statements.
