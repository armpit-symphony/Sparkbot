# Sparkbot Guardian/Spine Extraction Audit

**Date:** 2026-05-01
**Auditor:** Claude Code (read-only audit)
**Scope:** All Guardian Suite, Spine, Vault, Approval, Scheduler, Memory, and related modules in Sparkbot vs. LIMA-Guardian-Suite
**Status:** Phase 0 — Inventory Only (no code changes)

---

## 1. Executive Summary

### What Is Currently Running Inside Sparkbot

Sparkbot contains a **22-module Guardian ecosystem** spanning:

- **Guardian Suite** — unified entrypoint (`suite.py`) aggregating 10+ modules
- **Guardian Spine** — SQLite-backed canonical task/project/event state catalog (8 tables, 40+ functions, 3870+ lines)
- **Task Master Adapter** — execution layer bridging ChatTask ORM ↔ Spine state
- **Project Executive** — project lifecycle management (create/archive/reopen/attach/detach)
- **Vault** — Fernet-AES-128-CBC encrypted secret store with 4-tier access policy
- **Policy Engine** — 50+ tool classification rules, `decide_tool_use()` routing
- **Break-Glass Auth** — PBKDF2-HMAC-SHA256 PIN, privileged sessions, lockout
- **Pending Approvals** — TTL-gated action confirmation queue
- **Task Guardian** — scheduled job execution with retry, verification, bridge notifications
- **Token Guardian** — shadow/live model routing, cost estimation
- **Memory Guardian** — hybrid FTS+embedding retrieval, fact extraction, profile snapshots, PII redaction
- **Memory Hygiene** — lifecycle state machine (active → stale → archived → delete_proposed → soft_deleted)
- **Memory Taxonomy** — regex-based memory classification
- **Verifier** — output verification with confidence scoring
- **Tool Guardrails** — deterministic pre/post-execution validation
- **Executive Guardian** — high-risk action journaling (JSONL)
- **Governance** — connector health + evaluation cases
- **Improvement Loop** — outcome scoring + workflow adaptation proposals
- **Meeting Recorder** — LLM-powered meeting notes from transcripts
- **Meeting Heartbeat** — multi-agent meeting facilitation + seat management
- **Retrievers** — factory for FTS/embed/hybrid retrieval
- **Retrieval Eval** — BM25 vs hybrid precision diagnostics

These are served via **~50 Guardian/Spine API routes**, backed by **10 SQLite tables** (separate from the main app DB), with **7 background asyncio tasks** at startup, and a **full operator dashboard** in the React frontend.

### What Already Exists in LIMA-Guardian-Suite

The LIMA repo contains **two parallel implementations**:

1. **`app/services/guardian/`** — Production-grade copy of 10 Sparkbot guardian modules + vendored `memory_os/` and `tokenguardian/` engines. **NOT standalone** — still imports `app.crud`, `app.models`, `sqlmodel`.
2. **`guardian/`** — Simplified standalone library with 5 core guardians (Token, Memory, Executive, Task, Vault) + OpenClaw adapter. Self-contained, no Sparkbot deps, but weaker implementations (e.g., base64 vault instead of Fernet).

### What Overlaps

| Area | Sparkbot | LIMA `app/` | LIMA `guardian/` |
|------|----------|-------------|------------------|
| Suite entrypoint | Full (10 modules) | Full (10 modules) | Partial (5 modules) |
| Auth / Break-glass | Full | Full copy | Missing |
| Vault (Fernet) | Full | Full copy | Placeholder (base64) |
| Policy engine | Full (50+ tools) | Full copy | Missing |
| Executive Guardian | Full | Full copy | Basic |
| Task Guardian | Full | Full copy | Basic |
| Token Guardian | Full | Full copy | Basic |
| Memory Guardian | Full | Full copy | Basic (no FTS/embed) |
| Verifier | Full | Full copy | Missing |
| Pending Approvals | Full | Full copy | Missing |
| Meeting Recorder | Full | Full copy | Missing |

### What Is Missing from LIMA-Guardian-Suite

| Component | Status in LIMA |
|-----------|---------------|
| **Guardian Spine** (spine.py — 3870+ lines, 8 SQLite tables) | **Not present** |
| **Task Master Adapter** (task_master_adapter.py) | **Not present** |
| **Project Executive** (project_executive.py) | **Not present** |
| **Memory Hygiene** (memory_hygiene.py) | **Not present** |
| **Memory Taxonomy** (memory_taxonomy.py) | **Not present** |
| **Tool Guardrails** (tool_guardrails.py) | **Not present** |
| **Governance** (governance.py) | **Not present** |
| **Improvement Loop** (improvement.py) | **Not present** |
| **Meeting Heartbeat** (meeting_heartbeat.py) | **Not present** |
| **Retrievers factory** (retrievers.py) | **Not present** |
| **Retrieval Eval** (retrieval_eval.py) | **Not present** |
| **All API routes** (guardian.py, spine.py, dashboard.py, projects.py) | **Not present** |
| **Frontend dashboard** (spine.tsx, spine.ts) | **Not present** |
| **Alembic migrations** | **Not present** |
| **All Spine-related tests** | **Not present** |

### What Should Be Extracted First

1. **Vault + Auth + Pending Approvals** — most product-generic, fewest Sparkbot deps
2. **Policy Engine** — generic interface, tool registry is the only Sparkbot-specific part (configurable)
3. **Spine core** — large but self-contained; needs adapter boundary drawn around ChatTask sync

---

## 2. Runtime Inventory

### 2.1 Guardian Service Modules

#### `backend/app/services/guardian/suite.py`
- **Purpose:** Unified import surface for Guardian stack
- **Classes:** `GuardianComponent(name, module, description)`, `GuardianSuite(auth, executive, improvement, meeting_recorder, memory, pending_approvals, policy, task_guardian, token_guardian, tool_guardrails, vault, verifier)`
- **Functions:** `get_guardian_suite()` (singleton), `guardian_suite_inventory()` (metadata list)
- **Imports:** All 12 guardian submodules
- **Routes:** None (used by callers)
- **Background jobs:** None
- **DB:** None
- **Env vars:** None
- **Sparkbot-specific:** No — generic container

#### `backend/app/services/guardian/spine.py`
- **Purpose:** Canonical task/project/event state catalog — SQLite-backed work-state ledger
- **Size:** ~3870 lines, 137.5 KB (largest Guardian module)
- **Dataclasses:** `SpineTask`, `SpineEvent`, `SpineProject`, `SpineApproval`, `SpineHandoff`, `SpineLink`, `SpineAssignment`, `SpineProjectEvent`
- **Pydantic models:** `SpineSourceReference`, `SpineProjectInput`, `SpineTaskInput`, `SpineSubsystemEvent`, `SpineProducerRegistration`
- **Functions (40+):** `ingest_subsystem_event()`, `ingest_chat_message()`, `ingest_meeting_decision()`, `ingest_executive_decision()`, `sync_chat_task_created()`, `sync_chat_task_mirror()`, `emit_task_master_action()`, `emit_approval_event()`, `list_open_queue()`, `list_blocked_queue()`, `list_approval_waiting_queue()`, `list_stale_tasks()`, `list_executive_directives()`, `list_recently_resurfaced_tasks()`, `list_assignment_ready_tasks()`, `list_orphan_tasks()`, `get_task_master_overview()`, `get_project_workload_summary()`, `get_task_lineage()`, `get_spine_project()`, `list_spine_projects()`, `get_spine_overview()`, `list_recent_cross_room_events()`, `list_spine_events()`, `list_project_events()`, `register_spine_producer()`, `list_registered_spine_producers()`
- **DB tables (8):** `guardian_spine_tasks`, `guardian_spine_events`, `guardian_spine_links`, `guardian_spine_assignments`, `guardian_spine_approvals`, `guardian_spine_handoffs`, `guardian_spine_projects`, `guardian_spine_project_events`
- **DB location:** `data/guardian/spine.db` (SQLite, non-ORM)
- **Env vars:** `SPARKBOT_GUARDIAN_SPINE_AUTO_CREATE_THRESHOLD`, `SPARKBOT_GUARDIAN_SPINE_REVIEW_THRESHOLD`, `SPARKBOT_GUARDIAN_DATA_DIR`
- **Routes:** 30+ endpoints via `spine.py` router
- **Background jobs:** None (event-driven)
- **Sparkbot-specific:** Yes — ChatTask/ChatRoom domain knowledge embedded; sync_chat_task_mirror writes legacy chat_tasks table

