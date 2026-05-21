# Sparkbot Public Release Assessment Snapshot

Date: 2026-05-18
Branch: `public-release-final-cleanup-assessment`

This is the stopping-point snapshot before deciding whether to refresh the
`Sparkbot_shell` extraction map, run one more browser QA pass, or start a Layer
1 shell import.

## What Is Now Strong

- Workstation shell: the public-facing shell now has persistent navigation,
  cleaner surface labels, model-seat setup, and local AI setup.
- Round Table meetings: Seat 1 defaults to Meeting Manager, per-seat model
  selection is available, assignments persist as structured artifacts, and
  per-turn generated meeting notes remain disabled.
- Model seats: Invite Wing keeps Codex/OpenAI, Claude/Anthropic, Grok/xAI, and
  Local AI defaults, with backend/Vault-owned credential storage.
- Specialty Wing/custom agents: custom agents can be edited and can reference
  model seats without storing secrets in frontend state.
- Local AI: Ollama, LM Studio, llama.cpp / llama-server, OpenAI-compatible local
  endpoints, and custom local endpoints are represented as first-class local
  provider paths.
- Unified context/memory: major chat, meeting, connector, task, model-seat, and
  agent paths can write source-labeled context through the shared adapter.
- Command Center: model-seat editing, security profiles, custom blocker text,
  Task Guardian templates, and health-check visibility are now in one operator
  surface.
- Task Guardian health checks: PC and Server Health Check templates are built in,
  read-only, scheduled by default for daily 6:00 AM local time, and app-only
  unless the owner opts into connector delivery. Command Center now exposes a
  simple delivery picker for app, Telegram, Discord, and Slack.
- Public package hygiene: tracked `.venv-ci` files are removed, public packages
  prune private/audit/junk artifacts, and Windows/Git Bash packaging has a
  Python stdlib `.zip` fallback when `zip` is missing.
- Robo boundary: public/default Robo behavior is non-executing Robo Preview;
  private bridge execution requires an explicit private env gate, public package
  generation replaces private bridge source with a preview stub, and public
  registry labels use Robo Preview terms.

## What Remains Before Sparkbot Shell Extraction

P0 before extraction map refresh:

- Browser QA on `/login`, `/dm`, `/workstation`, `/meeting/:roomId`,
  Command Center AI Setup, Command Center Security, Task Guardian, and Robo
  Preview.
- Live local AI QA against Ollama and at least one OpenAI-compatible local
  endpoint such as LM Studio or llama.cpp / llama-server.
- Telegram, Discord, and Slack notification QA for health-check report delivery.
- Public package dry-run QA on Windows/Git Bash, Linux, and a clean clone.
- Guardrail/security QA for Personal, Balanced, Locked, and Custom blocker text
  using real terminal/browser/file/send examples.
- Scheduler leadership remains a later platform task. Public Docker/server
  defaults use `BACKEND_WORKERS=1` until recurring jobs have a leader lock or
  singleton scheduler.
- Sparkbot_shell extraction map refresh after QA so Layer 1 imports only the
  clean app frame and public-safe contracts.

P1 polish after the assessment:

- Replace remaining raw JSON task/reminder creation with a public task form.
- Add a proper approval modal for normal confirmation, elevated confirmation,
  and break-glass/privileged access.
- Browser-polish Round Table assignment cards, participant queue/status, and
  long-meeting scrolling at multiple viewport sizes.
- Decide first-run health-check offer copy for desktop versus server installs.
- Add typed Custom guardrail records later; current Custom mode is honest
  blocker-text enforcement only.

## Browser QA List

- Login/passphrase and local auto-login paths.
- AI Setup with OpenAI/Codex, Claude, Grok, and Local AI seats.
- Workstation model selection and Round Table launch.
- Meeting Room Seat 1 manager default, per-seat model changes, assignments,
  manager wrap-up/checkpoint memory, and no per-turn notes.
- Specialty Wing custom agent edit and model-seat binding.
- Command Center Security profile persistence and copy.
- Task Guardian PC/server health template add/edit/run/latest report.
- Robo Preview, confirming no live robotics controls appear in public/default
  mode.

## Packaging QA List

- `bash scripts/package-public-download.sh` from a clean checkout.
- Same packaging path on Windows/Git Bash with `zip` missing, exercising the
  Python `zipfile` fallback.
- Inspect generated `.tar.gz`, `.zip`, `RELEASE-NOTES.txt`, and `SHA256SUMS`.
- Confirm excluded artifacts stay out: `.venv-ci`, `backend/.venv-ci`, dotenv
  files, proposal scripts, private docs, caches, logs, local databases, keys,
  and desktop/private runtime build junk.
- Confirm `backend/app/services/lima_robotics_bridge.py` in the generated
  package is the public Robo Preview stub, not the private R&D bridge source.

## What Must Stay Private

- LIMA AI OS internals.
- Arc Bot proprietary worker shell/runtime behavior.
- LIMA Office and LIMA IT logic.
- Proprietary Guardian Suite internals beyond public-safe permission concepts.
- Real robotics/IoT control, robot/drone/humanoid adapters, and live Robo/LIMA
  bridge behavior.
- Private server paths, secrets, internal R&D notes, client-specific
  automation, paid-service orchestration, and private deployment runbooks.

## Shell Readiness Assessment

Sparkbot is much closer to a public shell source than it was at the start of
the readiness work. The product heart is now visible: one Sparkbot brain, one
context spine, many surfaces, many models, many agents, and a Round Table hero
flow.

