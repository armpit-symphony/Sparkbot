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
- Remaining Invite Wing blocker: Specialty Wing can select model-seat model IDs, but arbitrary specialty-agent routing does not yet bind to a seat-specific Vault credential when no global provider auth is configured.
- Public package exclusions/private path cleanup.
- Built-in public agent prompt rewrite.
- Balanced vs Locked policy behavior needs tuning so profiles are more than persisted names.
- Final Round Table assignment cards/phase UI polish.
- Remaining "Controls" naming should converge into AI setup versus Command Center.

## Recommended Next Phase

Run a focused public extraction-blocker phase:

1. Finish Specialty Wing model-seat credential routing for Vault-only seats.
2. Rewrite built-in public agent prompts.
3. Update public package exclusions and private path cleanup.
4. Tune Balanced vs Locked policy differences.
5. Add Meeting Room assignment display and phase/status UI.
6. Finish AI setup versus Command Center naming cleanup.

## Questions For Phil

- Should Balanced become the default for server install while Free / Personal remains the local desktop default?
- Should Slack outbound sends be public beta core or "configured connector" advanced until the profile UI is tuned?
- Should Robo teaser mention LIMA by name or only say "future robotics/runtime integrations"?
- Should the Windows chmod assertions be made platform-aware, or should validation require a POSIX environment for env-permission checks?
