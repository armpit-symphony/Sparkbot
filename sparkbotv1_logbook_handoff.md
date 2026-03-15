# sparkbotv1_logbook_handoff.md
# Sparkbot v1 Local — Release Program Document
# Created: 2026-03-12

---

## Objective

Turn the current Sparkbot v2 codebase into a public Sparkbot v1.0 Local release
that installs grandmother-proof on Windows: one installer, a few Next/OK clicks,
app opens, Controls guides setup, user reaches chat.

No Docker. No WSL. No terminal. No Docker Desktop. No Postgres. No command line.

The current live private deployment at `remote.sparkpitlabs.com` MUST NOT be
disrupted by any work in this track. All changes must remain branch- or
feature-flag-safe relative to the running server.

---

## Non-Negotiable Release Standard

The install experience must be:

```
1. Download sparkbot-setup.exe
2. Double-click installer
3. Click Next / Next / Install / Finish (standard Windows installer UX)
4. App opens automatically
5. Controls panel opens on first run
6. User enters one API key (or selects Ollama)
7. User starts chatting
```

No knowledge of Docker, WSL, Python, Node, PowerShell, or terminals is required.
If a grandmother cannot do it, it does not ship.

---

## Why the Current Windows Path Is Not Acceptable

Grounded in actual repo files:

**`scripts/quickstart.ps1` (line 20-35):**
The first thing it does is check for `docker` in PATH and then check that the
Docker daemon is running. If either fails, it prints "Install Docker Desktop from
docs.docker.com" and exits. The entire local path requires Docker Desktop to be
installed and running before a single line of product code runs.

**`compose.local.yml` (full file):**
Defines 4 containers that must be orchestrated:
- `db`: postgres:18 image — a full database server container
- `prestart`: runs alembic migrations and seeds the first superuser
- `backend`: the FastAPI app, 4 uvicorn workers
- `frontend`: Nginx serving the built React app

Docker Compose orchestrates health checks, dependency ordering, and volume
management. None of this is visible to the user — it is all implementation
complexity — but it requires Docker Desktop, which:
- Requires a full install (500MB+) with admin rights on Windows
- Requires WSL2 on Windows (automatically installed by Docker Desktop, but adds
  another layer of "something went wrong" failure surface)
- Requires the Docker daemon to be running (not auto-started; users forget)
- Can fail on corporate Windows machines with security policies blocking WSL2
- Has its own login, update nags, and license prompts

**`scripts/quickstart.ps1` (line 69):**
The actual launch command: `docker compose -f compose.local.yml up --build -d`
This compiles Docker images from source on the user's machine. On first run this
takes 3-10 minutes and can fail for dozens of reasons (build errors, network
timeouts, disk space). There is no prebuilt installer that skips the build step.

**The public download on sparkpitlabs.com/sparkbot:**
Currently provides a ZIP file containing the full repo and a PowerShell script.
Same Docker dependency. Same failure surface. Not a click-to-install experience.

**Conclusion:** The current local path assumes a developer audience. It cannot
serve a general consumer audience. A completely different packaging approach is
required for v1 Local.

---

## Locked Product Definition — Sparkbot v1 Local

### v1 Local INCLUDES

| Feature | Surface | Notes |
|---------|---------|-------|
| Main chat | `/dm` — SparkbotDmPage | Core product. Streaming, slash commands, file analysis, voice |
| Controls panel | Embedded in SparkbotDmPage | Model config, provider setup, Guardian settings |
| First-run setup | Controls auto-open on empty config | Guides user to add API key or connect Ollama |
| Cloud AI path | Via existing litellm routing | OpenAI, Anthropic, Gemini, Groq — user brings API key |
| Local Ollama path | Via `/api/v1/chat/model/ollama/status` | No API key needed; Ollama runs separately |
| Simple persistence | SQLite | Already coded in `config.py`; no Postgres required |
| Clean install and launch | Windows installer (.exe) | See architecture section |
| User auth | Simple JWT; passphrase-based chat auth | Existing system, slightly simplified for local |
| Memory | User memory via `/api/v1/chat/memory` | Works with SQLite |
| Reminders | Asyncio background scheduler | Works without changes |
| File uploads | Images/PDFs via `/api/v1/chat/rooms/{id}/upload` | Works with SQLite |
| Voice | Whisper + TTS via `/api/v1/chat/voice` | Works; requires OpenAI key for cloud TTS |
| Skills | Skill plugin list | Read-only, no changes needed |

### v1 Local EXCLUDES OR DEFERS

| Feature | Reason |
|---------|--------|
| Workstation / live terminal | `os.openpty()` is POSIX-only; crashes on Windows natively. Feature-flag off. |
| Roundtable `/meeting/$roomId` | Not required for v1; hide route in local build |
| SparkBud surfaces | Already holdback gates (SparkBudPage.tsx shows "not yet public"). Exclude from local sidebar/nav |
| Admin panel `/admin` | Single-user local install has no multi-user admin need; hide |
| Items CRUD `/items` | Template leftover; remove from nav |
| Multi-room `/chat` | Single DM room is sufficient for v1 local; defer multi-room UI |
| Bot bridges (Telegram, Discord, WhatsApp, Slack, GitHub webhooks) | Always-loaded services add startup weight; make optional/lazy |
| Token Guardian complex mode | Keep basic Guardian; defer advanced token accounting |
| Dashboard command center `/` | Defer; make `/dm` the launch default route instead |
| SMTP email | Not needed for local single-user; configure silently as no-op |
| Sentry error tracking | Not needed for local; disable if SENTRY_DSN is empty |

### Hosted / Advanced Track KEEPS

The live deployment at `remote.sparkpitlabs.com` and any future hosted product
release retains ALL current features. Nothing is removed from the main branch.
v1 Local is achieved by:
- Feature flags controlling which services start
- Frontend build-time env var controlling which routes/nav items appear
- The installer packaging only the required subset

The main branch continues running the full stack. The live server is untouched.

---

## Technical Architecture Recommendation — v1 Local

### Target: Tauri Desktop App

```
sparkbot-setup.exe (Windows Installer — WiX or NSIS via Tauri)
└── Installs:
    ├── sparkbot.exe  (Tauri shell — Rust binary ~5MB)
    │   ├── WebView2 runtime (already on Win10/11; installer bootstraps if missing)
    │   ├── Embedded dist/ (React frontend, served via tauri://localhost)
    │   └── sparkbot-backend.exe  (PyInstaller-frozen Python sidecar)
    │       ├── FastAPI + uvicorn
    │       ├── litellm + all Python deps
    │       └── sparkbot.db (SQLite, stored in %APPDATA%\Sparkbot\)
    └── Start Menu shortcut → sparkbot.exe
```

**Why Tauri over Electron:**
- No bundled Chromium (~120MB saved); uses system WebView2 (pre-installed on Win10+)
- Total installer size estimate: 80-120MB (vs 250-350MB with Electron)
- Tauri v2 (stable as of late 2024) has first-class sidecar support for bundled
  executables — exactly what is needed to spawn the Python backend
- Better Windows integration: native system tray, native dialogs, proper AppData paths
- More secure: system WebView2 is kept updated by Windows Update
- The existing frontend is standard React/Vite — no Electron-specific APIs used;
  zero frontend changes required for Tauri vs Electron at the component level

