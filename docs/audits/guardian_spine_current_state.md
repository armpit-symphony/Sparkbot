# Guardian/Spine Current State — Preservation Record

**Date:** 2026-05-01
**Purpose:** Establish Sparkbot as the source of truth for all Guardian/Spine implementation
**Status:** LOCKED — Do not extract until security gates pass

---

## Source of Truth Declaration

**Sparkbot** (`/home/sparky/Sparkbot/`) is the canonical, working implementation of the Guardian/Spine system.

**LIMA-Guardian-Suite** (`github.com/armpit-symphony/LIMA-Guardian-Suite`) contains:
- `app/services/guardian/` — direct copy of Sparkbot modules (still has `app.models` imports, **NOT standalone**)
- `guardian/` — simplified standalone with 5 modules (**INCOMPLETE** — weaker vault, no Spine, no policy engine)

**Extraction is explicitly blocked** until:
1. This preservation record exists (this file)
2. Security fix plan exists (`guardian_spine_security_fix_plan.md`)
3. All HIGH-severity security fixes are implemented and tested
4. All MEDIUM-severity issues have tests or documented TODOs

---

## 22 Guardian/Spine Modules

| # | Module | Path (relative to `backend/app/services/guardian/`) | Lines | Role | Generic? |
|---|--------|------------------------------------------------------|-------|------|----------|
| 1 | Suite | `suite.py` | ~109 | Unified entrypoint, singleton factory | Yes |
| 2 | Spine | `spine.py` | ~3870 | Canonical task/project/event state catalog | No — ChatTask sync |
| 3 | Task Master Adapter | `task_master_adapter.py` | ~263 | ChatTask ↔ Spine execution bridge | No |
| 4 | Project Executive | `project_executive.py` | ~300 | Project lifecycle (create/archive/reopen) | No |
| 5 | Vault | `vault.py` | ~324 | Fernet-AES encrypted secret store | Yes |
| 6 | Policy | `policy.py` | ~630 | Tool classification + decide_tool_use() | Mixed — registry is Sparkbot-specific |
| 7 | Auth | `auth.py` | ~285 | Break-glass PIN, privileged sessions, lockout | Yes |
| 8 | Pending Approvals | `pending_approvals.py` | ~233 | TTL-gated approval confirmation queue | Yes |
| 9 | Task Guardian | `task_guardian.py` | ~920 | Scheduled job execution with retry + verification | No — tool knowledge |
| 10 | Token Guardian | `token_guardian.py` | ~410 | Shadow/live model routing + cost estimation | Yes |
| 11 | Memory | `memory.py` | ~1600 | Hybrid FTS+embed retrieval, fact extraction, PII redaction | No — Sparkbot event types |
| 12 | Memory Hygiene | `memory_hygiene.py` | ~267 | Lifecycle state machine (active → stale → archived → deleted) | No |
| 13 | Memory Taxonomy | `memory_taxonomy.py` | ~150 | Regex-based memory type classification | No |
| 14 | Verifier | `verifier.py` | ~290 | Output verification + confidence scoring | No — tool-specific patterns |
| 15 | Tool Guardrails | `tool_guardrails.py` | ~94 | Deterministic pre/post-execution validation | No — tool-specific rules |
| 16 | Executive | `executive.py` | ~176 | High-risk action journaling (JSONL) | No — action type classification |
| 17 | Governance | `governance.py` | ~182 | Connector health + evaluation cases | No — Sparkbot integrations |
| 18 | Improvement | `improvement.py` | ~400 | Outcome scoring + workflow adaptation | Yes |
| 19 | Meeting Recorder | `meeting_recorder.py` | ~300 | LLM-powered meeting notes | No — ChatMeetingArtifact |
| 20 | Meeting Heartbeat | `meeting_heartbeat.py` | ~500 | Multi-agent meeting facilitation | No — ChatRoom |
| 21 | Retrievers | `retrievers.py` | ~100 | FTS/embed/hybrid retrieval factory | Yes |
| 22 | Retrieval Eval | `retrieval_eval.py` | ~150 | BM25 vs hybrid precision diagnostics | Yes |

**Vendored submodules:**
- `memory_os/` — ledger, FTS index, embedding index (stub), consolidation, retrieval, schemas
- `tokenguardian/` — classifier, monitor, optimizer, pipeline, config YAML files

**Total Guardian codebase:** ~420 KB across 22 modules + vendored submodules

---

## API Routes (50+ endpoints)

