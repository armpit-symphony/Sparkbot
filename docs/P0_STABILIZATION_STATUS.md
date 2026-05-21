# Sparkbot Public P0 Stabilization Status

Date: 2026-05-17
Branch: `public-release-p0-memory-guardrails-roundtable`
Base: `public-release-capability-memory-roundtable` at `ab65c76b13fe7964829258cb34f6eab8eed4f440`

## Completed In This Pass

- Added shared connector memory write path: `remember_bridge_message`.
- Wired Slack as the public baseline connector pattern for memory/context.
- Wired tasks, reminders, uploads/files/photos into the shared memory adapter.
- Added structured Round Table assignment persistence through `meeting_assignments` artifacts.
- Made Meeting Room UI load backend meeting manifests before localStorage.
- Made Round Table heartbeat scheduling best-effort at launch.
- Added persisted Command Center Security profiles: Free / Personal, Balanced, Locked, Custom.
- Removed hidden DM auto-`/breakglass` behavior for elevated confirmation events.
- Added public default Robo teaser guard for backend routes and chat tool catalog.
- Fixed frontend model-provider allowlist drift for `openai_codex` and `claude_sub`.

## Memory Surfaces

Connected:

- Chat
- Round Table participant turns
- Round Table manager wrap-up/checkpoint artifacts
- Agents/custom agents when speaking through chat/Round Table
- Tasks
- Reminders
- Uploads/files/photos
- Telegram
- Discord
- WhatsApp
- GitHub bridge
- Slack

Still disconnected or deferred:

- Workstation seat edits and desk/panel UI clicks
- Invite Wing draft credentials and local-only seat secrets
- Controls/model preferences as user-visible memory events
- Browser/terminal future action summaries beyond existing tool events

## Round Table Status

- Seat 1 manager-led flow remains the target and is explicitly enforced through chair/first participant selection.
- Initial ideas, manager assessment, assignments, second pass, and manager summary remain in the flow.
- Assignments now persist as structured artifact metadata when Seat 1 emits parseable `@handle: job` or `handle - job` lines.
- Persisted assignments are injected into heartbeat continuation prompts.
- Per-turn generated notes remain disabled except manager wrap-up/checkpoint/manual notes.
- UI assignment cards are not built yet.

## Command Center Security Status

- Profile selector is live in Command Center Security.
- Profile persistence is backend-backed through `/api/v1/chat/models/config`.
- Free / Personal mode is capable by default and maps to policy-off personal mode while keeping existing risky-action confirmations.
- Balanced, Locked, and Custom currently share the existing strict policy engine under different persisted profile names.
- Custom guardrails are blocker text today; typed user-owned allow/confirm/block records are not implemented yet.

## Slack Baseline

Slack is now treated as public MVP baseline connector work:

- No private workspace assumptions were added.
- No Slack secrets were added to docs or config.
- Slack inbound events use a durable memory room and shared connector memory route.
- Missing follow-up: bring Slack outbound/send tools fully under the same user-facing profile/permission labels and add public env examples if needed.

## Robo Teaser

Default public behavior is teaser-only:

- `SPARKBOT_ROBO_TEASER_ONLY` defaults to `true`.
- Robotics tool catalog is hidden from the chat LLM in teaser mode.
- Robotics `/tools` returns an empty teaser response.
- Robotics `/command` allows dry-run contracts but blocks live/non-dry-run and real-hardware requests.
- Robotics `/emergency-stop` is blocked in teaser mode.
- UI default now opens a static Robo preview panel. The operational MCP registry panel is available only in dev/private-flag builds.

## Surface UX Update - 2026-05-17

Branch: `public-release-surface-nav-room-ux`

Implemented:

- Workstation header is sticky so top tabs remain available while the workstation scrolls.
- Meeting Room now uses a fixed-height shell with sticky top navigation, a scrollable control sidebar, and an independently scrolling chat pane on desktop.
- Meeting Room top tabs now include Chat, Workstation, Robo, Command Center, and Info.
- `/chat` always redirects to `/dm` and no longer imports the legacy debug `ChatPage`.
- Devtools load only in dev mode.
- Admin and Items template routes redirect to `/dm` outside dev.
- Sidebar nav no longer exposes Dashboard, legacy Chat, Settings, or Admin as public tabs.
- Signup, recovery, settings, admin, and items route titles were renamed from FastAPI Template to Sparkbot.
- Live terminal UI is setup-gated by backend security status instead of looking like an always-on public shell.
- Robo UI defaults to teaser-only copy and does not link to private runtime docs.