#### `backend/app/services/guardian/task_master_adapter.py`
- **Purpose:** Execution mediator between chat/executor layer and canonical Spine state
- **Classes:** `TaskMasterQueueSnapshot` (frozen dataclass), `TaskMasterSpineAdapter`
- **Functions (14+):** `overview()`, `open()`, `blocked()`, `approval_waiting()`, `stale()`, `orphan()`, `resurfaced()`, `executive_directives()`, `register_created_task()`, `queue_task()`, `assign_task()`, `block_task()`, `complete_task()`, `reopen_task()`, `assign_existing_task()`, `mark_blocked()`, `archive_deleted_task()`, `change_status()`, `emit_status_change()`
- **Singleton:** `task_master_spine` instance exported
- **DB:** Uses Spine tables + SQLModel `ChatTask`
- **Env vars:** None
- **Sparkbot-specific:** Yes — ChatTask integration

#### `backend/app/services/guardian/project_executive.py`
- **Purpose:** Canonical boundary for explicit project mutations
- **Classes:** `ProjectHasOpenTasksError`, `ProjectNotFoundError`, `ProjectExecutiveAdapter`
- **Functions (8+):** `create_project()`, `archive_project(force=False)`, `reopen_project()`, `update_project()`, `set_owner()`, `update_status()`, `attach_task()`, `detach_task()`
- **Singleton:** `project_executive` instance exported
- **DB:** Uses Spine tables
- **Env vars:** None
- **Sparkbot-specific:** Yes — project/task lifecycle

#### `backend/app/services/guardian/vault.py`
- **Purpose:** Fernet-AES-128-CBC encrypted secret store with access policy tiers
- **Functions:** `init_vault_db()`, `vault_add()`, `vault_get_metadata()`, `vault_list()`, `vault_use()`, `vault_reveal()`, `vault_update()`, `vault_delete()`
- **DB tables (2):** `vault_entries`, `vault_audit` at `data/guardian/vault.db`
- **Encryption:** `cryptography.fernet.Fernet`
- **Env vars:** `SPARKBOT_VAULT_KEY`, `SPARKBOT_GUARDIAN_DATA_DIR`
- **Routes:** GET/POST/DELETE `/guardian/vault` (3 endpoints)
- **Sparkbot-specific:** No — generic secret store

#### `backend/app/services/guardian/policy.py`
- **Purpose:** Centralized tool policy registry and `decide_tool_use()` routing engine
- **Size:** 22.3 KB
- **Types:** `PolicyAction = Literal["allow", "confirm", "deny", "privileged", "privileged_reveal"]`, `PolicyScope`, `ToolPolicy`, `PolicyDecision`
- **Functions:** `_policy_enabled()`, `global_bypass_status()`, `global_bypass_enabled()`, `get_tool_policy()`, `decide_tool_use()`, `simulate_tool_policy()`
- **Registry:** 50+ tools classified (web_search, gmail_send, shell_run, terminal, ssh_exec, etc.)
- **Env vars:** `SPARKBOT_GUARDIAN_POLICY_ENABLED`, `SPARKBOT_GLOBAL_COMPUTER_CONTROL`, `SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT`
- **Sparkbot-specific:** Mixed — core engine is generic; tool registry is Sparkbot-specific (configurable)

#### `backend/app/services/guardian/auth.py`
- **Purpose:** Break-glass operator auth: PIN, privileged sessions, lockout
- **Classes:** `PrivilegedSession(session_id, user_id, operator, started_at, expires_at, scopes)`
- **Functions:** `set_operator_pin()`, `verify_pin()`, `open_privileged_session()`, `close_privileged_session()`, `get_active_session()`, `is_operator_identity()`, `operator_usernames()`, `is_locked_out()`, `pin_configured()`
- **Storage:** PIN hash at `data/guardian/operator_pin.hash`; sessions in-memory (die on restart — intentional)
- **Env vars:** `SPARKBOT_OPERATOR_PIN_HASH`, `SPARKBOT_OPERATOR_USERNAMES`, `SPARKBOT_BREAKGLASS_TTL_SECONDS`, `SPARKBOT_PIN_MAX_ATTEMPTS`, `SPARKBOT_PIN_LOCKOUT_WINDOW_SECONDS`
- **Routes:** GET/POST/DELETE `/guardian/breakglass` + POST `/guardian/pin`
- **Sparkbot-specific:** No — generic auth layer

#### `backend/app/services/guardian/pending_approvals.py`
- **Purpose:** Transient storage for tool invocations awaiting operator confirmation
- **Classes:** `PendingApproval(confirm_id, tool_name, tool_args_json, user_id, room_id, created_at, expires_at)`
- **Functions:** `store_pending_approval()`, `consume_pending_approval()`, `get_pending_approval()`, `discard_pending_approval()`, `list_pending_approvals()`
- **DB table:** `pending_approvals` at `data/guardian/pending_approvals.db`
- **TTL:** 600s default
- **Spine integration:** Emits `approval.required`, `approval.granted`, `approval.discarded` events
- **Env vars:** `SPARKBOT_GUARDIAN_DATA_DIR`
- **Sparkbot-specific:** No — generic approval store

#### `backend/app/services/guardian/task_guardian.py`
- **Purpose:** Scheduled task execution with retry logic, verification, and bridge notifications
- **Size:** 32.5 KB
- **DB tables (2):** `guardian_tasks`, `guardian_task_runs`
- **Allowed tools (16+):** web_search, gmail_fetch_inbox, list_tasks, memory_recall, etc.
- **Write tools (3):** gmail_send, slack_send_message, calendar_create_event (opt-in)
- **Functions:** `schedule_task()`, `run_task_once()`, `list_tasks()`, `list_runs()`, `get_task()`, `set_task_enabled()`, `memory_nightly()`, `set_write_enabled()`, `task_guardian_scheduler()`, `memory_guardian_nightly_scheduler()`
- **Background jobs:** `task_guardian_scheduler()` (polling loop), `memory_guardian_nightly_scheduler()` (nightly)
- **Env vars:** `SPARKBOT_TASK_GUARDIAN_ENABLED`, `SPARKBOT_TASK_GUARDIAN_POLL_SECONDS`, `SPARKBOT_TASK_GUARDIAN_MAX_OUTPUT`, `SPARKBOT_TASK_GUARDIAN_MAX_RETRIES`, `SPARKBOT_TASK_GUARDIAN_RETRY_BASE_SECONDS`, `SPARKBOT_TASK_GUARDIAN_RETRY_MAX_SECONDS`, `SPARKBOT_TASK_GUARDIAN_MEMORY_NIGHTLY_ENABLED`, `SPARKBOT_TASK_GUARDIAN_MEMORY_NIGHTLY_UTC`, `SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED`
- **Routes:** GET/POST/PATCH `/rooms/{room_id}/guardian/tasks`, `/guardian/tasks/write-mode`
- **Sparkbot-specific:** Yes — tool knowledge, bridge notifications

