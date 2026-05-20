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

- Sparkbot is not ready for `Sparkbot_shell` extraction yet. The product surfaces are mostly implementation-ready, but public packaging/source-boundary issues remain P0: public docs still point source installs at the full R&D repo, public bundles still include tests and GitHub workflows with private/stale context, and repo-root Docker contexts need a root `.dockerignore` before public source installs are promoted.

Recommended next phase:

1. Focused public package/source-boundary sanitation: public install source copy, tests/workflow package exclusions or sanitization, and root Docker context hygiene.
2. Browser/live QA using the new checklist and plan.
3. Refresh `Sparkbot_shell` extraction map from the validated public artifact.