### Guardian Routes (`backend/app/api/routes/chat/guardian.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/guardian/breakglass/status` | Operator | Check privileged session |
| POST | `/guardian/pin` | Operator | Set/change PIN |
| POST | `/guardian/breakglass` | Operator | Open privileged session |
| DELETE | `/guardian/breakglass` | Operator | Close privileged session |
| GET | `/guardian/vault` | Operator | List vault aliases |
| POST | `/guardian/vault` | Operator + Privileged | Add encrypted secret |
| DELETE | `/guardian/vault/{alias}` | Operator + Privileged | Delete secret |
| GET | `/rooms/{room_id}/guardian/tasks` | Room member | List scheduled tasks |
| GET | `/rooms/{room_id}/guardian/runs` | Room member | List task runs |
| POST | `/rooms/{room_id}/guardian/tasks` | Room owner/mod | Create scheduled task |
| PATCH | `/rooms/{room_id}/guardian/tasks/{task_id}` | Room owner/mod | Update task |
| POST | `/rooms/{room_id}/guardian/tasks/{task_id}/run` | Room owner/mod | Manual run |
| POST | `/guardian/tasks/write-mode` | Operator | Toggle write mode |
| GET | `/guardian/tasks/write-mode` | Operator | Get write mode status |
| GET | `/guardian/metrics` | Operator | Memory metrics |
| GET | `/guardian/status` | Operator | Subsystem status |

### Spine Routes (`backend/app/api/routes/chat/spine.py`)

**Room-level reads (12):** tasks, events, handoffs, overview, projects, project tasks, orphaned, lineage, approvals, project handoffs, project events, task-master overview

**Operator reads (16):** producers, recent events, queues (open, blocked, approval-waiting, stale, orphaned, missing-source, missing-project, resurfaced, executive-directives), projects, project workload, task-master overview, task detail

**Operator signals (13):** high-priority-blocked, high-priority-approval, stale-unowned, unassigned-executive, resurfaced-no-followup, missing-durable-linkage, fragmentation, projects-without-owner, projects-stale-tasks, projects-candidate-tasks, projects-blocked-approval, projects-unassigned-directives, projects-unclear-status

**Operator project writes (9):** create, update, set status, set owner, archive, cancel, reopen, attach task, detach task

### Dashboard Routes (`backend/app/api/routes/chat/dashboard.py`)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/dashboard/summary` | Auth user | Dashboard summary |
| GET | `/dashboard/runs/timeline` | Auth user | Runs timeline |
| GET | `/dashboard/connectors/health` | Auth user | Connector health |
| GET | `/dashboard/workflows/templates` | Auth user | Workflow templates |
| GET | `/dashboard/evals/agent-behavior` | Auth user | Agent behavior eval |
| POST | `/dashboard/approvals/{confirm_id}/approve` | Room member (non-viewer) | Approve action |
| POST | `/dashboard/approvals/{confirm_id}/deny` | Room member (non-viewer) | Deny action |

---

## SQLite Tables (10 tables across 3 databases)

### Guardian Spine DB (`data/guardian/spine.db`)
1. `guardian_spine_tasks` — canonical task records + approval state
2. `guardian_spine_events` — task/project lifecycle events
3. `guardian_spine_links` — task relationships (duplicate, related, parent_child, mirror, dependency)
4. `guardian_spine_assignments` — owner history
5. `guardian_spine_approvals` — approval request lifecycle
6. `guardian_spine_handoffs` — task handoff summaries
7. `guardian_spine_projects` — project catalog
8. `guardian_spine_project_events` — per-project event log

### Guardian Vault DB (`data/guardian/vault.db`)
9. `vault_entries` — encrypted secrets (Fernet-AES-128-CBC)
10. `vault_audit` — vault access audit trail

### Pending Approvals DB (`data/guardian/pending_approvals.db`)
11. `pending_approvals` — TTL-gated action confirmation queue (600s default)

### Task Guardian (shared app DB or separate SQLite)
12. `guardian_tasks` — scheduled task definitions
13. `guardian_task_runs` — execution history + verification results

### Main App DB (SQLAlchemy/SQLModel — PostgreSQL or SQLite)
- `chat_tasks` — mirrored by Spine
- `user_memories` — managed by Memory Guardian lifecycle
- `audit_logs` — Guardian tool audit trail
- `chat_meeting_artifacts` — Meeting Recorder output

---

## Background Jobs (7 asyncio tasks started in `main.py`)

| Job | Module | Schedule | Guardian? |
|-----|--------|----------|-----------|
| `task_guardian_scheduler()` | task_guardian.py | Poll every 60s | Yes |
| `memory_guardian_nightly_scheduler()` | task_guardian.py | Nightly 03:10 UTC | Yes |
| `reminder_scheduler()` | reminders.py | Poll every 60s | Tangential |
| `telegram_polling_loop()` | telegram_bridge.py | Continuous | No |
| `discord_bot_task()` | discord_bridge.py | Event loop | No |
| `terminal_manager.start()` | terminal_service.py | Idle cleanup | No |
| `process_watcher_loop()` | process_watcher.py | Poll every 30s | No |

---