#### `backend/app/services/guardian/token_guardian.py`
- **Purpose:** Model routing and token usage telemetry
- **Size:** 14.5 KB
- **Submodule:** `tokenguardian/` — classifier, monitor, optimizer, pipeline
- **Functions:** `token_guardian_mode()`, `token_guardian_shadow_enabled()`, `token_guardian_live_enabled()`, `_build_route_payload()`
- **Env vars:** `SPARKBOT_TOKEN_GUARDIAN_MODE`, `SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED`
- **Sparkbot-specific:** No — generic model routing

#### `backend/app/services/guardian/memory.py`
- **Purpose:** Memory Guardian adapter — hybrid retrieval, fact extraction, profile snapshots, PII redaction
- **Size:** 56.2 KB
- **Submodule:** `memory_os/` — ledger, FTS index, embedding index (stub), consolidation, retrieval
- **Functions:** `memory_guardian_enabled()`, `remember_chat_message()`, `remember_tool_event()`, `remember_fact()`, `build_memory_context()`, `recall()`, `memory_metrics()`, `memory_retrieval_stats()`, `recall_from_history()`, `delete_fact_memory()`, `clear_user_memory_events()`
- **Env vars:** `SPARKBOT_MEMORY_GUARDIAN_ENABLED`, `SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS`, `SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT`, `SPARKBOT_MEMORY_GUARDIAN_DATA_DIR`, `SPARKBOT_MEMORY_GUARDIAN_RETRIEVER`, `SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS`, `SPARKBOT_MEMORY_LEDGER_COMPRESSION`, `SPARKBOT_MEMORY_SNAPSHOT_REBUILD_EVERY_N`, `SPARKBOT_MEMORY_SNAPSHOT_REBUILD_MIN_SECONDS`
- **Routes:** GET/DELETE `/chat/memory`
- **Sparkbot-specific:** Yes — Sparkbot event types, profile snapshot format

#### `backend/app/services/guardian/memory_hygiene.py`
- **Purpose:** Governed lifecycle cleanup of stale/archived/unsafe memories
- **Classes:** `HygieneChange`, `HygieneReport`
- **Functions:** `run_memory_hygiene()`, `run_weekly_memory_hygiene_job()`, `run_monthly_memory_cleanup_proposal_job()`
- **Lifecycle states:** active → stale → archived → delete_proposed → (operator approval) → soft_deleted
- **Protected types:** identity, preference, project_decision, relationship_note
- **Env vars:** `SPARKBOT_MEMORY_STALE_*_DAYS`, `SPARKBOT_MEMORY_ARCHIVE_*_DAYS`, `SPARKBOT_MEMORY_PROPOSE_DELETE_*_DAYS`
- **Sparkbot-specific:** Yes — memory type classification

#### `backend/app/services/guardian/memory_taxonomy.py`
- **Purpose:** Classify memory type via regex + heuristics
- **Functions:** `classify_memory_type()`, `is_secret_like()`, `should_index_memory_candidate()`
- **Sparkbot-specific:** Yes — domain-specific classification rules

#### `backend/app/services/guardian/verifier.py`
- **Purpose:** Tool output verification with confidence scoring
- **Classes:** `VerificationResult(tool_name, status, confidence, evidence, recommended_next_action)`
- **Functions:** `verify_task_run()`, `verify_interactive_tool_run()`, `should_verify_interactive_tool_run()`, `format_verifier_note()`
- **Sparkbot-specific:** Yes — tool-specific verification patterns

#### `backend/app/services/guardian/tool_guardrails.py`
- **Purpose:** Deterministic pre/post-execution input/output validation
- **Classes:** `ToolGuardrailResult(allowed, phase, tool_name, behavior, reason)`
- **Functions:** `validate_tool_input()`, `validate_tool_output()`
- **Sparkbot-specific:** Yes — tool-specific validation rules

#### `backend/app/services/guardian/executive.py`
- **Purpose:** High-risk action journaling and decision logging
- **Functions:** `exec_with_guard()`, `get_status()`
- **Storage:** JSONL at `data/guardian/executive/decisions/{YYYY-MM-DD}.jsonl`
- **Env vars:** `SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED`, `SPARKBOT_GUARDIAN_DATA_DIR`
- **Sparkbot-specific:** Yes — action type classification (write_external, service_control, etc.)

#### `backend/app/services/guardian/governance.py`
- **Purpose:** Connector health reporting and evaluation test cases
- **Functions:** `connector_health()`, `workflow_templates()`, `evaluation_cases()`, `evaluation_summary()`
- **Sparkbot-specific:** Yes — Sparkbot integration knowledge (Gmail, GitHub, Slack, etc.)

#### `backend/app/services/guardian/improvement.py`
- **Purpose:** Durable outcome scoring and workflow adaptation proposals
- **Functions:** `improvement_loop_enabled()`, `record_outcome()`, `learn_pattern()`, `propose_improvement()`, `get_proposal()`, `list_proposals()`
- **Storage:** JSON at `data/improvement_loop/outcomes.json`
- **Env vars:** `SPARKBOT_IMPROVEMENT_LOOP_ENABLED`, `SPARKBOT_IMPROVEMENT_DATA_DIR`
- **Sparkbot-specific:** No — generic pattern storage

#### `backend/app/services/guardian/meeting_recorder.py`
- **Purpose:** LLM-powered meeting notes from chat transcripts
- **Functions:** `generate_meeting_notes()`, `_build_transcript()`, `_extract_section()`
- **DB:** Reads `ChatMessage`, writes `ChatMeetingArtifact`
- **Sparkbot-specific:** Yes — ChatRoom/ChatMeetingArtifact integration

#### `backend/app/services/guardian/meeting_heartbeat.py`
- **Purpose:** Multi-agent meeting facilitation, participant seat management
- **Functions:** `run_meeting_heartbeat()`, `_parse_meeting_status()`, `_meeting_role_instruction()`
- **Sparkbot-specific:** Yes — ChatRoom, multi-agent orchestration

#### `backend/app/services/guardian/retrievers.py`
- **Purpose:** Factory for building FTS/embed/hybrid retrievers
- **Functions:** `build_retriever(mode)`
- **Sparkbot-specific:** No

#### `backend/app/services/guardian/retrieval_eval.py`
- **Purpose:** BM25 vs hybrid precision/latency diagnostics
- **Functions:** `evaluate_retrieval()`, `_bm25_precision()`, `_hybrid_precision()`, `_compare_latency()`
- **Sparkbot-specific:** No

### 2.2 API Routes

