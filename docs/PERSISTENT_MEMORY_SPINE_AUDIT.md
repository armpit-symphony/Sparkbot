# Persistent Memory Spine Audit

Date: 2026-05-17
Branch: `public-release-capability-memory-roundtable`
Goal: One durable Sparkbot memory substrate across chat, Workstation, Round Table, files, buttons, bridges, agents, tasks, reminders, and tools.

## Existing Memory Modules

- SQL user memory model: `backend/app/models.py:355`.
- Memory CRUD/API: `backend/app/api/routes/chat/memory.py:1`.
- Guardian memory adapter: `backend/app/services/guardian/memory.py:1`.
- User session memory: `backend/app/services/guardian/memory.py:333`.
- Room-scoped memory: `backend/app/services/guardian/memory.py:337`.
- Shared work memory: `backend/app/services/guardian/memory.py:341`.
- Unified chat memory toggle: `backend/app/services/guardian/memory.py:345`.
- Meeting artifact rollup: `backend/app/services/guardian/memory.py:974`.
- Prompt context builder: `backend/app/services/guardian/memory.py:1168`.
- Structured recall API/tool support: `backend/app/services/guardian/memory.py:1355`.

## What Currently Writes To Memory

| Source | Current write behavior | Evidence |
|---|---|---|
| Main chat user turns | Writes user chat messages through Guardian memory. | `backend/app/api/routes/chat/rooms.py:1338` |
| Main chat assistant turns | Writes assistant responses and tool results. | `backend/app/api/routes/chat/rooms.py:1714`, `backend/app/api/routes/chat/rooms.py:1750` |
| Agent/Round Table turns | Writes participant messages. | `backend/app/api/routes/chat/rooms.py:1975`, `backend/app/api/routes/chat/rooms.py:2324` |
| Tool execution | Writes redacted tool events. | `backend/app/api/routes/chat/rooms.py:1143`, `backend/app/api/routes/chat/llm.py:2580` |
| Meeting artifacts | Roll up notes/decisions/action items/agendas into shared work memory. | `backend/app/crud.py:520`, `backend/app/services/guardian/memory.py:974` |
| Telegram | Writes user/assistant/tool events. | `backend/app/services/telegram_bridge.py:564`, `backend/app/services/telegram_bridge.py:667`, `backend/app/services/telegram_bridge.py:845` |
| Discord | Writes user/assistant/tool events. | `backend/app/services/discord_bridge.py:373`, `backend/app/services/discord_bridge.py:463`, `backend/app/services/discord_bridge.py:556` |
| WhatsApp | Writes user/assistant/tool events. | `backend/app/services/whatsapp_bridge.py:359`, `backend/app/services/whatsapp_bridge.py:448`, `backend/app/services/whatsapp_bridge.py:541` |
| GitHub bridge | Writes user/assistant/tool events. | `backend/app/services/github_bridge.py:584`, `backend/app/services/github_bridge.py:673`, `backend/app/services/github_bridge.py:759` |
| Task Guardian runs | Writes tool event summaries. | `backend/app/services/guardian/task_guardian.py:808` |

## What Currently Reads From Memory

| Surface | Current read behavior | Evidence |
|---|---|---|
| Main chat | Injects SQL memories plus Guardian memory context. | `backend/app/api/routes/chat/rooms.py:1472`, `backend/app/api/routes/chat/rooms.py:1492` |
| Round Table | Uses same memory context in participant prompts. | `backend/app/api/routes/chat/rooms.py:1819` |
| Meeting heartbeat | Loads SQL memories and Guardian context. | `backend/app/services/guardian/meeting_heartbeat.py:274`, `backend/app/services/guardian/meeting_heartbeat.py:277` |
| Telegram | Loads SQL memories and Guardian context. | `backend/app/services/telegram_bridge.py:583`, `backend/app/services/telegram_bridge.py:591` |
| Discord | Loads SQL memories and Guardian context. | `backend/app/services/discord_bridge.py:393`, `backend/app/services/discord_bridge.py:401` |
| WhatsApp | Loads SQL memories and Guardian context. | `backend/app/services/whatsapp_bridge.py:378`, `backend/app/services/whatsapp_bridge.py:386` |
| GitHub bridge | Loads SQL memories and Guardian context. | `backend/app/services/github_bridge.py:603`, `backend/app/services/github_bridge.py:611` |
| Memory UI/API | Lists, inspects, corrects, restores, deletes memory. | `backend/app/api/routes/chat/memory.py:98`, `backend/app/api/routes/chat/memory.py:112`, `backend/app/api/routes/chat/memory.py:174` |