**Why not Electron:**
- 120MB+ overhead for bundled Chromium that Windows already provides via WebView2
- No compelling advantage over Tauri for this use case
- More complex code-signing and notarization story

**One legitimate reason to prefer Electron:** if WebView2 compatibility is a real
concern on specific Windows versions (pre-1803). If testing reveals WebView2
issues, switch evaluation. Otherwise stay with Tauri.

### Runtime Flow

```
1. User launches sparkbot.exe (Tauri)
2. Tauri Rust core:
   a. Starts sparkbot-backend.exe sidecar (PyInstaller Python)
   b. Backend runs `alembic upgrade head` on SQLite db (fast; no network wait)
   c. Backend starts uvicorn on 127.0.0.1:8000
   d. Tauri polls http://127.0.0.1:8000/api/v1/utils/health-check/ until ready
   e. WebView2 navigates to tauri://localhost (serving embedded dist/)
3. Frontend loads
4. Frontend's OpenAPI client base URL is set to http://127.0.0.1:8000
5. If no model configured → Controls panel opens automatically
6. User configures API key or Ollama → starts chatting
7. On app close: Tauri sends SIGTERM to sidecar; backend shuts down cleanly
```

### Data Persistence

```
%APPDATA%\Sparkbot\
├── sparkbot.db              # SQLite — main app DB (users, rooms, messages, tasks, etc.)
├── guardian\
│   └── vault.db             # Guardian vault (separate SQLite, already used this way)
└── uploads\                 # Uploaded files
```

Config.py already supports this:
- `DATABASE_TYPE=sqlite` → default in `backend/app/core/config.py` line 53
- SQLite path derived from `PROJECT_NAME` → `sparkbot.db`
- Need to add: Tauri sidecar passes `--data-dir %APPDATA%\Sparkbot` to backend
  OR backend reads `SPARKBOT_DATA_DIR` env var to set the SQLite and uploads path

### AI Provider Paths

Both paths already work in the existing backend:

**Cloud path:** User enters API key in Controls → stored via `/api/v1/chat/model`
route → litellm routes to the appropriate provider. No changes needed.

**Ollama path:** Ollama runs as a separate desktop app (their own installer).
Backend calls `GET /api/v1/chat/model/ollama/status` → checks localhost:11434.
Existing implementation in `backend/app/api/routes/chat/model.py`. No changes needed.

---

## Repo-Grounded Audit Findings

### Files Inspected

| File | Purpose |
|------|---------|
| `scripts/quickstart.ps1` | Windows launch — Docker-only |
| `scripts/quickstart.sh` | Linux/Mac launch — Docker-only |
| `compose.local.yml` | 4-container local stack definition |
| `backend/app/core/config.py` | Settings — SQLite default confirmed (line 53) |
| `backend/app/core/db.py` | Engine creation — reads SQLALCHEMY_DATABASE_URI |
| `backend/app/main.py` | Startup tasks — bridges always loaded |
| `backend/pyproject.toml` | Dependencies — litellm MISSING as explicit dep |
| `backend/app/api/main.py` | Route aggregator |
| `backend/app/api/routes/terminal.py` | PTY terminal — POSIX only |
| `backend/app/services/terminal_service.py` | os.openpty() — breaks Windows |
| `backend/app/services/discord_bridge.py` | Always imported at startup |
| `backend/app/services/telegram_bridge.py` | Always imported at startup |
| `backend/app/services/whatsapp_bridge.py` | Always imported at startup |
| `frontend/src/routes/` | All route definitions (16 routes) |
| `frontend/src/pages/SparkbotDmPage.tsx` | Main chat surface (3,764 lines) |
| `frontend/src/pages/WorkstationPage.tsx` | Workstation/terminal (3,545 lines) |
| `frontend/src/components/Common/SparkbotSurfaceTabs.tsx` | Nav tabs |
| `frontend/src/components/Sidebar/Main.tsx` | Sidebar nav |
| `frontend/vite.config.ts` | Build config — Vite 7 + Tauri-compatible |
| `dist/` | Pre-built frontend — exists in repo |

### Blocker 1: No bare-metal startup path
**Severity: CRITICAL**
There are zero non-Docker startup scripts for the backend. `backend/setup_chat.sh`
exists but references `app.models.chat.models` which does not exist in the current
codebase. It is dead code from v1. A bare-metal `start-local.ps1` / `start-local.sh`
and a PyInstaller spec file do not exist. Both must be created from scratch.

### Blocker 2: Dependency state is broken — uv.lock stale, litellm untracked
**Severity: CRITICAL — fix before anything else**

**Confirmed by direct inspection (2026-03-12):**

The `uv.lock` file (2470 lines) lists only 75 packages. It is MISSING the following
packages that ARE declared in `backend/pyproject.toml`:
- `cryptography>=44.0.0,<46.0.0` — in pyproject.toml, NOT in uv.lock
- `discord.py>=2.3.2` — in pyproject.toml, NOT in uv.lock
- `pywa[fastapi]>=2.0.0` — in pyproject.toml, NOT in uv.lock

This means `uv lock` was NOT re-run after these deps were added to pyproject.toml.
Running `uv sync --frozen` (what the Dockerfile does) would currently FAIL because
pyproject.toml requests packages that are absent from the lock file.

The live Docker containers on `remote.sparkpitlabs.com` were built from an older
image where the lock file was in sync. They are running fine, but a fresh
`docker compose up --build` from this repo state would fail to build.

Additionally, `litellm` is imported in 4 backend files:
- `backend/app/api/routes/chat/llm.py` (839 lines — core chat)
- `backend/app/api/routes/chat/tools.py` (3,850 lines — all tools)
- `backend/app/api/routes/chat/uploads.py` (vision)
- `backend/app/api/routes/chat/rooms.py`

`litellm` is in NEITHER `pyproject.toml` NOR `uv.lock`. It must be installed
manually in the running server's venv or Docker image. Any fresh install — bare-metal
or Docker — will fail with ImportError on llm.py.

**Required fix before ANY other work:**
```bash
cd /home/sparky/sparkbot-v2
# 1. Add litellm to backend/pyproject.toml dependencies
# 2. Regenerate the lock file:
uv lock
# 3. Verify all declared deps are now in uv.lock:
grep -E "litellm|cryptography|discord|pywa" uv.lock
# 4. Test: uv sync installs cleanly
uv sync
```

Do NOT run `uv sync --frozen` until after the lock file is regenerated.
Do NOT build a new Docker image until this is resolved.

### Blocker 3: os.openpty() on Windows
**Severity: HIGH for workstation, LOW for v1 local**
`backend/app/services/terminal_service.py` uses `os.openpty()` which is POSIX-only.
On Windows (outside WSL2) this raises `AttributeError: module 'os' has no attribute
'openpty'`. The import happens at module level in `main.py` via the `terminal`
route import. If the terminal route is imported on Windows, the app crashes at startup.

**Fix:** Guard the import in `backend/app/api/main.py` with:
```python
if settings.WORKSTATION_LIVE_TERMINAL_ENABLED:
    from app.api.routes import terminal
    api_router.include_router(terminal.router, ...)
```
`WORKSTATION_LIVE_TERMINAL_ENABLED` already exists in `config.py`. Just make the
import conditional, not just the startup task. This is a 5-line fix.

