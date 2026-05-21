# Meeting Memory Operator Spine Status

Date: 2026-05-21
Branch: `public-release-meeting-memory-operator-spine`
Base: `origin/public-release-task-delivery-operator-channels`

## System Model

Sparkbot owns this first. Workstation is the operating floor, Main Chat is the operator command channel, Round Table is the meeting room, Meeting Manager is the coordinator/secretary, unified memory/context is shared company memory, and external text connectors are communication doors into the same Sparkbot system. This phase does not wire LIMA AI OS, Arc Bot, LIMA Office, LIMA IT, Sparkbot_shell, or real robotics/IoT control.

## Current Implementation

| Area | Status | Evidence / behavior | Remaining gap |
|---|---|---|---|
| Meeting notes generation | IMPLEMENTED | Manual Generate Meeting Notes and manager wrap-up/checkpoint notes create `notes` artifacts. Per-turn notes remain disabled. | Live browser QA still required. |
| Meeting notes save | IMPLEMENTED | Notes artifacts are saved in `chat_meeting_artifacts` and normalized with `meeting_id`, `artifact_id`, source, timestamps, structured fields, tags, draft, and memory rollup flags. | Rich field-by-field editor can be later polish. |
| Meeting notes edit | IMPLEMENTED | OWNER/MOD can edit artifacts through `PATCH /api/v1/chat/rooms/{room_id}/artifacts/{artifact_id}`. Meeting Room exposes an edit/update notes panel. | Browser permission QA required. |
| Memory rollup | IMPLEMENTED | Saved/final notes roll into shared work memory with source `meeting.notes.rollup`; edits retire stale rollups for the same artifact before adding the updated rollup. | UI memory inspector remains later polish. |
| Draft suppression | IMPLEMENTED | Draft/scaffold artifacts and failed generated-note drafts do not roll into memory. | Add browser QA around failed generation state. |
| Main Chat retrieval | IMPLEMENTED | Main Chat/DM uses `build_unified_context`, which includes shared meeting rollups for the same Sparkbot user identity. | Test with live prompt after notes update. |
| Telegram retrieval | IMPLEMENTED_WITH_IDENTITY_LIMIT | Telegram bridge calls `build_unified_context` for linked room/user identity. | Cross-surface recall requires explicit link to the intended Sparkbot user; do not expose notes to unknown chats. |
| Discord retrieval | IMPLEMENTED_WITH_IDENTITY_LIMIT | Discord bridge calls `build_unified_context` for linked channel/user identity. | Guild/channel allowlists and identity mapping need live QA. |
| WhatsApp retrieval | IMPLEMENTED_WITH_IDENTITY_LIMIT | WhatsApp bridge calls `build_unified_context` for linked phone/user identity. | Only linked/authorized numbers should retrieve private notes. |
| Slack retrieval | PARTIAL_IDENTITY_LIMIT | Slack route calls `build_unified_context` but currently uses a synthetic Sparkbot user/room pattern. | Needs explicit account/room linking before promising full cross-surface meeting memory. |
| SMS/text | FUTURE_UNSUPPORTED | No SMS/text inbound connector exists in this phase. | Keep documented as future until real provider and identity mapping exist. |
| Task/reminder/file memory | IMPLEMENTED | Existing task, reminder, upload, and connector memory routes use source-labeled memory events. | Same identity boundary applies. |

## Notes Data Shape

Meeting notes now carry public-safe metadata where available:

- `meeting_id`
- `artifact_id`
- `title`
- `created_at` / `updated_at`
- `created_by` / `updated_by`
- `source`: `meeting_manager` or `manual_edit`
- `summary`
- `decisions`
- `action_items`
- `next_steps`
- `open_questions`
- `participants`
- `memory_rollup`
- `draft`
- `tags`

No raw connector secrets are stored in note metadata. Failed auto-generated notes are marked draft/no-rollup so raw transcript fallback text does not become shared memory by default.

## Safety Decisions

- Per-turn participant notes remain disabled.
- Draft/scaffold notes do not roll into shared memory.
- Edited notes supersede the old rollup for that artifact instead of leaving stale decisions in active prompt context.
- External channels may read meeting notes only through their existing linked room/user identity. Missing identity mapping is documented as a blocker, not bypassed.
- No surprise external messages are sent by this phase.

## Remaining Gaps

| Priority | Gap | Recommended next action |
|---|---|---|
| P0 | Connector identity linking and fail-closed public setup need live review before promising cross-channel private meeting recall. | Run live QA with test Telegram/Discord/WhatsApp/Slack accounts and document exact linking requirements. |
| P1 | Browser QA the Meeting Room notes editor and role permissions. | Verify owner/mod edit, member/viewer denial, and edited memory recall in Main Chat. |
| P1 | Slack inbound identity remains synthetic. | Add explicit Slack account/room linking before marking Slack meeting recall GREEN. |
| P1 | Rich structured notes editor is textarea-based for now. | Add field-level editing only if browser QA shows real operator friction. |
| P2 | SMS/text is not implemented. | Keep disabled/future until provider and auth model are chosen. |

## LIMA Runtime Alignment

Later LIMA AI OS can generalize the pattern as meeting artifact -> structured note metadata -> memory rollup -> connector-safe retrieval. This branch keeps the implementation in Sparkbot Public and does not wire LIMA runtime.