## Disconnected Or Weak Surfaces

| Surface | Gap | Priority |
|---|---|---|
| Slack bridge | Slack event handler calls LLM directly with only `SYSTEM_PROMPT`; it does not write/read Guardian memory. | `P0` |
| Round Table launch scaffolds | Launch artifacts were saved as real `notes`, causing placeholder decisions/action items to roll into Shared Work Memory. | `P0` |
| Workstation UI actions | Seat changes, panel clicks, desk choices, and local invite configs are local UI state, not source-labeled memory or durable setup events. | `P1` |
| Meeting room UI manifest | Backend heartbeat reads persisted `meeting_manifest` artifacts, but Meeting Room UI still loads seat metadata from localStorage. | `P0` |
| Uploads and Telegram photos | File/photo paths do not consistently write useful source-labeled memory. | `P1` |
| Tasks | REST task CRUD writes to task/spine systems, but not directly to shared memory. | `P1` |
| Reminders | Fired reminders create chat messages and bridge notifications, but do not explicitly write memory. | `P1` |
| Controls/model choices | Stored as config/env, not memory preferences. That is correct for secrets, but non-secret preferences should become source-labeled memory events. | `P1` |
| File handling | Uploads attach to chat but there is no obvious durable memory event for file intent, summary, or user preference. | `P1` |
| UI buttons | Button-triggered actions generally do not record user intent unless they result in chat/tool/task artifacts. | `P2` |

## Meeting Notes And Memory

Meeting notes are stored as `ChatMeetingArtifact` rows. Artifact creation calls `remember_meeting_artifact` unless the artifact is a child artifact (`backend/app/crud.py:520`). Rollups go into Shared Work Memory under `work:user:{user_id}` (`backend/app/services/guardian/memory.py:974`).

This is the right public pattern, but it must avoid noisy spam:

- Save only manager wrap-up/checkpoint notes or manual generated notes.
- Deduplicate repeated rollups by fingerprint (`backend/app/services/guardian/memory.py:1005`).
- Keep raw room transcripts room-scoped.
- Store decisions, next steps, and action items in shared work memory.

## Desired Public MVP Behavior

1. One Sparkbot memory substrate:
   - SQL `UserMemory` for user-visible facts.
   - Guardian ledger for source-labeled events.
   - Shared Work Memory for cross-room/meeting outcomes.

2. Source-labeled memory events:
   - `chat.user`, `chat.assistant`, `tool.<name>`, `meeting.notes.rollup`, `telegram.user`, `discord.user`, `workstation.seat_config`, `task.created`, `reminder.fired`.

3. Meeting wrap-up summaries saved to memory:
   - Seat 1 manager summary becomes a notes artifact and shared work rollup.
   - No artifact after every participant turn.

4. User preferences remembered:
   - Non-secret model preference, tone, default working style, favorite surfaces, timezone, recurring project context.
   - Secrets stay in Vault/config, never memory.

5. Cross-channel continuity:
   - Chat can recall Telegram/Discord/WhatsApp/GitHub context.
   - Bridges can recall main chat and Round Table outcomes.
   - Slack must be upgraded to the same bridge memory pattern.
   - Phil decision: Slack is popular enough to be a public baseline connector and should set the reusable bridge-memory pattern for Sparkbot Public, Arc Bot, and future custom bots.

