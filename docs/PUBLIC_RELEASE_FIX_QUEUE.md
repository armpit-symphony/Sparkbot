# Sparkbot Public Release Fix Queue

Date: 2026-05-17
Goal: Stabilize current Sparkbot before extracting a public shell into `Sparkbot_shell`.

This queue is intentionally small enough for follow-up Codex phases. Do not copy code to `Sparkbot_shell` until the P0 blockers are closed.

## 1. P0 Blockers Before Extraction

1. Unify public chat route.
   - Redirect `/chat` to `/dm` or remove the debug `ChatPage` route.
   - Remove fixed debug overlays, tap logs, and raw `fetch` from the public route.
   - Evidence: `frontend/src/pages/ChatPage.tsx:33`, `frontend/src/pages/ChatPage.tsx:44`, `frontend/src/pages/ChatPage.tsx:433`.

2. Persist Round Table meeting manifest server-side.
   - Store seats, handles, models, route, chair, and protocol in backend meeting artifact metadata or a first-class table.
   - Load meeting metadata from backend before localStorage.
   - Keep localStorage only as a draft/cache.
   - Evidence: `frontend/src/lib/workstationMeeting.ts:22`, `frontend/src/lib/workstationMeeting.ts:344`, `frontend/src/pages/MeetingRoomPage.tsx:123`.

3. Make Round Table heartbeat non-blocking.
   - If Task Guardian heartbeat scheduling fails, launch the meeting anyway and show a warning.
   - Evidence: `frontend/src/lib/workstationMeeting.ts:187`, `frontend/src/lib/workstationMeeting.ts:199`.

4. Fix model provider allowlist mismatch.
   - Add `openai_codex` and `claude_sub` to the initial frontend `validProviders` set.
   - Add regression coverage for loading saved Codex/Claude subscription defaults.
   - Evidence: `frontend/src/hooks/useControlsState.ts:445`, `frontend/src/hooks/useControlsState.ts:786`.

5. Move Invite Wing credentials out of browser storage.
   - Persist model-seat provider credentials and sub-account keys through backend config or Guardian Vault-backed storage.
   - Keep only non-sensitive UI preferences in localStorage.
   - Show route-save errors instead of swallowing them.
   - Evidence: `frontend/src/pages/WorkstationPage.tsx:4261`, `frontend/src/pages/WorkstationPage.tsx:4585`, `frontend/src/lib/workstationMeeting.ts:659`.

6. Gate development tooling and define public navigation.
   - Mount TanStack Router Devtools and React Query Devtools only in development.
   - Ensure local-mode navigation exposes Chat, Workstation, Round Table, and Setup.
   - Remove template Admin/Items surfaces from public navigation.
   - Evidence: `frontend/src/routes/__root.tsx:12`, `frontend/src/routes/__root.tsx:13`, `frontend/src/components/Sidebar/AppSidebar.tsx:26`, `frontend/src/routeTree.gen.ts:117`.

7. Gate or hide terminal desks for public default.
   - Terminal UI should be hidden or disabled unless backend config confirms live terminal is enabled and user is an operator.
   - Evidence: `frontend/src/config/workstationStations.ts:106`, `frontend/src/config/workstationStations.ts:120`, `README.md:499`.

8. Convert Robo OS to teaser-only for public shell.
   - Remove or hard-disable `lima_robot_command` from public tool catalog.
   - Hide robotics endpoints behind a private build flag or remove from public route registration.
   - Replace top-tab Robo action with a static teaser card.
   - Evidence: `frontend/src/components/Common/SparkbotSurfaceTabs.tsx:42`, `backend/app/api/routes/chat/robotics.py:22`, `backend/app/api/routes/chat/tools.py:2014`.

9. Clean public source-bundle exclusions and private path references.
   - Exclude `docs/audits/*`, `docs/lima-robo-os-integration.md`, private deployment checklists, and extraction handoff docs from public packages.
   - Rewrite or move `remote.sparkpitlabs.com`, `/home/sparky`, `api.sparkpitlabs.com`, Kalshi, OpenClaw, and WEPO references before packaging.
   - Evidence: `scripts/package-public-download.sh:129`, `docs/audits/HANDOFF_next_phase.md:110`, `FRESH_INSTALL_CHECKLIST.md:15`, `README.md:611`, `release-notes.md:25`.

10. Rewrite built-in public agent prompts.
   - Remove SparkPit Labs, LIMA AI, Guardian services, and service-offering references from public default agents.
   - Evidence: `backend/app/api/routes/chat/agents.py:128`, `backend/app/api/routes/chat/agents.py:205`, `backend/app/api/routes/chat/agents.py:278`.

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

9. Rename template residue.
   - `package.json` name from `fastapi-full-stack-template` to `sparkbot`.
   - Signup page title from `FastAPI Template` to Sparkbot or hide unsupported signup.

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

1. Robo OS full control plane.
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

3. Robo OS teaser copy.
   - Mention LIMA by name, or describe it generically as "future robotics/runtime integrations"?

4. Public Guardian scope.
   - Public MVP should include basic confirmations and PIN gate. Decide whether Vault, policy simulation, Token Guardian, Task Guardian, and Spine queues are visible by default or advanced only.

5. Connector breadth.
   - Decide which connectors are public beta core versus advanced examples: GitHub, Google, Microsoft, Telegram, Discord, WhatsApp, Slack, Notion, Jira, Linear, Spotify, stocks, YouTube.

6. Source-bundle policy.
   - Public open-source repo can include R&D history, or should packages and `Sparkbot_shell` exclude internal audit/extraction docs entirely?

7. Round Table brand language.
   - Standardize "Round Table" versus "Roundtable", and "Seat 1 manager" versus "chair".

## Recommended Next Codex Phase

Phase B1 should be a focused P0 stabilization patch:

1. Redirect `/chat` to `/dm`.
2. Fix provider allowlist mismatch.
3. Make meeting heartbeat best-effort.
4. Add backend-backed meeting manifest load/save.
5. Move Invite Wing credentials out of browser storage.
6. Gate devtools, template routes, Robo/robotics, and terminal public surfaces behind clear public defaults.
7. Update package exclusions for internal docs and private path references.

After B1 passes build/tests, run browser QA on `/login`, `/dm`, `/workstation`, `/meeting/:roomId`, and `/spine`.
