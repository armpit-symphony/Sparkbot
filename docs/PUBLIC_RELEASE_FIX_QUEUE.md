# Sparkbot Public Release Fix Queue

Date: 2026-05-17
Goal: Stabilize current Sparkbot before extracting a public shell into `Sparkbot_shell`.

This queue is intentionally small enough for follow-up Codex phases. Do not copy code to `Sparkbot_shell` until the P0 blockers are closed.

## P0 Stabilization Status - 2026-05-17

Branch `public-release-p0-memory-guardrails-roundtable` moved several prior blockers forward:

- Backend-backed Round Table manifests now load into Meeting Room UI before localStorage cache.
- Round Table heartbeat scheduling is best-effort and no longer blocks launch.
- Frontend model provider allowlists include `openai_codex` and `claude_sub`.
- Seat 1 Round Table assignments persist as structured `meeting_assignments` artifacts.
- Slack is wired as the public baseline connector pattern for shared memory/context.
- Command Center Security profiles persist as Personal/Balanced/Locked/Custom.
- Hidden DM auto-breakglass was removed.
- Robo defaults to teaser-only backend/tool behavior, blocking live robotics control while allowing dry-run/demo contracts.

Branch `public-release-surface-nav-room-ux` moved the public shell UX blockers forward:

- `/chat` now redirects to `/dm` without importing the legacy debug page.
- Devtools are dev-only dynamic imports.
- Admin and Items template routes redirect to `/dm` outside dev.
- Public sidebar nav exposes Workstation, Sparkbot, and Command Center instead of template/admin/debug surfaces.
- Workstation and Meeting Room keep top navigation reachable while content scrolls.
- Meeting Room keeps room controls and message history in separate scroll regions on desktop.
- Live terminal UI is disabled unless backend security status confirms the live terminal feature is enabled.
- Robo defaults to a static preview panel; the operational MCP registry panel is dev/private-flag only.

Branch `public-release-unified-context-spine` moved unified memory/context blockers forward:

- Added a public shared context adapter over Guardian memory: `remember_context_event(...)` and `build_unified_context(...)`.
- Slack, Telegram, Discord, WhatsApp, and GitHub bridge handlers now use unified context retrieval and source-labeled context writes.
- Structured recall now returns source/surface, actor, thread, meeting, model-seat, agent, rollup, sensitivity, risk, and tag metadata.
- Specialty Wing/Command Center/legacy DM Controls agent overrides can persist non-secret `model_seat_id` values.
- Backend LLM route context resolves selected model-seat Vault credentials server-side and reports setup-needed instead of falling back to global provider auth when an explicit seat credential is missing.
- Draft/scaffold context rollups are skipped and manager/checkpoint rollups dedupe by fingerprint.
- Pending approval Spine events recursively redact nested secret-like payload keys.

## 1. P0 Blockers Before Extraction

1. Unify public chat route.
   - Redirect `/chat` to `/dm` or remove the debug `ChatPage` route.
   - Remove fixed debug overlays, tap logs, and raw `fetch` from the public route.
   - Status: `DONE_THIS_PHASE` - `/chat` always redirects to `/dm`, no longer imports `ChatPage`, and `ChatPage` no longer exports a route.
   - Evidence: `frontend/src/pages/ChatPage.tsx:33`, `frontend/src/pages/ChatPage.tsx:44`, `frontend/src/pages/ChatPage.tsx:433`.

2. Persist Round Table meeting manifest server-side.
   - Store seats, handles, models, route, chair, and protocol in backend meeting artifact metadata or a first-class table.
   - Load meeting metadata from backend before localStorage.
   - Keep localStorage only as a draft/cache.
   - Status: `PARTIAL_DONE` - backend manifest artifacts already existed and Meeting Room now loads them first; first-class table and UI assignment display remain.
   - Evidence: `frontend/src/lib/workstationMeeting.ts:22`, `frontend/src/lib/workstationMeeting.ts:344`, `frontend/src/pages/MeetingRoomPage.tsx:123`.

3. Make Round Table heartbeat non-blocking.
   - If Task Guardian heartbeat scheduling fails, launch the meeting anyway and show a warning.
   - Status: `DONE` - heartbeat task creation is now best-effort during launch.
   - Evidence: `frontend/src/lib/workstationMeeting.ts:187`, `frontend/src/lib/workstationMeeting.ts:199`.

4. Fix model provider allowlist mismatch.
   - Add `openai_codex` and `claude_sub` to the initial frontend `validProviders` set.
   - Add regression coverage for loading saved Codex/Claude subscription defaults.
   - Status: `DONE` for runtime allowlist; add focused frontend persistence test later if the project adds frontend test harness coverage.
   - Evidence: `frontend/src/hooks/useControlsState.ts:445`, `frontend/src/hooks/useControlsState.ts:786`.

