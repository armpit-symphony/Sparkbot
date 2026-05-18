# Public Package And Prompt Cleanup Status

Date: 2026-05-17
Branch: `public-release-package-prompt-cleanup`
Base: `public-release-unified-context-spine` at `1951faa6393f651347937e6d281e7eb6f032e5f7`

## Completed

- Expanded `scripts/package-public-download.sh` public-bundle pruning for readiness audits, status docs, private runtime research notes, historical release-note docs, proposal scripts, dotenv files, logs, local databases, key/certificate files, virtualenvs, build output, and cache directories.
- Added `.venv-ci/` and `backend/.venv-ci/` to `.gitignore` so new local CI virtualenv files do not keep entering the repo.
- Rewrote built-in backend agent prompts so public defaults are framed around the user's own projects instead of SparkPit Labs, TheSparkPit, LIMA AI, or Guardian services.
- Cleaned matching frontend fallback agent descriptions and chat/specialist desk public labels.
- Rewrote README and capabilities docs so Robo is presented as **Robo Preview** / teaser-only for public core.
- Replaced private host-inspection examples with generic host log roots and local service health language.
- Removed the OpenClaw config fallback from web search key loading; Sparkbot now uses `BRAVE_SEARCH_API_KEY` or an explicit `SPARKBOT_SEARCH_CONFIG_PATH`.
- Updated public download docs to use a generic publish path and describe the stronger package exclusions.

## Package Exclusions

Public source bundles now exclude:

- `docs/audits/`
- public-release readiness/status/audit docs
- `docs/release-notes/` historical release-note docs
- private LIMA/Robo runtime research docs
- `guardian_suite_integration.md`
- proposal scripts and scratch proposal files
- dotenv files, logs, local databases, key/certificate files
- backup files, Python bytecode, virtualenvs, caches, `node_modules`, `dist`, `build`, and coverage output

The script still builds a package from committed source with `git archive`, then emits fresh `RELEASE-NOTES.txt` and `SHA256SUMS`.

## Risk Scan Classification

| Finding | Public release action | Status |
|---|---|---|
| `armpit-symphony` GitHub repo references | Keep for current repo/download docs until Phil decides neutral shell naming | No code change |
| `remote.sparkpitlabs.com`, `/home/ubuntu`, `104.236` | Exclude or rewrite if found in package-bound docs | Covered by broader internal doc exclusions; no current README/package-script hit remained |
| `/home/sparky`, Kalshi, WEPO, OpenClaw in current public docs/tool prompts | Rewrite for public | Replaced with generic local service/log-root language and explicit `SPARKBOT_SEARCH_CONFIG_PATH` |
| `password`, `passphrase`, `secret`, `token` | Keep when describing security/config fields; never include real values | No real secrets found; packaging removes dotenv/key/log/database artifacts |
| `Vault`, `breakglass` | Keep as public security concepts but avoid proprietary internals | Current copy favors elevated confirmation/security wording where user-facing |
| `LIMA Office`, `Arc Bot`, `LIMA IT` | Do not wire into public core | No runtime wiring changed; readiness docs are excluded from packages |
| `Robo OS`, robotics, MCP | Teaser-only/public-safe copy; private runtime code remains a blocker before extraction | README/capabilities rewritten to Robo Preview; backend bridge source remains guarded and documented as follow-up |
| `.venv-ci` tracked files | Exclude from public package; remove from Git only with approval | Package pruning and `.gitignore` updated; tracked cleanup remains |

## Remaining Risks

- Tracked `.venv-ci` files still exist in Git history/current tracked source; this pass excludes them from generated public packages but does not remove tracked files from the repo.
- Robo/LIMA backend bridge source still exists in the full R&D repo behind teaser/default guards. Public extraction should replace it with a true stub before Sparkbot_shell extraction.
- Some historical README rows still describe older Guardian/MCP work. Current product copy has been scrubbed; full release-history sanitization can be handled during extraction docs cleanup.
- Balanced vs Locked behavior separation and final Round Table assignment UI polish remain separate P0/P1 phases.

## Public/Private Boundary

- Sparkbot_shell was not modified.
- LIMA AI OS, Arc Bot, LIMA Office, and LIMA IT were not wired.
- Real robotics/IoT control was not implemented.
- No secrets were added or moved into frontend/browser storage.

## Artifact / Robo / Guardrail Cleanup Update - 2026-05-18

Branch: `public-release-artifact-guardrail-robo-cleanup`

Completed in this pass:

- Removed tracked `.venv-ci/` and `backend/.venv-ci/` files from Git while keeping the ignore rules in place for local validation environments.
- Added a Windows-safe package fallback: public `.zip` artifacts still use `zip` when available, otherwise `scripts/package-public-download.sh` uses Python stdlib `zipfile`.
- Changed the default Robo backend boundary to public-safe `Robo Preview`: default service calls return non-executing preview contracts, `/tools` exposes no live robotics tools, and emergency stop/live control stay unavailable in public mode.
- Kept the private bridge source available only behind `SPARKBOT_PRIVATE_ROBO_BRIDGE_ENABLED`; setting `SPARKBOT_ROBO_TEASER_ONLY=false` alone is not enough to execute bridge calls.
- Aligned backend MCP registry manifests to `robo_preview.*` public preview names instead of LIMA-labelled motion/control manifests.
- Added first policy-engine separation for Balanced versus Locked: Balanced confirms high-risk configured actions, while Locked requires elevated approval/break-glass for high-risk actions.
- Hardened model-seat selector values to use stable `seat:<modelSeatId>` where visible selectors offer model seats, preventing duplicate model-id collisions.

Remaining risks:

- Private Robo/LIMA bridge source still exists in the R&D repo by design, but public packages continue to exclude private runtime research docs and public/default runtime behavior is stubbed.
- Full typed Custom guardrail records remain future work; Custom currently enforces user-owned blocker text.
