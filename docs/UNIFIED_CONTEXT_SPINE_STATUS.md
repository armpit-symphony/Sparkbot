# Unified Context Spine Status

Date: 2026-05-17
Branch: `public-release-unified-context-spine`

## Product Rule

Sparkbot Public should feel like one coordinated workstation:

- one Sparkbot brain
- one public context spine
- many surfaces
- many models
- many agents
- one fluent experience

This pass keeps Guardian internals private. It adds a clean public adapter on top of the existing Guardian memory substrate so surfaces can write and retrieve source-labeled context without exposing proprietary Guardian Suite details.

## Public Context Interface

Implemented in `backend/app/services/guardian/memory.py`:

- `remember_context_event(...)`
- `build_unified_context(...)`
- structured recall fields added to `recall_relevant_events(...)`

Supported public-safe fields:

| Field | Status |
|---|---|
| `source_type` / `surface` | Implemented |
| `actor_label` | Implemented |
| `role` | Implemented for user/assistant/system paths |
| `content_summary` | Implemented, redacted before storage |
| `thread_id` / `conversation_id` / `meeting_id` | Implemented |
| `model_seat_id` | Implemented as metadata only |
| `agent_id` | Implemented as metadata only |
| `memory_rollup` | Implemented |
| `sensitivity` / `risk_label` | Implemented as public-safe labels |
| `tags` | Implemented as bounded metadata |

Raw credentials, provider secrets, cookies, and Vault values are not accepted as public context fields and continue to be redacted if they appear in text.

## Write Path Status

| Surface | Current status |
|---|---|
| Main chat / DM | Reads via `build_unified_context`; existing chat writes still use `remember_chat_message` and mirror to shared chat memory when enabled. |
| Workstation | Meeting/model-seat actions can produce backend artifacts/routes; ordinary UI clicks remain deferred to avoid noisy memory spam. |
| Round Table / Meeting Room | Manager wrap-up/checkpoint rollups continue through artifact memory; new unified rollup helper skips drafts/scaffolds and dedupes repeated manager summaries. |
| Invite Wing model seats | Seat config remains backend-owned; secrets stay in Vault; non-secret `model_seat_id` can travel in agent/meeting metadata. |
| Specialty Wing agents | Agent overrides now preserve `model_seat_id` and backend route context resolves seat credentials server-side. |
| Command Center agents | Custom agents remain create/edit capable; route override saves can carry `model_seat_id`. |
| Tasks/reminders/files | Prior P0 pass already routes these through bridge/tool/file memory adapters; this pass documents them as part of the unified surface contract. |
| Telegram | Reads unified context and writes source-labeled Telegram user/assistant context events. |
| Discord | Reads unified context and writes source-labeled Discord user/assistant context events. |
| WhatsApp | Reads unified context and writes source-labeled WhatsApp user/assistant context events. |
| GitHub | Reads unified context and writes source-labeled GitHub user/assistant context events. |
| Slack | Reads unified context and writes source-labeled Slack user/assistant context events. |
| Terminal/browser/tools | Tool event summaries already write redacted tool memory; richer terminal/browser action summaries should remain permissioned tool events, not UI spam. |
| Guardian approvals | Existing audit/tool paths remain public-safe; dedicated confirmation-summary memory is documented as a follow-up to avoid duplicate approval noise. |

Approval payload hardening in this pass:

- Pending approval Spine events now recursively redact nested secret-like keys before public-safe approval events are emitted.

## Read Path Status

| Surface | Current status |
|---|---|
| Main chat / DM | Uses unified context read adapter. |
| Round Table / Meeting Room | Participant prompts reuse chat memory context; manager wrap-up memory remains shared. |
| Specialty Wing agent runs | Use chat/agent route context and the shared prompt memory path. |
| Invite Wing model-seat runs | Round Table custom invite agents route through backend invite route and can use shared prompt memory. |
| Slack/Telegram/Discord/WhatsApp/GitHub | Bridge handlers now call the unified context read adapter. |
| Tasks/reminders | Write shared events; direct retrieval into task generation remains a follow-up. |

Retrieval remains bounded through the existing Guardian memory retrieval limits and prefers summarized/shared memory over raw broad dumps.

## Model Seat And Vault Binding

Implemented:

- Added `backend/app/services/model_seats.py` as the shared public model-seat helper.
- `agent_overrides` can now persist `model_seat_id`.
- `get_agent_route_context(...)` resolves the selected model seat server-side.
- Explicit Vault-backed model-seat routes now report setup-needed when the seat credential is missing or disabled instead of silently falling back to a global provider key.
- Vault credentials are accessed only on the backend through the deterministic model-seat alias.
- Frontend config carries only route, model id, and `model_seat_id`.
- Workstation Specialty Wing, Command Center, and legacy DM Controls model override flows preserve `model_seat_id` when a model comes from an enabled Specialty Wing model seat.

Not implemented:

- A full Command Center model-seat editor.
- Dynamic provider model discovery for every company.
- A visible "setup needed" badge for every Specialty Wing model-seat mismatch.

## Duplicate Memory Spam Prevention

Implemented:

- `remember_context_event(..., memory_rollup=True)` fingerprints shared rollups and skips duplicates.
- Draft/scaffold/placeholder rollups are ignored.
- Connector events reuse the existing bridge dedupe behavior for Shared Work Memory.
- Per-turn Round Table notes remain disabled; manager checkpoint/wrap-up remains the preferred summary event.

Remaining risk:

- Main chat and Round Table participant messages still use existing chat memory write helpers. That is stable, but later public polish should add clearer actor/source metadata without creating duplicate writes.

## Public / Private Boundary

Preserved:

- No Sparkbot code was copied to `Sparkbot_shell`.
- No LIMA AI OS, Arc Bot, LIMA Office, or LIMA IT runtime code was wired.
- No real robotics/IoT control was implemented.
- No proprietary Guardian Suite internals were exposed.
- Model-seat credentials remain backend/Vault-owned.

## Remaining P0 Blockers

1. Balanced vs Locked guardrail behavior separation.
2. Final Round Table assignment UI polish.
3. Add public-safe confirmation/approval memory summaries without duplicating audit logs.
4. Add user-visible setup-needed indicators for Specialty Wing model seats that are selected but not configured.
5. Replace Robo/LIMA backend bridge source with a public stub before Sparkbot_shell extraction.

## Package Cleanup Note - 2026-05-17

The package/prompt cleanup pass completed the public package exclusions and built-in prompt rewrite items tracked here. It did not alter unified context behavior.
