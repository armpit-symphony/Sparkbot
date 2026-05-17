# Sparkbot Public Release Risk Audit

Date: 2026-05-17
Scope: Search and report only. No removals or proprietary-code movement were performed.

## Search Method

Searched the Sparkbot repo for:

`armpit-symphony`, `remote.sparkpitlabs.com`, `/home/sparky`, `/home/ubuntu`, `104.236`, `token`, `secret`, `password`, `passphrase`, `private`, `internal`, `proprietary`, `client`, `LIMA Office`, `Arc Bot`, `LIMA IT`, `Robo OS`, `robotics`, `MCP`, `Vault`, `breakglass`, `production`, `DigitalOcean`, `AWS`, and `sparkpitlabs internal paths`.

Ignored heavy/generated folders for search readability: `.git`, `node_modules`, frontend build output, Tauri target output, and lock files. Tracked env examples were inspected. Local untracked secret files were not printed.

No obvious committed live credential patterns were found with the credential regex scan excluding env templates. Tracked `frontend/.env` contains only local dev URLs (`VITE_API_URL=http://localhost:8000`, `MAILCATCHER_HOST=http://localhost:1080`).

Follow-up scan found private/staging references for `remote.sparkpitlabs.com`, `/home/sparky`, `api.sparkpitlabs.com`, and internal workload examples such as Kalshi, OpenClaw, and WEPO. No direct hits were found for `/home/ubuntu`, `104.236`, `DigitalOcean`, `LIMA Office`, `Arc Bot`, or `LIMA IT`.

## Findings

