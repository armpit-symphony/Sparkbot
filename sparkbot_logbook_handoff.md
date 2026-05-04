# Sparkbot Logbook Handoff

## v1.6.59 Release Stabilization

### What was wrong

- Main chat and roundtable/meeting rooms used the same Guardian Memory service, but retrieval was effectively split between durable user facts and the current room session. Meeting artifacts were stored as `ChatMeetingArtifact` rows and mirrored into Guardian Spine, but they were not promoted into a shared memory surface that main chat reliably queried.
- `/chat/model` updated only the backend process-local `_user_models` map. Controls updated persisted `.env` route state. That created selector drift after restarts and made desktop/local mode feel different from server mode.
- Meeting agent handoffs emitted only agent labels. The backend routing layer knew the resolved route/model, but the meeting UI did not show it at the point where speakers changed.
- Memory Guardian defaulted to a source-checkout `backend/app/data/memory_guardian` path unless `SPARKBOT_MEMORY_GUARDIAN_DATA_DIR` was set. Packaged Windows/local launches already set `SPARKBOT_DATA_DIR`, but memory did not use it by default.

### What changed

- Added a shared Guardian work-memory session keyed by user. `build_memory_context` now retrieves durable user memory, shared work memory, and the current room memory.
- Added `remember_meeting_artifact`, which rolls `notes`, `action_items`, `decisions`, and `agenda` artifacts into shared work memory using only decision/action/next-step/open-question/summary lines.
- Wired artifact creation through the rollup path, so generated and manually saved meeting artifacts can inform main chat without exposing full room transcript memory globally.
- Made `/chat/model` persist `SPARKBOT_MODEL`, `SPARKBOT_DEFAULT_PROVIDER`, and provider-specific local/OpenRouter defaults through the same `.env` writer Controls uses.
- Added non-secret route metadata to meeting `agent_start` SSE events and displayed the resolved model label next to the speaking agent.
- Changed Memory Guardian default data-dir selection to use `SPARKBOT_DATA_DIR/memory_guardian` when present.

### Intended memory rules

- Global assistant memory: explicit durable facts about the operator/user, stored in the user memory session and surfaced as `Durable Memory`.
- Room/meeting memory: normal chat transcript/tool context stays scoped to the current room and is surfaced as `Relevant Room Memory`.
- Meeting-to-main rollup: important meeting artifacts promote only summaries, key decisions, action items, open questions, and next steps into `Shared Work Memory`.
- Project/task memory: Guardian Spine remains canonical for tasks, project lineage, handoffs, and artifact events.
- Session-only context: transient chat history stays in the active prompt/history and should not be promoted unless it becomes an artifact, task, or explicit durable fact.
- Duplicate/conflict handling: durable user facts still use existing memory lifecycle/deprecation rules; meeting rollups are append-only work signals with artifact provenance.

### Intended model-routing rules

- The user-selected primary/default model is `SPARKBOT_MODEL`, persisted through Controls or `/chat/model`.
- Agent or meeting-specific overrides live in `SPARKBOT_AGENT_MODEL_OVERRIDES_JSON`.
- A locked per-agent route does not cross providers; default routes honor `SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK`.
- If a locked provider/model is unavailable, Sparkbot returns a direct setup error instead of silently switching provider.
- Meeting handoffs expose the resolved model label and route metadata so model changes are visible.
- Local/Windows mode uses the same persisted `.env` route state, with `SPARKBOT_DATA_DIR` anchoring packaged memory storage.

### Remaining before public release

- Run a full Windows packaged installer smoke test against the v1.6.59 artifacts.
- Verify an end-to-end roundtable in the installed app: generate notes, return to main chat, ask about a decision/action item, and confirm shared work memory appears.
- Consider a future cleanup for persisted per-user model preferences if Sparkbot needs multi-user primary-model ownership rather than one operator/default route.
