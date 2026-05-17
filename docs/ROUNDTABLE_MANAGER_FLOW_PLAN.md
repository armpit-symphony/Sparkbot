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
| Assignments are not structured/persisted. | Participants follow prompt context, but UI cannot show durable assignment cards. | `P1` | Parse/store Seat 1 assignments as meeting artifact metadata or room tasks. |
| Meeting UI does not show phase strongly enough. | Users cannot see why agents are speaking in sequence. | `P1` | Surface current phase, manager, queue, and status in Meeting Room. |
| Meeting Room UI still loads seat metadata from localStorage. | Reopened/shared meetings can lose seat display state. | `P0` | Load `meeting_manifest` artifact from backend before localStorage. |
| Heartbeat launch can block meeting launch. | Task Guardian issue can block core public hook. | `P0` | Make heartbeat scheduling best-effort in Workstation launch. |
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