## Environment Variables (names only — 40+ Guardian-related)

### Core
`SPARKBOT_GUARDIAN_DATA_DIR`, `SPARKBOT_GUARDIAN_POLICY_ENABLED`, `SPARKBOT_VAULT_KEY`, `SPARKBOT_OPERATOR_PIN_HASH`, `SPARKBOT_OPERATOR_USERNAMES`, `SPARKBOT_BREAKGLASS_TTL_SECONDS`, `SPARKBOT_PIN_MAX_ATTEMPTS`, `SPARKBOT_PIN_LOCKOUT_WINDOW_SECONDS`, `SPARKBOT_GLOBAL_COMPUTER_CONTROL`, `SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT`

### Spine
`SPARKBOT_GUARDIAN_SPINE_AUTO_CREATE_THRESHOLD`, `SPARKBOT_GUARDIAN_SPINE_REVIEW_THRESHOLD`

### Task Guardian
`SPARKBOT_TASK_GUARDIAN_ENABLED`, `SPARKBOT_TASK_GUARDIAN_POLL_SECONDS`, `SPARKBOT_TASK_GUARDIAN_MAX_OUTPUT`, `SPARKBOT_TASK_GUARDIAN_MAX_RETRIES`, `SPARKBOT_TASK_GUARDIAN_RETRY_BASE_SECONDS`, `SPARKBOT_TASK_GUARDIAN_RETRY_MAX_SECONDS`, `SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED`, `SPARKBOT_TASK_GUARDIAN_MEMORY_NIGHTLY_ENABLED`, `SPARKBOT_TASK_GUARDIAN_MEMORY_NIGHTLY_UTC`

### Token Guardian
`SPARKBOT_TOKEN_GUARDIAN_MODE`, `SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED`

### Memory Guardian
`SPARKBOT_MEMORY_GUARDIAN_ENABLED`, `SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS`, `SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT`, `SPARKBOT_MEMORY_GUARDIAN_DATA_DIR`, `SPARKBOT_MEMORY_GUARDIAN_RETRIEVER`, `SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS`, `SPARKBOT_MEMORY_LEDGER_COMPRESSION`, `SPARKBOT_MEMORY_SNAPSHOT_REBUILD_EVERY_N`, `SPARKBOT_MEMORY_SNAPSHOT_REBUILD_MIN_SECONDS`

### Memory Hygiene
`SPARKBOT_MEMORY_STALE_*_DAYS`, `SPARKBOT_MEMORY_ARCHIVE_*_DAYS`, `SPARKBOT_MEMORY_PROPOSE_DELETE_*_DAYS`

### Executive & Improvement
`SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED`, `SPARKBOT_IMPROVEMENT_LOOP_ENABLED`, `SPARKBOT_IMPROVEMENT_DATA_DIR`

---

## Test Coverage (13 test files, ~3882 lines)

| Test File | Lines | Coverage |
|-----------|-------|----------|
| `test_guardian_suite.py` | 36 | Inventory + module exposure |
| `test_guardian_spine.py` | 862 | Task lifecycle, approvals, lineage, signals, projects |
| `test_guardian_policy.py` | 107 | Personal/office mode, shell classification |
| `test_guardian_memory.py` | 388 | PII redaction, hygiene, fact scoring, retrieval |
| `test_guardian_vault.py` | 18 | Data dir resolution |
| `test_guardian_verifier.py` | 81 | Read/write verification, confidence |
| `test_guardian_governance.py` | 40 | Agent identity, connector health |
| `test_guardian_improvement.py` | 110 | Outcome recording, pattern promotion |
| `test_task_guardian.py` | 247 | Scheduling, allowlists, retry, escalation |
| `test_token_guardian_shadow.py` | 215 | Shadow/live routing, bias |
| `test_token_guardian_vault_configured.py` | 21 | Vault-as-provider bridging |
| `test_project_executive.py` | 787 | Project CRUD, signals, lineage |
| `test_guardian_breakglass.py` | 570 | PIN auth, vault ops, Telegram flow |

---

## LIMA-Guardian-Suite Gap Summary

**Missing entirely from LIMA (11 modules):**
Spine, Task Master Adapter, Project Executive, Memory Hygiene, Memory Taxonomy, Tool Guardrails, Governance, Improvement Loop, Meeting Heartbeat, Retrievers, Retrieval Eval

**Missing from LIMA (all infrastructure):**
All API routes, frontend dashboard, Alembic migrations, all Spine tests

**Incomplete in LIMA standalone `guardian/`:**
Vault (base64 placeholder, not Fernet), Memory (no FTS/embed), Task (no retry/verification), Executive (basic)

---

*This document is the Phase 0 preservation record. No extraction may proceed until the security fix plan (Phase 1-2) and immediate fixes (Phase 3) are complete.*
