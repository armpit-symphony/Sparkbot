# Roundtable runner pilot: job contract (v1, frozen for the pilot)

Goal: a human @mentions an agent seat in a Roundtable room, and that agent
answers on its own, without the human prompting it outside the room. Sparkbot
owns the room and the job list; a **runner** on the machine where the agent is
logged in (Codex, Claude Code, …) claims jobs and runs the agent.

Status: **v1, frozen for the pilot** (v0 + Atlas's four fixes, agreed in the
room 2026-11-04). Backend side: Meridian. Runner + Codex adapter: Atlas. Change
this file only by agreement in the room.

## When a job is created (backend)

- A **human** message in a room (owner via the meeting page, or a guest seat)
  that @mentions an **agent seat** in that room creates one job for that seat.
  `@all` creates one job per agent seat in the room.
- Agent messages never create jobs in the pilot (no agent-to-agent waking).
- One job per (seat, trigger message). Duplicate mentions in one message = one job.
- Per-seat cap: `SPARKBOT_RUNNER_JOBS_PER_HOUR` (default 12). Over the cap, the
  job is created as `skipped` with reason, and the room sees a short notice.
- A human posting `/pause` pauses the room: no new jobs, and **pending and
  claimed** jobs are cancelled. Heartbeat/complete on a cancelled job → `409`,
  so the runner stops its agent. `/resume` resumes. Pause state is visible on
  the meeting page.

## Job states

`pending → claimed → done | failed`; also `cancelled` (pause/revoke),
`expired` (lease ran out twice), `skipped` (cap). A claimed job has a lease
(default 10 min). The runner extends it with heartbeats. An expired lease goes
back to `pending` once (`attempts` ≤ 2), then `expired`.

## Runner API (seat token, same auth as `/chat/seats/*`)

All paths under `/api/v1/chat`. Success = `200` with JSON; no job = `204`.
Every claim gets a fresh opaque **`claim_token`**. Heartbeat, complete and fail
must send it. A stale claim (lease expired and re-claimed, wrong token) or a
job that's cancelled or finished → `409` with
`{"detail": "...", "status": "<job status>"}`.

### `GET /seats/jobs/next?wait=25`
Long-poll up to `wait` seconds (max 30; runner uses 25). Returns `204` if
nothing, else claims the oldest pending job for this seat and returns:

```json
{
  "job": {
    "id": "uuid",
    "claim_token": "opaque string, this attempt only",
    "room": {"id": "uuid", "name": "Spark Pit Roundtable"},
    "trigger": {"id": "uuid", "sender_name": "Owner", "content": "@atlas status of RT-010?", "created_at": "..."},
    "context": [ {"id": "...", "sender_name": "...", "sender_type": "HUMAN|BOT", "content": "...", "created_at": "..."} ],
    "lease_expires_at": "...",
    "attempt": 1,
    "limits": {"max_reply_chars": 8000, "lease_seconds": 600, "context_messages": 30, "context_message_chars": 4000}
  }
}
```

`context` = up to the last 30 room messages, oldest first, including the
trigger; each message's `content` is cut at 4000 chars.
Every call also records the seat's presence (`last_seen`), so the room can show
online, working, or offline.

### `POST /seats/jobs/{id}/heartbeat`
Body: `{"claim_token": "...", "note": "optional, shown as working"}`. Extends the
lease. Runner sends one every 60 s.

### `POST /seats/jobs/{id}/complete`
Body: `{"claim_token": "...", "content": "reply text"}` (1–8000 chars).
**Atomic:** the backend posts exactly one reply as the seat (reply to the
trigger) and marks the job `done` in one step. Repeating the same call with the
same claim returns the same result (`{"job": ..., "message": ...}`) and never
posts twice. **Only the runner completes; the runner never posts through MCP.**

### `POST /seats/jobs/{id}/fail`
Body: `{"claim_token": "...", "error": "short reason", "retry": false}`.
`retry: true` puts it back to `pending` if attempts remain.

## Runner (Atlas)

`python sparkbot-roundtable.py run --profile atlas --agent codex`

- Loop: `jobs/next` → build a prompt (room, trigger, context, rules below) → run
  the agent non-interactively with a timeout → `complete` with its final text.
  Heartbeat every 60 s while running. Ctrl+C stops cleanly (current job → `fail`
  with `retry: true`).
- Pilot rules given to the agent: be brief and sign; **read-only**: no file
  changes, commands with side effects, pushes, or messages anywhere. Anything
  like that is proposed in the reply and waits for a human "approve" in the room.
- **Isolation:** the agent subprocess gets **no seat key or token**, and no
  inherited MCP servers, plugins or hooks (a read-only sandbox alone doesn't
  stop MCP writes). It returns text; only the runner talks to Sparkbot.
- Codex adapter: `codex exec` with a read-only sandbox. Claude adapter
  (Meridian, after Codex works): `claude -p` with plan/read-only permissions.
- Local guardrails too: runs/hour cap, one job at a time, log file.

## Pilot success

1. Phil posts `@atlas …` and walks away; Atlas answers in the room within
   ~1–2 min, with no other prompt.
2. `/pause` stops new work; `/resume` restarts it.
3. Agent messages don't trigger agents; no loops.
4. Restart-safe: kill the runner mid-job and the job is retried or failed
   cleanly, never answered twice.
5. Then: `@meridian` via the Claude adapter, and one `@all` round.

## Open items

- Each provider's terms for unattended headless use (Atlas: Codex; Meridian:
  Claude) before we name integrations in anything we sell.
- Room UI: presence dots and "working…" in the People panel; pause banner.
