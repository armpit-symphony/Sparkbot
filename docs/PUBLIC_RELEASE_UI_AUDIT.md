# Sparkbot Public Release UI Audit

Date: 2026-05-17
Branch: `public-release-readiness-audit`
Scope: Audit only. This phase does not extract `Sparkbot_shell`, wire LIMA AI OS, wire Arc Bot, or move proprietary code.

## Baseline

- Repo: `git@github-armpit:armpit-symphony/Sparkbot.git`
- Baseline commit before audit docs: `9ebedb23548d16fd085e5d959d5c82fa0148a9ae`
- Starting branch: `main`, tracking `origin/main`
- Audit branch: `public-release-readiness-audit`
- Pre-existing untracked files preserved: `scripts/file_v1_6_72_proposals.py`, `scripts/file_v1_6_75_proposals.py`
- README release line: `v1.6.81`
- Backend package: `backend/pyproject.toml` project `app`, version `1.6.81`
- Frontend package: `frontend/package.json` package `frontend`, private, version `1.6.81`
- Tauri app config: `src-tauri/tauri.conf.json` product `Sparkbot Local`, version `1.6.81`
- Tauri Rust crate: `src-tauri/Cargo.toml` crate `sparkbot-local-shell`, version `1.2.10`
- Root package metadata: `package.json` is still named `fastapi-full-stack-template` and is private.

## App Structure Observed

- Frontend routes: `frontend/src/routes/_layout/index.tsx`, `_layout/chat.tsx`, `dm.tsx`, `workstation.tsx`, `meeting.$roomId.tsx`, `controls.tsx`, `command-center.tsx`, `_layout/spine.tsx`, auth routes, and SparkBud routes.
- Main public-facing chat surface appears to be `/dm` via `frontend/src/pages/SparkbotDmPage.tsx`; `/chat` still points at `frontend/src/pages/ChatPage.tsx`.
- Workstation surface: `frontend/src/pages/WorkstationPage.tsx`, station data in `frontend/src/config/workstationStations.ts`.
- Round Table launcher and local meeting metadata: `frontend/src/lib/workstationMeeting.ts`.
- Command Center and setup controls: `frontend/src/routes/_layout/spine.tsx`, `frontend/src/components/CommandCenter/SetupPanels.tsx`, `OperationalPanels.tsx`.
- Backend chat routes: `backend/app/api/routes/chat/rooms.py`, `model.py`, `memory.py`, `tasks.py`, `reminders.py`, `uploads.py`, `guardian.py`, `mcp.py`, `robotics.py`, `workstation.py`.
- Guardian services: `backend/app/services/guardian/*`.
- Packaging/download docs and scripts: `docs/index.html`, `docs/public-downloads.md`, `scripts/package-public-download.sh`, `scripts/sparkbot-start.sh`, `scripts/quickstart.*`, `src-tauri/*`.

## Classification Key

- `KEEP_PUBLIC`: Ship as public MVP surface after normal validation.
- `SIMPLIFY_PUBLIC`: Keep the capability but reduce scope, copy, defaults, or controls.
- `TEASER_ONLY`: Show as roadmap/demo only, no public-core execution path.
- `REMOVE_FOR_PUBLIC`: Remove from public shell or public bundle.
- `PRIVATE_PROPRIETARY`: Move private or keep out of open source public shell.
- `NEEDS_REVIEW`: Needs Phil/product decision before extraction.

## Landing, Login, First Run