6. User-visible memory controls later:
   - Inspect, correct, restore, archive, delete.
   - Per-source filtering and "do not remember this" controls.

## P0 Memory Findings

- Slack was disconnected from the shared memory substrate. This pass wires Slack inbound/outbound event memory through the shared connector adapter; outbound Slack tool permissions still need a public UX pass.
- Meeting Room UI now loads backend `meeting_manifest` artifacts before localStorage cache; assignment display UI still needs work.
- Round Table memory is directionally right, but public MVP needs an explicit rule: only manager wrap-ups/checkpoints create shared meeting memory.
- Launch scaffold artifacts must never become shared memory notes.

## Safe Patch Applied In This Phase

Round Table and project-meeting launch scaffolds now save as draft `agenda` artifacts with `memory_rollup: false`, and the artifact creation path skips memory rollups for draft artifacts. The meeting artifact rollup helper also filters placeholder lines such as "None recorded yet" and "To be determined". This prevents scaffold text from becoming Shared Work Memory.

Changed paths:

- `frontend/src/lib/workstationMeeting.ts`
- `backend/app/crud.py`
- `backend/app/services/guardian/memory.py`

## LIMA Runtime Alignment Note

The reusable learning is the shape of the memory contract:

- `source`
- `surface`
- `user_id`
- `room_id`
- `artifact_id`
- `confidence`
- `lifecycle_state`
- `secret_blocked`
- `visibility`

Do not move this to LIMA in this phase. Stabilize it in Sparkbot Public first, then use it as design input for future runtime memory.

## P0 Stabilization Update - 2026-05-17

Branch: `public-release-p0-memory-guardrails-roundtable`

Implemented:

- Added a shared connector memory adapter, `remember_bridge_message`, in `backend/app/services/guardian/memory.py`.
- Slack inbound events now create/use a `Slack Bridge` memory room, write inbound/outbound messages through the shared adapter, and read Guardian memory before calling the LLM.
- Task CRUD now writes source-labeled task memory events through the shared adapter.
- Reminder creation and fired reminder messages now write source-labeled memory events.
- Upload/file and image analysis paths now write source-labeled file memory events.
- Bridge memory can mirror into Shared Work Memory when `SPARKBOT_UNIFIED_CHAT_MEMORY_ENABLED=true`.
- Meaningful connector `system` events are allowed through the adapter without opening generic chat memory to system noise.

Connected or already connected:

| Surface | Status |
|---|---|
| Chat | Connected through Guardian room memory and shared chat memory when enabled. |
| Workstation | Meeting manifests now persist to backend artifacts and reload into Meeting Room UI; ordinary UI clicks remain non-memory. |
| Round Table | Participant turns write room memory; manager wrap-up/checkpoint notes roll up to shared memory. |
| Agents/custom agents | Connected when they speak through chat/Round Table routes. |
| Tasks | Connected through `task.created` and `task.updated` bridge events. |
| Reminders | Connected through `reminder.created` and `reminder.fired` bridge events. |
| Uploads/files/photos | Connected through `file.uploaded` and `file.analysis` bridge events. |
| Telegram/Discord/WhatsApp/GitHub | Already use Guardian memory context in their bridge flows. |
| Slack | Connected in this pass as the public baseline connector pattern. |

Still disconnected or intentionally deferred:

- Workstation seat edits, desk clicks, panel actions, and Invite Wing draft choices are not memory events yet.
- Controls/model preferences persist through config/env, not memory. Non-secret preference memory should be added later without storing credentials.
- Browser/terminal future action memory should be handled through permissioned tool events, not ad hoc UI events.

Regression coverage added:

- Shared bridge memory route, including Slack-style user events and task-style system events.
- Draft/scaffold meeting artifacts do not roll up to memory.
- Manager wrap-up/checkpoint notes can still become shared memory through the existing meeting artifact rollup path.