#### Guardian Routes — `backend/app/api/routes/chat/guardian.py`
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/guardian/breakglass/status` | Check active privileged session |
| POST | `/guardian/pin` | Set/change operator PIN |
| POST | `/guardian/breakglass` | Open privileged session (PIN auth) |
| DELETE | `/guardian/breakglass` | Close privileged session |
| GET | `/guardian/vault` | List vault aliases + metadata |
| POST | `/guardian/vault` | Add encrypted secret (requires break-glass) |
| DELETE | `/guardian/vault/{alias}` | Delete secret (requires break-glass) |
| GET | `/rooms/{room_id}/guardian/tasks` | List Task Guardian jobs for room |
| GET | `/rooms/{room_id}/guardian/runs` | List Task Guardian runs |
| POST | `/rooms/{room_id}/guardian/tasks` | Create Task Guardian job |
| PATCH | `/rooms/{room_id}/guardian/tasks/{task_id}` | Update Task Guardian job |
| POST | `/rooms/{room_id}/guardian/tasks/{task_id}/run` | Manually run Task Guardian job |
| POST | `/guardian/tasks/write-mode` | Toggle write mode |
| GET | `/guardian/tasks/write-mode` | Get write mode status |
| GET | `/guardian/metrics` | Memory Guardian metrics |
| GET | `/guardian/status` | Guardian subsystem status |

#### Spine Routes — `backend/app/api/routes/chat/spine.py`

**Room-level (12 endpoints):**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/rooms/{room_id}/spine/tasks` | List spine tasks in room |
| GET | `/rooms/{room_id}/spine/events` | List spine events |
| GET | `/rooms/{room_id}/spine/handoffs` | List task handoffs |
| GET | `/rooms/{room_id}/spine/overview` | Spine overview |
| GET | `/rooms/{room_id}/spine/projects` | List projects |
| GET | `/rooms/{room_id}/spine/projects/{project_id}/tasks` | Project tasks |
| GET | `/rooms/{room_id}/spine/tasks/orphaned` | Orphaned tasks |
| GET | `/rooms/{room_id}/spine/tasks/{task_id}/lineage` | Task lineage |
| GET | `/rooms/{room_id}/spine/tasks/{task_id}/approvals` | Task approvals |
| GET | `/rooms/{room_id}/spine/projects/{project_id}/handoffs` | Project handoffs |
| GET | `/rooms/{room_id}/spine/projects/{project_id}/events` | Project events |
| GET | `/rooms/{room_id}/spine/task-master/overview` | Room task master overview |

**Operator-level reads (16 endpoints):**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/spine/operator/producers` | List producers |
| GET | `/spine/operator/events/recent` | Recent events |
| GET | `/spine/operator/queues/open` | Open queue |
| GET | `/spine/operator/queues/blocked` | Blocked queue |
| GET | `/spine/operator/queues/approval-waiting` | Approval waiting |
| GET | `/spine/operator/queues/stale` | Stale queue |
| GET | `/spine/operator/queues/orphaned` | Orphaned queue |
| GET | `/spine/operator/queues/missing-source` | Missing source |
| GET | `/spine/operator/queues/missing-project` | Missing project |
| GET | `/spine/operator/queues/resurfaced` | Resurfaced queue |
| GET | `/spine/operator/queues/executive-directives` | Executive directives |
| GET | `/spine/operator/projects` | List projects |
| GET | `/spine/operator/projects/workload` | Project workload |
| GET | `/spine/operator/task-master/overview` | Operator task master overview |
| GET | `/spine/operator/tasks/{task_id}/detail` | Task detail |

**Operator signals (13 endpoints):**
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/spine/operator/signals/high-priority-blocked` | High priority blocked tasks |
| GET | `/spine/operator/signals/high-priority-approval` | High priority awaiting approval |
| GET | `/spine/operator/signals/stale-unowned` | Stale unowned tasks |
| GET | `/spine/operator/signals/unassigned-executive` | Unassigned executive directives |
| GET | `/spine/operator/signals/resurfaced-no-followup` | Resurfaced without followup |
| GET | `/spine/operator/signals/missing-durable-linkage` | Missing durable linkage |
| GET | `/spine/operator/signals/fragmentation` | Task fragmentation |
| GET | `/spine/operator/signals/projects-without-owner` | Projects without owner |
| GET | `/spine/operator/signals/projects-stale-tasks` | Projects with stale tasks |
| GET | `/spine/operator/signals/projects-candidate-tasks` | Projects with candidate tasks |
| GET | `/spine/operator/signals/projects-blocked-approval` | Projects blocked on approval |
| GET | `/spine/operator/signals/projects-unassigned-directives` | Projects with unassigned directives |
| GET | `/spine/operator/signals/projects-unclear-status` | Projects with unclear status |

**Operator project writes (9 endpoints):**
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/spine/operator/projects` | Create project |
| PATCH | `/spine/operator/projects/{project_id}` | Update project |
| POST | `/spine/operator/projects/{project_id}/status` | Set project status |
| POST | `/spine/operator/projects/{project_id}/owner` | Set project owner |
| POST | `/spine/operator/projects/{project_id}/archive` | Archive project |
| POST | `/spine/operator/projects/{project_id}/cancel` | Cancel project |
| POST | `/spine/operator/projects/{project_id}/reopen` | Reopen project |
| POST | `/spine/operator/projects/{project_id}/tasks/attach` | Attach task |
| DELETE | `/spine/operator/projects/{project_id}/tasks/{task_id}` | Detach task |

#### Dashboard Routes — `backend/app/api/routes/chat/dashboard.py`
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/dashboard/summary` | Dashboard summary |
| GET | `/dashboard/runs/timeline` | Runs timeline |
| GET | `/dashboard/connectors/health` | Connector health |
| GET | `/dashboard/workflows/templates` | Workflow templates |
| GET | `/dashboard/evals/agent-behavior` | Agent behavior evaluation |
| POST | `/dashboard/approvals/{confirm_id}/approve` | Approve action |
| POST | `/dashboard/approvals/{confirm_id}/deny` | Deny action |

#### Project Routes — `backend/app/api/routes/chat/projects.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/rooms/{room_id}/projects` | Create project in room |
| PATCH | `/rooms/{room_id}/projects/{project_id}` | Update project |
| DELETE | `/rooms/{room_id}/projects/{project_id}` | Delete project |
| POST | `/rooms/{room_id}/projects/{project_id}/tasks/{task_id}` | Attach task |
| DELETE | `/rooms/{room_id}/projects/{project_id}/tasks/{task_id}` | Detach task |

#### MCP Approval Routes — `backend/app/api/routes/chat/mcp.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/mcp/runs/{run_id}/request-approval` | Request approval |
| POST | `/mcp/runs/{run_id}/approve` | Approve MCP run |
| POST | `/mcp/runs/{run_id}/deny` | Deny MCP run |

### 2.3 Database Tables

#### Main App DB (SQLAlchemy/SQLModel — PostgreSQL or SQLite)
| Table | Model | Guardian-Related |
|-------|-------|------------------|
| `chat_tasks` | `ChatTask` | Yes — mirrored by Spine |
| `user_memories` | `UserMemory` | Yes — managed by Memory Guardian |
| `audit_logs` | `AuditLog` | Yes — Guardian tool audit trail |
| `chat_meeting_artifacts` | `ChatMeetingArtifact` | Yes — Meeting Recorder output |
| `reminders` | `Reminder` | Tangential — Task Guardian can trigger |
| `custom_agents` | `CustomAgent` | No |
| `chat_users` | `ChatUser` | No |
| `chat_rooms` | `ChatRoom` | No |
| `chat_messages` | `ChatMessage` | No |
| `chat_room_members` | `ChatRoomMember` | No |
| `chat_room_invites` | `ChatRoomInvite` | No |

#### Guardian Spine DB (`data/guardian/spine.db` — direct SQLite)
| Table | Purpose |
|-------|---------|
| `guardian_spine_tasks` | Canonical task records + approval state |
| `guardian_spine_events` | Task/project lifecycle events |
| `guardian_spine_links` | Task relationships |
| `guardian_spine_assignments` | Owner history |
| `guardian_spine_approvals` | Approval request lifecycle |
| `guardian_spine_handoffs` | Task handoff summaries |
| `guardian_spine_projects` | Project catalog |
| `guardian_spine_project_events` | Per-project event log |