5. Move Invite Wing credentials out of browser storage.
   - Persist model-seat provider credentials and sub-account keys through backend config or Guardian Vault-backed storage.
   - Status: `DONE` for Invite Wing, Round Table, and Specialty Wing backend routing. Workstation removes the legacy `sparkbot_invite_configs` key, saves model-seat metadata through `/api/v1/chat/models/config`, stores supplied credentials in Guardian Vault, and Specialty Wing agent overrides can carry `model_seat_id` for backend-only credential resolution.
   - Keep only non-sensitive UI preferences in localStorage.
   - Show route-save errors instead of swallowing them.
   - Evidence: `frontend/src/pages/WorkstationPage.tsx:4261`, `frontend/src/pages/WorkstationPage.tsx:4585`, `frontend/src/lib/workstationMeeting.ts:659`.

6. Gate development tooling and define public navigation.
   - Mount TanStack Router Devtools and React Query Devtools only in development.
   - Ensure local-mode navigation exposes Chat, Workstation, Round Table, and Setup.
   - Remove template Admin/Items surfaces from public navigation.
   - Status: `DONE_THIS_PHASE` for visible route/nav cleanup; a later shared-shell refactor can consolidate layout wrappers.
   - Evidence: `frontend/src/routes/__root.tsx:12`, `frontend/src/routes/__root.tsx:13`, `frontend/src/components/Sidebar/AppSidebar.tsx:26`, `frontend/src/routeTree.gen.ts:117`.

7. Gate or hide terminal desks for public default.
   - Terminal UI should be hidden or disabled unless backend config confirms live terminal is enabled and user is an operator.
   - Status: `DONE_THIS_PHASE` for visible live-terminal UI gating. Workstation now reads `/api/v1/chat/security/status` and disables the live terminal desk/CTA unless `features.live_terminal.enabled` is true.
   - Evidence: `frontend/src/config/workstationStations.ts:106`, `frontend/src/config/workstationStations.ts:120`, `README.md:499`.

8. Convert Robo to teaser-only for public shell.
   - Remove or hard-disable `lima_robot_command` from public tool catalog.
   - Hide robotics endpoints behind a private build flag or remove from public route registration.
   - Replace top-tab Robo action with a static teaser card.
   - Status: `DONE_THIS_PHASE` for public default UI plus prior backend guard. Public default `SPARKBOT_ROBO_TEASER_ONLY=true` hides the chat robot tool, returns no live tool list, blocks non-dry-run robotics commands, and blocks emergency stop. The Workstation default Robo panel is now static teaser copy; the operational registry panel is dev/private-flag only.
   - Evidence: `frontend/src/components/Common/SparkbotSurfaceTabs.tsx:42`, `backend/app/api/routes/chat/robotics.py:22`, `backend/app/api/routes/chat/tools.py:2014`.

9. Clean public source-bundle exclusions and private path references.
   - Exclude `docs/audits/*`, `docs/lima-robo-os-integration.md`, private deployment checklists, and extraction handoff docs from public packages.
   - Rewrite or move `remote.sparkpitlabs.com`, `/home/sparky`, `api.sparkpitlabs.com`, Kalshi, OpenClaw, and WEPO references before packaging.
   - Evidence: `scripts/package-public-download.sh:129`, `docs/audits/HANDOFF_next_phase.md:110`, `FRESH_INSTALL_CHECKLIST.md:15`, `README.md:611`, `release-notes.md:25`.

10. Rewrite built-in public agent prompts.
   - Remove SparkPit Labs, LIMA AI, Guardian services, and service-offering references from public default agents.
   - Evidence: `backend/app/api/routes/chat/agents.py:128`, `backend/app/api/routes/chat/agents.py:205`, `backend/app/api/routes/chat/agents.py:278`.

11. Keep one shared context spine across public surfaces.
   - Route meaningful chat, connector, meeting, model-seat, agent, task, file, and approval events through a shared source-labeled context interface.
   - Status: `PARTIAL_DONE` - chat, external connectors, meeting rollups, model-seat metadata, and existing task/file/reminder adapters are aligned. Approval summaries and Workstation UI intent events remain follow-ups.
   - Evidence: `backend/app/services/guardian/memory.py`, `backend/app/services/model_seats.py`.

## 2. P1 Polish Before Public Beta

1. Reframe first-run UX.
   - Local desktop: auto-login -> AI Setup if no provider/local model -> DM.
   - Server: passphrase login -> AI Setup -> DM.
   - Reduce dashboard "future state" copy.

2. Simplify Command Center for public users.
   - Split public Setup from advanced Guardian/Spine internals.
   - Keep `/controls` alias, but converge copy on one public name.

3. Add Round Table phase/status UI.
   - Show Seat 1 manager, current phase, participant queue, and status result.
   - Backend already has phase prompts; surface them as SSE metadata or derive from events.

