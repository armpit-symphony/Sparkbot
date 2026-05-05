# Roundtable Meeting Flow v1.6.60

## Current Paths

- Frontend meeting room: `frontend/src/pages/MeetingRoomPage.tsx`
- Workstation launch/manifest/provider preflight: `frontend/src/lib/workstationMeeting.ts`
- Live meeting stream: `backend/app/api/routes/chat/rooms.py`
- Background continuation: `backend/app/services/guardian/meeting_heartbeat.py`
- Manual notes generator: `backend/app/services/guardian/meeting_recorder.py`

## Flow

Seat 1 is the meeting manager. For an owner kickoff in a Roundtable room, the existing multi-agent stream now runs:

1. `initial_ideas` - every seated participant contributes first-pass ideas.
2. `manager_assessment` - Seat 1 assesses the first pass.
3. `assignments` - Seat 1 assigns concrete jobs to every participant.
4. `assigned_work_pass` - every participant responds from the assigned job.
5. `manager_summary` - Seat 1 summarizes and chooses a plan, adjustment, continuation, or operator-input request.
6. `continue_or_operator_input` - when useful, Seat 1 can launch one more assigned pass before final summary.

## Meeting Notes

Generated meeting notes are manual-only. The meeting page still exposes Generate Meeting Notes, and explicit text requests such as `/meeting notes` and `generate meeting notes` call the same manual endpoint. Stream completion and hourly heartbeat no longer call the notes generator automatically.

## Provider Readiness

Before a meeting launch, the Workstation launcher checks only providers/models assigned to the selected seats. Missing assigned routes stop launch with a concise warning that names only the affected seats.

In meeting chat, provider-readiness self-inspection for assigned participants renders only the requested room participants and omits unrelated provider inventory.

## Mobile Layout

The meeting page switches to a compact stacked layout below 820px. The sidebar is no longer sticky on compact screens, the page can scroll normally, and the chat area keeps a mobile minimum height so content and controls remain reachable from remote phone browsers.