#### Guardian Vault DB (`data/guardian/vault.db` — direct SQLite)
| Table | Purpose |
|-------|---------|
| `vault_entries` | Encrypted secret storage |
| `vault_audit` | Vault access audit trail |

#### Pending Approvals DB (`data/guardian/pending_approvals.db` — direct SQLite)
| Table | Purpose |
|-------|---------|
| `pending_approvals` | TTL-gated action confirmation queue |

#### Task Guardian tables (in shared app DB or separate SQLite)
| Table | Purpose |
|-------|---------|
| `guardian_tasks` | Scheduled task definitions |
| `guardian_task_runs` | Execution history + verification |

#### Memory Guardian data (filesystem)
| Path | Purpose |
|------|---------|
| `data/memory_guardian/ledger.jsonl` | Append-only event log |
| `data/memory_guardian/indexes/` | FTS5 SQLite index |
| `data/memory_guardian/snapshots/` | Profile snapshots |

### 2.4 Background Jobs (asyncio — started in `main.py`)

| Job | Source Module | Schedule | Guardian-Related |
|-----|--------------|----------|------------------|
| `task_guardian_scheduler()` | `task_guardian.py` | Polling (default 60s) | Yes — core |
| `memory_guardian_nightly_scheduler()` | `task_guardian.py` | Nightly (default 03:10 UTC) | Yes — core |
| `reminder_scheduler()` | `reminders.py` | Polling (60s) | Tangential |
| `telegram_polling_loop()` | `telegram_bridge.py` | Continuous polling | No |
| `discord_bot_task()` | `discord_bridge.py` | Event loop | No |
| `terminal_manager.start()` | `terminal_service.py` | Idle cleanup loop | No |
| `process_watcher_loop()` | `process_watcher.py` | Polling (30s) | No |

### 2.5 Frontend Components

#### `frontend/src/lib/spine.ts` — Spine/Guardian API Client
- 363 lines
- TypeScript interfaces: `SpineTask`, `SpineProject`, `SpineEvent`, `SpineProducer`, `SpineApproval`, `SpineHandoff`, `SpineTaskLineage`, `BreakglassStatus`, `VaultEntry`, `GuardianStatus`
- Functions: `fetchSpineTMOverview()`, `fetchSpineQueue()`, `fetchSpineRecentEvents()`, `fetchSpineProjects()`, `fetchSpineProjectWorkload()`, `fetchSpineProducers()`, `fetchSpineTaskDetail()`, `fetchBreakglassStatus()`, `activateBreakglass()`, `deactivateBreakglass()`, `fetchVaultList()`, `addVaultSecret()`, `deleteVaultSecret()`, `fetchGuardianStatus()`, `setTaskGuardianWriteMode()`, `createProject()`, `updateProject()`, `archiveProject()`, `attachTaskToProject()`, `detachTaskFromProject()`

#### `frontend/src/routes/_layout/spine.tsx` — Spine Ops Dashboard
- 1500+ lines
- Full operator UI: queue browser, task/project inspector, break-glass form, vault management, project CRUD, task lineage viewer
- Before-load guard redirects non-operators

### 2.6 Test Files

| Test File | Module Tested | Size |
|-----------|--------------|------|
| `tests/test_guardian_suite.py` | suite.py | — |
| `tests/test_guardian_spine.py` | spine.py | 35,990 bytes |
| `tests/test_guardian_policy.py` | policy.py | 4.3 KB |
| `tests/test_guardian_memory.py` | memory.py | 14.1 KB |
| `tests/test_guardian_vault.py` | vault.py | 728 bytes |
| `tests/test_guardian_verifier.py` | verifier.py | 2.5 KB |
| `tests/test_guardian_governance.py` | governance.py | 1.6 KB |
| `tests/test_guardian_improvement.py` | improvement.py | 3.6 KB |
| `tests/test_task_guardian.py` | task_guardian.py | 9.2 KB |
| `tests/test_token_guardian_shadow.py` | token_guardian.py | 7.5 KB |
| `tests/test_token_guardian_vault_configured.py` | vault + token | 781 bytes |
| `tests/test_project_executive.py` | project_executive.py | — |
| `tests/test_guardian_breakglass.py` | auth.py + routes | 23.3 KB |

---

## 3. LIMA-Guardian-Suite Comparison

### Component-Level Comparison

| Sparkbot Component | LIMA `app/services/guardian/` | LIMA `guardian/` (standalone) | Status |
|---|---|---|---|
| `suite.py` (entrypoint, 10 modules) | Exists (identical structure) | Exists (5 modules) | **Already exists** |
| `spine.py` (8 tables, 40+ functions) | Not present | Not present | **Missing from LIMA** |
| `task_master_adapter.py` | Not present | Not present | **Missing from LIMA** |
| `project_executive.py` | Not present | Not present | **Missing from LIMA** |
| `vault.py` (Fernet encryption) | Exists (identical) | Exists (base64 placeholder) | **Partial overlap** — standalone needs Fernet upgrade |
| `policy.py` (50+ tool registry) | Exists (identical) | Not present | **Partial overlap** — tool registry is Sparkbot-specific |
| `auth.py` (break-glass, PIN, sessions) | Exists (identical) | Not present | **Already exists** (in `app/` only) |
| `pending_approvals.py` | Exists (identical) | Not present | **Already exists** (in `app/` only) |
| `task_guardian.py` (scheduler, retry) | Exists (identical) | Exists (basic) | **Partial overlap** — standalone is simplified |
| `token_guardian.py` + `tokenguardian/` | Exists (identical) | Exists (basic) | **Partial overlap** — standalone is simplified |
| `memory.py` + `memory_os/` | Exists (identical) | Exists (basic, no FTS) | **Partial overlap** — standalone is simplified |
| `memory_hygiene.py` | Not present | Not present | **Missing from LIMA** |
| `memory_taxonomy.py` | Not present | Not present | **Missing from LIMA** |
| `verifier.py` | Exists (identical) | Not present | **Already exists** (in `app/` only) |
| `tool_guardrails.py` | Not present | Not present | **Missing from LIMA** |
| `executive.py` | Exists (identical) | Exists (basic) | **Partial overlap** |
| `governance.py` | Not present | Not present | **Sparkbot-specific, do not extract** |
| `improvement.py` | Not present | Not present | **Should become core LIMA module** |
| `meeting_recorder.py` | Exists (identical) | Not present | **Sparkbot-specific, do not extract** |
| `meeting_heartbeat.py` | Not present | Not present | **Sparkbot-specific, do not extract** |
| `retrievers.py` | Not present | Not present | **Should become core LIMA module** |
| `retrieval_eval.py` | Not present | Not present | **Should become core LIMA module** |

### Route-Level Comparison

| Sparkbot Route Group | LIMA Status |
|---|---|
| Guardian routes (`guardian.py` — 16 endpoints) | **Missing from LIMA** — no HTTP routes at all |
| Spine routes (`spine.py` — 50 endpoints) | **Missing from LIMA** |
| Dashboard routes (`dashboard.py` — 7 endpoints) | **Missing from LIMA** |
| Project routes (`projects.py` — 5 endpoints) | **Missing from LIMA** |

### Frontend Comparison

| Sparkbot Frontend | LIMA Status |
|---|---|
| `spine.ts` — API client library | **Missing from LIMA** |
| `spine.tsx` — Operator dashboard | **Missing from LIMA** |

### Test Coverage Comparison