| File | Line/context summary | Public release action |
|---|---|---|
| `README.md:25` | Positions Sparkbot as command center for the wider LIMA system. | `rewrite` - public README should lead with self-hosted AI workstation and Round Table; LIMA can be roadmap/teaser. |
| `README.md:28` | Defines LIMA Robotics OS as robotics runtime exposed through MCP tools. | `stub` - keep teaser only, not public-core capability. |
| `README.md:93` | Top tabs include Robo OS as a normal public surface. | `rewrite` - public docs should not present Robo OS as core MVP. |
| `README.md:402` | Full "Robo OS And MCP Control Plane" docs. | `move private` or `stub` - too much robotics/MCP control detail for public shell. |
| `README.md:420` | Documents `LIMA_MCP_URL` and robotics bridge endpoints. | `move private` or `stub` - not public core. |
| `README.md:427` | Documents natural-language robot command tool. | `move private` - conflicts with "no full robotics/IoT natural-language control". |
| `docs/lima-robo-os-integration.md:1` | Dedicated LIMA Robo OS integration runbook. | `move private` or exclude from public bundle. |
| `docs/lima-robo-os-integration.md:25` | Lists robotics status/tools/command/emergency-stop endpoints. | `move private`; public teaser should not ship execution runbook. |
| `docs/lima-robo-os-integration.md:73` | Future work explicitly includes approved MCP run handoff and real hardware adapters. | `move private`; keep out of public MVP docs. |
| `frontend/src/components/Common/SparkbotSurfaceTabs.tsx:42` | Top-level Robo OS tab. | `stub` - make teaser only or hide unless private build flag. |
| `frontend/src/components/Common/SparkbotSurfaceTabs.tsx:48` | Opens `https://github.com/armpit-symphony/LIMA-Robo-OS`. | `needs Phil decision` - public link may reveal staging/private direction. |
| `frontend/src/pages/WorkstationPage.tsx:3049` | MCP Control Plane comment ties Sparkbot tools to LIMA Robotics OS. | `stub` - remove from public core UI or gate as teaser. |
| `frontend/src/pages/WorkstationPage.tsx:3269` | UI copy explains LIMA Robotics OS runtime through MCP. | `stub` - replace with roadmap teaser in public shell. |
| `frontend/src/pages/WorkstationPage.tsx:3473` | Shows no-hardware LIMA demo commands. | `stub` - demo commands are not core public workstation. |
| `frontend/src/pages/WorkstationPage.tsx:3499` | Opens LIMA Robo OS README. | `needs Phil decision` - hide for public beta unless repo is intentionally public. |
| `frontend/src/lib/mcpRegistry.ts:119` | LIMA robot motion manifest in frontend fallback registry. | `remove` or `stub` - robot-motion manifests should not be public core. |
| `frontend/src/lib/mcpRegistry.ts:148` | Emergency stop and simulation manifests exposed in fallback registry. | `stub` - keep only teaser, no action lifecycle. |
| `backend/app/api/routes/chat/robotics.py:22` | Public API request supports `real_hardware` environment. | `remove` or feature-gate private. |
| `backend/app/api/routes/chat/robotics.py:92` | Robotics command endpoint executes through LIMA bridge service. | `move private` or hard-disable for public build. |
| `backend/app/api/routes/chat/robotics.py:113` | Emergency-stop endpoint exposed under chat robotics API. | `needs Phil decision` - emergency stop is safety-critical and belongs only with actual robotics product. |
| `backend/app/api/routes/chat/tools.py:2014` | `lima_robot_command` tool definition. | `remove` from public tool catalog or keep private build only. |
| `backend/app/services/lima_robotics_bridge.py:31` | LIMA MCP bridge URL configuration and bridge logic. | `move private` or exclude from public shell; keep only stub interface if needed. |
| `backend/app/api/routes/chat/mcp.py:104` | Unified Sparkbot + LIMA MCP registry. | `simplify` - Sparkbot tool registry can remain; LIMA tool registry should be stubbed. |
| `docs/audits/HANDOFF_next_phase.md:1` | Guardian/Spine LIMA extraction handoff. | `move private` or exclude from public bundle. |
| `docs/audits/HANDOFF_next_phase.md:39` | Instructs copying Vault/Auth to LIMA. | `move private`; extraction implementation notes are not public shell docs. |
| `docs/audits/HANDOFF_next_phase.md:110` | References private live path `/home/sparky/sparkbot-v2/` and `remote.sparkpitlabs.com`. | `move private`; do not include private live paths in public package/docs. |
| `docs/audits/sparkbot_guardian_spine_extraction_audit.md:5` | Full Guardian Suite extraction audit. | `move private` or exclude from public bundle. |
| `docs/audits/sparkbot_guardian_spine_extraction_audit.md:708` | Phase plan to move Guardian core to LIMA. | `move private`; not public MVP. |
| `scripts/package-public-download.sh:129` | Removes a small list of internal docs but does not exclude `docs/audits/*` or Robo integration docs. | `rewrite` - expand public bundle exclusions. |
| `scripts/package-public-download.sh:127` | Public source bundle name still uses `sparkbot-v2`. | `rewrite` - public package names should align with current product/repo naming. |
| `docs/public-downloads.md:127` | Documents private publish directory `/var/www/sparkpitlabs.com/downloads/sparkbot/latest`. | `move private` - public install docs should not include private deployment paths. |
| `FRESH_INSTALL_CHECKLIST.md:15` | References private instance `remote.sparkpitlabs.com`. | `move private` or rewrite as generic self-hosted hostname example. |
| `docs/systemd-single-node.md:118` | References `api.sparkpitlabs.com` in public server setup context. | `rewrite` - use example domain placeholders. |
| `docs/release-readiness-v1.6.57.md:75` | References `api.sparkpitlabs.com` and older release readiness environment. | `move private` or keep only outside public bundle. |
| `.env.example:128` | Public template includes LIMA Robotics OS MCP bridge env vars. | `stub` - leave blank only if Robo teaser remains; otherwise remove from public template. |
| `.env.local.example:73` | Local template includes LIMA MCP bridge. | `stub` - hide under advanced/private notes. |
| `backend/app/api/routes/chat/agents.py:128` | Web designer prompt references Sparkbot, SparkPit Labs, LIMA AI, Guardian services, and related projects. | `rewrite` - public built-in agents need product-neutral prompts. |
| `backend/app/api/routes/chat/agents.py:205` | Marketing agent prompt references service packaging for SparkPit Labs/LIMA/Guardian. | `rewrite` or `move private`. |
| `backend/app/api/routes/chat/agents.py:278` | Business analyst prompt references SparkPit Labs/LIMA/Guardian. | `rewrite` or `move private`. |
| `README.md:485` | Production env template in public README includes placeholder `SECRET_KEY`, passphrase, and admin password. | `keep` - placeholders only; ensure examples remain non-secret and clearly generated by installer. |
| `.env.example:21` | Placeholder `SECRET_KEY`, `FIRST_SUPERUSER_PASSWORD`, `SPARKBOT_PASSPHRASE`. | `keep` - placeholders, not live secrets. |
| `.env.local.example:10` | Local default `SPARKBOT_PASSPHRASE=sparkbot-local`. | `keep` for local-only, but public server path must never use it. |
| `frontend/.env:1` | Tracked dev env has localhost API and Mailcatcher URL. | `keep` or `rewrite` - not secret, but a tracked `.env` file is confusing for public users. Consider `.env.example` instead. |
| `frontend/src/lib/apiBase.ts:71` | Reads `chat_token` from `sessionStorage` for auth fallback. | `needs Phil decision` - document as local-desktop-only or replace for public server mode. |
| `frontend/src/lib/localSession.ts:52` | Writes local chat token into browser session storage. | `needs Phil decision` - JS-readable token storage needs a public security stance. |
| `frontend/src/pages/WorkstationPage.tsx:4261` | Invite/model-seat config uses browser localStorage. | `rewrite` - provider credentials and model-seat auth state should live in backend config or Guardian Vault storage. |
| `frontend/src/pages/WorkstationPage.tsx:4585` | Invite config persistence reads/writes browser-local state. | `rewrite` - keep only non-sensitive UI preferences client-side. |
| `frontend/src/routes/__root.tsx:12` | TanStack Router Devtools mounted from root. | `rewrite` - gate to development builds. |
| `frontend/src/routes/__root.tsx:13` | React Query Devtools mounted from root. | `rewrite` - gate to development builds. |
| `frontend/src/components/Sidebar/AppSidebar.tsx:26` | Local-mode filter hides Workstation and `/chat`. | `rewrite` - public local shell navigation must include core public surfaces. |
| `frontend/src/routeTree.gen.ts:117` | Template Admin/Items routes remain generated. | `remove` from public shell if not supported. |
| `backend/app/api/routes/items.py:10` | FastAPI template Items API remains present. | `needs Phil decision` - remove or mark internal/admin-only before extraction. |
| `package.json:2` | Root package still named `fastapi-full-stack-template`. | `rewrite` - template residue, public polish issue. |
| `package.json:3` | Root package `private: true`. | `keep` - normal for workspace, not a secrecy leak. |
| `src-tauri/tauri.conf.json:5` | Identifier `com.sparkpitlabs.sparkbot.local`. | `needs Phil decision` - likely okay for SparkPit Labs ownership; decide before `Sparkbot_shell` branding. |
| `docs/public-downloads.md:28` | Public install docs use `github.com/armpit-symphony/Sparkbot.git`. | `keep` for current repo; revisit after shell extraction. |
| `docs/index.html:1004` | Public downloader points to `armpit-symphony/Sparkbot` release artifacts. | `keep` for current release; revisit after shell extraction. |
| `README.md:29` | "Everything agent" control-plane copy includes robot skills. | `rewrite` - too broad for public MVP. |
| `README.md:342` | Computer Control copy includes server/browser/terminal/SSH/comms reads. | `simplify` - keep local operator tools but make public safety boundaries clearer. |
| `README.md:376` | Command Center docs preserve Guardian Spine internals. | `simplify` - public docs should not foreground Spine internals. |
| `README.md:611` | Release history references OpenClaw, WEPO, Kalshi, and `/home/sparky/kalshi-bot`. | `move private` or rewrite historical notes before public packaging. |
| `release-notes.md:25` | Release notes reference Kalshi/OpenClaw/WEPO internal workloads. | `move private` or rewrite. |
| `release-notes.md:35` | Release notes mention `/home/sparky` workload paths. | `move private` or rewrite. |
| `backend/tests/api/routes/test_chat_server_ops.py:204` | Test fixtures include `/home/sparky` paths. | `keep in private R&D repo`; do not carry into public shell tests unless generalized. |
| `backend/app/api/routes/chat/tools.py:197` | Tooling defaults include `sparkbot-v2` service naming. | `rewrite` for public naming consistency before extraction. |
| `backend/app/api/routes/chat/tools.py:4714` | Tool comments/paths reference Kalshi workload handling. | `move private` or rewrite as generic operator example. |
| `docs/capabilities.md:1529` | MCP approval routes documented. | `needs Phil decision` - Sparkbot MCP explain-plan may be public, LIMA MCP should be private/teaser. |
| `docs/capabilities.md:1533` | Robotics endpoints documented. | `move private` or `stub`. |
| `docs/release-readiness-v1.6.57.md:75` | LIMA Robo OS status in older release readiness doc. | `move private` or exclude from public bundle. |
| `docs/release-notes/v1.6.57.txt:6` | Release note includes robotics bridge endpoints. | `keep historical` but avoid surfacing in public marketing as core. |
| `.github/workflows/deploy-production.yml:1` | Production deployment workflow remains in the R&D repo. | `needs Phil decision` - exclude/replace for public shell if it encodes private infra assumptions. |
| `.github/workflows/deploy-staging.yml:1` | Staging deployment workflow remains in the R&D repo. | `needs Phil decision` - exclude/replace for public shell if it encodes private infra assumptions. |

## Risk Summary

P0 public/private boundary risks:

- Robo OS is implemented and documented as more than a teaser.
- Robotics API/tool paths are present in public backend routes and tool catalog.
- Internal Guardian/LIMA extraction docs are still in `docs/audits` and would be included by current source-bundle packaging.
- Built-in agent prompts include SparkPit/LIMA/Guardian service business references.
- Invite Wing/model-seat config can be browser-local, which is not acceptable for public provider credentials.
- Private instance paths and internal workload examples remain in docs/history and need rewrite or exclusion before public packaging.
- Developer tools and template routes are still wired into app surfaces and should not ship as public beta defaults.

No live committed secrets were identified in the static credential-pattern scan. The main risk is not leaked credentials; it is publishing too much R&D, robotics, and internal extraction intent as public core.