## Validation

Passed:

- Python compile check for changed backend modules.
- Focused backend suite: 122 passed.
- Frontend production build: passed.

Known validation caveat:

- `backend/tests/api/routes/test_chat_security_controls.py` still fails two Windows file mode assertions where `.env` chmod reports `0o666` instead of expected `0o600`. The code path was not changed in this pass; keep this as a Windows validation issue unless Phil wants the tests made platform-aware.

## Invite Wing Model Seat Update - 2026-05-17

Branch: `public-release-invite-wing-model-seats`

Completed in this pass:

- Added backend-owned Invite Wing model-seat config with Codex/OpenAI, Claude/Anthropic, and Grok/xAI defaults.
- Moved Invite Wing submitted credentials to Guardian Vault and removed browser `localStorage` credential persistence.
- Changed Round Table invite seats to pass `modelSeatId` instead of frontend-held secrets.
- Added a small Command Center edit path for custom Specialty Wing agents.
- Added targeted backend tests for model-seat Vault storage and backend-side invite route secret resolution.

Validation in this pass:

- `git diff --check`: passed.
- `python -m py_compile backend/app/api/routes/chat/model.py`: passed.
- `npm --prefix frontend run build`: passed.
- `.\\.venv-ci\\Scripts\\uv.exe run pytest -q backend\\tests\\api\\routes\\test_chat_models_openrouter.py -k "model_seat or invite_route"`: 2 passed.

## Remaining P0 Blockers

- Invite Wing credential storage moved to backend/Vault-backed storage for Round Table model seats.
- Specialty Wing model-seat Vault binding is now implemented for agent overrides that carry `model_seat_id`; setup-needed UI and the Command Center seat editor have a first public implementation.
- Legacy DM Controls now preserves `model_seat_id` in the same way as Command Center and Workstation controls.
- Explicit model-seat routing now reports setup-needed instead of falling back to a global provider key when the selected seat's Vault credential is missing.
- Pending approval Spine payloads now recursively redact nested secret-like keys before public-safe approval events are emitted.
- Public package exclusions/private path cleanup.
- Built-in public agent prompt rewrite.
- Balanced vs Locked policy behavior needs tuning so profiles are more than persisted names.
- Final Round Table assignment cards/phase UI polish has a first public implementation; browser QA and small visual refinements remain.
- Remaining "Controls" naming should converge into AI setup versus Command Center.

## Unified Context Spine Update - 2026-05-17

Branch: `public-release-unified-context-spine`

Completed in this pass:

- Added the public `remember_context_event(...)` and `build_unified_context(...)` adapters over Guardian memory.
- Added bounded structured recall metadata for source/surface, actor, thread, meeting, model-seat, agent, rollup, sensitivity, risk, and tags.
- Slack, Telegram, Discord, WhatsApp, and GitHub bridge handlers now read unified context and write source-labeled user/assistant context events.
- Added shared model-seat helper logic and preserved `model_seat_id` in Specialty Wing/Command Center agent overrides.
- Backend route context now resolves model-seat Vault credentials server-side for Specialty Wing agents.
- Added regression coverage for unified context source labels, draft/scaffold rollup skipping, manager checkpoint rollups, model-seat override persistence, and backend-side credential resolution.

Validation in this pass:

- Targeted validation is recorded in the final report for `public-release-unified-context-spine`.

Remaining after this pass:

- Public package exclusions/private path cleanup.
- Built-in public agent prompt rewrite.
- Balanced vs Locked behavior separation.
- Final Round Table assignment UI polish.
- Sparkbot_shell extraction map refresh.

## Package And Prompt Cleanup Update - 2026-05-17

Branch: `public-release-package-prompt-cleanup`

Completed in this pass:

- Expanded public package pruning for readiness/status/audit docs, private runtime research docs, historical release-note docs, proposal scripts, dotenv files, logs, local databases, key/certificate files, virtualenvs, build output, and cache directories.
- Added `.venv-ci/` and `backend/.venv-ci/` to `.gitignore`; public packages now prune `.venv-ci` even though tracked CI virtualenv files remain a separate repo hygiene cleanup.
- Rewrote backend built-in public agent prompts to remove SparkPit Labs, TheSparkPit, LIMA AI, and Guardian services assumptions.
- Reframed README and capabilities docs around **Robo Preview** as teaser-only public core.
- Replaced private host-inspection paths/examples with generic host log roots and local service health wording.
- Removed the OpenClaw config fallback from web search key loading; public Sparkbot uses `BRAVE_SEARCH_API_KEY` or explicit `SPARKBOT_SEARCH_CONFIG_PATH`.

Remaining after this pass:

- Remove tracked `.venv-ci` files from Git in a dedicated cleanup if Phil approves.
- Replace Robo/LIMA backend bridge source with a public stub before Sparkbot_shell extraction.
- Tune Balanced vs Locked behavior separation.
- Add final Round Table assignment display/phase UI polish.
- Refresh the Sparkbot_shell extraction map.

## Local AI Integration Update - 2026-05-17

Branch: `public-release-local-ai-integration`

Completed in this pass:

- Added a public local provider abstraction for Ollama, LM Studio, llama.cpp / llama-server, generic OpenAI-compatible endpoints, and custom local endpoints.
- Added a backend local AI status/config helper and route without introducing new dependencies or probing unconfigured local endpoints by default.
- Kept Ollama first-class and fixed AI Setup so editable Ollama base URLs save through the existing config route.
- Added a default `invite-local` model seat with no-key local auth, editable runtime/base URL/model id metadata, and Round Table plus Specialty Wing visibility.
- Routed `local/<model-id>` chat completions through the existing LiteLLM/OpenAI-compatible path with backend-owned base URL and optional backend-only API key.
- Updated Invite Wing, Specialty Wing, Round Table invite route setup, and Command Center AI Setup to recognize local model seats without storing secrets in browser storage.
- Added targeted tests for local config persistence, no-secret model seats, backend route setup, and local completion routing.

Remaining after this pass:

- Add a full Command Center model-seat editor for local and cloud seats.
- Add visible setup-needed badges where a selected local endpoint is unreachable or unconfigured.
- Browser-test local setup against live Ollama and a live OpenAI-compatible local server.
- Keep embedded/local runtime runner work out of public MVP until the external endpoint path is stable.

## Round Table Model-Seat UI Update - 2026-05-18

Branch: `public-release-roundtable-modelseat-ui-polish`

Completed in this pass:

- Workstation now defaults Round Table seat 1 to the `meetings_manager` Specialty Wing office when available, including empty room drafts, stack autofill, task meetings, and post-launch resets.
- Workstation chair picker now exposes a per-agent seat model selector and setup-needed guidance for Invite Wing/model-seat chairs.
- Meeting Room seated participant controls now show manager/Seat 1, allow agent changes, allow per-seat model changes, and preserve non-secret model-seat metadata.
- Meeting Room now displays current meeting phase and latest structured assignment cards from `meeting_assignments` artifacts.
- Command Center AI Setup now includes a model-seat editor for create/edit, provider/company, local runtime/base URL, model id, auth mode, enabled state, Round Table/Specialty Wing visibility, notes, and write-only credential entry.
- Backend model-seat payloads now include `setup_status` and `setup_message`; local seats report unreachable/setup-needed instead of silently failing, and Vault-backed seats no longer appear configured just because a global provider key exists.

Validation in this pass:

- `npm --prefix frontend run build`: passed.
- `.\\.venv-ci\\Scripts\\uv.exe run pytest -q backend\\tests\\api\\routes\\test_chat_models_openrouter.py -k "model_seat or local_model_seat or invite_route"`: 9 passed.

Remaining after this pass:

- Browser QA for the Command Center model-seat editor, Workstation chair picker, Meeting Room model selector, live Ollama, and at least one OpenAI-compatible local endpoint.
- Add uniqueness-safe selection if multiple model seats intentionally share the same model id.
- Run the approved artifact/.venv/Robo/guardrail cleanup branch.
- Tune deeper Balanced vs Locked policy behavior if not handled in that branch.
- Refresh the Sparkbot_shell extraction map.

## Recommended Next Phase

Run a focused public extraction-blocker phase:

1. Run the artifact/.venv/Robo/guardrail cleanup branch that Phil approved.
2. Browser QA Round Table model-seat selection and Local AI setup against live endpoints.