| Sparkbot Tests | LIMA `tests/services/` | LIMA `tests/` (standalone) |
|---|---|---|
| `test_guardian_suite.py` | Exists | Exists (different) |
| `test_guardian_spine.py` (36 KB) | Not present | Not present |
| `test_guardian_policy.py` | Not present | Not present |
| `test_guardian_memory.py` (14 KB) | Not present | Not present |
| `test_guardian_vault.py` | Not present | Not present |
| `test_guardian_verifier.py` | Not present | Not present |
| `test_guardian_breakglass.py` (23 KB) | Not present | Not present |
| `test_task_guardian.py` (9 KB) | Not present | Not present |
| `test_token_guardian_shadow.py` (8 KB) | Not present | Not present |
| `test_project_executive.py` | Not present | Not present |

---

## 4. Dependency Map

### 4.1 Guardian Core Modules (product-generic)

```
suite.py (entrypoint)
├── auth.py              ← PIN, break-glass, sessions
├── vault.py             ← Fernet encryption, access policies
│   └── cryptography     (external dep)
├── policy.py            ← Tool classification, decide_tool_use()
├── pending_approvals.py ← TTL-gated approval queue
├── token_guardian.py    ← Model routing
│   └── tokenguardian/   (vendored: classifier, monitor, optimizer, pipeline)
├── verifier.py          ← Output verification
├── improvement.py       ← Outcome scoring
└── retrievers.py        ← Retrieval factory
```

### 4.2 Sparkbot-Only Adapters

```
spine.py (canonical state)
├── task_master_adapter.py ← ChatTask ↔ Spine sync
│   └── models.ChatTask, models.TaskStatus (SQLModel)
├── project_executive.py   ← Project lifecycle
├── memory.py              ← Sparkbot memory adapter
│   └── memory_os/         (vendored: ledger, FTS, embed, consolidation)
│   └── memory_hygiene.py  ← Lifecycle state machine
│   └── memory_taxonomy.py ← Type classification
├── task_guardian.py        ← Scheduled jobs (tool knowledge)
├── executive.py           ← High-risk journaling
├── tool_guardrails.py     ← Per-tool validation
├── governance.py          ← Connector health (Sparkbot integrations)
├── meeting_recorder.py    ← ChatMeetingArtifact integration
└── meeting_heartbeat.py   ← Multi-agent facilitation
```

### 4.3 DB Dependencies

```
Main App DB (SQLAlchemy/SQLModel)
├── chat_tasks         ← task_master_adapter sync
├── user_memories      ← memory_hygiene lifecycle
├── audit_logs         ← Guardian tool audit
├── chat_meeting_artifacts ← meeting_recorder
└── reminders          ← task_guardian can trigger

Guardian Spine DB (SQLite)
├── guardian_spine_tasks
├── guardian_spine_events
├── guardian_spine_links
├── guardian_spine_assignments
├── guardian_spine_approvals
├── guardian_spine_handoffs
├── guardian_spine_projects
└── guardian_spine_project_events

Guardian Vault DB (SQLite)
├── vault_entries
└── vault_audit

Pending Approvals DB (SQLite)
└── pending_approvals

Task Guardian tables (SQLite)
├── guardian_tasks
└── guardian_task_runs

Memory Guardian (filesystem)
├── ledger.jsonl
├── indexes/ (FTS5)
└── snapshots/ (JSON)
```

### 4.4 API Route Dependencies

```
guardian.py (router)
├── auth.py            → break-glass/pin endpoints
├── vault.py           → vault CRUD endpoints
├── task_guardian.py    → scheduled task endpoints
├── memory.py          → metrics endpoint
└── suite.py           → status endpoint

spine.py (router)
├── spine.py (service) → all spine query endpoints
├── task_master_adapter.py → task master overview
├── project_executive.py   → project write endpoints
└── auth.py            → operator identity check

dashboard.py (router)
├── governance.py      → connector health, templates, evals
├── pending_approvals.py → approve/deny actions
└── task_guardian.py    → runs timeline
```

### 4.5 Background Job Dependencies

```
task_guardian_scheduler()
├── task_guardian.py     → poll + execute
├── verifier.py          → verify output
├── executive.py         → journal decisions
├── policy.py            → decide_tool_use()
├── spine.py             → emit events
└── bridges (telegram/discord/whatsapp) → notifications

memory_guardian_nightly_scheduler()
├── memory_hygiene.py    → lifecycle cleanup
├── memory.py            → consolidation
└── spine.py             → emit events
```

### 4.6 Frontend Dependencies

```
spine.tsx (React dashboard)
└── spine.ts (API client)
    ├── /api/v1/chat/spine/operator/* → spine.py router
    ├── /api/v1/chat/guardian/*       → guardian.py router
    └── cookie-first auth             → login.py
```

### 4.7 Approval/Break-glass Chain

```
User action → policy.decide_tool_use()
  ├── "allow"   → execute immediately
  ├── "confirm" → pending_approvals.store_pending_approval()
  │              → dashboard approve/deny
  │              → pending_approvals.consume_pending_approval()
  │              → spine.emit_approval_event()
  ├── "deny"    → block
  ├── "privileged" → require break-glass session
  │   └── auth.open_privileged_session(pin)
  │       → vault operations allowed
  └── "privileged_reveal" → break-glass + reveal secret
```

---

## 5. Extraction Plan

### Phase 0: Inventory Only (this document)
- **Goal:** Map every Guardian/Spine component, route, table, job, env var
- **Status:** COMPLETE
- **Output:** This audit report

### Phase 1: Adapter Boundaries
- **Goal:** Define clean interfaces between generic Guardian core and Sparkbot-specific adapters
- **Actions:**
  1. Define `GuardianStorageBackend` protocol (abstract over SQLite paths, env vars)
  2. Define `GuardianToolRegistry` protocol (abstract over tool policy registry)
  3. Define `GuardianEventSink` protocol (abstract over Spine event emission)
  4. Define `GuardianNotificationSink` protocol (abstract over bridge notifications)
  5. Mark each function as `@core` or `@adapter` in documentation
- **Files affected:**
  - `vault.py` — extract storage path config
  - `policy.py` — split registry from engine
  - `pending_approvals.py` — extract storage path config
  - `auth.py` — extract env var config
  - `task_guardian.py` — extract tool lists and notification calls

### Phase 2: Move Generic Guardian Core to LIMA
- **Goal:** Extract product-generic modules to LIMA package
- **Modules to move:**
  - `vault.py` (Fernet encryption, access policies, audit)
  - `auth.py` (PIN, break-glass, sessions, lockout)
  - `pending_approvals.py` (TTL-gated approval queue)
  - `policy.py` (core engine — NOT the tool registry)
  - `verifier.py` (core verification — NOT tool-specific patterns)
  - `improvement.py` (outcome scoring, pattern learning)
  - `retrievers.py` (retrieval factory)
  - `retrieval_eval.py` (diagnostics)
- **Dependencies to resolve:**
  - Remove all `SPARKBOT_*` env var prefixes → `LIMA_GUARDIAN_*` or configurable prefix
  - Replace hardcoded `data/guardian/` paths → configurable `data_dir`
  - Remove `app.models` imports → protocol-based interfaces

### Phase 3: Move Spine/Task Network Core to LIMA
- **Goal:** Extract Spine as standalone state catalog
- **Modules to move:**
  - `spine.py` — core state catalog (remove ChatTask sync, keep event/task/project/approval tables)
  - `task_master_adapter.py` — keep as Sparkbot adapter, extract queue snapshot interface
  - `project_executive.py` — keep as Sparkbot adapter, extract project lifecycle interface
- **Key challenge:** `spine.py` has `sync_chat_task_created()` and `sync_chat_task_mirror()` which depend on SQLModel `ChatTask`. These must become adapter hooks.

