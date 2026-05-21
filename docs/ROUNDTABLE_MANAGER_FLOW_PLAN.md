# Round Table Manager Flow Plan

Date: 2026-05-17
Branch: `public-release-capability-memory-roundtable`
Scope: Audit plus one safe stabilization patch to prevent generated notes outside manager wrap-up/checkpoint phases.

## Target Flow

1. User gives task/problem.
2. First pass: all participants give ideas.
3. Meeting manager / Seat 1 assesses.
4. Manager assigns jobs to participants.
5. Second pass: participants perform assigned jobs.
6. Manager summarizes, adjusts plan, declares next step, or closes.
7. Manager can save final notes to memory.

Meeting notes should happen only at manager wrap-up/checkpoint or by manual user action. They should not be generated after every participant turn.

## Current Implementation

| Flow part | Current state | Evidence |
|---|---|---|
| Seat 1 manager | First valid participant becomes chair. | `backend/app/api/routes/chat/rooms.py:2022` |
| First idea pass | All participants run `initial_ideas`. | `backend/app/api/routes/chat/rooms.py:2032`, `backend/app/api/routes/chat/rooms.py:2052` |
| Manager assessment | Seat 1 assesses ideas. | `backend/app/api/routes/chat/rooms.py:2055`, `backend/app/api/routes/chat/rooms.py:2073` |
| Assignments | Seat 1 assigns jobs by handle. | `backend/app/api/routes/chat/rooms.py:2075`, `backend/app/api/routes/chat/rooms.py:2093` |
| Second pass | Participants respond to assigned work. | `backend/app/api/routes/chat/rooms.py:2095`, `backend/app/api/routes/chat/rooms.py:2116` |
| Manager summary | Seat 1 returns status plus structured message. | `backend/app/api/routes/chat/rooms.py:2118`, `backend/app/api/routes/chat/rooms.py:2149` |
| Continue loop | One continuation round is supported. | `backend/app/api/routes/chat/rooms.py:2159` |
| Heartbeat | Guardian Task can continue a meeting from persisted manifest. | `backend/app/services/guardian/meeting_heartbeat.py:238`, `backend/app/services/guardian/meeting_heartbeat.py:446` |
| Manual notes | Meeting Room has an explicit Generate Meeting Notes button. | `frontend/src/pages/MeetingRoomPage.tsx:501`, `frontend/src/pages/MeetingRoomPage.tsx:1132` |

## Notes Generation Before This Patch

Generated notes were created in these paths:

- Autonomous meeting `_run_agent_turn` created a `notes` artifact whenever a parsed non-`continue` meeting status existed (`backend/app/api/routes/chat/rooms.py:1985` before this patch).
- Meeting heartbeat did the same for parsed non-`continue` status (`backend/app/services/guardian/meeting_heartbeat.py:417` before this patch).
- Manual endpoint remains available at `backend/app/api/routes/chat/rooms.py:2418`.

The code only parsed status on manager summary/checkpoint calls, so it was not literally writing notes after every token or every participant in the normal path. The risk was that the artifact condition lived inside the generic turn helper, so future parsed phases could accidentally create per-turn notes.

## Safe Patch Applied

Changed:

- `backend/app/api/routes/chat/rooms.py`
- `backend/app/services/guardian/meeting_heartbeat.py`

New behavior:

- Generated note artifacts are saved only when:
  - the turn is status-parsed,
  - the speaker is Seat 1 / chair,
  - the phase is `manager_summary`, `continue_or_operator_input`, or final heartbeat synthesis,
  - the status is not `continue`.
- Heartbeat messages now include `meeting_phase` metadata.
- Launch scaffolds are saved as draft `agenda` artifacts with memory rollup disabled.
- Manual Generate Meeting Notes still works.

Evidence after patch:

- Main meeting guard: `backend/app/api/routes/chat/rooms.py:1983`.
- Heartbeat guard: `backend/app/services/guardian/meeting_heartbeat.py:420`.
- Heartbeat phase metadata: `backend/app/services/guardian/meeting_heartbeat.py:396`.
- Launch scaffold artifact type/metadata: `frontend/src/lib/workstationMeeting.ts:468`, `frontend/src/lib/workstationMeeting.ts:603`.
- Draft artifact memory skip: `backend/app/crud.py:515`.

## Remaining Gaps

| Gap | Impact | Priority | Recommended fix |
|---|---|---|---|
| Assignments are structured/persisted but not displayed. | Backend can store parsed assignment objects and Meeting Room now renders latest assignment cards. | `DONE_FIRST_PASS` | Browser QA and refine card density/status labels. |
| Meeting UI does not show phase strongly enough. | Meeting Room now shows phase in the header and assignment panel. | `DONE_FIRST_PASS` | Add participant queue/status result polish after browser QA. |
| Meeting Room UI backend manifest load is partial. | It loads persisted manifest first, but still has no explicit error/status when backend manifest is absent. | `P1` | Keep backend manifest primary and show cache/fallback state. |
| Heartbeat launch previously blocked meeting launch. | Task Guardian issue no longer blocks core public hook. | `DONE_THIS_PHASE` | Add optional warning toast when heartbeat scheduling fails. |
| Manager final notes are saved as `notes`, same as manual notes. | Artifact list can mix launch/checkpoint/manual outputs. | `P1` | Add artifact meta `source=manager_wrapup` and UI label "Manager wrap-up". |
| The launch placeholder artifact can look like notes. | Users may think notes were generated before discussion. | `DONE_THIS_PHASE` | Launch scaffold now saves as draft `agenda` with memory rollup disabled. |
| Approval execution paths can run `privileged` decisions. | Meeting participants/tool approvals can bypass intended PIN path. | `DONE_THIS_PHASE` | Approval executors now execute only `allow`/`confirm` decisions. |

## Manager Memory Save Plan

Manager wrap-up should save:

- objective
- participants
- final status
- recommendation
- action plan
- owner input/approval needed
- blockers
- next step

Memory write path:

1. Save manager wrap-up as `ChatMeetingArtifact`.
2. `create_chat_meeting_artifact` calls `remember_meeting_artifact`.
3. `remember_meeting_artifact` rolls selected sections into Shared Work Memory.
4. Main chat and future Round Tables retrieve Shared Work Memory through `build_memory_context`.

## Public MVP Definition

Round Table is public-ready when:

- Seat 1 manager flow is visible and predictable.
- Meeting manifests load from backend.
- Assignments are visible or at least stored in metadata.
- No generated notes happen outside manager wrap-up/checkpoint/manual user action.
- Final manager summary becomes shared memory without duplicate spam.
- Tool calls inside meetings use the same permission model as chat.

## P0 Stabilization Update - 2026-05-17

Branch: `public-release-p0-memory-guardrails-roundtable`

Implemented:

- Added `backend/app/services/guardian/meeting_assignments.py`.
- Seat 1 assignment turns now parse structured assignment lines by participant handle and persist them as `action_items` meeting artifacts with `meta_json.source=meeting_assignments`.
- Assignment artifacts carry `assigned_by`, `meeting_phase`, `assignments`, `assignment_count`, and `memory_rollup=false`.
- Meeting heartbeat now loads the latest persisted assignments and injects them into follow-up participant prompts.
- Workstation Round Table launch now treats heartbeat task creation as best-effort, so a Task Guardian scheduling issue does not block the meeting.
- Meeting Room UI now attempts backend `meeting_manifest` artifact load before using localStorage cache.
- Per-turn generated notes remain disabled except manager wrap-up/checkpoint/manual notes generation.

Current assignment persistence status:

| Behavior | Status |
|---|---|
| Seat 1 manager explicit | Implemented as first valid participant/chair. |
| First pass all participants give ideas | Already implemented. |
| Manager assesses | Already implemented. |
| Manager assigns jobs | Implemented in prompt and now persisted when parseable. |
| Second pass uses assignments | Uses discussion history immediately; heartbeat also receives persisted assignment context. |
| Assignments survive refresh/reopen | Backend artifacts persist; UI display cards are not built yet. |
| Manager wrap-up saves notes | Implemented through notes artifact rollup. |
| Normal participant turns generate notes | Disabled. |

Remaining before public beta:

- Browser QA persisted assignments in the Meeting Room UI as cards.
- Refine participant queue/status result display after live meeting testing.
- Consider storing assignments as first-class room tasks only after the artifact metadata path proves stable.

## Surface UX Update - 2026-05-17

Branch: `public-release-surface-nav-room-ux`

Implemented UI behavior:

- Meeting Room top navigation is sticky and includes Chat, Workstation, Robo, Command Center, and Info.
- Meeting Room uses a fixed-height shell on desktop so the page itself does not bury the controls.
- Sidebar room controls, seated participant controls, meeting list/tasks tabs, manual notes, and Back to Workstation stay in a scrollable control rail.
- Chat history scrolls inside the meeting pane with the composer still reachable.
- Existing manager wrap-up/checkpoint/manual notes behavior was not changed.
- Existing structured assignment persistence was not changed.

## Invite Wing Model Seat Update - 2026-05-17

- Round Table meeting seat metadata now carries `modelSeatId` and model id instead of frontend-held provider secrets.
- Invite-seat route registration calls `/api/v1/chat/agents/{name}/invite-route` with the seat id. The backend resolves any Guardian Vault credential for that seat before storing the runtime route.
- Route-registration errors are no longer swallowed by the frontend meeting launcher, so a broken Invite Wing route should block launch instead of silently falling back to the wrong model.
- Per-turn meeting notes remain disabled; model-seat work did not re-enable them.

Remaining public polish:

- Render latest persisted `meeting_assignments` artifacts as visible assignment cards/status rows. `DONE_FIRST_PASS_2026-05-18`
- Add a compact phase indicator for first ideas, manager assessment, assignments, second pass, and manager wrap-up. `DONE_FIRST_PASS_2026-05-18`
- Add a visible "manager / Seat 1" label in the sticky room header or control rail. `DONE_FIRST_PASS_2026-05-18`

## Round Table Model-Seat UI Update - 2026-05-18

Branch: `public-release-roundtable-modelseat-ui-polish`

Implemented:

- Workstation defaults seat 1 to the `meetings_manager` Specialty Wing office where available.
- Stack autofill and task meeting launch use the Meeting Manager as chair instead of the generic main desk when available.
- Meeting Room control rail now labels Chair 1 as Manager.
- Meeting Room seated participant controls include per-seat agent and model selectors.
- Meeting Room displays current phase and latest structured assignments from `meeting_assignments` artifacts.
- Meeting manifests preserve model seat setup status, model-seat id, route, auth mode, and agent provisioning on backend/local reload.
- Per-turn generated notes remain disabled; this pass did not change manager wrap-up/checkpoint/manual notes behavior.

## Meeting Memory Operator Spine Update - 2026-05-21

Branch: `public-release-meeting-memory-operator-spine`

Completed in this pass:

- Added source-labeled meeting-note metadata for saved/generated Meeting Manager notes.
- Added OWNER/MOD meeting artifact editing and a Meeting Room notes editor.
- Updated meeting-note memory rollups so edits supersede stale active rollups for the same artifact.
- Kept per-turn notes disabled and blocked draft/failed-generation notes from shared memory rollup.
- Documented Main Chat and connector continuity through the shared context path with explicit identity-linking limits.

Remaining after this pass:

- Browser QA notes save/edit and role permissions.
- Live QA meeting recall through Main Chat and linked Telegram/Discord/WhatsApp/Slack identities.
- Treat SMS/text as future until a real connector and identity model exist.
