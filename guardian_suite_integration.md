# Guardian Suite Integration Plan

## Goal

Turn `sparkbot-v2` into the unified operator and office-worker surface while integrating the Guardian repos as focused subsystems instead of a loose pile of side projects.

## Principle

- `sparkbot-v2` remains the product surface.
- Guardians are integrated as adapters, libraries, or sidecars.
- Policy comes before autonomy.
- Read-only access comes before mutation.
- Memory and routing observability come before arbitrary execution.

## Integration Order

1. `Memory_Guardian`
2. `tokenguardian` in shadow mode
3. `agent-shield` policy model
4. `Executive_Guardian` execution membrane
5. `Task_Guardian` background and recurring work
6. richer operator tooling

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

## Constraints

- No blanket shell execution
- No broad OS privilege grants
- No repo-wide blind merges from Guardian projects
- All risky actions must remain auditable and policy-gated
