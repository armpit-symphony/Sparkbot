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
- Added memory quality controls: exact duplicate rollups are skipped by fingerprint, and generated child artifacts with `parent_notes_id` do not re-promote decisions/actions already captured in the parent notes artifact.
- Made `/chat/model` persist `SPARKBOT_MODEL`, `SPARKBOT_DEFAULT_PROVIDER`, and provider-specific local/OpenRouter defaults through the same `.env` writer Controls uses.
- Hardened packaged/local first-run selector persistence by creating the `SPARKBOT_DATA_DIR` parent before writing `.env`.
- Added non-secret route metadata to meeting `agent_start` SSE events and displayed the resolved model label next to the speaking agent.
- Changed Memory Guardian default data-dir selection to use `SPARKBOT_DATA_DIR/memory_guardian` when present.

### Intended memory rules

- Global assistant memory: explicit durable facts about the operator/user, stored in the user memory session and surfaced as `Durable Memory`.
- Room/meeting memory: normal chat transcript/tool context stays scoped to the current room and is surfaced as `Relevant Room Memory`.
- Meeting-to-main rollup: important meeting artifacts promote only summaries, key decisions, action items, open questions, and next steps into `Shared Work Memory`.
- Project/task memory: Guardian Spine remains canonical for tasks, project lineage, handoffs, and artifact events.
- Session-only context: transient chat history stays in the active prompt/history and should not be promoted unless it becomes an artifact, task, or explicit durable fact.
- Duplicate/conflict handling: durable user facts still use existing memory lifecycle/deprecation rules; repeated meeting rollups are suppressed when the extracted content fingerprint matches an existing active shared-work event; non-identical meeting conflicts remain artifact-provenance work signals and should be reconciled through Guardian Spine/project state.

### Intended model-routing rules

- The user-selected primary/default model is `SPARKBOT_MODEL`, persisted through Controls or `/chat/model`.
- Agent or meeting-specific overrides live in `SPARKBOT_AGENT_MODEL_OVERRIDES_JSON`.
- A locked per-agent route does not cross providers; default routes honor `SPARKBOT_DEFAULT_CROSS_PROVIDER_FALLBACK`.
- If a locked provider/model is unavailable, Sparkbot returns a direct setup error instead of silently switching provider.
- Meeting handoffs expose the resolved model label and route metadata so model changes are visible.
- Local/Windows mode uses the same persisted `.env` route state, with `SPARKBOT_DATA_DIR` anchoring packaged memory storage.

### Release validation results

- Running Linux service health: `GET /api/v1/utils/health-check/` returned `true`; Docker shows `sparkbot-backend-1` healthy on `127.0.0.1:8000`, frontend on `3001`, and Postgres healthy. Recent backend logs show normal health-check traffic without new tracebacks.
- Main chat -> meeting -> main chat continuity: isolated runtime validation wrote a main-room message, promoted a Release Roundtable notes artifact, then queried main chat context. Result: `main_chat_shared_memory=True`.
- Shared Work Memory quality: duplicate validation promoted the first rollup and skipped the second exact duplicate. Result: `meeting_rollup_first=True`, `meeting_rollup_duplicate_skipped=True`, `shared_work_event_count=1`.
- Structured memory recall: `memory_recall` now includes the shared work session. Result: `structured_recall_shared_work=True`.
- Model selector restart persistence: isolated runtime validation selected `ollama/phi4-mini`, cleared process memory/env to simulate restart, reloaded persisted `.env`, and confirmed both runtime and Controls state matched. Results: `selector_after_restart=ollama/phi4-mini`, `controls_default_selection=ollama/phi4-mini`.
- Windows/local packaged path: with only `SPARKBOT_DATA_DIR` set, Memory Guardian defaulted to `<SPARKBOT_DATA_DIR>/memory_guardian`; first-run `.env` writes now create the missing data-dir parent.
- Multi-agent meeting route labeling: route display validation returned `ollama/phi4-mini`, provider `ollama`, route `local` for an agent override, without exposing secrets.
- Guardian Spine continuity: creating a meeting action artifact still produced one Spine task for the meeting room.
- Focused tests: `uv run pytest -q backend/tests/services/test_guardian_memory.py backend/tests/api/routes/test_chat_models_openrouter.py backend/tests/services/test_guardian_spine.py` passed `61` tests.

### Live Linux deployment results

- Rebuilt the live local Compose stack with `docker compose -f compose.local.yml build backend frontend prestart`.
- Ran rebuilt prestart successfully: `sparkbot-prestart-1` exited `0`.
- Recreated backend and frontend with `docker compose -f compose.local.yml up -d --no-deps --force-recreate backend frontend`.
- Deployed backend package confirmed live: `docker exec sparkbot-backend-1 python -c "import importlib.metadata; print(importlib.metadata.version('app'))"` returned `1.6.59`.
- Recreated image IDs/start times: backend `sha256:aedcac7ddf439808e015379f6d41ed3271209d4babb9abb99b33e60e6e43a521` started `2026-05-04T15:54:10Z`; frontend `sha256:88c5561b7a16d86b8f783dd4314b24c89945a612dc0626930fdb47ced3ab0b0f` started `2026-05-04T15:54:10Z`.
- Live health after redeploy: backend healthy, Postgres healthy, `curl -s http://127.0.0.1:8000/api/v1/utils/health-check/` returned `true`, and `curl -s http://127.0.0.1:3001/` returned the frontend HTML shell.
- Backend logs after redeploy show normal startup, two worker startups, Guardian Vault DB initialization at `/app/backend/data/guardian/vault.db`, reminder scheduler startup, and health-check traffic. No new deployment traceback was observed.
- Live smoke inside the redeployed backend container returned:
  - `deployed_package_version=1.6.59`
  - `main_chat_meeting_continuity=True`
  - `shared_work_retrieval=True`
  - `shared_work_duplicate_control=True`
  - `desktop_memory_default=/tmp/sparkbot-live-smoke-pjqaq15q/desktop_data/memory_guardian`
  - `selector_persisted=True ollama/phi4-mini restart=ollama/phi4-mini controls=ollama/phi4-mini`
  - `meeting_model_label=Phi-4 Mini — best default quality/speed balance (~2.5 GB) provider=ollama route=local`
  - `spine_task_continuity=True task_count=1 artifact=40acda63-c9f9-4c70-bf26-4803bad21af2`

### Remaining before public release

- Run a full Windows packaged installer smoke test against the v1.6.59 artifacts.
- Verify an end-to-end roundtable in the installed Windows app: generate notes, return to main chat, ask about a decision/action item, and confirm shared work memory appears.
- Consider a future cleanup for persisted per-user model preferences if Sparkbot needs multi-user primary-model ownership rather than one operator/default route.