## Artifact / Guardrail / Robo Cleanup Update - 2026-05-18

Branch: `public-release-artifact-guardrail-robo-cleanup`

Completed in this pass:

- Tracked `.venv-ci/` and `backend/.venv-ci/` files were removed from Git; ignore rules remain so local CI virtualenvs stay untracked.
- Public packaging now has a Windows-safe `.zip` fallback through Python stdlib `zipfile` when the `zip` binary is missing.
- Robo default behavior is now a true public preview boundary: public/default calls return non-executing preview contracts, `/tools` returns no live Robo tools, and emergency stop/live control are blocked.
- Private Robo bridge execution now requires `SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED=true` in addition to any teaser-mode override.
- Backend MCP registry now exposes `robo_preview.*` manifests in public mode rather than LIMA-labelled motion/control manifests.
- Balanced and Locked profile behavior now differs in the policy engine: Balanced confirms high-risk configured actions; Locked requires elevated approval or break-glass for high-risk actions.
- Model-seat selectors now use stable `seat:<modelSeatId>` values where seats are selectable, avoiding ambiguity when multiple seats share the same model id.

Remaining after this pass:

- Browser QA the public package artifact, Command Center Security profiles, Robo Preview panel, and duplicate-seat selector behavior.
- Build typed Custom guardrail records later; current Custom mode is honest blocker-text enforcement.
- Refresh the Sparkbot_shell extraction map after validation.
3. Refresh the Sparkbot_shell extraction map after cleanup passes.
4. Start the first shell import layer only after package exclusions, Robo stubbing, and extraction map refresh are complete.

## Questions For Phil

- Should Balanced become the default for server install while Free / Personal remains the local desktop default?
- Should Slack outbound sends be public beta core or "configured connector" advanced until the profile UI is tuned?
- Should Robo teaser mention LIMA by name or only say "future robotics/runtime integrations"?
- Should the Windows chmod assertions be made platform-aware, or should validation require a POSIX environment for env-permission checks?

## Task Guardian Health Check Update - 2026-05-17

Branch: `public-release-task-guardian-health-checks`

Completed in this pass:

- Added built-in PC Health Check and Server Health Check Task Guardian templates.
- Added `daily-local:<HH:MM>` scheduling so the default health report can run at 6:00 AM in the host's local timezone.
- Added a read-only health collector for uptime, CPU/load, memory, swap, disk, battery where available, Sparkbot process/task status, local AI status, connector status, and manual update posture.
- Added a plain-text Sparkbot Health Report renderer with SEV-1/SEV-2/SEV-3 sections, passed checks, and recommended actions.
- Wired health task summaries into shared memory with `task_guardian.health.pc` and `task_guardian.health.server` source labels.
- Added Command Center Task Guardian template cards so owners can add disabled PC/server health jobs, inspect JSON, and choose delivery later.
- Kept external delivery opt-in: app/task history by default, with Telegram, Discord, and Slack only when configured by the owner.

Remaining after this pass:

- Browser QA the simple delivery-channel picker for Telegram/Discord/Slack.
- Browser QA the Task Guardian template cards and latest-report display.
- Decide whether the first-run flow should offer PC Health Check on desktop and Server Health Check on server installs.
- Add multi-worker scheduler leadership/locking before recommending high-frequency jobs in public beta.

## Final Cleanup Assessment Update - 2026-05-18

Branch: `public-release-final-cleanup-assessment`

Completed in this pass:

- Integrated the approved artifact/Robo/guardrail cleanup after the Task Guardian health-check branch.
- Removed tracked `.venv-ci/` and `backend/.venv-ci/` files from Git while keeping ignore rules in place.
- Kept the Windows-safe public package `.zip` fallback through Python stdlib `zipfile`.
- Kept Robo Preview as the public/default backend behavior and kept private bridge execution behind `SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED=true`.
- Public package generation replaces the private R&D Robo bridge implementation with a non-executing Robo Preview stub.
- Public MCP registry runtime/status labels now use Robo Preview wording instead of LIMA runtime labels.
- Updated Command Center security status to report the private Robo bridge flag instead of a stale robotics env name.
- Kept Balanced and Locked behavior distinct in backend policy: Balanced confirms high-risk configured actions; Locked requires elevated approval or break-glass.
- Added a non-JSON health-report delivery picker for app, Telegram, Discord, and Slack in Command Center Task Guardian.
- Changed public Docker/server worker defaults to `BACKEND_WORKERS=1` until recurring jobs have scheduler leadership/locking.
- Added `docs/PUBLIC_RELEASE_ASSESSMENT_SNAPSHOT.md` as the stopping-point readiness snapshot.