4. Clean meeting notes UX.
   - Rename launch placeholder to agenda or hide until a real notes generation.
   - Keep notes manual, not after every turn.

5. Split public download/build docs from private publish steps.
   - Keep local/server install instructions public.
   - Move `/var/www/sparkpitlabs.com/...`, `sparkbot-v2`, production deploy workflow assumptions, and private publish paths into private operator docs.

6. Make memory inspect/edit polished.
   - Replace `window.prompt` correction with a small modal.
   - Add a Memory panel or command palette item.

7. Add simple task/reminder panels.
   - Keep slash commands, but expose basic task/reminder workflows without raw JSON.
   - Keep Task Guardian advanced.

8. Improve Guardian confirmation UI.
   - Replace automatic hidden `/breakglass` flow with explicit PIN/approval modal.
   - Show action summary, TTL, and cancel path.
   - Status: `PARTIAL_DONE` - hidden `/breakglass` auto-send removed; full modal still needed.

9. Rename template residue.
   - `package.json` name from `fastapi-full-stack-template` to `sparkbot`.
   - Signup page title from `FastAPI Template` to Sparkbot or hide unsupported signup.
   - Status: `PARTIAL_DONE` - frontend public route titles for signup/recovery/settings/admin/items now say Sparkbot. Package metadata remains.

10. Align or document desktop crate version.
    - `src-tauri/Cargo.toml` is `1.2.10` while product release is `1.6.81`.

## 3. P2 Post-Beta Improvements

1. Add a formal public shell contract doc for:
   - `models/config`
   - Round Table meeting manifest
   - shared memory retrieval/writeback
   - Guardian confirmation envelope

2. Add Playwright smoke flows:
   - First-run setup
   - `/dm` chat
   - Workstation Round Table launch
   - Meeting kickoff with fake agents/providers
   - Memory inspect/correct/remove
   - Task/reminder slash commands

3. Add UI feature flags/build modes:
   - public shell
   - private R&D
   - robotics lab

4. Reduce Workstation component size.
   - Split panels into focused components after behavior is stable.
   - Keep the existing behavior intact first.

5. Improve docs/download provenance.
   - Version checks across README, backend, frontend, Tauri, release notes, Pages, and package artifacts.
   - Document Rust crate version policy.

## 4. Remove Or Stub For Public

1. Robo full control plane.
   - Keep teaser only.
   - Remove/stub LIMA tool manifests, robot-motion policy, emergency stop, and simulation commands from public UI.

2. Robotics backend routes and chat tool.
   - Remove from public route registration or feature-gate private.
   - Keep no public natural-language robot/drone/humanoid control.

3. Internal Guardian/LIMA extraction docs.
   - Move private or exclude from public packages.

4. SparkPit/LIMA/Guardian service prompts in built-in agents.
   - Rewrite public prompts.

5. Deep Guardian Spine internals in first-run/public setup.
   - Hide behind advanced/operator mode.

6. Terminal/live shell controls.
   - Hide by default and require explicit local operator enablement.

## 5. Needs Phil Decision

1. Repository and org naming.
   - Keep `armpit-symphony/Sparkbot` in public docs until `Sparkbot_shell` extraction, or start preparing neutral shell naming now?

2. SparkPit Labs branding.
   - Should public shell keep `com.sparkpitlabs.sparkbot.local` and SparkPit ownership, or adopt neutral open-source branding?

3. Robo teaser copy.
   - Mention LIMA by name, or describe it generically as "future robotics/runtime integrations"?

4. Public Guardian scope.
   - Public MVP should include basic confirmations and PIN gate. Decide whether Vault, policy simulation, Token Guardian, Task Guardian, and Spine queues are visible by default or advanced only.

5. Connector breadth.
   - Decide which connectors are public beta core versus advanced examples: GitHub, Google, Microsoft, Telegram, Discord, WhatsApp, Slack, Notion, Jira, Linear, Spotify, stocks, YouTube.

6. Source-bundle policy.
   - Public open-source repo can include R&D history, or should packages and `Sparkbot_shell` exclude internal audit/extraction docs entirely?

7. Round Table brand language.
   - Standardize remaining legacy "Roundtable" copy, and decide "Seat 1 manager" versus "chair".

## Recommended Next Codex Phase

Phase B2 should be a focused P0/P1 stabilization patch:

1. Update package exclusions for internal docs and private path references.
2. Rewrite built-in public agent prompts.
3. Tune Balanced vs Locked policy behavior.
4. Add final Round Table assignment display/phase UI polish.
5. Refresh the Sparkbot_shell extraction map.
6. Converge remaining "Controls" copy into AI setup versus Command Center.

After B2 passes build/tests, run browser QA on `/login`, `/dm`, `/workstation`, `/meeting/:roomId`, and `/spine`.
