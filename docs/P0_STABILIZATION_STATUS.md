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
- UI copy still needs a public teaser pass before extraction.

## Validation

Passed:

- Python compile check for changed backend modules.
- Focused backend suite: 122 passed.
- Frontend production build: passed.

Known validation caveat:

- `backend/tests/api/routes/test_chat_security_controls.py` still fails two Windows file mode assertions where `.env` chmod reports `0o666` instead of expected `0o600`. The code path was not changed in this pass; keep this as a Windows validation issue unless Phil wants the tests made platform-aware.

## Remaining P0 Blockers

- Public `/chat` route/template/debug cleanup.
- Invite Wing credential storage needs backend/Vault-backed storage instead of browser storage.
- Devtools/template Admin/Items public navigation cleanup.
- Terminal desks need explicit public default gating/copy.
- Robo UI copy still needs teaser-only pass even though backend/tool execution is guarded.
- Public package exclusions/private path cleanup.
- Built-in public agent prompt rewrite.
- Balanced vs Locked policy behavior needs tuning so profiles are more than persisted names.

## Recommended Next Phase

Run a focused public surface cleanup phase:

1. Remove/debug-gate public `/chat`, template Admin/Items, and devtools surfaces.
2. Move Invite Wing credentials out of localStorage.
3. Add Meeting Room assignment display and phase/status UI.
4. Tune Balanced vs Locked policy differences.
5. Public-teaser copy pass for Robo and terminal/live tools.
6. Update public package exclusions and install docs.

## Questions For Phil

- Should Balanced become the default for server install while Free / Personal remains the local desktop default?
- Should Slack outbound sends be public beta core or "configured connector" advanced until the profile UI is tuned?
- Should Robo teaser mention LIMA by name or only say "future robotics/runtime integrations"?
- Should the Windows chmod assertions be made platform-aware, or should validation require a POSIX environment for env-permission checks?
