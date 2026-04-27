# Guardian Suite Integration Plan

## Goal

Turn `sparkbot-v2` into the unified operator and office-worker surface while integrating the Guardian repos as focused subsystems instead of a loose pile of side projects.

## Principle

- `sparkbot-v2` remains the product surface.
- Guardians are integrated as adapters, libraries, or sidecars.
- Policy comes before autonomy.
- Read-only access comes before mutation.
- Memory and routing observability come before arbitrary execution.
- Meetings, scheduled jobs, approvals, and follow-up tasks should behave like one orchestrator, not separate assistant tricks.

## Orchestrator Baseline

Implemented in Sparkbot today:

- Workstation Round Table creates autonomous multi-agent rooms with a chair, specialist seats, owner interrupt, and structured terminal states.
- New meetings persist a participant manifest and can schedule an hourly `meeting_heartbeat` Guardian task to continue the room.
- Task-linked project meetings open or re-open a dedicated room with task context, stack bots, and a project notes artifact.
- Meeting Recorder extracts notes, decisions, and action items, then seeds Guardian/Spine follow-up tasks.
- Pending approvals are durable and visible through the dashboard, Telegram, GitHub, and bridge approval flows.
- `guardian_simulate_policy` gives operators a read-only what-if check before enabling a risky automation.

## Integration Order

1. `Memory_Guardian`
2. `tokenguardian` in shadow mode
3. `agent-shield` policy model
4. `Executive_Guardian` execution membrane
5. `Task_Guardian` background and recurring work
6. Guardian Improvement loop
7. richer operator tooling

## Phase 1: Memory Guardian

### Scope

- Vendor the minimal Memory Guardian modules inside `backend/app/services/guardian/memory_os/`
- Add a Sparkbot adapter in `backend/app/services/guardian/memory.py`
- Feed the adapter with:
  - user chat messages
  - assistant chat messages
  - redacted tool events
  - explicit `remember_fact` writes
- Inject packed memory context into the room streaming prompt path
- Preserve the existing `/memory` UI and `user_memories` DB table for curated facts

### Session mapping

- durable user memory: `user:{user_id}`
- room-context memory: `room:{room_id}:user:{user_id}`

### Current tradeoff

- `user_memories` remains the user-facing fact list
- Memory Guardian is now the richer retrieval layer behind the prompt
- This avoids breaking current UI contracts while adding long-horizon recall

### Follow-up work after Phase 1

1. Add consolidation jobs and summary surfacing
2. Expose a diagnostic memory status endpoint
3. Decide whether to migrate `/memory` entirely to Memory Guardian-backed data
4. Add room-shared memory policies distinct from user-private memory

## Phase 2: Token Guardian

- Run the routing pipeline in shadow mode first
- Record classification, confidence, selected model, and estimated cost beside Sparkbot audit data
- Only switch live routing after several sessions of observed behavior
- Current phase intent:
  - keep Sparkbot's actual live model selection unchanged
  - log `tokenguardian_shadow` decisions into the existing audit trail
  - use Sparkbot-specific routing config instead of the upstream OpenClaw model map

## Phase 3: Agent Shield

Implemented:
- Sparkbot now classifies tools into `read`, `write`, `execute`, and `admin`
- Every tool attempt produces a `policy_decision` audit entry
- `execution_allowed` is now enforced for server and SSH operations
- The existing confirmation modal is now driven by policy decisions instead of a hard-coded write-tool set

## Phase 4: Executive Guardian

Implemented:
- High-risk tool executions now pass through an Executive Guardian journal
- Current wrapped action families:
  - external writes
  - service control
  - server/SSH execution profiles
- Decision logs are written under `data/guardian/executive/decisions/`

## Phase 5: Task Guardian

Implemented as a Sparkbot-native sidecar:
- Schedules approved read-only tools only
- Stores jobs and run history in a dedicated SQLite store
- Posts job results back into the room as Sparkbot messages
- Supports:
  - recurring office routines
  - inbox and PR digests
  - calendar and search checks
  - read-only server and SSH diagnostics

Current Task Guardian tool surface:
- `guardian_schedule_task`
- `guardian_list_tasks`
- `guardian_list_runs`
- `guardian_run_task`
- `guardian_pause_task`

## Phase 6: Guardian Improvement Loop

Implemented:
- Outcome learning records successful and failed model/tool routes, then promotes reliable workflow patterns back into room memory.
- Sparkbot can call `guardian_propose_improvement` when it detects repeated misses, uncertain answers, missing capabilities, stale docs, or safer workflow ideas.
- Operators can inspect room proposals with `guardian_list_improvements`.
- Improvement proposals are durable, marked `approval_required`, and mirrored into Guardian Spine as awaiting approval.
- Sparkbot's global guardrails now require it to disclose uncertainty under 90% confidence and name the missing verification step.
- In Guardian policy mode, write-like `shell_run` commands require confirmation before local file, package, git, build, or destructive commands run.

Current Improvement tool surface:
- `guardian_propose_improvement`
- `guardian_list_improvements`

## Phase 7: Governance UX And Enterprise Controls

Implemented:
- Persistent approval storage and approval-waiting queues.
- Dashboard approval actions for stored confirmations.
- Telegram/GitHub/bridge approval and denial flows.
- Policy simulation via `guardian_simulate_policy`.
- First-class agent identity records: owner, purpose, scopes, allowed tools, expiration, risk tier, and kill switch.
- Run timeline endpoint for prompt-adjacent tool calls, policy decisions, model/agent attribution, summaries, and audit hashes.
- Approval-gated tool resume through durable pending approvals.
- Per-tool preflight validators and post-execution output validators.
- Workflow-builder templates for morning brief, PR monitor, deploy checklist, inbox triage, calendar prep, and incident response.
- Mobile/PWA companion shell for the public docs/download surface.
- Connector quality gates: setup tests, health status, read/write scopes, and audit metadata.
- Agent behavior evaluation harness for tool choice, approval requirements, guardrails, and agent routing.

Future expansion:
- Full serialized multi-hour agent graph resume beyond single pending tool calls.
- Dedicated visual UI for the run timeline endpoint.
- Editable workflow builder UI backed by the shipped template schema.

## Constraints

- No blanket shell execution
- No broad OS privilege grants
- No repo-wide blind merges from Guardian projects
- All risky actions must remain auditable and policy-gated
- Self-improvement may propose changes autonomously, but applying code, config, docs, scheduled jobs, or external writes still requires explicit operator approval