### Blocker 4: Bridge services always loaded at startup
**Severity: MEDIUM**
`backend/app/main.py` imports at module level:
```python
from app.services.telegram_bridge import telegram_polling_loop
from app.services.discord_bridge import discord_bot_task
from app.services.whatsapp_bridge import register_whatsapp_bridge
```
These imports pull in `telegram`, `discord.py`, `pywa` packages regardless of
whether the tokens are set. On Windows, `discord.py` and `pywa` require binary
packages (`aiohttp`, etc.) that add bundling complexity. More importantly,
they add startup time and a potential crash surface.

**Fix:** Make the bridge imports conditional on env vars being set, or add a
`BRIDGES_ENABLED=false` flag that skips all bridge imports.

### Blocker 5: No Tauri or installer infrastructure
**Severity: HIGH — requires new work**
Confirmed: zero Tauri/Electron setup in the repo. No `src-tauri/`, no `Cargo.toml`
at the desktop level, no `electron.js`. The entire desktop shell must be built
from scratch. This is the largest single workstream by effort.

### Blocker 6: Frontend API base URL baked in at Docker build time
**Severity: MEDIUM**
`compose.local.yml` line 115: `VITE_API_URL=http://localhost:8000` is injected as a
Docker build arg. The auto-generated client at `frontend/src/client/core/OpenAPI.ts`
reads this at build time. For the Tauri build, this must be set to
`http://127.0.0.1:8000` (same thing). But the Tauri build pipeline needs to
explicitly pass `VITE_API_URL=http://127.0.0.1:8000` to `vite build`. This is
a configuration issue, not a code change. Low effort, but must not be forgotten.

### What is already in good shape (no changes needed)
- SQLite: `DATABASE_TYPE=sqlite` is the config.py default. No code changes needed.
- Alembic: migrations are SQLAlchemy-generic; SQLite is supported.
- Guardian vault: already uses its own separate SQLite DB (`data/guardian/vault.db`).
- SparkBud routes: already stub/gate pages — safe to hide from v1 local nav.
- Controls: already in SparkbotDmPage.tsx. First-run logic needs verification only.
- litellm itself: works identically on Windows; just needs to be declared as a dep.
- Ollama integration: existing `/api/v1/chat/model/ollama/status` works on Windows.
- Voice: Whisper transcription works via API; TTS works via OpenAI; no PTY needed.

---

## Implementation Workstreams

---

### Workstream A — Scope Freeze and Feature Gating

**Objective:** Add a `V1_LOCAL_MODE` feature flag. When set, the backend skips
PTY/terminal startup safely, skips bridge service loading, and the frontend hides
nav items for workstation/meeting/sparkbud/admin/items.

**Real files involved:**
- `backend/app/core/config.py` — add `V1_LOCAL_MODE: bool = False`
- `backend/app/main.py` — wrap bridge imports in conditional blocks
- `backend/app/api/main.py` — make terminal router include conditional
- `frontend/src/components/Sidebar/Main.tsx` — read `VITE_V1_LOCAL_MODE` build var
- `frontend/src/components/Common/SparkbotSurfaceTabs.tsx` — hide workstation/meeting tabs
- `frontend/src/routes/` — can leave routes in the router; just hide from nav
- `frontend/vite.config.ts` — pass `VITE_V1_LOCAL_MODE=true` for local build

**What "done" means:**
- `V1_LOCAL_MODE=true` starts the backend without `os.openpty()` being called
- Backend starts cleanly on Windows with no bridge import errors
- Frontend built with `VITE_V1_LOCAL_MODE=true` shows only: DM chat, Settings
  (Controls is embedded in DM). Workstation, Meeting, SparkBud, Admin, Items
  are not visible in nav.
- The main branch without the flag behaves identically to today.

**Out of scope:** Removing any routes or backend services. Flag-only. No deletions.

---

### Workstream B — Non-Docker Local Backend Path

**Objective:** Create a bare-metal startup path that runs the Python backend
without Docker on any OS, including Windows. This is the foundation for packaging.

**Real files involved:**
- `backend/pyproject.toml` — add `litellm` as explicit dependency; add optional
  `[project.optional-dependencies] bridges = [...]` group for telegram/discord/pywa
- `scripts/start-local-backend.ps1` — NEW: Windows bare-metal startup script
  (sets DATABASE_TYPE=sqlite, sets WORKSTATION_LIVE_TERMINAL_ENABLED=false,
  runs `uv run alembic upgrade head`, then `uv run fastapi run app/main.py --port 8000`)
- `scripts/start-local-backend.sh` — NEW: same for Linux/Mac
- `backend/scripts/prestart.sh` — add guard: skip Postgres wait loop if DATABASE_TYPE=sqlite
- `backend/app/backend_pre_start.py` — same guard

**What "done" means:**
- On a fresh Windows machine with Python 3.10+ and `uv` installed, running
  `scripts/start-local-backend.ps1` starts the backend on port 8000 without
  Docker, without Postgres, without any bridge errors.
- SQLite DB is created automatically on first run.
- Alembic migrations run against SQLite without errors.
- `GET http://localhost:8000/api/v1/utils/health-check/` returns 200.

**Out of scope:** Full installer. This workstream proves the backend runs bare-metal.
The Tauri sidecar in Workstream D will use the PyInstaller output, not this script.

---

### Workstream C — SQLite Local Persistence Validation

**Objective:** Verify the entire SQLite path works end-to-end. The config.py says
it works, but it has only been run against Postgres in production. SQLite has
type constraints that can fail silently on Alembic migrations.

**Real files involved:**
- `backend/app/alembic/versions/` — all 10+ migration files; audit for Postgres-isms
- `backend/app/core/config.py` — add `SPARKBOT_DATA_DIR` env var to control DB path
- `backend/app/core/db.py` — use `SPARKBOT_DATA_DIR` to build SQLite path if set
- `backend/app/services/guardian/vault.py` — make vault DB path respect `SPARKBOT_DATA_DIR`
- `backend/app/api/routes/chat/uploads.py` — make upload directory respect `SPARKBOT_DATA_DIR`