Remaining after this pass:

- Browser QA the public surfaces before starting `Sparkbot_shell` extraction.
- Live QA Ollama/local OpenAI-compatible endpoints and connector health delivery.
- Package QA on Windows/Git Bash and Linux clean clones.
- Refresh the `Sparkbot_shell` extraction map after QA, then decide whether Layer 1 import can start.

## QA Assessment Update - 2026-05-20

Branch: `public-release-qa-assessment`
Base commit: `0f8d059fc5927e3466d269ca5479df4c56b3c06f`

Completed in this pass:

- Created browser QA checklist: `docs/PUBLIC_RELEASE_BROWSER_QA_CHECKLIST.md`.
- Created live QA plan: `docs/PUBLIC_RELEASE_LIVE_QA_PLAN.md`.
- Created readiness scorecard: `docs/PUBLIC_RELEASE_READINESS_SCORECARD.md`.
- Created next decision matrix: `docs/PUBLIC_RELEASE_NEXT_DECISION_MATRIX.md`.
- Verified `.venv-ci` and `backend/.venv-ci` are no longer tracked.
- Verified public package generation replaces the private Robo bridge source with the Robo Preview stub.
- Fixed `scripts/package-public-download.sh` so relative `--output-dir` and `--publish-dir` paths resolve from the repo root before the script changes into its temporary stage directory.

Automated validation:

| Check | Result |
|---|---|
| `git diff --check` | Passed before docs/script edits; rerun before commit. |
| `git diff --cached --check` | Passed before docs/script edits; rerun before commit. |
| `bash -n scripts/package-public-download.sh` | Passed. |
| Frontend build | Passed. |
| Python compile for relevant backend modules | Passed. |
| Focused backend tests | Passed: 130 passed, 144 warnings. |
| Package dry-run | Passed after relative-path fix. |
| Package inspection | Robo Preview stub and key exclusions verified; tests/workflows still need package-boundary decision. |

Remaining P0 before extraction after source-boundary cleanup:

- Run package artifact inspection on the generated release candidate tar/zip and keep Windows/Git Bash plus clean-clone package smoke in the release checklist.
- Run browser/live QA for Round Table, Local AI, Command Center Security profiles, Task Guardian health checks, connector delivery, terminal gating, and Robo Preview.
- Refresh the `Sparkbot_shell` extraction map from the validated sanitized artifact before any shell import.

Recommended next phase:

Run a focused package/source-boundary cleanup pass, then browser/live QA, then `Sparkbot_shell` extraction map refresh.

## Source Boundary Cleanup Update - 2026-05-21

Branch: `public-release-source-boundary-cleanup`
Base: `public-release-qa-assessment` at `45b12b5c07a4b4069fc7ed01ab4cf8e2ff53f2fa`

This pass addresses the QA-assessment RED blocker without deleting tests/workflows from the R&D repo and without modifying `Sparkbot_shell`.

Completed in this pass:

- Public Docker/source install docs now recommend sanitized release bundles from the download page or GitHub Releases, not a raw clone of the active R&D repo.
- `scripts/package-public-download.sh` removes `.github`, `.agents`, backend/frontend tests, Playwright config, and test runner scripts from staged public bundles.
- Root `.dockerignore` was added for repo-root Compose contexts so local env/example files, DBs, logs, keys/certs, caches, package outputs, tests, CI metadata, and private docs are not sent into Docker build contexts.
- `docs/public-downloads.md` now includes explicit artifact inspection commands for package exclusions, Robo Preview stub verification, and checksums.

Assessment movement:

- Packaging/downloads: RED -> YELLOW pending final artifact inspection on release candidates and Windows/Git Bash / clean-clone packaging smoke.
- Public/private separation: RED -> YELLOW because sanitized bundles now exclude tests/workflows/internal agent instructions, but raw R&D source still is not the approved public install or extraction target.

Recommended next phase remains browser/live QA, then `Sparkbot_shell` extraction map refresh from the validated sanitized artifact.