The code is not ready for blind extraction yet. It is ready for a deliberate
extraction-map refresh after validation and browser QA, with `Sparkbot_shell`
Layer 1 limited to the clean app frame, public navigation, public setup docs,
and public-safe contracts. Local AI, model seats, Round Table, and context spine
should import only after their browser QA and package QA are reviewed.

## Recommended Decision

Stop after this branch lands and assess:

1. Run the browser/package/security QA list above.
2. Refresh the `Sparkbot_shell` extraction map from the validated branch.
3. Start Layer 1 shell import only if QA finds no new public-blocking defects.

## QA Assessment Update - 2026-05-20

Branch: `public-release-qa-assessment`
Base commit: `0f8d059fc5927e3466d269ca5479df4c56b3c06f`

Validation completed in this pass:

| Check | Result | Notes |
|---|---|---|
| `git status --short --branch` | Passed | Branch was created from `public-release-final-cleanup-assessment`; worktree started clean. |
| `.venv-ci` tracked-file check | Passed | `git ls-files .venv-ci backend/.venv-ci` returned no tracked files. |
| Package script Python zip fallback | Passed | `scripts/package-public-download.sh` uses Python stdlib `zipfile` when `zip` is unavailable. |
| Robo public package stub | Passed | Generated tarball contains a non-executing `lima_robotics_bridge.py` Robo Preview stub. |
| `Sparkbot_shell` untouched | Passed | No local `Sparkbot_shell` checkout was present; no shell extraction or code copy occurred. |
| `git diff --check` / `git diff --cached --check` | Passed before edits | Re-run required before commit. |
| `bash -n scripts/package-public-download.sh` | Passed | Script syntax valid after relative output path fix. |
| Frontend production build | Passed | `npm --prefix frontend run build`; Vite emitted existing large chunk warnings only. |
| Backend compile | Passed | `uv run python -m py_compile` over model seats, local AI, memory/context, meeting assignments, health checks, Robo, MCP, policy, model, rooms, robotics, and security modules. |
| Focused backend tests | Passed | 130 passed, 144 warnings. Covered model seats, Local AI, memory/context, meeting assignments, Task Guardian health checks, Robo Preview/private gate, MCP registry, and security profiles. |
| Package dry-run | Passed after tiny fix | Absolute output path passed first. Relative output path initially failed during zip creation, then passed after normalizing relative `--output-dir`/`--publish-dir` to repo-root paths. |
| Package inspection | Passed with caveats | Verified exclusions for `.venv-ci`, `backend/.venv-ci`, dotenv files, logs, DBs, key/cert examples, proposal script sample, private readiness docs, audit docs, and LIMA integration doc. Verified Robo Preview stub. |

New QA docs created:

- `docs/PUBLIC_RELEASE_BROWSER_QA_CHECKLIST.md`
- `docs/PUBLIC_RELEASE_LIVE_QA_PLAN.md`
- `docs/PUBLIC_RELEASE_READINESS_SCORECARD.md`
- `docs/PUBLIC_RELEASE_NEXT_DECISION_MATRIX.md`

Key assessment change:

- Sparkbot is not ready for `Sparkbot_shell` extraction yet. The product surfaces are mostly implementation-ready. At QA-assessment time, the P0 package/source-boundary issues were raw R&D repo install copy, tests/workflows in public bundles, and missing repo-root `.dockerignore`; these are addressed by the 2026-05-21 Source Boundary Cleanup update below, pending final artifact inspection.

Recommended next phase:

1. Focused public package/source-boundary sanitation: public install source copy, tests/workflow package exclusions or sanitization, and root Docker context hygiene.
2. Browser/live QA using the new checklist and plan.
3. Refresh `Sparkbot_shell` extraction map from the validated public artifact.

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

## Task Guardian Operator Delivery Update - 2026-05-21

Branch: `public-release-task-delivery-operator-channels`

Completed in this pass:

- PC and Server Health Check jobs now normalize delivery preferences for app, Telegram, Discord, Slack, WhatsApp, and SMS/text while keeping app/in-room history as the default.
- Delivery status and warnings are persisted into Task Guardian run evidence and tool args, then written to unified memory/context as source-labeled delivery events.
- Telegram, Discord, Slack, and WhatsApp delivery paths check configuration before sending; SMS/text is marked setup-needed/future and does not fake a send.
- Command Center Task Guardian cards show external delivery as opt-in, expose WhatsApp, keep SMS disabled/future, and display last delivery status.

Remaining after this pass:

- Live QA with test Telegram, Discord, Slack, and WhatsApp targets.
- Confirm Main Chat natural-language schedule setup through the actual model/tool confirmation flow.
- Keep SMS/text as future until a real provider is selected.

## Meeting Memory Operator Spine Update - 2026-05-21

Branch: `public-release-meeting-memory-operator-spine`

Completed in this pass:

- Added source-labeled meeting-note metadata for saved/generated Meeting Manager notes.
- Added OWNER/MOD meeting artifact editing and a Meeting Room notes editor.
- Updated meeting-note memory rollups so edits supersede stale active rollups for the same artifact.
- Kept per-turn notes disabled and blocked draft/failed-generation notes from shared memory rollup.
- Documented Main Chat and connector continuity through the shared context path with explicit identity-linking limits.

Remaining after this pass:

- Browser QA notes save/edit and role permissions.
- Live QA meeting recall through Main Chat and linked Telegram/Discord/WhatsApp/Slack identities.
- Treat SMS/text as future until a real connector and identity model exist.

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