- Current state: Login supports local desktop auto-login and server passphrase entry (`frontend/src/routes/login.tsx:115`, `frontend/src/routes/login.tsx:128`). Dashboard route is an operational overview, not a focused first-run product path (`frontend/src/routes/_layout/index.tsx:403`, `frontend/src/routes/_layout/index.tsx:410`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: Dashboard copy says "what this dashboard becomes" and "new home surface", which reads like an internal build note rather than a polished public MVP. Signup still has `Sign Up - FastAPI Template` metadata (`frontend/src/routes/signup.tsx:54`).
- Broken buttons/routes/API calls: `/settings` remains visible from the dashboard (`frontend/src/routes/_layout/index.tsx:434`) and should be verified as a fully supported public path.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: First-run should route users directly to provider setup or local model setup, then chat. Current path mixes dashboard, DM, settings, Command Center, and legacy auth surfaces.
- Extraction risk: Public shell could inherit template-era routes and unfinished dashboard language.
- Recommended fix: Make a single public first-run path: local desktop auto-login -> Command Center AI Setup if no provider/local model -> DM. Update signup metadata or hide signup if not supported for local public MVP.
- Priority: `P1_POLISH`

## Shell Navigation And Developer Surfaces

- Current state: The root route mounts TanStack Router Devtools and React Query Devtools unconditionally (`frontend/src/routes/__root.tsx:12`, `frontend/src/routes/__root.tsx:13`). Local-mode sidebar filtering hides Workstation and `/chat` entries (`frontend/src/components/Sidebar/AppSidebar.tsx:26`). Template-era Admin/Items route metadata remains in the generated route tree and backend (`frontend/src/routeTree.gen.ts:117`, `backend/app/api/routes/items.py:10`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: Public users can see developer tooling while core public surfaces may be hidden in local mode, depending on sidebar state.
- Broken buttons/routes/API calls: Admin/Items surfaces are template residue and should not be public beta navigation.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Public navigation should be small and obvious: Chat, Workstation, Round Table, Setup/Controls, Files/Memory, and optional advanced tools.
- Extraction risk: Public shell extraction could inherit debug/dev routes and hide the very Workstation/Round Table hook being extracted.
- Recommended fix: Gate devtools to development only, remove template route residue from public navigation, and define one public local-mode nav list.
- Priority: `P0_BLOCKER`

## Chat Page

- Current state: `/dm` is the main chat surface. `/chat` still renders `frontend/src/pages/ChatPage.tsx`, which contains fixed debug overlays, tap logs, raw `fetch`, and console logging (`frontend/src/pages/ChatPage.tsx:33`, `frontend/src/pages/ChatPage.tsx:44`, `frontend/src/pages/ChatPage.tsx:151`, `frontend/src/pages/ChatPage.tsx:433`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: Debug overlay can cover the chat UI; loading and room state display internal `BOOT`, `STUCK`, and `tapLog` text (`frontend/src/pages/ChatPage.tsx:379`, `frontend/src/pages/ChatPage.tsx:402`, `frontend/src/pages/ChatPage.tsx:411`, `frontend/src/pages/ChatPage.tsx:448`).
- Broken buttons/routes/API calls: Raw `fetch("/api/v1/chat/rooms")` is used instead of `apiFetch` (`frontend/src/pages/ChatPage.tsx:53`, `frontend/src/pages/ChatPage.tsx:159`, `frontend/src/pages/ChatPage.tsx:325`). This is a known Tauri/server-mode risk because other fixes moved raw origin fetches to `apiFetch`.
- Console/backend errors discovered: Static evidence shows extensive console output (`frontend/src/pages/ChatPage.tsx:40`, `frontend/src/pages/ChatPage.tsx:51`, `frontend/src/pages/ChatPage.tsx:268`, `frontend/src/pages/ChatPage.tsx:321`).
- Polish issues: `/chat` looks like a debug fallback while `/dm` is the actual product chat.
- Extraction risk: Public shell may expose the wrong chat route or duplicate chat code.
- Recommended fix: Redirect `/chat` to `/dm` or remove the debug component from public routing. Keep one chat entry point.
- Priority: `P0_BLOCKER`

## Workstation Page

- Current state: Workstation is a rich spatial office map with model stack desks, invite desks, Roundtable, terminal panels, Company Operations, and Robo OS (`frontend/src/pages/WorkstationPage.tsx`, `frontend/src/config/workstationStations.ts`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: The map is compelling, but it mixes public workstation concepts with terminal control, MCP, LIMA Robotics OS, and internal operations language.
- Broken buttons/routes/API calls: Workstation overview fetches `/api/v1/chat/workstation/overview` and Guardian status (`frontend/src/pages/WorkstationPage.tsx:4296`, `frontend/src/pages/WorkstationPage.tsx:4299`). Needs runtime validation in Tauri and server mode.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: The visual style is custom and dense. It needs a public MVP pass focused on "Round Table meetings for your AI agents" instead of every R&D desk.
- Extraction risk: Workstation is the highest-risk public shell source because it imports MCP/Robo logic, terminal logic, invite config localStorage, and meeting launch orchestration in one component.
- Recommended fix: For public beta, keep Sparkbot desk, model stack desks, basic agent offices, and Round Table. Hide terminal and Robo behind explicit disabled/teaser states unless configured.
- Priority: `P1_POLISH`

## Round Table Meeting Flow

- Current state: Workstation launches rooms through `launchMeetingRoom` and Meeting Room runs an autonomous meeting stream. Backend flow implements first ideas, manager assessment, assignments, assigned work, and manager summary (`backend/app/api/routes/chat/rooms.py:2019`, `backend/app/api/routes/chat/rooms.py:2031`, `backend/app/api/routes/chat/rooms.py:2055`, `backend/app/api/routes/chat/rooms.py:2076`, `backend/app/api/routes/chat/rooms.py:2096`, `backend/app/api/routes/chat/rooms.py:2119`).
- Classification: `KEEP_PUBLIC`
- Visible user problems: The core hook is present, but the UI does not make the chair protocol or current phase clear enough for a new public user.
- Broken buttons/routes/API calls: Meeting launch hard-fails if meeting heartbeat scheduling fails (`frontend/src/lib/workstationMeeting.ts:187`, `frontend/src/lib/workstationMeeting.ts:199`). A Task Guardian issue should not block the public Round Table launch.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: "Chair" and "Seat 1 manager" terminology is mixed. Meeting notes artifact is created at launch as a placeholder (`frontend/src/lib/workstationMeeting.ts:435`, `frontend/src/lib/workstationMeeting.ts:463`), which can look like generated notes before real discussion.
- Extraction risk: Meeting seat metadata and room links are localStorage-only (`frontend/src/lib/workstationMeeting.ts:22`, `frontend/src/lib/workstationMeeting.ts:344`, `frontend/src/pages/MeetingRoomPage.tsx:123`). A meeting opened from another browser or after cleared storage can lose participants and stop behaving like a Round Table.
- Recommended fix: Persist seat manifest and meeting metadata server-side as the source of truth. Make heartbeat best-effort. Add visible phase/status affordances.
- Priority: `P0_BLOCKER`

## Controls And Setup UX

- Current state: `/controls` redirects to `/spine` (`frontend/src/routes/controls.tsx:4`). Command Center embeds setup panels for AI Setup, Security/PIN, Comms, and Agents (`frontend/src/routes/_layout/spine.tsx:1189`, `frontend/src/routes/_layout/spine.tsx:1190`, `frontend/src/routes/_layout/spine.tsx:1194`, `frontend/src/routes/_layout/spine.tsx:1197`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: "Controls", "Command Center", and route name `spine` are still mixed, which is confusing for a public local-first workstation.
- Broken buttons/routes/API calls: The redirect itself is safe, but references and copy should converge on Command Center or Setup. Command Center still contains a disabled "New Project" path that reports the feature is not configured (`frontend/src/routes/_layout/spine.tsx:1413`).
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Command Center includes deep Guardian Spine internals below public setup panels, which can overwhelm first-run users.
- Extraction risk: Public shell may accidentally export private Guardian Spine work-state UI as a core public feature.
- Recommended fix: Split public Setup from internal Command Center/Spine tabs. Keep route aliases for compatibility but hide internal tabs by default.
- Priority: `P1_POLISH`

## Model Stack And Model Selector

- Current state: Backend supports default provider, model stack, agent overrides, provider tokens, OpenAI Codex subscription, Claude subscription, OpenRouter, local Ollama, and Token Guardian (`backend/app/api/routes/chat/model.py:864`, `backend/app/api/routes/chat/model.py:953`, `backend/app/api/routes/chat/model.py:991`, `backend/app/api/routes/chat/model.py:1090`). Frontend setup exposes the same broad set (`frontend/src/components/CommandCenter/SetupPanels.tsx:245`).
- Classification: `KEEP_PUBLIC`
- Visible user problems: The model surface is powerful but dense. New users need a single "pick cloud provider or local Ollama" flow before advanced stack controls.
- Broken buttons/routes/API calls: Frontend config load has a provider allowlist missing `openai_codex` and `claude_sub`, so saved subscription defaults can be coerced to `openrouter` on load (`frontend/src/hooks/useControlsState.ts:445`). The change handler later includes those providers (`frontend/src/hooks/useControlsState.ts:786`), indicating an inconsistency.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Root package still says `fastapi-full-stack-template`, which undermines model stack/product polish.
- Extraction risk: Model provider state is shared across chat, agents, Workstation seats, and Round Table. Any extraction must preserve the config contract.
- Recommended fix: Fix provider allowlists, add a simple first-run path, and document the `models/config` contract as public shell API before extraction.
- Priority: `P0_BLOCKER`

## Invite Wing And Model Seats

- Current state: Workstation has Claude, ChatGPT/Codex, and xAI Grok invite desks (`frontend/src/config/workstationStations.ts:56`, `frontend/src/config/workstationStations.ts:70`, `frontend/src/config/workstationStations.ts:84`). Invite route data is partly local to Workstation and partly persisted through backend agent routes (`frontend/src/pages/WorkstationPage.tsx:4261`, `frontend/src/lib/workstationMeeting.ts:659`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: The language "sub-account key", per-desk key, and direct provider routing needs a clearer safety story for public users.
- Broken buttons/routes/API calls: `ensureInviteAgentRoutes` swallows invite route save failures (`frontend/src/lib/workstationMeeting.ts:659`). A user can think a seat is configured when backend routing failed.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Invite config is stored in browser localStorage (`frontend/src/pages/WorkstationPage.tsx:4261`, `frontend/src/pages/WorkstationPage.tsx:4585`), not a durable public setup source. If provider credentials or sub-account keys are stored there, the public security story is not acceptable.
- Extraction risk: Seats are a public hook, but storage and routing are not cleanly separated from full Workstation.
- Recommended fix: Move invite-seat state and provider credentials into backend public config or Guardian Vault-backed storage, show route-save errors, and make model seat readiness explicit before launch.
- Priority: `P0_BLOCKER`

## Agents And Custom Agents

- Current state: Built-in agents and custom agents are available through `/api/v1/chat/agents`, Command Center Agents panel, and Workstation specialty offices (`frontend/src/components/CommandCenter/SetupPanels.tsx:900`, `backend/app/api/routes/chat/agents.py`).
- Classification: `KEEP_PUBLIC`
- Visible user problems: "Spawn Agent" is useful, but identity, owner, scopes, kill switch, and risk tier may feel like R&D/security internals on first use.
- Broken buttons/routes/API calls: Static audit did not find a specific broken route. Custom meeting seat provisioning creates agents on launch and treats 409 as ok (`frontend/src/lib/workstationMeeting.ts:637`).
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Built-in prompts mention SparkPit Labs, LIMA AI, Guardian services, and related projects (`backend/app/api/routes/chat/agents.py:128`, `backend/app/api/routes/chat/agents.py:205`, `backend/app/api/routes/chat/agents.py:278`).
- Extraction risk: Public agents should not inherit internal SparkPit/LIMA service prompts.
- Recommended fix: Rewrite public built-in prompts to be product-neutral. Keep custom agent creation, but make identity controls advanced.
- Priority: `PRIVATE_REMOVE`

## Files And Memory UX

- Current state: `/dm` supports file upload and image/file handling (`frontend/src/pages/SparkbotDmPage.tsx:4340`, `frontend/src/pages/SparkbotDmPage.tsx:4367`). Backend upload route stores files locally and serves non-images as forced downloads (`backend/app/api/routes/chat/uploads.py:22`, `backend/app/api/routes/chat/uploads.py:48`, `backend/app/api/routes/chat/uploads.py:75`). Memory inspector and correction/removal exist (`frontend/src/pages/SparkbotDmPage.tsx:4223`, `frontend/src/pages/SparkbotDmPage.tsx:4927`, `backend/app/api/routes/chat/memory.py`).
- Classification: `KEEP_PUBLIC`
- Visible user problems: Memory correction uses `window.prompt` (`frontend/src/pages/SparkbotDmPage.tsx:4937`), which is functional but not polished. File uploads are chat-first, not a visible file library.
- Broken buttons/routes/API calls: No specific static route mismatch found.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Memory actions are buried behind slash commands and inline system messages.
- Extraction risk: Memory continuity is a current priority and must not be split between duplicate stores during extraction.
- Recommended fix: Keep existing APIs, add a small Memory panel in public Setup/Chat, and preserve shared memory contract before shell extraction.
- Priority: `P1_POLISH`

## Tasks And Reminders UX

- Current state: Room tasks and reminders have REST APIs (`backend/app/api/routes/chat/tasks.py`, `backend/app/api/routes/chat/reminders.py`) and chat slash commands (`frontend/src/pages/SparkbotDmPage.tsx:4249`, `frontend/src/pages/SparkbotDmPage.tsx:4273`). Task Guardian jobs are managed through Command Center and room panels.
- Classification: `KEEP_PUBLIC`
- Visible user problems: Basic tasks/reminders are not surfaced as first-class simple UI; users are told to type natural language or slash commands.
- Broken buttons/routes/API calls: Task Guardian creation uses raw JSON `taskArgs` in setup state (`frontend/src/hooks/useControlsState.ts:410`, `frontend/src/hooks/useControlsState.ts:1153`), which is risky for public beta.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: There are three related concepts: basic tasks, reminders, and Guardian scheduled jobs. Public UX needs clearer separation.
- Extraction risk: Task Guardian is deeper Guardian internals and should not become the only public task/reminder path.
- Recommended fix: Keep simple tasks/reminders public. Move Guardian scheduled jobs behind advanced controls or a clearly labeled automation section.
- Priority: `P1_POLISH`

## Guardian Confirmations And Approvals

- Current state: Chat has confirmation modal and break-glass flow (`frontend/src/pages/SparkbotDmPage.tsx:63`, `frontend/src/pages/SparkbotDmPage.tsx:4569`, `frontend/src/pages/SparkbotDmPage.tsx:4771`). Backend Guardian routes handle PIN, breakglass, Vault, tasks, status, and metrics (`backend/app/api/routes/chat/guardian.py`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: Break-glass is automatically initiated by sending `/breakglass` after a privileged event (`frontend/src/pages/SparkbotDmPage.tsx:4575`, `frontend/src/pages/SparkbotDmPage.tsx:4588`). That may be convenient but needs clearer UI trust boundaries.
- Broken buttons/routes/API calls: No specific static route mismatch found.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Terms "Security", "Computer Control", "break-glass", "Vault", "Guardian", and "Spine" compete.
- Extraction risk: Advanced proprietary Guardian Suite internals are too visible for public MVP.
- Recommended fix: Keep basic yes/no confirmations and PIN gate public. Hide Spine, policy simulation, internal queues, and advanced Guardian internals by default.
- Priority: `P1_POLISH`

## Terminal And Live Tools Exposure

- Current state: Workstation exposes Local Terminal and Secondary Terminal desks (`frontend/src/config/workstationStations.ts:106`, `frontend/src/config/workstationStations.ts:120`) and lazy-loads xterm terminal UI (`frontend/src/pages/WorkstationPage.tsx:46`). Public docs warn live terminal is raw shell access and disabled for public deploys unless private/operator-only (`README.md:499`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: Even when disabled by config, terminal desks are visible in the public Workstation mental model.
- Broken buttons/routes/API calls: Backend terminal router can be disabled (`backend/app/api/routes/chat/terminal.py:60`), but the Workstation UI still advertises terminal desks and panels (`frontend/src/pages/WorkstationPage.tsx:3003`).
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Terminal is a power feature, not public-first hook.
- Extraction risk: Shell access must not accidentally ship as a casual public-core control.
- Recommended fix: Keep terminal behind explicit "local operator tools" advanced gate, hidden or disabled by default in public beta.
- Priority: `P0_BLOCKER`

## Robo Tab

- Current state: Robo OS is a top navigation tab (`frontend/src/components/Common/SparkbotSurfaceTabs.tsx:42`) and Workstation MCP panel includes LIMA Robotics OS messaging and an external README button (`frontend/src/pages/WorkstationPage.tsx:3241`, `frontend/src/pages/WorkstationPage.tsx:3269`, `frontend/src/pages/WorkstationPage.tsx:3499`). Backend robotics endpoints and chat tool exist (`backend/app/api/routes/chat/robotics.py:22`, `backend/app/api/routes/chat/tools.py:2014`).
- Classification: `TEASER_ONLY`
- Visible user problems: Robo OS looks like a core public feature even though the stated public target says teaser only.
- Broken buttons/routes/API calls: Direct external link opens `https://github.com/armpit-symphony/LIMA-Robo-OS` if no Robo handler is provided (`frontend/src/components/Common/SparkbotSurfaceTabs.tsx:48`).
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Robot-motion, MCP, LIMA bridge, emergency stop, and replay/simulation language overpowers the Round Table hook.
- Extraction risk: This is the clearest public/private separation risk. Public shell should not include full robotics/IoT natural-language control or adapters.
- Recommended fix: Stub Robo as a static teaser card with "coming later" copy. Disable or remove public robotics endpoints/tools unless explicitly building a private R&D build.
- Priority: `PRIVATE_REMOVE`

## Docs, Downloads, Install UX

- Current state: Public download docs and site align to `v1.6.81` (`docs/public-downloads.md:14`, `docs/index.html:982`, `README.md:9`). Packaging script builds source bundles and removes some internal-only files (`scripts/package-public-download.sh:129`).
- Classification: `SIMPLIFY_PUBLIC`
- Visible user problems: README and docs present Sparkbot as an expansive agent OS with many integrations and LIMA Robotics OS. Public MVP should lead with self-hosted AI workstation and Round Table meetings.
- Broken buttons/routes/API calls: Download links are hardcoded with fallback GitHub release URLs in `docs/index.html`; dynamic release loader exists, but should be smoke-tested against current release assets.
- Console/backend errors discovered: Not runtime-tested in browser during static audit.
- Polish issues: Packaging script does not exclude `docs/audits/*` or `docs/lima-robo-os-integration.md`, which are not public shell core.
- Extraction risk: Source bundle can expose extraction notes, LIMA comparison docs, and R&D phase plans.
- Recommended fix: Add public bundle excludes or move internal audit docs out of public source. Reframe README/docs around public MVP areas.
- Priority: `P0_BLOCKER`

## Summary Recommendation

Sparkbot is not ready to be the source for a product-ready public shell extraction yet. The highest-value public feature, Round Table meetings for AI agents, exists and has a backend chaired meeting protocol, but public readiness is blocked by debug chat routes, local-only Roundtable metadata, Invite Wing credential storage, model selector inconsistency, always-mounted devtools, visible terminal/Robo/LIMA surfaces, and packaging/docs that still include internal R&D material.
