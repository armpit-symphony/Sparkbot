# Sparkbot

**Sparkbot** is a self-hosted AI assistant that runs entirely on your own machine — no cloud subscription, no data sharing, no monthly fee. Download the installer, add a provider key, and you have a personal AI that knows your files, controls your desktop, fills out web forms, reads your inbox, manages your calendar, runs your code, and remembers everything you tell it — across every conversation.

> **Desktop app (Windows · macOS · Linux)** — [Download at sparkpitlabs.com](https://armpit-symphony.github.io/Sparkbot/)
> **Self-host on a server** — one Docker command, full HTTPS, works on any VPS

---

## What Sparkbot Can Do

### Local Computer Control
- **Shell access** — run any PowerShell / bash command from chat; working directory persists so `cd` carries forward between messages
- **Live terminal** — xterm.js terminal panel in the Workstation; Sparkbot can inject commands into it while you watch
- **Code execution** — run Python, Node.js, or Bash scripts directly in chat; get the output back immediately
- **Browser automation** — Sparkbot opens a real Chromium browser, navigates to sites, fills forms, clicks buttons, logs in, and reads page content — all from a single chat message
- **Web scraping** — fetch and read any public URL; use it for research, docs, price checks, anything

### Productivity & Work
- **Email (Gmail + IMAP/SMTP)** — read inbox, search, compose and send, summarize threads
- **Google Calendar** — list events, create meetings, check availability in natural language
- **CalDAV** — works with iCloud, Nextcloud, Fastmail, Baikal, Radicale
- **Google Drive** — search files, read documents, create folders
- **GitHub** — list PRs, read PR diffs, create issues, check CI status
- **Slack** — post messages, list channels, read channel history
- **Notion** — search pages, read content, create new pages
- **Confluence** — search and read spaces, create pages
- **Task management** — create, track, and complete tasks inside any chat room
- **Reminders** — schedule one-time or recurring reminders that post to the room (and fan out to Telegram / Discord / WhatsApp)
- **Morning briefing** — one-shot digest of Gmail unread, calendar for today, and pending reminders

### AI & Intelligence
- **Multi-model** — switch between OpenAI (GPT-4o, o1, o3), Anthropic (Claude Sonnet, Haiku, Opus), Google (Gemini), Groq (Llama), MiniMax, Ollama (local), OpenRouter — all from chat
- **Multi-model stack** — configure a Primary, two Backups, and a Heavy Hitter; Sparkbot auto-routes and falls back across providers when one fails
- **Multi-agent rooms** — mention `@researcher`, `@coder`, `@writer`, `@analyst`, or any custom agent to get a specialist response
- **Spawn agents** — create custom named agents with a full system prompt from 11 specialty templates (DevOps, Legal, Finance, HR, PM, Security, and more)
- **Persistent memory** — Sparkbot proactively stores facts about you (name, role, timezone, preferences, projects) and injects them into every conversation
- **Knowledge base (RAG)** — ingest any document or URL; Sparkbot searches it with BM25 full-text ranking when relevant
- **Skill plugins** — drop a `.py` file into `backend/skills/` and Sparkbot gains a new tool with no restart; all existing skills are auto-discovered

### Workstation (Desktop HQ)
- **Office floor view** — a visual grid of all your AI desks: main Sparkbot, model stack companions, specialty agents, invite desks, and live terminals
- **Invite Wing** — seat a Claude, GPT, or Ollama model into a desk with its own API key and model ID; routes directly to that provider at meeting launch
- **Round Table** — launch a multi-agent autonomous meeting room; all seated agents contribute in turn without you typing between every reply
- **Company Operations dashboard** — view all Guardian Tasks across every room, active meeting rooms, and launch project meetings in one click
- **Task-linked meetings** — hit "Meet" on any Guardian Task and a room opens pre-seeded with task context and stack bots
- **Live terminal panel** — full interactive xterm.js terminal backed by ConPTY (Windows) or PTY (Linux/macOS)

### Scheduled Autonomy (Task Guardian)
- **Scheduled jobs** — tell Sparkbot to run any tool on a schedule (hourly, daily, custom interval)
- **Autonomous execution** — jobs run in the background and post results back into the room
- **Write-action scheduling** — opt-in to scheduled send-email, post-to-Slack, create-calendar-event
- **Verifier guardian** — each scheduled run is evaluated before commit; bounded retries with escalation instead of silent loops
- **Suggested jobs**: daily morning briefing, hourly inbox check, daily calendar preview, open-task digest, pending reminders, news headlines, PR review

### Communication Channels
- **Telegram** — long-poll bridge; private Telegram chats map to Sparkbot rooms; `/approve` / `/deny` resolve pending confirmations
- **Discord** — gateway bot; DMs and @mentions map to rooms; same approval flow
- **WhatsApp** — Meta Cloud API webhook (pywa); free-form replies in the 24-hour session window
- **GitHub** — signed webhook for issue and PR comments; `approve` / `deny` resolves confirmations in-thread
- **Notification fan-out** — reminders and Task Guardian results push to all connected channels simultaneously

### Security (Built-In, Not Bolted On)
- **Policy layer** — every tool call classified read / write / execute / admin; unknown tools denied by default
- **Write-tool confirmation** — the LLM cannot email, post to Slack, or commit to GitHub autonomously; a confirmation modal is required for every external write
- **Execution gate** — server commands and shell access require the room owner to explicitly enable; defaults off per room
- **Guardian Vault** — encrypted secret storage; break-glass PIN required before writing secrets
- **Break-glass** — PIN-gated privileged mode; works from chat (`/breakglass`); all sessions logged
- **Audit trail** — every tool call logged with allow/confirm/deny, redacted args, and timestamps
- **HttpOnly cookies** — session tokens never exposed to JavaScript
- **Dep scanning** — `pip-audit` + `npm audit` + `gitleaks` on every push via GitHub Actions

---

## Quick Start

Sparkbot runs anywhere Docker is installed: Windows, macOS, Linux, or a cloud server.

### Desktop / laptop (Windows, macOS, Linux)

**One command:**

```bash
# Linux / macOS
bash scripts/quickstart.sh

# Windows (PowerShell)
.\scripts\quickstart.ps1
```

Then open **http://localhost:3000**.

Or manually:

```bash
cp .env.local.example .env.local     # add at least one LLM API key
docker compose -f compose.local.yml up --build
```

Default passphrase: `sparkbot-local`
Change it by setting `SPARKBOT_PASSPHRASE` in `.env.local`.

### CLI (terminal chat — no browser needed)

```bash
python sparkbot-cli.py                           # interactive
python sparkbot-cli.py --setup                   # provider keys + model roles
python sparkbot-cli.py "/model gpt-5-mini"      # prompt for key if needed, then switch
python sparkbot-cli.py "What's on my calendar?"  # one-shot
echo "Summarise my inbox" | python sparkbot-cli.py
```

Requires Python 3.10+. No extra packages — pure stdlib.
On first run it prompts for the URL and passphrase and saves them to `~/.sparkbot/cli.json`.
The CLI does not run models by itself. It connects to a running Sparkbot server.
Use `--setup` or `/setup` to send provider API keys and choose the Sparkbot model stack on your own instance.
For terminal-only installs, `/model <id>` will prompt for the matching provider API key if that model is not configured yet.
Keys are stored on that Sparkbot instance, not in the CLI config file.

### First browser launch

On a fresh self-hosted install, Sparkbot opens **Sparkbot Controls** automatically when no provider/model setup exists yet.
That first-run panel is where users:

- paste provider API keys
- choose the model stack
- configure comms channels
- keep the execution gate off by default

### Server / VPS (public HTTPS)

See [deployment.md](./deployment.md) for the full Traefik + Docker Compose + Let's Encrypt setup.
For the lighter-weight systemd profile that matches the working server layout more closely, see [docs/systemd-single-node.md](./docs/systemd-single-node.md) and [deploy/systemd/sparkbot-v2.service.example](./deploy/systemd/sparkbot-v2.service.example).

### Public download packaging

To reproduce the website download bundle from committed source:

```bash
bash scripts/package-public-download.sh
```

Default artifacts are written to `dist/public-download/latest/`.
To publish directly to the website download directory, pass `--publish-dir /var/www/sparkpitlabs.com/downloads/sparkbot/latest`.
For versioned or tag-bound packaging instructions, see [docs/public-downloads.md](./docs/public-downloads.md).

### Desktop release packaging

Windows desktop releases are published from tags matching `desktop-v*`.

Release standard:

- download `*-setup.exe`
- run the installer with standard Windows prompts
- open Sparkbot from the Start Menu
- finish provider setup in **Sparkbot Controls**
- start chatting without Docker, WSL, or terminal work

Create and push a desktop release tag:

```bash
git tag desktop-v1.6.12
git push origin desktop-v1.6.12
```

The public desktop workflow is [desktop-release.yml](./.github/workflows/desktop-release.yml).
For signed Windows installers, configure these GitHub Actions secrets before tagging:

- `SIGNPATH_API_TOKEN`
- `SIGNPATH_ORG_ID`
- `SIGNPATH_PROJECT_SLUG`
- `SIGNPATH_SIGNING_POLICY_SLUG`
- `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` optional

If those secrets are missing, the release still builds, but the Windows installer is published unsigned and SmartScreen may require **More info -> Run anyway**.

The manual workflow [build-installer.yml](./.github/workflows/build-installer.yml) is for QA builds only. It does not publish a public GitHub Release.

---

## Recent Milestones

### April 17, 2026 — v1.2.2

- **Workstation opens to a clean floor view.** The Corner Office (Sparkbot DM panel) no longer auto-opens when you enter the Workstation page — it opens only when you click Sparkbot's desk, so the full office floor is always visible on load.
- **Invite Wing now routes to real external APIs.** The invite seat modal has two new fields — Model ID and API Key — with provider-specific hints (e.g. `claude-sonnet-4-6`, `gpt-4o`, `ollama/phi4-mini`). Entering a key for an Anthropic, OpenAI, or Ollama seat wires that seat to the real provider at meeting launch using your own key, not Sparkbot's configured stack.
- **`shell_run` — Sparkbot now has full local shell access.** New tool that runs any command on the host machine: PowerShell on Windows, bash on Linux/macOS. Working directory persists across calls in the same conversation (`cd` carries forward). Sparkbot can run `git`, `npm`, `pip`, move files, open apps — anything you'd type in a terminal.
- **Live terminal panel now works on Windows.** The Workstation xterm.js terminal panel previously failed silently on Windows (POSIX-only PTY). Replaced with a cross-platform backend: ConPTY via `pywinpty` on Windows, existing pty/fcntl on Unix. `WORKSTATION_LIVE_TERMINAL_ENABLED` is now `true` by default in the desktop build.
- **`terminal_send` / `terminal_list_sessions` tools.** Sparkbot can now inject commands into a running terminal session visible in the Workstation panel — type in the visual terminal from chat.
- **Browser automation works on fresh installs.** Playwright's Chromium driver is now auto-downloaded on first desktop launch (one-time, ~150 MB). Browser tools (`browser_open`, `browser_fill_field`, `browser_click`, etc.) are ready without any manual setup. Playwright Python bindings are bundled in the installer.

### April 9, 2026

- **Workstation is now a company operations dashboard.** The Workstation page is connected to Guardian Suite end-to-end: it loads all Guardian Tasks across every room, lists active Meeting rooms, and lets you launch or re-enter a project meeting in one click.
- **Top 4 bots always synced.** The four model-stack desks (Primary, Backup 1, Backup 2, Heavy Hitter) now refresh automatically whenever you return focus to the Workstation after saving a stack change in Controls.
- **Auto-fill Stack.** The Round Table side panel has an "Auto-fill Stack" button that seats all four stack models into chairs instantly — no manual drag required.
- **Company Operations section.** A new panel below the office floor shows your Guardian Tasks with live status dots and a "Meet" button per task, plus a scrollable list of active meetings. One click enters or creates the project meeting for that task.
- **Task-linked project meetings.** When you hit "Meet" on a Guardian Task, a dedicated meeting room is created with task context pre-seeded (task name, tool, schedule, last status), the stack bots auto-seated, and a project notes artifact ready. Re-entering the same task re-opens the same room.
- **New Project button.** Launch a named meeting room from the Company Operations section without needing to go through the round table — stack bots are auto-seated, autonomous meeting mode enabled.
- **Meeting room Tasks tab.** Every meeting room now has a third sidebar tab ("Tasks") showing the Guardian Tasks registered in that room with live status, last run time, and a one-click Run trigger.

### March 17, 2026

- **Code interpreter shipped.** Sparkbot can now execute Python 3, Node.js, and Bash directly from chat via `run_code(language, code)`. Subprocess-sandboxed with configurable timeout (default 30s, max 120s). Disable with `SPARKBOT_CODE_DISABLE=true`.
- **Named browser sessions added.** After logging in to a site, `browser_save_session(session_id, name)` persists cookies and localStorage to disk. `browser_restore_session(name)` reloads them in any future conversation — no re-login required. `browser_list_sessions()` shows active and saved sessions.
- **Knowledge base (RAG) shipped.** `ingest_document(text, name, source?)` stores text or auto-fetches a URL and indexes it with SQLite FTS5 (BM25). `search_knowledge(query)` retrieves relevant chunks with full-text ranking. `list_knowledge()` and `delete_knowledge(name)` round out the API. Zero new dependencies.
- **Multi-tool skill hook added.** The skill plugin system now supports `_register_extra(registry)` so a single `.py` file can register multiple tools (used by the knowledge base plugin).
- **System prompt expanded to ~400 words.** The new `SYSTEM_PROMPT` covers Identity, Collaboration (no echo/repeat), Proactivity, Quality, Boundaries, Tool Philosophy, and Tone in named sections. Loaded from `backend/prompts/system.md` at startup — editable without touching Python code. Override path via `SPARKBOT_SYSTEM_PROMPT_FILE`.
- **Room context injection.** Every LLM call now receives a `## Room Context` block with the room name, optional description, and execution gate state. Sparkbot knows what room it's in without being told.

### March 16, 2026

- **Operator UI is now a real control surface.** The `/spine` page gained three new operator tabs: **Security** (break-glass activation/deactivation, guardian status overview, PIN setup guidance), **Vault** (encrypted secret listing, add/delete with break-glass gate), and **Task Guardian** (write-mode runtime toggle). The Projects tab now has a "New Project" button and per-project Archive action.
- **All task mutations now emit Spine events.** Previously only `reopen` went through the Task Master adapter; create, complete, assign, and delete now all route through the adapter, making the canonical Spine event log complete for task lifecycle.
- **Vault, memory, and token guardian now produce Spine events.** `vault.secret_added/used/deleted`, `memory.fact_stored`, and `token_guardian.quota_event` are now wired — the Spine event log covers all major guardian subsystems.
- **Project management has a REST API.** `ProjectExecutiveAdapter` is now exposed via HTTP: create, update, archive projects; attach/detach tasks. The canonical Spine project lifecycle is now reachable from any API client or UI.
- **Security defaults are self-hosted friendly.** Break-glass and vault no longer restrict to a hardcoded `sparkbot-user` username. If `SPARKBOT_OPERATOR_USERNAMES` is not set, any authenticated human user is an operator (open mode). Restrict by setting the env var. The `.env.example` now documents all guardian security variables with inline setup commands.
- **Sparkbot can read any URL.** The new `fetch_url` tool lets Sparkbot retrieve and read page content from any public URL — useful for researching docs, checking pages, or participating in external resources.

### March 15, 2026

- **Guardian Spine became a background operating subsystem.** It now acts as Sparkbot’s canonical cross-guardian catalog and history layer: structured subsystem events, canonical projects/tasks/events/handoffs/approvals, project lineage and dependencies, Task Master-oriented queue views, operator-global inspection routes, and explicit Memory/Executive/Approval/Task Guardian hooks.
- **Roundtable became instance-based and autonomous.** Launching Roundtable now creates a fresh meeting room, meetings can continue chair-led without manual user turns between speakers, and the UI exposes ongoing meetings with end/delete controls.
- **Sparkbot can inspect its own safe runtime state from chat.** Asking what stack/provider/model it is running now returns live operational state such as provider/model routing, Token Guardian mode, fallback status, agent overrides, Ollama reachability, and breakglass status without exposing secrets.
- **Breakglass works naturally from chat again.** When a task crosses a privileged boundary, Sparkbot now asks for `/breakglass`, prompts for the PIN in chat, resumes the waiting action after approval, and supports `/breakglass close`.

### March 8-10, 2026

- **Public release discipline matured.** Sparkbot now ships from a tracked packaging flow with committed-source bundles, checksums, release notes, and traceable public tags through `v1.3.0`.
- **Security hardening shipped publicly.** The public release line picked up fixes for unauthenticated user enumeration, IDOR on user update/delete paths, upload path traversal, unsafe inline file serving, and audit-log safety.
- **Guardian Auth + Vault went live.** Sparkbot now supports PIN-gated break-glass privileged mode plus encrypted vault-backed secret storage for operator workflows.
- **Workstation became a real product surface.** The workstation UI shipped, gained in-shell navigation, and became the post-login landing path for chat-session users.
- **Live terminal landed in workstation.** Terminal panels now run real xterm.js + WebSocket PTY sessions in the live internal instance instead of placeholder panels.
- **Memory got better, not just larger.** Guardian memory now promotes safer learned profile/workflow context with redaction before higher-value memory promotion. This shipped publicly in `v1.3.0`.
- **Autonomy became more evidence-bound.** Verifier Guardian now evaluates scheduled runs and interactive high-risk actions, and Task Guardian has bounded retries plus escalation instead of optimistic looping.

### What this means now

Sparkbot is no longer just a self-hosted chat UI with integrations. It now has a clearer public release process, a stronger workstation/control surface, safer adaptive memory, privileged operator controls, and early verifier-backed autonomy.

For privacy and retention details, see [PRIVACY.md](./PRIVACY.md).

---

## Why Sparkbot

Most AI assistants give the LLM unrestricted access to your email, calendar, Slack, and GitHub the moment you connect them. Sparkbot does not.

Every tool the LLM can call is **classified, policy-gated, and logged** before it touches anything external. External writes — send email, post to Slack, create a GitHub issue — require explicit confirmation in the UI. Server commands require the room owner to enable an execution gate. The LLM cannot bypass either control. This is architecture, not a config option.

| What competitors do | What Sparkbot does |
|--------------------|--------------------|
| LLM calls tools freely | Policy layer classifies every tool: read / write / execute / admin |
| External writes happen silently | Confirmation modal required before any external mutation |
| No audit trail | Every tool call logged + redacted before write |
| Secrets may leak into logs | Audit redaction strips key-name and token-pattern values at write time |
| Session token in localStorage | HttpOnly `Secure SameSite=Strict` cookie — never reachable from JavaScript |
| No dependency scanning | `pip-audit` + `npm audit` on every push via GitHub Actions |

Full architecture: [SECURITY.md](./SECURITY.md)

---

## Architecture

```
Browser
  │
  └── nginx (your-domain.com)
        ├── /            → static files (/var/www/sparkbot)
        ├── /api/        → FastAPI backend (configurable port)
        └── /ws/         → WebSocket (same port, upgrade headers)
```

| Component           | Path                                  | Port  |
|---------------------|---------------------------------------|-------|
| FastAPI backend     | `/home/youruser/sparkbot-v2/backend`  | configurable |
| React frontend      | `/home/youruser/sparkbot-v2/frontend` | — (built/deployed) |
| PostgreSQL          | system service                        | 5432  |
| nginx               | `/etc/nginx/sites-available/sparkbot` | 80/443 |

---

## Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com) — async Python API framework
- [SQLModel](https://sqlmodel.tiangolo.com) — ORM (PostgreSQL)
- [litellm](https://docs.litellm.ai) — unified LLM routing (100+ providers)
- [caldav](https://github.com/python-caldav/caldav) — CalDAV calendar access
- JWT authentication

**Frontend**
- React + TypeScript + [Vite](https://vitejs.dev)
- [TanStack Router](https://tanstack.com/router)
- [shadcn/ui](https://ui.shadcn.com) + Tailwind CSS
- `react-markdown` + `react-syntax-highlighter` (Prism oneDark)

---

## Features

### Chat
- **Streaming responses** — token-by-token SSE (`/messages/stream`), typing cursor, no waiting
- **Conversation context** — last 20 messages passed as history on every LLM call
- **Safe self-inspection** — Sparkbot can answer chat questions about its current provider/model stack, Token Guardian mode, routing, Ollama reachability, and breakglass status using live backend state
- **Guardian Spine task capture** — actionable chat and meeting language is normalized into canonical tracked work with event history, approval state, handoff notes, and markdown mirrors under the guardian data directory
- **Markdown rendering** — headings, lists, bold, tables, code blocks in bot replies
- **Syntax highlighting** — fenced code blocks with language detection (oneDark theme)
- **Copy-code button** — one click to clipboard on every code block
- **Message search** — full-text search across room history (`/search`)
- **File uploads** — images (vision analysis), documents (text extraction + summarisation), other files (10 MB max)
- **Voice input** — click the mic button to record; Whisper transcribes the audio and the transcript enters the normal LLM pipeline (all policy/tool/confirmation logic unchanged)
- **Text-to-speech replies** — enable voice mode (speaker button) to hear bot replies spoken aloud via OpenAI TTS

### Voice (Whisper + TTS)
Record a voice message directly in the browser — no extra packages needed.

**How it works:**
1. Click the **mic button** (between the upload and text input) — browser prompts for mic permission
2. While recording the button pulses red and shows a second counter
3. Click again to stop — audio is sent to Whisper (`whisper-1`) for transcription
4. The transcript appears as your human message; the bot replies via the normal streaming pipeline
5. Enable **voice mode** (speaker icon after the send button) to have bot replies read aloud automatically

**UI controls in the input bar:**

| Button | State | Action |
|--------|-------|--------|
| 🎙 Mic | idle → click | Start recording |
| 🔴 `Ns` | recording → click | Stop + send |
| 🔇 VolumeX | voice mode off | Toggle on — replies spoken aloud |
| 🔊 Volume2 | voice mode on | Toggle off |

Voice mode preference is persisted in `localStorage`.

### Guardian Spine

Guardian Spine is Sparkbot’s background operating subsystem for cross-guardian coordination. It is not just a room-task feature.

Current backend role:

- catalog actionable work from chat messages, agent outputs, meeting artifacts, and room task lifecycle changes
- accept structured subsystem events from other guardians and internal systems
- maintain canonical projects, tasks, task events, project events, handoffs, approvals, lineage, dependencies, and related-work links
- preserve source traceability across chat, meeting, task, memory, executive, approval, and system-originated events
- expose queryable state for Task Master, other guardians, and backend inspection routes
- act as the shared backend operating substrate for work-state across rooms, projects, guardians, and Task Master

Structured subsystem event contract:

- `SpineSourceReference`
- `SpineProjectInput`
- `SpineTaskInput`
- `SpineSubsystemEvent`

Built-in integration hooks:

- `ingest_subsystem_event(...)`
- `ingest_memory_signal(...)`
- `ingest_executive_decision(...)`
- `emit_approval_event(...)`
- `emit_breakglass_event(...)`
- `ingest_task_guardian_result(...)`
- `emit_task_master_action(...)`
- `emit_room_lifecycle_event(...)`
- `emit_project_lifecycle_event(...)`
- `emit_handoff_event(...)`
- `emit_meeting_output_event(...)`
- `emit_worker_status_event(...)`

Task Master contract:

- `TaskMasterSpineAdapter` is the primary backend adapter for execution/assignment logic over Spine
- Task Master should read queues and workload state from Spine first, then round-trip assignment/status actions back into Spine
- explicit task lifecycle mutations now route through the adapter for create, assign, complete, reopen, and delete/archive flows in the room task surface
- canonical task mutation paths now fail closed instead of silently swallowing adapter errors in the room task CRUD path
- Task Master is not a competing source of truth; Guardian Spine remains the canonical catalog/history layer

Current built-in producers that emit into Spine:

- chat message and meeting-artifact intake
- room task lifecycle sync and Task Master-style task actions
- Executive guardian decisions
- approval store/consume/discard events
- breakglass request/open/close/failure events
- Task Guardian verifier/run outcomes
- room lifecycle creation events
- structured meeting summary/decision/action-item events
- worker agent status/progress events from agent-style room messages
- explicit handoff events
- explicit project lifecycle events

Task Master-facing derived views now available in the backend:

- open queue
- blocked queue
- orphan queue
- approval-waiting queue
- stale queue
- recently resurfaced queue
- assignment-ready queue
- project workload summary
- missing-source-traceability queue
- missing-project-linkage queue
- executive-directive queue
- recent cross-room events
- high-priority blocked tasks
- high-priority approval-waiting tasks
- stale unowned tasks
- unassigned executive directives
- resurfaced tasks without follow-up
- missing durable linkage
- fragmentation indicators

Read-only room inspection routes:

- `GET /api/v1/chat/rooms/{room_id}/spine/overview`
- `GET /api/v1/chat/rooms/{room_id}/spine/tasks`
- `GET /api/v1/chat/rooms/{room_id}/spine/tasks/orphaned`
- `GET /api/v1/chat/rooms/{room_id}/spine/tasks/{task_id}/lineage`
- `GET /api/v1/chat/rooms/{room_id}/spine/tasks/{task_id}/approvals`
- `GET /api/v1/chat/rooms/{room_id}/spine/events`
- `GET /api/v1/chat/rooms/{room_id}/spine/handoffs`
- `GET /api/v1/chat/rooms/{room_id}/spine/projects`
- `GET /api/v1/chat/rooms/{room_id}/spine/projects/{project_id}/tasks`
- `GET /api/v1/chat/rooms/{room_id}/spine/projects/{project_id}/handoffs`
- `GET /api/v1/chat/rooms/{room_id}/spine/projects/{project_id}/events`
- `GET /api/v1/chat/rooms/{room_id}/spine/task-master/overview`

Read-only operator/global inspection routes:

- `GET /api/v1/chat/spine/operator/producers`
- `GET /api/v1/chat/spine/operator/events/recent`
- `GET /api/v1/chat/spine/operator/queues/open`
- `GET /api/v1/chat/spine/operator/queues/blocked`
- `GET /api/v1/chat/spine/operator/queues/approval-waiting`
- `GET /api/v1/chat/spine/operator/queues/stale`
- `GET /api/v1/chat/spine/operator/queues/orphaned`
- `GET /api/v1/chat/spine/operator/queues/missing-source`
- `GET /api/v1/chat/spine/operator/queues/missing-project`
- `GET /api/v1/chat/spine/operator/queues/resurfaced`
- `GET /api/v1/chat/spine/operator/queues/executive-directives`
- `GET /api/v1/chat/spine/operator/projects`
- `GET /api/v1/chat/spine/operator/projects/workload`
- `GET /api/v1/chat/spine/operator/task-master/overview`
- `GET /api/v1/chat/spine/operator/signals/high-priority-blocked`
- `GET /api/v1/chat/spine/operator/signals/high-priority-approval`
- `GET /api/v1/chat/spine/operator/signals/stale-unowned`
- `GET /api/v1/chat/spine/operator/signals/unassigned-executive`
- `GET /api/v1/chat/spine/operator/signals/resurfaced-no-followup`
- `GET /api/v1/chat/spine/operator/signals/missing-durable-linkage`
- `GET /api/v1/chat/spine/operator/signals/fragmentation`

Canonical rule:

- Guardian Spine’s structured store is the source of truth.
- Markdown mirrors under the guardian data directory are secondary audit/handoff mirrors, not the canonical writer.
- Other guardians may observe, emit events, propose changes, and query state, but they should not silently maintain conflicting canonical work-state truth when Spine already models that domain.
- Remaining intentional exceptions are internal mirror-sync helpers inside Spine itself and low-level canonical-writer functions inside the Spine service; those are implementation details, not alternate sources of truth.

**SSE protocol for voice** (superset of `/messages/stream`):
```
data: {"type": "transcription",  "text": "what's the weather in Tokyo?"}
data: {"type": "human_message",  "message_id": "..."}
data: {"type": "token",          "token": "..."}
data: {"type": "done",           "message_id": "..."}
```

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat/rooms/{id}/voice` | Audio → Whisper → SSE stream (multipart, `audio` field ≤ 5 MB) |
| `POST` | `/api/v1/chat/voice/tts` | Text → `audio/mpeg` stream |

Both require authentication. Room membership is enforced on the per-room endpoint.

### Document Summarisation
Upload a PDF, DOCX, TXT, Markdown, or CSV and the bot reads and summarises it. Use the caption field as your prompt — e.g. *"What are the action items?"* or *"Summarise the key findings"*.

| Format | How text is extracted |
|--------|-----------------------|
| `.pdf` | pypdf (text-layer PDFs; scanned/image PDFs return no text) |
| `.docx` | python-docx |
| `.txt` / `.md` / `.csv` | UTF-8 decode |

Up to 12,000 characters (~3k tokens) are sent to the LLM. Large documents are truncated with a note.

### Slash Commands (type `/` to autocomplete)
| Command | Description |
|---------|-------------|
| `/help` | List all commands |
| `/clear` | Clear local view (server history preserved) |
| `/new` | Fresh start |
| `/export` | Download conversation as `.md` |
| `/search <query>` | Search message history with highlighting |
| `/meeting start\|stop\|notes` | Meeting mode — capture notes, decisions, actions |
| `/breakglass` | Open privileged mode from chat; Sparkbot prompts for your operator PIN |
| `/breakglass close` | Close the current privileged session |
| `/model` | List available AI models |
| `/model <id>` | Switch to a different AI model |
| `/memory` | List stored facts the bot remembers about you |
| `/memory clear` | Wipe all stored memories |
| `/tasks` | List open tasks in this room |
| `/tasks done` | List completed tasks |
| `/tasks all` | List all tasks regardless of status |
| `/remind` | List pending reminders for this room |
| `/agents` | List available named agents |

### Meeting Mode
Activated with `/meeting start`. While active, prefix messages with:
- `note:` → captured as a meeting note
- `decided:` → recorded as a decision
- `action:` → added as an action item

`/meeting stop` exports the full notes as a dated `.md` file.

### Roundtable
- Roundtable launches a fresh meeting instance each time instead of reusing one long-running chat.
- Meeting rooms can run in autonomous chair-led mode: framing, specialist perspectives, synthesis, optional refinement, then a final recommendation or action plan.
- The owner can still interrupt at any time, but the room no longer waits for a user reply between every bot turn.
- The meeting stops when it is solved, blocked, looping, ready for approval, or needs owner input.
- The Roundtable UI includes a meetings manager so ongoing meetings can be opened, ended, or deleted.

### Breakglass From Chat
- Privileged actions do not silently fail or dump users into an API-only workflow.
- If a task requires elevated approval, Sparkbot replies in chat with a breakglass prompt.
- Send `/breakglass`, enter the operator PIN, and Sparkbot continues the waiting privileged action after approval.
- PIN submissions are handled as chat approval input and are not stored in plaintext chat history.
- Use `/breakglass close` to end the privileged session explicitly.

### Operator Access (Self-Hosted)
- **Open mode (default):** if `SPARKBOT_OPERATOR_USERNAMES` is not set, any authenticated human user is a guardian operator. Suitable for single-user installs.
- **Restricted mode:** set `SPARKBOT_OPERATOR_USERNAMES=your-username` in `.env` to limit operator access to specific chat usernames.
- **PIN protection:** set `SPARKBOT_OPERATOR_PIN_HASH` (generate with the inline command in `.env.example`) to require a PIN before break-glass privileges are granted.
- **Vault:** set `SPARKBOT_VAULT_KEY` (generate with the inline command in `.env.example`) to enable the encrypted secrets vault. Break-glass activation is required before writing secrets.
- All guardian security settings are documented with setup commands in `.env.example` under the `--- Guardian Security ---` section.
- The `/spine` Security tab provides a first-run-friendly GUI for break-glass, vault, and guardian status.

### Skill Plugin System
Drop a `.py` file into `backend/skills/` and it auto-loads on the next restart — no other files need editing.

Each skill file must export:
- `DEFINITION` — OpenAI function-calling schema dict
- `execute` — `async def execute(args, *, user_id=None, room_id=None, session=None) -> str`

Optionally declare `POLICY` to set guardian scope/action (defaults to `read/allow`).

```
backend/skills/
├── example_weather.py          # get_weather via wttr.in (no API key)
├── calendar_list_events.py     # list Google Calendar events (uses GOOGLE_* OAuth vars)
├── calendar_create_event.py    # create Google Calendar event (requires confirmation)
├── news_headlines.py           # news_headlines: HN top stories or BBC RSS (no API key)
├── currency_convert.py         # currency_convert: live rates via open.er-api.com (no API key)
└── crypto_price.py             # crypto_price: BTC/ETH/SOL/… via CoinGecko (no API key)
```

Set `SPARKBOT_SKILLS_DIR` env var to change the directory (relative to `backend/` or absolute).

Skills are guarded by the same policy/executive/memory stack as built-in tools. Built-in tools always take priority — skills are only reached as fallback.

### Agent Tools
The bot calls tools automatically mid-conversation — a chip appears briefly in the UI while the tool runs, then disappears as the response streams in.

| Tool | Trigger emoji | Description |
|------|--------------|-------------|
| `web_search` | 🔍 | Search the web (Brave → SerpAPI → DuckDuckGo fallback chain) |
| `fetch_url` | 🌐 | Fetch and read the full content of any public URL — lets Sparkbot visit and read websites, not just search |
| `get_datetime` | 🕐 | Current UTC date and time |
| `calculate` | 🧮 | Safe AST-based math evaluator (no `eval()`) |
| `create_task` | 📋 | Create a task in the current room (with optional assignee + due date) |
| `list_tasks` | 📋 | List open/done/all tasks in the current room |
| `complete_task` | ✅ | Mark a task as done by ID |
| `calendar_list_events` | 📅 | List upcoming calendar events via CalDAV |
| `calendar_create_event` | 📅 | Create a calendar event via CalDAV |
| `set_reminder` | ⏰ | Schedule a reminder (once/daily/weekly) to be sent to this room |
| `list_reminders` | ⏰ | List pending reminders for this room |
| `cancel_reminder` | ⏰ | Cancel a reminder by ID |
| `gmail_fetch_inbox` | 📬 | Fetch recent Gmail messages via Google Workspace API |
| `gmail_search` | 📬 | Search Gmail using Gmail query syntax |
| `gmail_get_message` | 📬 | Read a Gmail message in detail by message ID |
| `gmail_send` | 📤 | Send an email through Gmail API |
| `drive_search` | 📁 | Search Google Drive files and folders |
| `drive_get_file` | 📁 | Read Drive file metadata and text content when available |
| `drive_create_folder` | 📁 | Create a folder in Google Drive |
| `server_read_command` | 🖥️ | Run approved read-only diagnostics on the local server |
| `server_manage_service` | 🛠️ | Start, stop, or restart an approved local systemd service |
| `ssh_read_command` | 🔐 | Run approved read-only diagnostics on an approved SSH host alias |
| `email_fetch_inbox` | 📧 | Fetch N recent (or unread) emails from IMAP inbox |
| `email_search` | 📧 | Search inbox by subject or sender keyword |
| `email_send` | 📤 | Send an email via SMTP |
| `github_list_prs` | 🐙 | List pull requests (open/closed/all) for a repo |
| `github_get_pr` | 🐙 | Full PR details — title, body, diff stats, files, CI checks |
| `github_create_issue` | 🐙 | Create a GitHub issue with title, body, optional labels |
| `github_get_ci_status` | 🔬 | Latest workflow run results for a branch |
| `notion_search` | 📝 | Search Notion pages by keyword |
| `notion_get_page` | 📝 | Read a Notion page (blocks → readable text) |
| `notion_create_page` | 📝 | Create a Notion page with markdown-aware content |
| `confluence_search` | 🏔️ | CQL search across Confluence spaces |
| `confluence_get_page` | 🏔️ | Read a Confluence page (strips storage HTML) |
| `confluence_create_page` | 🏔️ | Create a Confluence page in any space |
| `slack_send_message` | 💬 | Post a message to a Slack channel |
| `slack_list_channels` | 💬 | List public Slack channels |
| `slack_get_channel_history` | 💬 | Fetch recent messages from a channel |
| `remember_fact` | — | Store a fact about the user for future sessions |
| `forget_fact` | — | Remove a stored fact by ID |

Tool calling uses litellm's function-calling API (OpenAI format, compatible with all supported models). Up to 5 tool-calling rounds per message.

### Persistent Memory
The bot proactively calls `remember_fact` when you reveal your name, role, timezone, preferences, or ongoing projects. Curated facts are stored in the `user_memories` DB table for the `/memory` UI, and Sparkbot now also uses a vendored Memory Guardian layer to retain redacted message/tool context and inject relevant packed memory into prompts.

- `/memory` — list stored facts (with short IDs)
- `/memory clear` — wipe all stored facts
- API: `GET /api/v1/chat/memory/`, `DELETE /api/v1/chat/memory/{id}`, `DELETE /api/v1/chat/memory/`

Memory Guardian phase-1 notes:
- durable user memory session: `user:{user_id}`
- room-context memory session: `room:{room_id}:user:{user_id}`
- current user-facing `/memory` endpoints still list curated fact memories, while prompt retrieval uses the richer memory ledger

### Calendar Integration (CalDAV)
When configured, the bot can read and create calendar events in natural language:
- *"What's on my calendar this week?"* → calls `calendar_list_events`
- *"Schedule a standup tomorrow at 9am for 30 minutes"* → calls `calendar_create_event`

Works with any CalDAV-compatible service: Google Calendar, iCloud, Nextcloud, Baikal, Radicale, Fastmail.

### Multi-Agent Rooms
Prefix any message with `@agentname` to route to a specialist:

| Agent | Emoji | Specialty |
|-------|-------|-----------|
| `@researcher` | 🔍 | Finds accurate info; uses web search proactively; cites sources |
| `@coder` | 💻 | Clean, working code with explanations |
| `@writer` | ✍️ | Writing, editing, emails, summaries, docs |
| `@analyst` | 📊 | Structured reasoning, data analysis, calculations |

- Type `@` in the input to get an agent autocomplete picker
- The bot's response shows an agent badge (e.g. `🔍 RESEARCHER`) above the text
- `/agents` command lists all available agents
- Custom agents configurable via `SPARKBOT_AGENTS_JSON` env var

### Multi-Model Support
Model preferences are per-user (in-memory, resets on service restart). Switch at any time with `/model <id>`.

| Model ID | Description |
|----------|-------------|
| `gpt-4o-mini` | GPT-4o Mini — fast, cost-effective (default) |
| `gpt-4o` | GPT-4o — most capable OpenAI model |
| `gpt-4.5` | GPT-4.5 — OpenAI advanced reasoning model |
| `gpt-5-mini` | GPT-5 Mini — fast, cost-effective next-gen model |
| `claude-3-5-haiku-20241022` | Claude Haiku — fast Anthropic model |
| `claude-sonnet-4-5` | Claude Sonnet — balanced Anthropic model |
| `gemini/gemini-2.0-flash` | Gemini Flash — fast Google model |
| `groq/llama-3.3-70b-versatile` | Llama 3.3 70B via Groq — very fast |
| `minimax/MiniMax-M2.5` | MiniMax M2.5 — reasoning + tool calling |

Token Guardian phase-2 note:
- Sparkbot can run a shadow routing pass per prompt and log a `tokenguardian_shadow` audit event with classification, confidence, recommended model, and estimated cost, without changing the live model dispatch yet.

Agent Shield / Executive / Task Guardian phase notes:
- Sparkbot now applies a policy decision to every tool call and logs `policy_decision` audit entries with `allow`, `confirm`, or `deny`.
- Room-level `execution_allowed` is now enforced for server and SSH operations.
- High-risk tool calls are wrapped by an Executive Guardian decision journal under `data/guardian/executive/decisions/`.
- Task Guardian can schedule approved read-only jobs and post their results back into the room.
- Sparkbot DM now includes a controls panel for execution gate, recent policy decisions, and Task Guardian jobs.
- Consumer rollout notes live in `consumer_readiness_checklist.md`.
- Telegram bridge can run in long-polling mode with only `TELEGRAM_BOT_TOKEN`; private Telegram chats map into real Sparkbot rooms, and `/approve` or `/deny` can resolve pending confirmations.
- Discord gateway bot responds to DMs and @mentions; each channel maps to a dedicated Sparkbot room; `/approve` and `/deny` work identically to Telegram.
- WhatsApp Cloud API bridge (via pywa) mounts a webhook at `/whatsapp`; user-initiated replies are free-form within the 24-hour session window; `approve`/`deny` text commands handle pending confirmations.
- GitHub bridge accepts signed webhooks for issue comments and PR review comments; `/sparkbot` or `@sparkbot` in a comment maps the thread into a Sparkbot room, and `approve` / `deny` resolves pending confirmations in-thread.
- All three inbound bridges emit an explicit startup status log so ops can confirm enabled vs disabled state immediately after boot.

---

## Configuration

All configuration is via environment variables, but there are now two distinct templates:

- Desktop / laptop Docker installs: copy [`.env.local.example`](./.env.local.example) to `.env.local`
- Server / systemd installs: copy [`.env.example`](./.env.example) to repo-root `.env`

Important: the backend reads the repo-root `.env` (`/home/youruser/sparkbot-v2/.env`) for the simple systemd deployment. `backend/.env` is not the production file for that layout.

### Server / systemd profile

The checked-in service example at [deploy/systemd/sparkbot-v2.service.example](./deploy/systemd/sparkbot-v2.service.example) matches the working server shape:

- working directory: `/home/youruser/sparkbot-v2/backend`
- environment file: `/home/youruser/sparkbot-v2/.env`
- backend bind: `127.0.0.1:8091`

Full steps: [docs/systemd-single-node.md](./docs/systemd-single-node.md)

### Minimum required for a hosted install
```env
ENVIRONMENT=production
FRONTEND_HOST=https://chat.example.com
BACKEND_CORS_ORIGINS=https://chat.example.com
SECRET_KEY=<random 32+ char string>
FIRST_SUPERUSER_PASSWORD=<strong admin password>
SPARKBOT_PASSPHRASE=<strong passphrase>
```

Then set either:

- `DATABASE_TYPE=sqlite` plus `SPARKBOT_DATA_DIR=/home/youruser/sparkbot-v2/backend/data`
- or `DATABASE_TYPE=postgresql` plus the `POSTGRES_*` variables

And set at least one provider key such as `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `MINIMAX_API_KEY`, or `OPENROUTER_API_KEY`.

### Optional — Additional LLM Providers
```env
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=gsk_...
MINIMAX_API_KEY=...
SPARKBOT_MODEL=gpt-4o-mini   # default model for all users
```

### Optional — Google Workspace (Gmail + Drive)
```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
GOOGLE_GMAIL_USER=me                 # optional, default "me"
GOOGLE_DRIVE_SHARED_DRIVE_ID=...     # optional, for a shared drive default corpus
```

Recommended Google OAuth scopes on the refresh token:
- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.send`
- `https://www.googleapis.com/auth/drive.readonly`
- `https://www.googleapis.com/auth/drive.file`

### Optional — Memory Guardian
```env
SPARKBOT_MEMORY_GUARDIAN_ENABLED=true
SPARKBOT_MEMORY_GUARDIAN_DATA_DIR=./data/memory_guardian
SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS=1200
SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT=6
```

### Optional — Token Guardian Shadow Mode
```env
SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED=true
```

### Optional — Executive Guardian + Task Guardian
```env
SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED=true
SPARKBOT_TASK_GUARDIAN_ENABLED=true
SPARKBOT_TASK_GUARDIAN_POLL_SECONDS=60
SPARKBOT_TASK_GUARDIAN_MAX_OUTPUT=2000
SPARKBOT_GUARDIAN_DATA_DIR=./data/guardian
```

### Optional — Telegram Bridge
```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_POLL_ENABLED=true
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_REQUIRE_PRIVATE_CHAT=true
TELEGRAM_POLL_TIMEOUT_SECONDS=45
TELEGRAM_POLL_RETRY_SECONDS=5
```

Notes:
- First version uses Telegram long polling so setup can stay as simple as adding the bot token.
- Telegram is private-chat-first; each Telegram chat is mapped into a dedicated Sparkbot room.
- Sparkbot stores Telegram conversations in the same room history and uses `/approve` or `/deny` for pending confirmations.
- Reminder and Task Guardian room notifications can fan back out to linked Telegram chats.

### Optional — Discord Bridge
```env
DISCORD_BOT_TOKEN=
DISCORD_ENABLED=false
DISCORD_DM_ONLY=false         # true = DMs only; false = DMs + @mentions
DISCORD_GUILD_IDS=            # comma-separated snowflakes to restrict guilds (optional)
```

Setup:
1. [Discord Developer Portal](https://discord.com/developers) → New App → Bot → copy token
2. Bot Settings → **Message Content Intent** must be **enabled** (privileged intent)
3. OAuth2 → URL Generator → scopes: `bot` + permissions: Send Messages, Read Message History
4. Set `DISCORD_ENABLED=true` and paste the token

Notes:
- Each DM channel and each guild channel where the bot is @mentioned maps to a dedicated Sparkbot room.
- Runs as an asyncio task alongside FastAPI — same pattern as Telegram, no extra process needed.
- `message.content` in DMs is always available; guild messages require the Message Content Intent toggle in the portal.
- `/approve` and `/deny` resolve pending tool confirmations (same as Telegram).

### Optional — WhatsApp Bridge (Meta Cloud API)
```env
WHATSAPP_ENABLED=false
WHATSAPP_PHONE_ID=            # numeric Phone Number ID from Meta Developer Portal
WHATSAPP_TOKEN=               # permanent system user token (whatsapp_business_messaging scope)
WHATSAPP_VERIFY_TOKEN=sparkbot-wa-verify   # must match what you set in Meta portal
WHATSAPP_APP_ID=              # optional: for auto webhook registration
WHATSAPP_APP_SECRET=          # optional: for auto webhook registration
WHATSAPP_ALLOWED_PHONES=      # comma-separated E.164 numbers to allowlist (optional)
PUBLIC_URL=https://your-domain.com
```

Setup:
1. [Meta Developer Portal](https://developers.facebook.com) → New App → WhatsApp → Add Phone Number
2. System User → generate permanent token with `whatsapp_business_messaging` scope
3. Webhook URL: `https://yourdomain.com/whatsapp` (pywa mounts this automatically)
4. Verify Token: match `WHATSAPP_VERIFY_TOKEN`; subscribe to: `messages`

Notes:
- The registered phone **cannot** be simultaneously used in personal WhatsApp or WhatsApp Business App. Use a dedicated number or Meta's free sandbox test number for development.
- User-initiated replies within the 24-hour session window are free-form text — no templates needed for a conversational bot.
- Business-initiated messages (templates, marketing) are billed per message — not relevant for a reactive chatbot.
- `approve` / `deny` text resolves pending tool confirmations (same as Telegram/Discord).
- Uses [pywa](https://github.com/david-lev/pywa) 3.8.0 — the only well-maintained Python library for the official Cloud API.

### Optional — GitHub Bridge
```env
GITHUB_BRIDGE_ENABLED=false
GITHUB_TOKEN=               # token used for GitHub tools + posting bridge replies
GITHUB_WEBHOOK_SECRET=      # required for X-Hub-Signature-256 verification
GITHUB_BOT_LOGIN=sparkbot
GITHUB_DEFAULT_REPO=owner/repo
GITHUB_ALLOWED_REPOS=owner/repo,owner/another-repo
```

Setup:
1. GitHub repo → Settings → Webhooks → Add webhook
2. Payload URL: `https://yourdomain.com/api/v1/chat/github/events`
3. Content type: `application/json`
4. Secret: match `GITHUB_WEBHOOK_SECRET`
5. Events: `Issue comments` and `Pull request review comments`

Notes:
- The bridge verifies `X-Hub-Signature-256` and ignores repos outside `GITHUB_ALLOWED_REPOS` when the allowlist is set.
- Use `/sparkbot your request` or `@sparkbot your request` in a comment to invoke Sparkbot.
- `approve` / `deny` in the same thread resolves pending confirmations.
- Each GitHub issue / PR thread maps to a dedicated Sparkbot room and shares the same audit, policy, and approval flow as chat.

### Optional — Skill Plugins
```env
SPARKBOT_SKILLS_DIR=skills   # path relative to backend/ or absolute
```

### Optional — Voice (Whisper + TTS)
Requires `OPENAI_API_KEY` (already needed for the default model).
```env
SPARKBOT_TTS_VOICE=alloy   # alloy | echo | fable | onyx | nova | shimmer
SPARKBOT_TTS_MODEL=tts-1   # tts-1 (fast) or tts-1-hd (higher quality)
```

### Optional — Server Operations
```env
SPARKBOT_ALLOWED_SERVICES=sparkbot-v2
SPARKBOT_SERVICE_USE_SUDO=false
SPARKBOT_SERVER_COMMAND_TIMEOUT_SECONDS=20
SPARKBOT_SSH_ALLOWED_HOSTS=
SPARKBOT_SSH_ALLOWED_SERVICES=
SPARKBOT_SSH_CONNECT_TIMEOUT_SECONDS=10
SPARKBOT_SSH_COMMAND_TIMEOUT_SECONDS=30
```

Notes:
- `server_read_command` is limited to built-in read-only profiles like system overview, memory, disk, listeners, process snapshot, service status, and recent service logs.
- `server_manage_service` is limited to services listed in `SPARKBOT_ALLOWED_SERVICES`, requires room `execution_allowed=true`, and uses the chat confirmation modal before execution.
- `ssh_read_command` only works for SSH aliases listed in `SPARKBOT_SSH_ALLOWED_HOSTS`.
- Task Guardian only schedules approved read-only tools. It does not run arbitrary shell commands.
- If service actions require elevation, set `SPARKBOT_SERVICE_USE_SUDO=true` and give the Sparkbot service user a narrow passwordless sudo rule for the allowed units.

### Optional — Web Search
Sparkbot uses a fallback chain: Brave → SerpAPI → DuckDuckGo. **DuckDuckGo works out of the box with no API key** — web search is available immediately after install. For higher reliability and rate limits, configure one of the paid providers:
```env
BRAVE_SEARCH_API_KEY=...       # Brave Search API — free tier 2k req/day, most reliable
SERPAPI_KEY=...                # SerpAPI (Google) — fallback
SEARCH_CACHE_TTL_SECONDS=300   # Cache identical queries for N seconds (default 300)
OPENCLAW_CONFIG_PATH=...       # Optional: path to openclaw.json to reuse its search key
```

### Optional — Calendar (CalDAV)
```env
CALDAV_URL=https://www.google.com/calendar/dav/you@gmail.com/events
CALDAV_USERNAME=you@gmail.com
CALDAV_PASSWORD=your-app-password
```

**Provider setup:**
| Provider | URL | Password |
|----------|-----|----------|
| Google Calendar | `https://www.google.com/calendar/dav/{email}/events` | [App Password](https://myaccount.google.com/apppasswords) |
| iCloud | `https://caldav.icloud.com` | [App-Specific Password](https://appleid.apple.com) |
| Nextcloud | `https://your-server/remote.php/dav/` | Account password |
| Fastmail | `https://caldav.fastmail.com/dav/` | App password |
| Baikal / Radicale | Your server URL | Account password |

After changing env vars: `sudo systemctl restart sparkbot-v2`

---

## Running Locally

**Docker (recommended — works on all platforms):**

```bash
cp .env.local.example .env.local
docker compose -f compose.local.yml up --build
```

**Without Docker (for backend development):**

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
bun install
bun run dev
```

---

## Deployment (Production)

```bash
# Build frontend
cd frontend
bun run build
sudo cp -r dist/* /var/www/sparkbot/

# Restart backend
sudo systemctl restart sparkbot-v2

# Health check
curl https://your-domain.com/api/v1/utils/health-check/
```

---

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat/users/bootstrap` | Auto-create user + DM room, return room_id |
| `POST` | `/api/v1/chat/users/login` | Login with passphrase → sets HttpOnly `chat_token` cookie |
| `DELETE` | `/api/v1/chat/users/session` | Logout → clears session cookie |
| `GET` | `/api/v1/chat/rooms/{id}/messages` | Room message history |
| `POST` | `/api/v1/chat/rooms/{id}/messages/stream` | Send message, receive SSE stream |
| `POST` | `/api/v1/chat/rooms/{id}/upload` | Upload file, receive SSE stream |
| `POST` | `/api/v1/chat/rooms/{id}/voice` | Voice recording → Whisper → SSE stream |
| `POST` | `/api/v1/chat/voice/tts` | Text → `audio/mpeg` TTS stream |
| `GET` | `/api/v1/chat/messages/{id}/search?q=` | Full-text message search |
| `GET` | `/api/v1/chat/models` | List available LLM models |
| `POST` | `/api/v1/chat/model` | Set model preference `{"model": "gpt-4o"}` |
| `GET` | `/api/v1/chat/memory/` | List stored user memories |
| `DELETE` | `/api/v1/chat/memory/{id}` | Delete a specific memory |
| `DELETE` | `/api/v1/chat/memory/` | Clear all memories |
| `GET` | `/api/v1/chat/audit` | Recent tool audit log (room-scoped) |
| `GET` | `/api/v1/utils/health-check/` | Health check → `true` |

Interactive API docs: `http://localhost:8000/docs` (or whichever port you configured)

---

## Project Files

```
sparkbot-v2/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── main.py                   # Router assembly
│   │   │   └── routes/chat/
│   │   │       ├── llm.py                # litellm routing, model registry
│   │   │       ├── tools.py              # LLM tool definitions + executors
│   │   │       ├── rooms.py              # Room CRUD + streaming message endpoint
│   │   │       ├── messages.py           # Message CRUD + search
│   │   │       ├── memory.py             # User memory CRUD endpoints
│   │   │       ├── uploads.py            # File upload + vision SSE
│   │   │       ├── voice.py              # Voice: Whisper transcription + TTS endpoints
│   │   │       ├── model.py              # Model switching endpoints
│   │   │       ├── github.py             # GitHub webhook bridge endpoint
│   │   │       ├── users.py              # Chat user management + bootstrap
│   │   │       └── websocket.py          # WebSocket handler
│   │   ├── services/
│   │   │   ├── skills.py                 # Skill plugin loader (auto-discovers backend/skills/)
│   │   │   ├── telegram_bridge.py        # Telegram long-poll bridge
│   │   │   ├── discord_bridge.py         # Discord gateway bot bridge
│   │   │   ├── whatsapp_bridge.py        # WhatsApp Cloud API webhook bridge (pywa)
│   │   │   ├── github_bridge.py          # GitHub issue / PR comment webhook bridge
│   │   │   └── guardian/                 # Policy, executive, memory, task guardian
│   │   ├── models.py                     # SQLModel DB models
│   │   ├── crud.py                       # DB helper functions
│   │   └── alembic/                      # DB migrations
│   ├── skills/                           # Drop skill .py files here — auto-loaded on restart
│   │   ├── example_weather.py            # get_weather via wttr.in (no API key)
│   │   ├── calendar_list_events.py       # list Google Calendar events
│   │   ├── calendar_create_event.py      # create Google Calendar event (confirmation required)
│   │   ├── morning_briefing.py           # morning_briefing: Gmail + Calendar + reminders digest
│   │   ├── news_headlines.py             # news_headlines: HN + BBC RSS (no API key)
│   │   ├── currency_convert.py           # currency_convert: live FX rates (no API key)
│   │   └── crypto_price.py              # crypto_price: CoinGecko (no API key)
│   ├── pyproject.toml                    # Python dependencies
│   └── venv/                             # Python virtualenv
├── frontend/
│   ├── src/
│   │   ├── pages/SparkbotDmPage.tsx      # Main chat UI (streaming, commands, tools, meeting)
│   │   ├── components/chat/
│   │   │   ├── MessageBubble.tsx         # Markdown + syntax highlight + copy button
│   │   │   └── ChatInput.tsx             # Input bar
│   │   └── lib/chat/types.ts             # Shared TypeScript types
│   └── dist/                             # Built frontend (deployed to /var/www/sparkbot-remote)
└── uploads/                              # Uploaded files storage
```

---

## Security

Sparkbot v2 has passed a full internal security audit (Phases A–E). Security is the primary differentiator — see [SECURITY.md](./SECURITY.md) for the full architecture.

### Guardian Stack (summary)

```
User message → Token Guardian → Memory Guardian → LLM
                                                    │ tool_calls
                                                    ▼
                                           Agent Shield (policy)
                                                    │ allowed / confirmed
                                                    ▼
                                          Executive Guardian (journal)
                                                    │
                                                    ▼
                                           Tool executes → audit log
```

| Control | Implementation |
|---------|----------------|
| **Policy layer** | Every tool classified read / write / execute / admin; unknown tools denied |
| **Write-tool gate** | LLM cannot email/Slack/GitHub/Notion/Confluence/Calendar/Drive autonomously — confirmation modal required |
| **Execution gate** | Server + SSH require room owner to explicitly enable; defaults off |
| **Executive journal** | High-risk actions written to a decision log before + after execution |
| **Audit trail** | Every tool call logged (allow/confirm/deny) with redacted args |
| **Audit redaction** | Secret-pattern keys and token-format values stripped at write time |
| **Session tokens** | HttpOnly `Secure SameSite=Strict` cookie — never exposed to JavaScript |
| **Response headers** | HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy, Referrer-Policy |
| **Rate limiting** | Passphrase login: 10 attempts / 15 min per IP |
| **Room authz** | All message/upload/audit endpoints gated by membership; non-members get 403 |
| **Dep scanning** | `pip-audit` + `npm audit` on every push and weekly via GitHub Actions |
| **Secret scanning** | `gitleaks` pre-commit hook + CI gate |
| **Git history** | `.env` purged from all commits via `git filter-repo` |

---

## Roadmap

### Features — all complete ✅
- ✅ Streaming SSE responses, markdown rendering, conversation context
- ✅ Slash commands + autocomplete, meeting mode, message search, file uploads
- ✅ Multi-model support via litellm (7 providers)
- ✅ Tool calling framework (25+ tools across web, calendar, email, GitHub, Notion, Confluence, Slack)
- ✅ Persistent per-user memory (DB-backed, injected into system prompt)
- ✅ Calendar integration (CalDAV), task management, proactive reminders
- ✅ Document summarisation (PDF/DOCX/TXT/MD/CSV)
- ✅ Email integration (IMAP + SMTP), GitHub, Notion, Confluence, Slack
- ✅ Multi-agent rooms (@researcher / @coder / @writer / @analyst)
- ✅ Audit log (tool calls recorded, room-scoped, `/audit` command)
- ✅ Voice input + TTS replies (Whisper transcription → LLM pipeline → optional TTS playback)
- ✅ Discord bridge — gateway bot, DMs + @mentions, `/approve` / `/deny` confirmation flow
- ✅ WhatsApp bridge — Meta Cloud API webhook (pywa), free-form replies in 24h service window
- ✅ GitHub bridge — signed webhook for issue / PR comments, room mapping, `approve` / `deny`

### Security audit — all phases complete ✅
- ✅ Phase A — access control + secret hygiene
- ✅ Phase B — authentication/session hardening
- ✅ Phase C — runtime correctness
- ✅ Phase D — write-tool gate, audit redaction, HttpOnly cookies, security headers
- ✅ Phase E — dependency scanning CI workflow

### Phase 1 — Personal + Work Assistant Foundations ✅ (2026-03-07)
- ✅ Proactive notification fan-out — reminders and Task Guardian results now push to Telegram, Discord, AND WhatsApp (was Telegram-only)
- ✅ Google Calendar skill — `calendar_list_events` and `calendar_create_event` via existing Google OAuth (no new packages)
- ✅ News skill — `news_headlines`: Hacker News top stories (tech) or BBC RSS (world/business/science/sports/health), no API key
- ✅ Currency skill — `currency_convert`: live FX rates via open.er-api.com, no API key
- ✅ Crypto skill — `crypto_price`: BTC/ETH/SOL/… prices + 24h change + market cap via CoinGecko, no API key

### Pending (ops, not blocking)
- Key rotation — run after active testing window closes (see `ROTATION_RUNBOOK.md`)
- Skill marketplace / built-in skill library (filesystem drop-in is the foundation)

### Phase 2 — Proactive Autonomy ✅ (2026-03-07)
- ✅ Task Guardian write-actions — `gmail_send`, `slack_send_message`, `calendar_create_event` can now run on a schedule. Pre-authorized via the existing `guardian_schedule_task` confirmation modal. Opt-in via `SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true`.
- ✅ Morning briefing skill — `morning_briefing`: one-shot compound digest combining Gmail unread summary, Google Calendar events, and pending room reminders. Fans out to Telegram/Discord/WhatsApp via Phase 1 fan-out. Perfect daily Task Guardian job.

### Phase 3 — Work UX Polish ✅ (2026-03-07)
- ✅ Reply threading UI — hover any message to reply; banner above input shows quoted snippet; `reply_to_id` sent in stream POST body; quote preview renders inside bubble
- ✅ Message edit UI — hover own messages to edit inline; auto-resizing textarea; saves via PATCH `/api/v1/chat/messages/{room_id}/message/{message_id}`; `· edited` timestamp badge

### Phase 4 — Onboarding & Health Observability ✅ (2026-03-07)
- ✅ Guardian health card — four color-coded subsystem tiles (LLM, Task Guardian, Token Guardian, Comms/Approvals) replace the plain dashboard summary; shows last run status, pending approvals, and routing mode inline
- ✅ Onboarding copy — three-panel layout: Start here steps, updated first prompts (morning briefing, crypto), "How Sparkbot protects you" explainer (write confirmations, execution gate, Token Guardian shadow mode)
- ✅ Task tool dropdown — added morning_briefing, calendar_create_event, news_headlines, crypto_price, currency_convert to the Task Guardian create-job form

### Phase 5 — Persona, Skill Discovery & Voice Quick-Capture ✅ (2026-03-07)
- ✅ Per-room persona — 500-char freetext instruction prepended to every LLM system prompt in the room; saved via PATCH room; textarea + char counter in settings dialog; Alembic migration included
- ✅ Skill marketplace UI — `GET /api/v1/chat/skills` lists all loaded plugins with name, description, action_type (read/write), high_risk, and execution_gate flags; settings dialog shows colored chip cards; auto-refreshes on open
- ✅ Voice quick-capture — `POST /rooms/{id}/voice/transcribe` returns `{"text":"..."}` (no LLM); voiceMode OFF = mic transcribes and pastes to input; voiceMode ON = original full voice-message flow with TTS readback

### Phase 6 — Spawn Agent ✅ (2026-03-07)
- ✅ Spawn Agent in Control Center — "Spawn Agent" section in the settings dialog; select from 11 specialty templates (Data Scientist, DevOps, Legal Advisor, HR Manager, Marketing, Finance, Customer Support, PM, Security Analyst, Technical Writer, or Custom); auto-fills emoji, name, description, and system prompt; name sanitized to lowercase alphanumeric/underscore
- ✅ CustomAgent DB persistence — `custom_agents` table (Alembic migration `c4e8b2f9a017`); spawned agents survive restart; `created_by` FK to user
- ✅ Hot-load runtime registry — spawned agents available via `@name` mention immediately after creation; no restart required; `_RUNTIME_AGENTS` dict updated in-process by `register_agent()` / `unregister_agent()`
- ✅ Built-in agent protection — DELETE endpoint returns 403 for built-in agents (researcher, coder, writer, analyst)
- ✅ Active agents list — settings dialog shows all custom agents with Remove buttons; built-in agents shown as read-only badges

### Phase 7 — Smart Scheduling & Mobile Polish (planned)
- Skill scheduler helper — detect "every morning / daily" intent in chat and auto-suggest a Task Guardian job
- Mobile-optimized input — swipe-to-reply, better touch targets
- Mobile UX — swipe-to-reply, larger touch targets
