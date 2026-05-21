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
| Slack retrieval | FAIL_CLOSED_TESTED | Slack route calls `build_unified_context` only after signed request, allowed channel, allowed sender, and existing linked Sparkbot owner are present. | Live Slack test app still required before marking recall GREEN. |
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
| P1 | Slack inbound identity is env-linked and fail-closed, but not live-tested. | Run signed Slack test app with channel + sender allowlists before marking Slack meeting recall GREEN. |
| P1 | Rich structured notes editor is textarea-based for now. | Add field-level editing only if browser QA shows real operator friction. |
| P2 | SMS/text is not implemented. | Keep disabled/future until provider and auth model are chosen. |

## LIMA Runtime Alignment

Later LIMA AI OS can generalize the pattern as meeting artifact -> structured note metadata -> memory rollup -> connector-safe retrieval. This branch keeps the implementation in Sparkbot Public and does not wire LIMA runtime.

## Connector Identity Live QA Update - 2026-05-21

Branch: `public-release-connector-identity-live-qa`
Previous meeting-memory commit verified: `7f327b2e45011facef7bb751166adac6e5c223cc`

Completed in this pass:

- Added `docs/CONNECTOR_IDENTITY_LINKING_STATUS.md`.
- Hardened Slack inbound memory recall to fail closed without request signing, allowed channel, allowed Slack sender, and explicit existing Sparkbot owner link.
- Added focused Slack identity tests for missing signing secret, channel allowlist, sender allowlist, and linked owner lookup.
- Confirmed this process environment has no configured test Telegram/Discord/WhatsApp/Slack identities, but `.env.local` contains Telegram/Discord connector keys; no live connector messages were sent.

Current status:

- Main Chat meeting-note recall remains GREEN by automated memory tests.
- Slack private meeting-note recall is YELLOW/UNKNOWN: fail-closed channel + sender checks are implemented, live test pending.
- Telegram/Discord/WhatsApp are YELLOW: they use linked bridge identity and unified context, but web-operator cross-surface recall needs explicit mapping/QA.
- SMS/text remains future/unsupported.

Recommended next phase:

Run browser QA for notes save/edit/Main Chat recall and live connector QA with configured test identities. After that, refresh the `Sparkbot_shell` extraction map if no P0 connector leaks remain.

## Connector PIN Verification Update - 2026-05-21

- Added connector-scoped, time-limited PIN verification sessions for private meeting recall.
- Reused existing Guardian operator PIN hashing, verification, failed-attempt tracking, and lockout behavior; no raw PIN is stored in connector sessions.
- Private meeting recall now fails closed unless the external connector has a linked/authorized operator identity or a valid connector PIN session.
- Telegram private recall requires `TELEGRAM_ALLOWED_CHAT_IDS`; Telegram `/breakglass` now requires explicit `SPARKBOT_OPERATOR_TELEGRAM_CHAT_IDS` mapping.
- Discord shared guild channels are blocked from private meeting recall; use DM plus `/pin <PIN>` for test/private recall.
- Slack still requires signed request, allowed channel, allowed sender, and linked owner before private context is considered.
- WhatsApp inbound now requires explicit `WHATSAPP_VERIFY_TOKEN` and `WHATSAPP_ALLOWED_PHONES`; the predictable runtime verify-token default was removed.
- SMS/text remains future/unsupported.
- Live connector QA remains required with test-only identities/channels.

## Live Connector QA Update - 2026-05-21

- Created `docs/PUBLIC_RELEASE_LIVE_CONNECTOR_QA_RESULTS.md` for non-secret live QA evidence.
- Current process environment does not expose usable Telegram, Discord, Slack, WhatsApp, SMS/text, Task Guardian external-delivery, or operator PIN test configuration.
- Local env-file inspection did not confirm any safe test-only target; `DISCORD_ENABLED` is present but disabled.
- No live connector messages were sent and no secrets/PINs/tokens/IDs were printed.
- Telegram, Discord, Slack, WhatsApp, and Task Guardian external delivery remain UNKNOWN for live QA.
- SMS/text remains FUTURE_UNSUPPORTED.
- Sparkbot_shell extraction map refresh is reasonable for classification/planning, but public external recall should stay YELLOW/UNKNOWN until live connector QA passes.