### Phase 4: Sparkbot Shim Adapters
- **Goal:** Create thin adapters so Sparkbot consumes LIMA modules
- **Adapters to create:**
  - `sparkbot_tool_registry.py` — Sparkbot's 50+ tool policy entries
  - `sparkbot_spine_sync.py` — ChatTask ↔ Spine mirror sync
  - `sparkbot_notification_sink.py` — Telegram/Discord/WhatsApp bridge
  - `sparkbot_memory_adapter.py` — Sparkbot-specific memory event types
  - `sparkbot_meeting_adapter.py` — ChatRoom/ChatMeetingArtifact integration

### Phase 5: Standalone LIMA Package Tests
- **Goal:** Ensure LIMA Guardian Suite works without Sparkbot
- **Tests to write:**
  - Vault: encrypt/decrypt/list/delete without Sparkbot DB
  - Auth: PIN create/verify/lockout without Sparkbot models
  - Policy: core engine with custom registry (not Sparkbot tools)
  - Spine: event ingestion/querying without ChatTask
  - Pending Approvals: store/consume/expire lifecycle
  - Token Guardian: routing decisions without Sparkbot config

### Phase 6: Sparkbot Consumes LIMA as Dependency
- **Goal:** Replace inline guardian modules with `lima-guardian-suite` package import
- **Steps:**
  1. Add `lima-guardian-suite` to `pyproject.toml`
  2. Replace `from app.services.guardian.vault import ...` → `from lima_guardian.vault import ...`
  3. Wire Sparkbot adapters to LIMA protocols
  4. Run full Sparkbot test suite
  5. Deploy to staging
  6. Verify all routes, jobs, dashboard still work
  7. Deploy to production

---

## 6. High-Risk Areas

### 6.1 Vault (CRITICAL)
- **Risk:** Contains encrypted secrets (API keys, tokens, passwords)
- **Encryption:** Fernet-AES-128-CBC keyed by `SPARKBOT_VAULT_KEY` env var
- **Concern:** Extraction must preserve encryption compatibility — cannot change key format or cipher
- **Mitigation:** Vault module is already self-contained; just change env var prefix
- **No key rotation tooling exists** (known gap — TODO-SEC-5)

### 6.2 Break-Glass / Privileged Sessions (HIGH)
- **Risk:** Controls access to vault writes, secret reveals, admin operations
- **PIN storage:** PBKDF2-HMAC-SHA256 at `data/guardian/operator_pin.hash`
- **Sessions:** In-memory only — die on restart (intentional security choice)
- **Concern:** Session management must remain in-memory; cannot externalize to DB without security review
- **Lockout:** 5 failed attempts / 300s window — must be preserved

### 6.3 Pending Approvals (MEDIUM)
- **Risk:** Holds serialized tool arguments (could contain sensitive data)
- **TTL:** 600s default — expired entries pruned automatically
- **Concern:** If approval store is shared across LIMA consumers, tool args may leak between tenants
- **Mitigation:** Keep approval store per-deployment (no shared state)

### 6.4 Spine Event Emission (MEDIUM)
- **Risk:** All Guardian subsystems emit events to Spine — changing emission format could break consumers
- **Concern:** Multiple producers (crud, tasks, executive, pending_approvals, task_guardian, rooms) are wired
- **Mitigation:** Define stable event schema before extraction; version events

### 6.5 Scheduled Jobs (MEDIUM)
- **Risk:** Task Guardian runs tools automatically on schedule
- **Write tools:** gmail_send, slack_send_message, calendar_create_event — opt-in only
- **Concern:** Extraction must preserve write-mode gate (`SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED`)
- **Mitigation:** Keep write-mode default OFF in LIMA

### 6.6 Memory Writes (MEDIUM)
- **Risk:** Memory Guardian writes user facts, profiles, and PII-redacted content
- **Hygiene lifecycle:** active → stale → archived → delete_proposed → soft_deleted
- **Concern:** Memory data contains user information; extraction must preserve PII redaction
- **Mitigation:** PII redaction is in memory.py adapter, not in memory_os core — keep redaction in adapter

### 6.7 Approval Bypass Risk (LOW)
- **Risk:** `global_bypass_enabled()` in policy.py allows Computer Control bypass with TTL
- **Env var:** `SPARKBOT_GLOBAL_COMPUTER_CONTROL` + `SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT`
- **Concern:** Bypass must not be enabled by default in LIMA
- **Mitigation:** Default to disabled; require explicit opt-in

### 6.8 Production DB Migrations (LOW)
- **Risk:** Spine/Vault/Approvals use separate SQLite DBs — no Alembic migrations
- **Concern:** Schema changes during extraction could corrupt running DBs
- **Mitigation:** Spine/Vault already manage their own schema in Python code; don't change schema during extraction

---

## 7. Recommended First 3 PRs

### PR 1: Extract Vault + Auth to Standalone LIMA Module

**Goal:** Move `vault.py` and `auth.py` to LIMA as standalone, zero-Sparkbot-dependency modules with configurable env var prefix.

**Files likely touched (in LIMA repo):**
- `lima_guardian/vault.py` — copy from Sparkbot, replace `SPARKBOT_` prefix with configurable
- `lima_guardian/auth.py` — copy from Sparkbot, replace `SPARKBOT_` prefix with configurable
- `lima_guardian/config.py` — new: `GuardianConfig(env_prefix="SPARKBOT_", data_dir="data/guardian/")`
- `tests/test_vault.py` — standalone vault tests (encrypt/decrypt/list/delete/audit)
- `tests/test_auth.py` — standalone auth tests (PIN/break-glass/lockout)
- `pyproject.toml` — add `cryptography>=41.0.0`

**Tests to run:**
- `pytest tests/test_vault.py tests/test_auth.py`
- Verify: vault encrypt/decrypt roundtrip, PIN create/verify, break-glass open/close/expire, lockout after 5 failures

**Rollback plan:**
- Delete LIMA files; Sparkbot unchanged (no Sparkbot modifications in this PR)

---

### PR 2: Extract Pending Approvals + Policy Engine Core

**Goal:** Move `pending_approvals.py` and the core policy engine (without Sparkbot tool registry) to LIMA.

**Files likely touched (in LIMA repo):**
- `lima_guardian/pending_approvals.py` — copy, configurable data_dir
- `lima_guardian/policy.py` — copy core engine (`decide_tool_use()`, `PolicyAction`, `PolicyDecision`); split tool registry to separate file
- `lima_guardian/registries/default_tools.py` — new: empty default registry (consumers provide their own)
- `tests/test_pending_approvals.py` — store/consume/expire/list/discard lifecycle
- `tests/test_policy.py` — core engine with mock registry

**Tests to run:**
- `pytest tests/test_pending_approvals.py tests/test_policy.py`
- Verify: approval store/consume roundtrip, TTL expiry, policy decisions with custom registry

**Rollback plan:**
- Delete LIMA files; Sparkbot unchanged

---

### PR 3: Extract Token Guardian + Verifier + Improvement Loop

**Goal:** Move product-generic analysis modules to LIMA.

**Files likely touched (in LIMA repo):**
- `lima_guardian/token_guardian.py` — copy, remove Sparkbot config refs
- `lima_guardian/tokenguardian/` — copy vendored submodule (classifier, monitor, optimizer, pipeline, config/)
- `lima_guardian/verifier.py` — copy, extract tool-specific patterns to configurable registry
- `lima_guardian/improvement.py` — copy, configurable data_dir
- `tests/test_token_guardian.py` — shadow/live routing, cost estimation
- `tests/test_verifier.py` — confidence scoring, failure detection
- `tests/test_improvement.py` — outcome recording, pattern learning