**What "done" means:**
- Complete bare-metal startup with `DATABASE_TYPE=sqlite` runs without errors.
- All alembic migrations apply cleanly to a fresh SQLite DB.
- Chat works: create room, send message, receive LLM response, stored in SQLite.
- Guardian vault works: create/use/delete vault entry.
- Data is stored in `SPARKBOT_DATA_DIR` (for installer: `%APPDATA%\Sparkbot\`).
- No orphaned Postgres references remain in the SQLite startup path.

**Out of scope:** Postgres migration testing. Postgres path is unchanged.

---

### Workstream D — Desktop Shell and Installer

**Objective:** Build the Tauri wrapper, PyInstaller spec, and Windows installer.
This is the largest workstream and the one that turns "it runs bare-metal" into
"grandmother can install it."

**Real files involved (new):**
- `src-tauri/` — NEW directory; full Tauri v2 project
  - `src-tauri/Cargo.toml` — Tauri app manifest
  - `src-tauri/tauri.conf.json` — app config: identifier, version, window settings,
    sidecar allowlist, file system permissions for AppData
  - `src-tauri/src/main.rs` — Tauri main: spawn sidecar, poll health check, open window
  - `src-tauri/icons/` — app icons (PNG set required by Tauri)
- `sparkbot-backend.spec` — NEW: PyInstaller spec file
  - Includes all of: fastapi, uvicorn, sqlmodel, alembic, litellm, pyjwt, cryptography,
    pwdlib, httpx, python-multipart, jinja2, pydantic, pydantic-settings, sentry-sdk
  - Hidden imports for litellm's dynamic provider loading
  - Excludes: psycopg (not needed for SQLite path), discord.py, pywa, telegram
    (when V1_LOCAL_MODE=true)
  - Data files: alembic.ini, alembic/versions/, email templates
- `scripts/build-local-windows.ps1` — NEW: full build script
  - Step 1: `bun install` + `VITE_API_URL=http://127.0.0.1:8000 bun run build` in frontend/
  - Step 2: `pip install pyinstaller && pyinstaller sparkbot-backend.spec`
  - Step 3: copy dist/ and sparkbot-backend.exe into Tauri's resource dir
  - Step 4: `cargo tauri build` to produce the installer

**Real files modified:**
- `frontend/package.json` — add `tauri` script: `tauri dev` / `tauri build`
- `frontend/vite.config.ts` — add Tauri-compatible server config (port 5173 for dev)
- `package.json` (root) — add Tauri build task to workspace

**What "done" means:**
- `cargo tauri build` produces `sparkbot-setup.exe` in `src-tauri/target/release/bundle/`
- Running `sparkbot-setup.exe` on a fresh Windows 10/11 VM (no Docker, no Python, no Node):
  - Installs to Program Files (or user AppData if non-admin install chosen)
  - Creates Start Menu entry
  - Launches Sparkbot
  - WebView2 opens showing the frontend
  - Backend health check passes
  - User can reach chat

**Out of scope (Workstream D):** macOS/Linux packaging. Windows first. CI/CD pipeline.
Code signing / Authenticode (required before public release but not for milestone done).

---

### Workstream E — Controls First-Run Simplification

**Objective:** Verify and harden the first-run experience. When a user installs
fresh with no API keys configured, the Controls panel must open automatically and
guide them to a working configuration.

**Real files involved:**
- `frontend/src/pages/SparkbotDmPage.tsx` (3,764 lines) — find the Controls panel
  open trigger; verify it fires when no model is configured
- `backend/app/api/routes/chat/model.py` — `GET /api/v1/chat/model` returns the
  current model config; if empty/default, frontend triggers Controls open
- `frontend/src/lib/sparkbotControls.ts` — Controls panel state management

**What needs verification (not assumed):**
- Does SparkbotDmPage already auto-open Controls on first run? Read the component
  to find the trigger condition.
- Does `GET /api/v1/chat/model` return a state that the frontend interprets as
  "not configured yet"? The backend seeds a default model config in `initial_data.py` —
  what is that default? Does the frontend treat it as "needs setup"?
- If Controls does not auto-open: add a `useEffect` that checks model config on
  mount and opens Controls if no provider key is set.

**What "done" means:**
- Fresh install: user opens app → Controls panel is visible before any chat input
  is possible.
- Controls guides user through: pick provider (cloud vs local Ollama), enter key
  or confirm Ollama URL, confirm model selection, close Controls.
- After Controls close: user can send a message and get a response.
- No "undefined model" errors or silent failures.

**Out of scope:** Redesigning the Controls UI. This workstream is about wiring the
existing Controls correctly for first-run, not rebuilding it.

---

### Workstream F — Public Site and Packaging Honesty

**Objective:** Update the download on sparkpitlabs.com to offer the v1 Local
Windows installer as the primary download, replacing ZIP+PowerShell as the
consumer-facing story.

**Real files involved (on server):**
- `/var/www/sparkpitlabs.com/sparkbot/index.html` — update Windows download section
- `/var/www/sparkpitlabs.com/downloads/sparkbot/latest/` — add sparkbot-setup.exe
- `/var/www/sparkpitlabs.com/downloads/sparkbot/1.0.0-local/` — versioned dir

**What "done" means:**
- Primary CTA on the public page: "Download for Windows (.exe)" linking to
  `sparkbot-setup.exe`.
- ZIP+PowerShell path moved to "Advanced / Power Users" section.
- SHA256 checksum listed for the .exe.
- Version clearly labeled v1.0.0-local (or v1.0 Local) with brief feature list.
- Page does NOT promise features that are not in v1 Local (no workstation,
  no roundtable).

**Out of scope:** Full site redesign. Copy and download-link updates only.

---

### Workstream G — Clean-Room QA

**Objective:** Verify grandmother-proof install on a fresh Windows 10/11 VM with
no developer tools pre-installed.

**Test matrix:**
1. Windows 11 (fresh VM, no Docker, no Python, no Node, no WSL)
   - Install sparkbot-setup.exe
   - First-run → Controls → OpenAI key → chat
   - Restart machine → relaunch → chat still works (data persisted)
2. Windows 11 with Ollama pre-installed
   - Install sparkbot-setup.exe
   - First-run → Controls → select Ollama → chat
3. Windows 10 (1803+) — same tests as Win11
4. Windows 10 (pre-1803 or no WebView2) — expect installer to bootstrap WebView2

**Using:** `FRESH_INSTALL_CHECKLIST.md` as the basis; update it with v1-local-specific steps.

**What "done" means:**
- All 4 test scenarios pass without any developer intervention.
- No terminal windows visible to the user during normal use.
- App launches in under 10 seconds after clicking the Start Menu shortcut
  (after first-run is complete; first launch may be slower due to DB init).

---

## Implementation Order (Official)

```
Phase 0: Fix broken dependency state        ← COMPLETED 2026-03-12
Phase 1: Make backend run bare-metal on Windows
Phase 2: Add local-mode gating and simplify local frontend
Phase 3: Build Tauri + PyInstaller installer path
```

---

## Exact First Implementation Steps

The following is the ordered coding pass to start immediately. This list assumes
the goal is to reach a working bare-metal backend (no Docker) as quickly as possible,
then build up to the installer. Each step is a concrete file change.

**Phase 0: Fix the broken dependency state — COMPLETED 2026-03-12**

0. **Fixed uv.lock and added litellm to `backend/pyproject.toml`**

   **What was broken:**
   - `uv.lock` had 75 packages (2470 lines); declared deps `cryptography`, `discord.py`,
     `pywa` were in `pyproject.toml` but absent from the lock file
   - `litellm` was used in 4 backend route files but declared in neither
     `pyproject.toml` nor `uv.lock`
   - Fresh `docker compose up --build` or bare-metal `uv sync` would have failed

   **What was done:**
   1. Added `"litellm>=1.0.0,<2.0.0"` to `backend/pyproject.toml` dependencies
   2. Installed uv v0.10.9 on the host via `curl -LsSf https://astral.sh/uv/install.sh | sh`
      (uv was only available inside Docker, not on the host)
   3. Ran `uv lock` from repo root → resolved 118 packages (3977 lines)
   4. Ran `uv sync` → installed 112 packages cleanly, zero errors

   **Verified results:**
   - `litellm==1.82.1` — in lock, imports clean
   - `cryptography==45.0.7` — in lock, imports clean
   - `discord-py==2.7.1` — in lock, imports clean
   - `pywa==3.9.0` — in lock, imports clean
   - `uv lock --check` → passes (lock is consistent with pyproject.toml)
   - `app/core/config.py` imports without errors from the new venv

   **Remaining anomaly (non-blocking):**
   - `pywa` resolved to v3.9.0 but pyproject.toml constraint is `>=2.0.0` with no upper
     bound. pywa had breaking API changes between v2 and v3. The running server was built
     from an image where pywa was not yet installed (the old lock was stale before pywa
     was added to pyproject.toml). Before deploying a fresh Docker image, verify the
     WhatsApp bridge code (`backend/app/services/whatsapp_bridge.py`) is compatible with
     pywa 3.x. Consider adding `<4.0.0` upper bound after testing.
   - `uv` is not in the system PATH; it is at `/home/sparky/.local/bin/uv`. Add to PATH
     or use full path for future uv commands.

**Phase 1: Make the backend run bare-metal on Windows — COMPLETED 2026-03-12**

See Phase 1 session log for full detail. Summary of what was done:
1. `V1_LOCAL_MODE` and `SPARKBOT_DATA_DIR` added to `config.py`
2. Terminal router import made conditional on `WORKSTATION_LIVE_TERMINAL_ENABLED` in `api/main.py`
3. Bridge imports/startup/shutdown made conditional on `V1_LOCAL_MODE` in `main.py`
4. Bridge status imports in `model.py` made lazy — `_build_comms_status()` with deferred import
5. `alembic/env.py` unchanged — SQLite init uses `local_db_init.py` instead
6. `local_db_init.py` created — `create_all` + `alembic stamp head` for SQLite
7. `backend/scripts/prestart.sh` updated — calls `local_db_init.py` for SQLite
8. `scripts/start-local-backend.sh` created — bare-metal Linux/Mac startup
9. `scripts/start-local-backend.ps1` created — bare-metal Windows startup
10. Backend verified to start with V1_LOCAL_MODE=true, SQLite, no POSIX crash, no bridge import, clean logs

2. **Add `V1_LOCAL_MODE` to `backend/app/core/config.py`**
   ```python
   V1_LOCAL_MODE: bool = False
   WORKSTATION_LIVE_TERMINAL_ENABLED: bool = True  # already exists
   SPARKBOT_DATA_DIR: str = ""  # empty = use current dir default
   ```

3. **Make terminal router import conditional in `backend/app/api/main.py`**
   Find `from app.api.routes import terminal` and guard it:
   ```python
   if settings.WORKSTATION_LIVE_TERMINAL_ENABLED:
       from app.api.routes import terminal
       api_router.include_router(terminal.router, prefix="/terminal", tags=["terminal"])
   ```
   This prevents `os.openpty()` from being called on Windows.

4. **Make bridge imports conditional in `backend/app/main.py`**
   Wrap the three bridge service imports and their startup tasks in:
   ```python
   if not settings.V1_LOCAL_MODE:
       from app.services.telegram_bridge import telegram_polling_loop
       from app.services.discord_bridge import discord_bot_task
       from app.services.whatsapp_bridge import register_whatsapp_bridge
   ```
   Guard the corresponding `asyncio.create_task()` calls and `register_whatsapp_bridge(app, get_db)` similarly.

5. **Add `SPARKBOT_DATA_DIR` path resolution to `backend/app/core/db.py`**
   Modify the SQLite URI to use the data dir if set:
   ```python
   if settings.DATABASE_TYPE == "sqlite":
       if settings.SPARKBOT_DATA_DIR:
           db_path = Path(settings.SPARKBOT_DATA_DIR) / f"{settings.PROJECT_NAME.lower().replace(' ', '_')}.db"
           return f"sqlite:///{db_path}"
       return f"sqlite:///{settings.PROJECT_NAME.lower().replace(' ', '_')}.db"
   ```

6. **Make vault DB path respect `SPARKBOT_DATA_DIR` in `backend/app/services/guardian/vault.py`**
   The vault currently hardcodes `data/guardian/vault.db`. Parameterize it via settings.

7. **Update `backend/scripts/prestart.sh` to skip Postgres wait if SQLite**
   ```bash
   if [ "$DATABASE_TYPE" != "sqlite" ]; then
       python app/backend_pre_start.py
   fi
   alembic upgrade head
   python app/initial_data.py
   ```

8. **Create `scripts/start-local-backend.ps1`** (NEW file)
   Sets env vars (`DATABASE_TYPE=sqlite`, `V1_LOCAL_MODE=true`,
   `WORKSTATION_LIVE_TERMINAL_ENABLED=false`, `ENVIRONMENT=local`,
   `SECRET_KEY` auto-generated, `FIRST_SUPERUSER=admin@localhost`,
   `FIRST_SUPERUSER_PASSWORD=sparkbot-local`, `SPARKBOT_PASSPHRASE=sparkbot-local`),
   then runs: `uv run alembic upgrade head && uv run fastapi run app/main.py --port 8000`

9. **Test bare-metal startup on Windows (or in WSL2 as proxy)**
   Run `scripts/start-local-backend.ps1`. Verify:
   - Backend starts without errors
   - SQLite DB created in project dir
   - `GET /api/v1/utils/health-check/` returns 200
   - Can create a chat user and send a message

**Phase 2: Frontend V1 local build (1-2 hours)**

10. **Add `VITE_V1_LOCAL_MODE` env check to `frontend/src/components/Sidebar/Main.tsx`**
    Read the file first to find the nav item rendering. Add:
    ```typescript
    const isV1Local = import.meta.env.VITE_V1_LOCAL_MODE === 'true'
    ```
    Hide nav items for workstation, meeting, sparkbud, admin, items when true.

11. **Add same check to `frontend/src/components/Common/SparkbotSurfaceTabs.tsx`**
    Hide the Workstation tab when `isV1Local`.

12. **Verify Controls auto-open on first run**
    Read `frontend/src/pages/SparkbotDmPage.tsx` around the Controls panel mount.
    If no auto-open trigger exists for "no model configured" state, add one.

13. **Test frontend build with V1 local flags:**
    ```
    VITE_API_URL=http://127.0.0.1:8000 VITE_V1_LOCAL_MODE=true bun run build
    ```
    Open the built `dist/` against the running bare-metal backend. Verify chat works.

**Phase 3: Tauri scaffold (4-8 hours)**

14. **Initialize Tauri v2 project at repo root:**
    ```
    cargo install tauri-cli
    cargo tauri init
    ```
    Configure for `frontendDist: "../frontend/dist"` and `devUrl: "http://localhost:5173"`.

15. **Create `sparkbot-backend.spec`** (PyInstaller spec)
    - Entry point: `backend/app/main.py` via uvicorn programmatic API
    - Or: a thin `sparkbot_backend_entry.py` wrapper that calls uvicorn.run()
    - Hidden imports: litellm's provider modules (they use dynamic imports)
    - Data: alembic.ini, versions/, email templates
    - Excludes: discord, pywa, telegram, psycopg (when V1_LOCAL_MODE)

16. **Write Tauri sidecar launch code in `src-tauri/src/main.rs`**
    - Start `sparkbot-backend` sidecar on app launch
    - Poll health check endpoint with retry + timeout
    - Show "Starting..." window while backend warms up
    - On backend ready: navigate main window to the frontend URL

17. **Test Tauri dev mode:**
    ```
    cargo tauri dev
    ```
    Backend sidecar should start, health check should pass, frontend should load.

**Phase 4: Installer and QA**

18. **Test PyInstaller build:**
    ```
    pyinstaller sparkbot-backend.spec
    ```
    Run the resulting `.exe` and verify all routes work (particularly litellm call).

19. **Build Windows installer:**
    ```
    cargo tauri build
    ```
    Test on a fresh Windows VM.

20. **Run FRESH_INSTALL_CHECKLIST.md on the VM.**
    Fix any failures. Do not ship until all checklist items pass.

---

## Release Gates

The following must ALL be true before publishing v1 Local:

| Gate | Status |
|------|--------|
| litellm explicit in pyproject.toml | DONE (2026-03-12) |
| V1_LOCAL_MODE flag exists | DONE (2026-03-12) |
| Terminal import is conditional (Windows safe) | DONE (2026-03-12) |
| Bridge imports conditional (V1_LOCAL_MODE) | DONE (2026-03-12) |
| SQLite path tested end-to-end bare-metal | DONE (2026-03-12) |
| SPARKBOT_DATA_DIR puts DB in %APPDATA% | DONE in script; vault.db path pending |
| Tauri scaffold created | NOT DONE |
| PyInstaller build succeeds | NOT DONE |
| Installer produced by `cargo tauri build` | NOT DONE |
| Fresh Windows 11 VM: install → chat in < 10 minutes | NOT DONE |
| Fresh Windows 11 VM: Ollama path tested | NOT DONE |
| Controls auto-opens on fresh install | UNVERIFIED |
| sparkpitlabs.com updated | NOT DONE |
| GitHub tag v1.0.0-local or v1.0 | NOT DONE |
| Code-signed installer (Authenticode) | NOT DONE — required for public release |
| live server at remote.sparkpitlabs.com unaffected | ONGOING (verify after each change) |

---

## Risks and Unknowns

**R1 — PyInstaller + litellm complexity (HIGH)**
litellm uses dynamic imports and lazy provider loading. PyInstaller's static analysis
will miss many of these. The hidden imports list in the spec will need iteration.
Expected: 3-5 build → test → fix cycles before the PyInstaller binary works end-to-end.
Mitigation: test with a single provider (OpenAI) first, add others incrementally.

**R2 — Alembic SQLite compatibility (MEDIUM)**
The migrations were written for Postgres. SQLite has limitations:
- No `ALTER COLUMN` (SQLite doesn't support column type changes)
- No `DROP COLUMN` in older SQLite versions
Some migrations may use `op.alter_column()` with type changes that fail on SQLite.
Must audit all 10+ migration files before claiming the SQLite path works.

**R3 — WebView2 on older Windows (LOW for Win10/11, MEDIUM for Win7/8)**
Tauri's Windows installer can bootstrap WebView2 via Microsoft's evergreen bootstrapper.
On Windows 10 (1803+) and Windows 11 this is a no-op (WebView2 already present).
On Windows 7/8: WebView2 is not supported. Decision: target Windows 10+ only.
State this minimum requirement clearly on the download page.

**R4 — Anti-virus false positives on PyInstaller exe (MEDIUM)**
PyInstaller-packed Python executables are commonly flagged by Windows Defender and
third-party AV. Code signing (Authenticode) significantly reduces but does not
eliminate this. Budget time for AV false positive investigation.
Mitigation: Code signing is a release gate (see above). Get the cert before the
build. EV code signing virtually eliminates false positives but costs more.

**R5 — Backend startup time (LOW-MEDIUM)**
litellm is large. The PyInstaller-frozen backend may take 3-8 seconds to start.
The Tauri sidecar launcher should show a "Starting Sparkbot..." state rather than
a blank window or appearing hung.

**R6 — litellm not in pyproject.toml (CRITICAL — must fix before anything else)**
If litellm was installed manually into the venv and is not tracked in pyproject.toml,
any fresh `uv sync` will NOT install it. This would make every bare-metal startup
fail with ImportError. Fix this first.

**R7 — Controls first-run behavior unverified (MEDIUM)**
SparkbotDmPage.tsx is 3,764 lines. The Controls auto-open behavior for a fresh
install has not been read/verified. It may already work correctly, or it may
require an explicit first-run trigger to be added. Must read before coding Workstream E.

**R8 — Live server stability during branch work (LOW but HIGH consequence)**
The live deployment at `remote.sparkpitlabs.com` runs from the main branch or a
production branch. All v1 local work should happen on a `v1-local` feature branch
and only merge to main after verification that the feature flags do not affect the
hosted path. Never push direct-to-main without testing the hosted startup path.

---

## Recommended Next Action

**Step 1 (do first, 30 minutes):**
On the bare-metal server, check whether litellm is in `uv.lock`:
```bash
grep "litellm" /home/sparky/sparkbot-v2/uv.lock | head -5
```
If it is there, add it explicitly to `pyproject.toml`. If it is NOT there,
investigate how `llm.py` is currently running — there may be an env-local
install that is not tracked.

**Step 2 (same session):**
Make the three changes to `config.py`, `api/main.py`, and `main.py` described
in Phase 1 steps 2-4. These are small, low-risk, and unlock safe bare-metal startup.

**Step 3 (same session):**
Create `scripts/start-local-backend.ps1`. Run it. Prove the backend starts without
Docker. This is the foundation everything else builds on. Until this works, the
installer work has no foundation to stand on.

**Step 4 (next session):**
Audit all alembic migration files for SQLite-incompatible operations. Fix any that
exist. Run a fresh SQLite migration. Send a real chat message through the bare-metal backend.

**Step 5 (separate work session):**
Initialize the Tauri v2 project. Do not skip to this before Steps 1-4 are solid.
The Tauri work is wasted effort if the bare-metal Python backend is not proven.

**Do NOT do in parallel:**
Do not start the Tauri work while the bare-metal Python path is unproven.
The sidecar packaging is the last step, not the first.

---

## Note on the Live Server

`remote.sparkpitlabs.com` is the operator's personal live instance running the
full Sparkbot v2 stack. It must remain running and unaffected throughout all
v1 local development work.

All v1 local changes should be made on a `v1-local` branch. The feature flags
(V1_LOCAL_MODE, WORKSTATION_LIVE_TERMINAL_ENABLED) should default to `false`
and `true` respectively, so that the default configuration (main branch, no
special flags) behaves identically to today's hosted deployment.

Before merging any branch to main: verify that `compose.local.yml up` with no
extra flags still starts the full stack correctly.

---

## Files to Preserve (Do Not Delete)

| File | Why |
|------|-----|
| `compose.local.yml` | Docker path for developers and power users — keep |
| `compose.yml` + `compose.traefik.yml` | Server/VPS deployment — keep |
| `scripts/quickstart.ps1` + `.sh` | Developer quickstart — move to "Advanced" not deleted |
| `backend/app/api/routes/terminal.py` | Hosted workstation still needs this |
| `backend/app/services/terminal_service.py` | Same |
| `backend/app/services/*_bridge.py` | Hosted path uses all bridges |
| `frontend/src/pages/WorkstationPage.tsx` | Hosted path uses workstation |
| `frontend/src/routes/workstation.tsx` | Same |
| `frontend/src/routes/meeting.$roomId.tsx` | Hosted roundtable |

---

---

## Update — 2026-03-12 14:25 UTC

### Objective

Do a quick sanity pass on the live local-mode Controls surface, fix only obvious
UX/copy confusion, and begin Phase 3 by scaffolding the desktop installer path
around a Tauri shell plus a PyInstaller backend sidecar.

### Findings

- Live local-mode Controls now renders correctly on the internal app after the
  recent routing work. A browser-driven check against `remote.sparkpitlabs.com`
  confirmed these are visible in local mode:
  - `AI setup`
  - default-provider selection chips (`OpenRouter`, `Ollama`)
  - `Default provider is authoritative`
  - `Allow cross-provider fallback`
  - `Local AI on this machine`
  - `Agent overrides`
- The one obvious UX issue was that Ollama mode still showed a generic
  `Save provider key` button even though no provider key is relevant there.
- Repo audit for desktop work found no existing Tauri scaffold. Current frontend
  and backend realities matter:
  - backend now has a valid local-mode startup path and data-dir discipline
  - frontend still contains many direct relative `fetch("/api/...")` calls in
    `SparkbotDmPage.tsx`, `useAuth.ts`, and related files
  - this means a packaged Tauri window cannot yet talk to the sidecar backend
    unless the next pass adds a desktop API-base helper or a local proxy path
- Existing local data-dir decision remains the target desktop path:
  - Windows: `%APPDATA%\Sparkbot\`
  - guardian vault: `%APPDATA%\Sparkbot\guardian\vault.db`

### Changes Made

- Local-mode Controls UX cleanup:
  - updated `frontend/src/pages/SparkbotDmPage.tsx`
  - changed `Refresh cloud models` to `Refresh OpenRouter models`
  - changed the generic provider-key action so it only appears in OpenRouter mode
  - renamed it to `Save OpenRouter key`
- Desktop scaffold added:
  - `backend/app/desktop_entry.py`
    - new sidecar entrypoint for a packaged local backend
    - sets local-mode env vars
    - resolves `SPARKBOT_DATA_DIR`
    - initializes SQLite/local data
    - launches uvicorn on `127.0.0.1:8000`
  - `sparkbot-backend.spec`
    - initial PyInstaller spec targeting the new desktop entrypoint
    - outputs the sidecar into `src-tauri/binaries/`
  - `src-tauri/Cargo.toml`
  - `src-tauri/build.rs`
  - `src-tauri/src/main.rs`
    - minimal Tauri shell
    - starts the backend sidecar on app launch
    - passes local-mode/data-dir env vars
    - kills the sidecar on app exit
  - `src-tauri/tauri.conf.json`
    - local desktop app metadata
    - frontend build hook
    - NSIS bundle target
    - external sidecar registration
  - `src-tauri/capabilities/default.json`
    - least-privilege shell capability for the Sparkbot backend sidecar only
  - `src-tauri/binaries/.gitkeep`
  - `scripts/run-desktop-frontend.mjs`
    - cross-platform frontend build/dev helper for desktop mode
  - updated root `package.json`
    - added `desktop:*` scripts for frontend build, sidecar build, and tauri dev/build
  - updated root `.gitignore`
    - ignores `src-tauri/target/` and built sidecar binaries

### Verification Performed

- Browser-driven live sanity pass (headless Playwright against the internal app):
  - authenticated via the same passphrase chat login endpoint used by the app
  - opened `/dm?controls=open`
  - confirmed these were visible together in local mode:
    - `AI setup`
    - `Default provider is authoritative`
    - `Allow cross-provider fallback`
    - `Local AI on this machine`
    - `Agent overrides`
    - provider chips for `OpenRouter` and `Ollama`
  - switched provider chips and confirmed:
    - OpenRouter mode shows `OpenRouter API key` and `Default cloud model`
    - Ollama mode shows `Preferred local model`
    - the old generic key-save button was indeed the confusing element
- Frontend redeploy for the copy cleanup:
  - rebuilt local-mode frontend with:
    - `cd /home/sparky/sparkbot-v2/frontend && VITE_API_URL=http://127.0.0.1:8000 VITE_V1_LOCAL_MODE=true /home/sparky/.bun/bin/bun run build`
  - deployed to the internal static host with:
    - `rsync -a --delete /home/sparky/sparkbot-v2/frontend/dist/ /var/www/sparkbot-remote/`
  - re-ran the browser check and confirmed live:
    - `Refresh OpenRouter models` is visible
    - `Save OpenRouter key` is visible in OpenRouter mode
    - that button is hidden in Ollama mode
- Repo-only verification:
  - confirmed the desktop scaffold files are now present in-repo
  - confirmed the scaffold uses the already-established local data-dir target
  - did NOT run `cargo tauri dev`, `cargo tauri build`, or `pyinstaller` in this pass

### Unresolved Items

1. The new Tauri shell currently starts the sidecar and lets the frontend own
   readiness. A small splash/health-poll step should be added before calling the
   desktop path "user-ready".
2. The PyInstaller spec is a first scaffold only. It still needs a real Windows
   build pass to confirm hidden imports and bundled data are complete.
3. No installer asset set (icons, signing, versioned bundle metadata) has been
   prepared yet.

### Recommended Next Action

1. Run the first real desktop sequence:
   - `bun run desktop:frontend:build`
   - `pyinstaller sparkbot-backend.spec`
   - `cargo tauri dev --config src-tauri/tauri.conf.json`
2. If Tauri dev boot works, add a small startup splash/health wait so the shell
   does not open the app before the backend sidecar is ready.
3. After that, tighten the remaining non-v1 frontend API callers only as needed:
   - workstation / meeting / terminal
   - legacy chat page
   - dashboard surfaces
4. Once the shell can boot the bundled frontend and hit the sidecar locally,
   add a simple startup splash/health wait and then build the first Windows NSIS
   installer.

---

## Update — 2026-03-12 15:05 UTC

### Objective

Remove the desktop packaging blocker by introducing a shared frontend API-base
layer for Sparkbot v1 Local and refactoring the critical local-v1 surfaces away
from raw relative `/api/...` assumptions.

### Findings

- The frontend already had one centralized API-base concept through
  `OpenAPI.BASE`, but the local-v1 path bypassed it almost everywhere with raw
  `fetch("/api/...")`.
- The blocking local-v1 surfaces were:
  - passphrase chat login/logout
  - Controls config lookup for first-run routing
  - Sparkbot DM bootstrap
  - Controls model/provider refresh + save actions
  - local Ollama status refresh
  - chat streaming
  - upload/voice flows inside the main DM page
- Remaining direct same-origin API callers are outside the first local-v1 path:
  - `WorkstationPage.tsx`
  - `MeetingRoomPage.tsx`
  - `ChatPage.tsx`
  - `hooks/useTerminalSession.ts`
  - `routes/_layout/index.tsx`
  - these are hosted/advanced surfaces and do not block the first local desktop proof

### Changes Made

- Added `frontend/src/lib/apiBase.ts`
  - `getApiBase()`
  - `apiUrl()`
  - `apiFetch()`
  - `apiWebSocketUrl()`
- Updated `frontend/src/main.tsx`
  - `OpenAPI.BASE` now comes from `getApiBase()` instead of directly from `VITE_API_URL`
- Updated `frontend/src/vite-env.d.ts`
  - made `VITE_API_URL` optional
- Updated `frontend/src/hooks/useAuth.ts`
  - passphrase chat login/logout now use `apiFetch()`
- Updated `frontend/src/lib/sparkbotControls.ts`
  - Controls config fetch now uses `apiFetch()`
- Updated `frontend/src/lib/chat/websocket.ts`
  - websocket URL now comes from `apiWebSocketUrl()`
- Updated `frontend/src/pages/SparkbotDmPage.tsx`
  - converted the critical DM/bootstrap/Controls/chat/upload/voice flows to `apiFetch()`
  - converted upload image URLs to `apiUrl()` so desktop mode does not emit broken relative file links

### Verification Performed

- Code audit:
  - confirmed no raw `fetch("/api/...")` calls remain in the local-v1 critical path:
    - `useAuth.ts`
    - `sparkbotControls.ts`
    - `SparkbotDmPage.tsx`
- Desktop frontend build:
  - `cd /home/sparky/sparkbot-v2 && bun run desktop:frontend:build`
  - result: build succeeded
- Static checks:
  - `python3 -m py_compile /home/sparky/sparkbot-v2/backend/app/desktop_entry.py`
  - `node --check /home/sparky/sparkbot-v2/scripts/run-desktop-frontend.mjs`

### Unresolved Items

1. Remaining raw same-origin API callers still exist in hosted/advanced surfaces
   and will need the same helper if those surfaces are ever brought into the
   desktop shell.
2. Packaged non-dev Tauri origin behavior still needs a real runtime pass after
   the first `cargo tauri dev` proof, especially around cookies/CORS outside the
   local HTTP dev server origin.
3. The sidecar/backend packaging itself is still unproven until PyInstaller and
   Tauri dev are actually run.

### Recommended Next Action

1. Run:
   - `pyinstaller --distpath src-tauri/binaries sparkbot-backend.spec`
   - `cargo tauri dev --config src-tauri/tauri.conf.json`
2. If the dev shell boots, verify:
   - passphrase login
   - first-run Controls open
   - OpenRouter/Ollama settings load
   - normal chat reply
3. Then add a startup splash/health wait before moving to the first Windows installer build.

---

## Update — 2026-03-12 15:25 UTC

### Objective

Restore the original four-model stack controls inside the live Controls UI after
user review noted that the `primary / backup_1 / backup_2 / heavy_hitter` stack
was no longer available.

### Findings

- Backend support for the four-slot stack was still intact.
- Frontend state for `modelStack` was also still intact.
- The missing piece was only the actual Controls section and its save action.

### Changes Made

- Updated `frontend/src/pages/SparkbotDmPage.tsx`
  - restored a visible `Four-model stack` section
  - restored selects for:
    - `Primary`
    - `Backup 1`
    - `Backup 2`
    - `Heavy hitter`
  - added `Save stack`
  - added a save handler posting `{ stack: modelStack }` to the existing
    `/api/v1/chat/models/config` backend path
- Rebuilt and redeployed the frontend bundle to the internal app

### Verification Performed

- `cd /home/sparky/sparkbot-v2 && bun run desktop:frontend:build`
  - result: build succeeded
- Browser-driven live check confirmed:
  - `Four-model stack` visible
  - `Save stack` visible
  - `Primary` visible
  - `Heavy hitter` visible

### Unresolved Items

1. I did not do a full save-and-reload persistence check of edited stack values
   in this pass.

### Recommended Next Action

1. Optionally do one quick persistence pass on the restored stack controls.
2. Then continue with the original desktop path:
   - `pyinstaller --distpath src-tauri/binaries sparkbot-backend.spec`
   - `cargo tauri dev --config src-tauri/tauri.conf.json`

---

## Update — 2026-03-12 15:35 UTC

### Objective

Verify that the restored four-model stack in Controls actually saves and persists
across reloads, then restore the original state.

### Findings

- Live persistence is working.
- Tested slot: `backup_2`.

### Changes Made

- No repo edits in this verification pass.
- Temporary live stack change only:
  - original `backup_2`: `gpt-4o-mini`
  - temporary test value: `openrouter/openai/gpt-4o-mini`
  - restored to the original value after verification

### Verification Performed

- Changed `backup_2` in the live Controls UI
- Clicked `Save stack`
- Reloaded and confirmed the changed value persisted
- Changed `backup_2` back to `gpt-4o-mini`
- Clicked `Save stack`
- Reloaded and confirmed the original value persisted

### Unresolved Items

1. Only one slot was exercised, but that is enough to confirm the restored stack
   section is truly wired to the backend save path.

### Recommended Next Action

1. Manual user testing can proceed.
2. Then resume the desktop path:
   - `pyinstaller --distpath src-tauri/binaries sparkbot-backend.spec`
   - `cargo tauri dev --config src-tauri/tauri.conf.json`

---

## Update — 2026-03-14 00:12 UTC

### Objective

Append the current release-program truth after repo/live parity restoration,
desktop packaging proof, first real installer build, GitHub draft-release
upload, and checksum verification.

### Findings

- The live repo checkout and GitHub `main` now match.
- The current committed source-of-truth commit is:
  - `f284d43f281c42eda21d69518be853129456e391`
- Packaging should now be built only from committed repo truth, not stale local
  artifacts.
- The Tauri desktop scaffold is working.
- `cargo tauri dev` compiled and launched `sparkbot.exe` successfully.
- Prior exit-code false alarms were caused by forced task termination, not app
  crashes.
- The backend sidecar packaging path was proven sufficiently to produce release
  bundles.
- Fresh Windows installer artifacts were built from the current committed source:
  - NSIS: `Sparkbot_1.3.0_x64-setup.exe`
  - NSIS SHA256:
    `244010B3514B23247907D72B005CAEA597982CFDB7568E5B578392DBE0F82B89`
  - MSI: `Sparkbot_1.3.0_x64_en-US.msi`
  - MSI SHA256:
    `587ADB089F18309BC33C03C7AB9EF886D756F4136D152005025BE9C8FE0E8933`
- A GitHub draft release exists for `sparkbot-v1.3.0`.
- Both installer assets are uploaded there.
- GitHub asset digests match the local Windows-built checksums.
- The release remains draft/unpublished on purpose.
- The release is not yet public.
- `sparkpitlabs.com/sparkbot` is not updated yet.
- Sparkbot is not yet declared market-ready.
- Final Sparkbot polish notes are still pending before any public release or
  website update.

### Changes Made

- Appended this release-state handoff entry.
- Preserved the release as draft/unpublished.
- Made no publish, website, or product-code changes in this pass.

### Verification Performed

- Recorded the already-established release-track facts:
  - source-of-truth commit pinned to
    `f284d43f281c42eda21d69518be853129456e391`
  - `cargo tauri dev` proof compiled and launched `sparkbot.exe`
  - fresh NSIS/MSI artifacts and SHA256 values captured
  - GitHub draft release exists with both assets uploaded
  - GitHub asset digests matched the local Windows-built checksums
- This pass was documentation/state sync only:
  - no rebuild
  - no multi-machine re-test
  - no publication
  - no website update

### Unresolved Items

1. Final Sparkbot polish notes still need to be applied.
2. A fresh installer rebuild from updated committed source is still required
   after that polish pass.
3. Multi-machine re-testing is still required before publication.
4. The GitHub release intentionally remains draft/unpublished.
5. The website intentionally remains unchanged.
6. Sparkbot should not yet be described as public-ready or market-ready.

### Recommended Next Action

1. apply final Sparkbot polish notes
2. rebuild fresh installer from updated committed source
3. re-test on multiple machines
4. only then update GitHub release/publication state
5. only then update `sparkpitlabs.com/sparkbot`

*End of sparkbotv1_logbook_handoff.md — 2026-03-14*