**Tests to run:**
- `pytest tests/test_token_guardian.py tests/test_verifier.py tests/test_improvement.py`
- Verify: routing decisions, verification scoring, outcome persistence

**Rollback plan:**
- Delete LIMA files; Sparkbot unchanged

---

## 8. Commands Used

All commands were read-only file searches and inspections:

```bash
# File discovery
find . -iname '*guardian*' -o -iname '*spine*' -o -iname '*vault*' -o -iname '*verifier*'
find . -iname '*approval*' -o -iname '*breakglass*' -o -iname '*executive*'
find . -iname '*meeting*' -o -iname '*memory*' -o -iname '*improvement*'

# Content search (via Grep tool — not shell grep)
grep -r "get_guardian_suite\|guardian_suite_inventory" .
grep -r "task_guardian\|memory_guardian\|token_guardian" .
grep -r "pending_approvals\|breakglass\|spine" .
grep -r "APIRouter\|@router\|BackgroundTasks\|scheduler" app/
grep -r "os.getenv\|Settings\|BaseSettings" app/
grep -r "PolicyAction\|decide_tool_use\|PolicyDecision" .
grep -r "__tablename__\|class.*Base\|SQLModel" app/models.py
grep -r "vault_entries\|vault_audit\|guardian_spine_" .

# File reading (via Read tool)
# Read all guardian service files
# Read all guardian route files
# Read guardian test files
# Read frontend spine.ts and spine.tsx
# Read main.py for startup/shutdown hooks
# Read models.py for DB models
# Read alembic migration files

# LIMA repo
git clone https://github.com/armpit-symphony/LIMA-Guardian-Suite /tmp/lima-guardian-suite/
# Read all files in LIMA repo

# No destructive commands were used.
# No env values were printed.
# No secrets were accessed.
# No production behavior was changed.
```

---

## Appendix A: Environment Variables Summary (names only)

### Guardian Core
| Variable | Module | Default |
|----------|--------|---------|
| `SPARKBOT_GUARDIAN_DATA_DIR` | vault, spine, auth, pending_approvals, executive | `data/guardian` |
| `SPARKBOT_GUARDIAN_POLICY_ENABLED` | policy | `true` |
| `SPARKBOT_VAULT_KEY` | vault | (required) |
| `SPARKBOT_OPERATOR_PIN_HASH` | auth | (optional) |
| `SPARKBOT_OPERATOR_USERNAMES` | auth | (optional) |
| `SPARKBOT_BREAKGLASS_TTL_SECONDS` | auth | `900` |
| `SPARKBOT_PIN_MAX_ATTEMPTS` | auth | `5` |
| `SPARKBOT_PIN_LOCKOUT_WINDOW_SECONDS` | auth | `300` |
| `SPARKBOT_GLOBAL_COMPUTER_CONTROL` | policy | `false` |
| `SPARKBOT_GLOBAL_COMPUTER_CONTROL_EXPIRES_AT` | policy | (none) |

### Spine
| Variable | Module | Default |
|----------|--------|---------|
| `SPARKBOT_GUARDIAN_SPINE_AUTO_CREATE_THRESHOLD` | spine | `0.85` |
| `SPARKBOT_GUARDIAN_SPINE_REVIEW_THRESHOLD` | spine | `0.60` |

### Task Guardian
| Variable | Module | Default |
|----------|--------|---------|
| `SPARKBOT_TASK_GUARDIAN_ENABLED` | task_guardian | `true` |
| `SPARKBOT_TASK_GUARDIAN_POLL_SECONDS` | task_guardian | `60` |
| `SPARKBOT_TASK_GUARDIAN_MAX_OUTPUT` | task_guardian | `2000` |
| `SPARKBOT_TASK_GUARDIAN_MAX_RETRIES` | task_guardian | `3` |
| `SPARKBOT_TASK_GUARDIAN_RETRY_BASE_SECONDS` | task_guardian | `300` |
| `SPARKBOT_TASK_GUARDIAN_RETRY_MAX_SECONDS` | task_guardian | `3600` |
| `SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED` | task_guardian | `false` |
| `SPARKBOT_TASK_GUARDIAN_MEMORY_NIGHTLY_ENABLED` | task_guardian | `true` |
| `SPARKBOT_TASK_GUARDIAN_MEMORY_NIGHTLY_UTC` | task_guardian | `03:10` |

### Token Guardian
| Variable | Module | Default |
|----------|--------|---------|
| `SPARKBOT_TOKEN_GUARDIAN_MODE` | token_guardian | `shadow` |
| `SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED` | token_guardian | `true` |

### Memory Guardian
| Variable | Module | Default |
|----------|--------|---------|
| `SPARKBOT_MEMORY_GUARDIAN_ENABLED` | memory | `true` |
| `SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS` | memory | `1200` |
| `SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT` | memory | `6` |
| `SPARKBOT_MEMORY_GUARDIAN_DATA_DIR` | memory | (default) |
| `SPARKBOT_MEMORY_GUARDIAN_RETRIEVER` | memory | `fts` |
| `SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS` | memory | (false) |
| `SPARKBOT_MEMORY_LEDGER_COMPRESSION` | memory | (default) |
| `SPARKBOT_MEMORY_SNAPSHOT_REBUILD_EVERY_N` | memory | (default) |
| `SPARKBOT_MEMORY_SNAPSHOT_REBUILD_MIN_SECONDS` | memory | (default) |
| `SPARKBOT_MEMORY_STALE_*_DAYS` | memory_hygiene | (per-type) |
| `SPARKBOT_MEMORY_ARCHIVE_*_DAYS` | memory_hygiene | (per-type) |
| `SPARKBOT_MEMORY_PROPOSE_DELETE_*_DAYS` | memory_hygiene | (per-type) |

### Executive & Improvement
| Variable | Module | Default |
|----------|--------|---------|
| `SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED` | executive | `true` |
| `SPARKBOT_IMPROVEMENT_LOOP_ENABLED` | improvement | `true` |
| `SPARKBOT_IMPROVEMENT_DATA_DIR` | improvement | `data/improvement_loop` |

---

## Appendix B: File Size Reference

| File | Size | Lines (approx) |
|------|------|----------------|
| `spine.py` | 137.5 KB | ~3870 |
| `memory.py` | 56.2 KB | ~1600 |
| `task_guardian.py` | 32.5 KB | ~920 |
| `policy.py` | 22.3 KB | ~630 |
| `token_guardian.py` | 14.5 KB | ~410 |
| `auth.py` | 10.1 KB | ~285 |
| `verifier.py` | 10.3 KB | ~290 |
| `meeting_heartbeat.py` | ~17.5 KB | ~500 |
| `meeting_recorder.py` | ~10.5 KB | ~300 |
| `improvement.py` | ~14 KB | ~400 |
| `pending_approvals.py` | 8.2 KB | ~233 |
| `memory_hygiene.py` | ~9.4 KB | ~267 |
| `executive.py` | 6.2 KB | ~176 |
| `governance.py` | 6.4 KB | ~182 |
| `suite.py` | 3.8 KB | ~109 |
| `tool_guardrails.py` | 3.3 KB | ~94 |
| `memory_taxonomy.py` | ~5.3 KB | ~150 |
| `task_master_adapter.py` | ~9.3 KB | ~263 |
| `project_executive.py` | ~10.6 KB | ~300 |
| `retrievers.py` | ~3.5 KB | ~100 |
| `retrieval_eval.py` | ~5.3 KB | ~150 |

**Total Guardian codebase in Sparkbot:** ~420 KB across 22 modules + vendored submodules

---

*End of audit. No production code was modified. No secrets were accessed or printed.*
