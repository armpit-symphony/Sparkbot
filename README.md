# Sparkbot

**Sparkbot** is a self-hosted AI workspace assistant for people who want the power of a connected AI system without handing their whole workflow to a hosted SaaS account. It can run as a desktop app on Windows, macOS, and Linux, or as a Docker/server install for a team or private network.

Use it to chat, search, summarize documents, control a browser, run shell commands, manage tasks, schedule briefings, work with email and calendars, coordinate agents, and keep an audit trail around sensitive actions.

**Download:** [armpit-symphony.github.io/Sparkbot](https://armpit-symphony.github.io/Sparkbot/)

**Current release line:** v1.6.55

> Sparkbot stores its app data locally. If you connect a cloud LLM provider or an external service, the text and actions needed for that provider or service are sent to that provider. Local models can run without an LLM cloud account.

---

## What Sparkbot Is

Sparkbot combines five pieces into one local assistant:

1. **Chat workspace** - rooms, files, memory, slash commands, meetings, and searchable history.
2. **Computer control** - browser automation, shell commands, live terminal sessions, and code execution.
3. **Connected work tools** - email, calendars, files, GitHub, Slack, Notion, Confluence, Jira, Linear, contacts, stocks, Spotify, YouTube, and more.
4. **Agent orchestrator** - multi-agent Round Table meetings, task-linked project rooms, scheduled Guardian jobs, meeting heartbeats, notes/artifacts, and owner interruptions.
5. **Guardian controls** - policy checks, confirmations, policy simulation, persistent approvals, vault-backed secrets, break-glass access, scheduled-job verification, and audit logs.

Sparkbot is also the command center for the wider **LIMA** system:

- **Sparkbot** = governed agentic assistant for computer work, cloud ops, business workflows, approvals, memory, and audit.
- **LIMA Robotics OS** (**LIMA = Local Intelligent Machine Agent**) = robotics and physical-world runtime exposed through MCP tools.
- **Together** = one "everything agent" control plane for computer work, connected services, and robot skills, with replay/simulation demos available before any hardware is attached.

The desktop app is the easiest path for one person. Docker and systemd deployments are available when you want Sparkbot on a server.

---

## Main Capabilities

### Chat, Files, And Knowledge
- Streaming chat with Markdown, code blocks, search, replies, message editing, and exports
- File uploads for PDFs, DOCX files, text, Markdown, CSVs, images, and other documents
- Knowledge base ingestion for documents and URLs, with BM25 full-text retrieval when related questions come up
- Persistent memory for user facts, preferences, relationships, and recurring work context
- Meeting mode that captures notes, decisions, and action items into a dated Markdown export

### Computer Control
- **Shell** — run any PowerShell or bash command from chat; working directory persists so `cd` carries forward
- **Live terminal** — interactive xterm.js terminal panel in the Workstation; Sparkbot can inject commands while you watch
- **Browser automation** — opens a real Chromium browser, navigates, fills forms, clicks buttons, logs in, reads page content
- **Code execution** — run Python, Node.js, or Bash directly in chat; get output back immediately
- **Web scraping** — fetch and read any public URL for research, docs, price checks

### Productivity & Work
- **Email** — Gmail + Outlook (Microsoft 365) + IMAP/SMTP: read inbox, search, compose, send, summarize threads
- **Calendar** — Google Calendar + Outlook Calendar + CalDAV (iCloud, Nextcloud, Fastmail): list events, create meetings, check availability
- **Google Drive** — search files, read documents, create folders
- **OneDrive** — list and read files via Microsoft Graph
- **GitHub** — list PRs, read diffs, create issues, check CI status
- **Slack** — post messages, list channels, read channel history
- **Notion** — search pages, read content, create pages
- **Confluence** — search spaces, read pages, create pages
- **Linear** — list, create, and update issues; filter by team/state/assignee
- **Jira** — list, create issues, add comments; full JQL filter support
- **Tasks & reminders** — create and track tasks in any room; schedule recurring reminders that fan out to Telegram, Discord, and WhatsApp
- **Contacts** — personal contact manager with Google Contacts sync; search by name, email, or phone
- **Time tracking** — start/stop project timers, manually log sessions, view weekly reports
- **Morning digest** — fully configurable: weather, stocks, Gmail/Outlook, calendar, news headlines, reminders in one message

### Intelligence & Memory
- **Relationship memory** — personal CRM built from conversation; remember facts, notes, and interaction history for any person
- **Multi-model** — OpenAI, Anthropic, Google, Groq, MiniMax, OpenRouter, Ollama — switch live with `/model`
- **Model stack** — configure Primary, two Backups, and a Heavy Hitter; Sparkbot auto-routes and falls back across providers
- **Multi-agent rooms** — mention `@researcher`, `@coder`, `@writer`, `@analyst`, `@meetings_manager`, `@web_designer`, `@marketing_agent`, `@business_analyst`, or any custom agent for a specialist response
- **Spawn agents** — create named agents with custom system prompts and first-class identity metadata from 11 specialty templates
- **Agent identity + kill switches** — each agent exposes owner, purpose, scopes, allowed tools, expiration, risk tier, and kill-switch state; disabled agents do not route from `@mention`
- **Persistent memory** — Sparkbot stores facts about you and injects them into every conversation
- **Memory retrieval controls** — Guardian Memory now defaults to BM25 full-text recall, with optional hybrid embedding rerank gated behind `SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS=true`
- **Verified memory writes** — durable facts carry source, confidence, verification state, and redaction metadata; low-confidence facts go to pending approvals instead of being promoted automatically
- **Memory lifecycle controls** — short chat noise is filtered before ledger writes, nightly consolidation promotes durable facts, old hot-ledger events rotate into month archives, and stale low-weight facts leave the prompt path
- **Self-introspection** — built-in `memory_recall`, `memory_retrieval_stats`, and `memory_reindex` tools let Sparkbot search hot memory plus opt-in cold archives, report hit rate / precision@5 / latency, and rebuild indexes; Task Guardian runs nightly verification/evaluation metrics
- **Knowledge base** — ingest any document or URL; Sparkbot searches it with BM25 full-text ranking when relevant
- **Skill plugins** — drop a `.py` file into `backend/skills/` to add a new tool; auto-discovered on restart

### Media & Content
- **Voice chat** — mic input can run as transcribe-only, one-shot voice message, or hands-free conversation loop with spoken replies
- **YouTube summarization** — paste a YouTube URL and get a transcript + summary; no API key required
- **Podcast/audio transcription** — upload or link an audio file; transcribed via OpenAI Whisper
- **News headlines** — Hacker News top stories or BBC RSS (world, tech, business, science, sports, health)
- **Spotify** — play, pause, skip, search, and control volume; works on any active Spotify device
- **Stocks & portfolio** — real-time quotes for any ticker; track a personal portfolio with P&L

### Workstation
- **Office floor** — visual grid of all your AI desks: Sparkbot, model stack companions, agents, invite seats, terminal
- **Unified top tabs** — Chat, Workstation, Controls, Robo OS, Command Center, and Info stay visible from the main app surfaces
- **Command Center** — the former Spine Ops surface is now Sparkbot's operational hub, with Room Persona first, then System Health, Computer Control, Token Guardian, Task Guardian, and Spine/Guardian queues
- **Full-page Controls** — model setup, providers, comms, agents, and routing configuration stay in a connected app page instead of a chat-only panel
- **Phone access** — the full workstation now opens on phone-sized screens as a horizontally scrollable operations map instead of blocking mobile users
- **Robo OS** — Workstation button for the unified MCP control plane, LIMA Robotics OS manifests, policy tags, no-hardware replay/simulation commands, and robot-skill safety posture
- **Invite Wing** — seat any model with its own API key and model ID; routes directly to that provider. The **Claude** and **ChatGPT** desks now use a matching `API Key / Subscription` setup pattern for Anthropic and OpenAI subscription-linked credentials, and the third desk is preset for **xAI Grok**
- **Round Table** — autonomous multi-agent meeting room; all agents contribute without you typing between turns
- **Company Operations** — view all Guardian Tasks across every room, active meetings, and launch project rooms in one click
- **Task-linked meetings** — hit **Meet** on any task and a pre-seeded project room opens
- **Orchestrated runs** — meeting rooms keep a participant manifest, run an hourly `meeting_heartbeat` Guardian task, generate structured notes/artifacts, and seed follow-up Guardian tasks from action items

### Proactive Mode & Scheduled Autonomy (Task Guardian)
- **Scheduled jobs** — tell Sparkbot to run any tool on a schedule (hourly, daily, custom interval)
- **Daily schedules** — use `daily:HH:MM` UTC schedules for predictable morning briefings and calendar previews
- **Push alerts** — scheduled jobs can push results to your phone via Telegram or Discord — works even when you're away from the desktop
- **Autonomous execution** — jobs run in the background and post results to the room
- **Write-action scheduling** — opt-in to scheduled email, Slack, and calendar writes
- **Verifier guardian** — each scheduled run is evaluated before commit; bounded retries with escalation

### Communication Channels
- **Telegram** — private chats map to Sparkbot rooms; `/approve` / `/deny` resolve confirmations; receives proactive push alerts
- **Discord** — DMs and @mentions map to rooms; same approval flow; receives push alerts
- **WhatsApp** — Meta Cloud API webhook; free-form replies in the 24-hour session window
- **GitHub** — token, SSH, or GitHub App setup from Controls; token scopes and repo allowlists define what Sparkbot can access

### Platform Integrations
- **Microsoft 365** — Outlook mail + calendar, OneDrive (requires Azure app registration)
- **Apple (macOS)** — Contacts, Reminders, and Notes via native AppleScript; no API key required
- **Google Workspace** — Gmail, Google Calendar, Google Drive, Google Contacts
- **Natural language → SQL** — query any local SQLite database using plain English

### Security
- **Policy layer** — every tool classified read / write / execute / admin; unknown tools denied by default
- **Computer Control** — room-level always-on device control; when off, commands, edits, browser writes, comms sends, Vault, and break-glass actions require the 6-digit operator PIN
- **Write-tool confirmation** — confirmation and break-glass flows stop risky writes unless Computer Control is explicitly on
- **Run timeline** — dashboard trace endpoint shows policy/tool events with model, agent, decision, summary, and audit hash
- **Connector health** — dashboard endpoint reports setup state, read/write scopes, setup tests, and audit metadata
- **Workflow templates + evals** — governed workflow templates and deterministic agent-behavior evals ship with the Guardian dashboard
- **Guardian Vault** — encrypted secret storage; break-glass PIN required before writing secrets
- **Audit trail** — every tool call logged with allow/confirm/deny, redacted args, and timestamps
- **HttpOnly cookies** — session tokens never exposed to JavaScript
- **Dep scanning** — `pip-audit` + `npm audit` + `gitleaks` on every push

---

## Install

### Desktop App (Windows · macOS · Linux)

The desktop app is a standalone installer — no Docker, no terminal, no WSL required.

**Step 1 — Download and install**

Go to [armpit-symphony.github.io/Sparkbot](https://armpit-symphony.github.io/Sparkbot/) and download the installer for your platform.

- **Windows:** run `Sparkbot.Local_x.x.x_x64-setup.exe`. If Windows SmartScreen appears, click **More info → Run anyway** (the app is unsigned; see [Code Signing](#code-signing) below).
- **macOS:** open the `.dmg` and drag Sparkbot to Applications.
- **Linux:** make the `.AppImage` executable and run it.

**Step 2 — Add a provider key**

On first launch, Sparkbot opens **Sparkbot Controls**. Paste at least one LLM API key, or configure a local Ollama model if you want local-only model execution.

| Provider | Where to get a key |
|----------|--------------------|
| OpenAI | [platform.openai.com](https://platform.openai.com) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) |
| Google | [aistudio.google.com](https://aistudio.google.com) |
| Groq | [console.groq.com](https://console.groq.com) |
| MiniMax | [minimax.io](https://www.minimax.io) |
| OpenRouter | [openrouter.ai](https://openrouter.ai) — one key, 100+ models |

**Step 3 — Start chatting**

Click **Sparkbot** on the office floor to open the main chat. Everything else can be configured from there.

---

### Docker Local

Local machine:

```bash
git clone https://github.com/armpit-symphony/Sparkbot.git
cd Sparkbot
bash scripts/sparkbot-start.sh --local
```

Cloud server / VPS / DigitalOcean:

```bash
git clone https://github.com/armpit-symphony/Sparkbot.git
cd Sparkbot
bash scripts/sparkbot-start.sh --server
```

The start script supports both Docker Compose v2 (`docker compose`) and legacy Docker Compose v1.29.x (`docker-compose`), creates `.env.local` when needed, opens the setup wizard if no provider is configured, writes the non-secret Compose interpolation values to root `.env`, and starts Sparkbot detached in the background. Local mode binds to `127.0.0.1`. Server mode binds the web UI to `0.0.0.0`, disables local auto-login, prompts you to create a private passphrase before startup, detects the public IP, prints the real browser URL, and warns you to use firewall rules or a reverse proxy with auth.

Server mode rejects blank, placeholder, too-short, and local-default passphrases. Passphrase prompts try the secure hidden path when it is reliable, then automatically switch to visible input with a warning if the SSH terminal cannot accept hidden input. Add `--show-passphrase-input` to make passphrase creation visible from the start for troubleshooting. The passphrase is saved to `.env.local` and is not printed by the launcher.

On a fresh Ubuntu server, install the Docker Compose v2 and buildx plugins first:

```bash
sudo apt update
sudo apt install docker-buildx-plugin docker-compose-plugin -y
```

Or let Sparkbot try that install step:

```bash
bash scripts/sparkbot-start.sh --install-docker-plugins
```

Provider key prompts are visible by default so SSH paste works reliably. The setup script warns before each visible key prompt and does not print stored secrets itself. If you prefer hidden provider-key entry, run:

```bash
bash scripts/sparkbot-start.sh --server --hide-input
```

For SSH servers, the most reliable no-prompt path is exporting a provider key first:

```bash
export OPENAI_API_KEY="sk-..."
bash scripts/sparkbot-start.sh --server --from-env
```

You can also seed the server passphrase without an interactive prompt:

```bash
export OPENAI_API_KEY="sk-..."
export SPARKBOT_PASSPHRASE="long-private-passphrase"
bash scripts/sparkbot-start.sh --server --from-env

# or
bash scripts/sparkbot-start.sh --server --openai-key "sk-..." --passphrase "long-private-passphrase"
```

To validate the first-run prompts without starting Docker:

```bash
bash scripts/sparkbot-start.sh --server --dry-run-setup
```

If another app already uses port 3000, Sparkbot auto-selects the next open port and prints the actual URL. You can also choose one:

```bash
SPARKBOT_FRONTEND_PORT=3001 bash scripts/sparkbot-start.sh --local
```

Normal installs should use `scripts/sparkbot-start.sh`. Advanced users can still edit `.env.local` directly or run Compose manually, but raw `docker compose` reads root `.env` for interpolation and bypasses the launcher's mode, port, and setup checks.

For a public or private server install, use [deployment.md](./deployment.md) for Docker, Traefik, and Let's Encrypt, or [docs/systemd-single-node.md](./docs/systemd-single-node.md) for systemd and nginx.

---

### CLI (No Browser Required)

```bash
python sparkbot-cli.py --setup                  # first-run provider/model setup
python sparkbot-cli.py                          # interactive
python sparkbot-cli.py "What's on my calendar?" # one-shot
echo "Summarise my inbox" | python sparkbot-cli.py
```

Requires Python 3.10+, no extra packages. When Sparkbot is running, `--setup` configures provider keys and model roles through the backend Controls API. Before the server is running, it falls back to the local `.env.local` setup wizard.

---

## Using Sparkbot

### Daily Chat

Just type naturally. Sparkbot decides which tools to call based on what you ask.

```
"What's on my calendar this week?"
"Summarize the last 10 emails from my boss"
"Search Google for the latest Python release notes and give me a summary"
"Run git status in my project folder"
"Open YouTube and find a video about FastAPI"
```

For tool calls that write or send anything (email, Slack, calendar events), a **confirmation modal** appears before anything is sent. You approve or deny it.

### Slash Commands

Type `/` in the input to open the command menu.

| Command | What it does |
|---------|-------------|
| `/help` | Show all commands |
| `/model` | List available models |
| `/model gpt-4o` | Switch to a different model live |
| `/memory` | See what Sparkbot remembers about you |
| `/memory clear` | Wipe all stored memories |
| `/tasks` | List open tasks in this room |
| `/remind` | List pending reminders |
| `/search <query>` | Search message history |
| `/export` | Download conversation as Markdown |
| `/meeting start` | Begin meeting mode |
| `/meeting stop` | End meeting and export notes |
| `/audit` | Show recent bot tool actions |
| `/perf` | Model + tool latency, call counts, and last error this session |
| `/clear` | Clear view (history preserved on server) |

### Computer Control

Computer Control capabilities are shown in **Command Center** and mirrored in the **Workstation → Computer Control** panel. Command Center keeps the existing approval, break-glass, and 6-digit PIN guardrails.

**Shell commands** — just ask:
```
"Run `npm install` in my project"
"Show me what's using port 3000"
"Create a folder called backups on my Desktop"
```

**Terminal** — open the Workstation, click the Terminal desk, then click **Connect**. You get a live interactive terminal. Sparkbot can also inject commands into it from chat.

**Browser** — ask Sparkbot to open a URL, fill a form, or click a button. The browser window appears on your screen so you can watch. For sites that require login, Sparkbot can save and restore sessions.

### Agents

Prefix your message with `@agentname` to route to a specialist.

| Agent | Best for |
|-------|---------|
| `@researcher` | Finding accurate info; cites sources; uses web search |
| `@coder` | Code generation and debugging |
| `@writer` | Emails, docs, editing, summaries |
| `@analyst` | Data analysis, structured reasoning, calculations |
| `@meetings_manager` | Agendas, meeting recaps, decisions, action items, owners, and deadlines |
| `@web_designer` | Responsive page design, UI review, visual hierarchy, and implementation specs |
| `@marketing_agent` | Positioning, launch copy, campaigns, social posts, and practical growth plans |
| `@business_analyst` | Requirements, risks, priorities, metrics, workflows, and execution plans |

Type `@` in the input to get the autocomplete picker. Create custom agents in **Controls → Agents → Spawn Agent**, now positioned above Model Overrides. Fresh installs and upgraded installs receive the packaged built-in agents from the backend registry; custom agents remain database-backed and preserved.

### Command Center

Open **Command Center** from the top tabs or `/spine` (alias: `/command-center`). It is the official operator page for Room Persona, System Health, Computer Control, Token Guardian, Task Guardian, and Guardian Spine queues/logs. The page uses the same top navigation pattern as Chat, Workstation, and Controls, with the old Spine Ops internals preserved behind the route/component names where needed.

Controls is now configuration-focused: providers, model stack, comms, agents, and model routing setup stay there, while operational status/actions live in Command Center. Planned actions without complete backend wiring are disabled or marked as not configured/read-only instead of appearing as live controls.

### Meeting Mode

Start a meeting to capture structured notes.

```
/meeting start

note: We're migrating the auth service to JWT
decided: Launch date is May 15
action: @alice to update the deployment runbook by Friday

/meeting stop
```

Exports a dated `.md` file with all notes, decisions, and action items.

### Roundtable

The **Round Table** in the Workstation launches an autonomous multi-agent meeting. New meeting setup preloads `@meetings_manager` into the first seat, but you can change that chair before launch. Click **Auto-fill Stack** to seat your configured models, then start the meeting. The chair frames the problem, specialists contribute, Sparkbot synthesizes the result, and the room can keep moving through a Guardian `meeting_heartbeat` task until it reaches a terminal state such as solved, blocked, recommendation ready, or needs approval. Meeting notes, decisions, action items, and project artifacts are captured so the room behaves like an orchestrator instead of a one-off chat. You can interrupt at any time.

The Workstation **Specialty Wing** has five office slots backed by the same packaged and custom Agents list used in Controls. The default offices are `@meetings_manager`, `@researcher`, `@analyst`, `@writer`, and `@workstation_backup_1`; each office can be changed from its dropdown and the assignment persists locally in the browser. Opening an office shows the selected agent details plus a model selector that saves to the same per-agent model override system as **Controls -> Agents -> Model Overrides**.

### Robo OS And MCP Control Plane

Open **Workstation -> Robo OS** to see the unified MCP registry for Sparkbot and LIMA Robotics OS. The panel is backed by `GET /api/v1/chat/mcp/registry`, with a local fallback for offline desktop views. It lists typed tool manifests, owner/runtime, policy tags (`read-only`, `write`, `destructive`, `external-send`, `robot-motion`, `secret-use`), risk level, required secrets, approval posture, dry-run posture, and live health for Sparkbot APIs, Task Guardian, Guardian Vault, and the optional LIMA bridge.

Click **Explain** beside any Robo OS or Sparkbot manifest to call `POST /api/v1/chat/mcp/explain-plan`. The endpoint never executes tools; it runs the same Guardian policy simulator used by chat tools, returns the dry-run timeline, records an audit entry, and tells the operator whether approval, break-glass, or policy cleanup is required first.

Each explain-plan creates a durable MCP run record. Use `GET /api/v1/chat/mcp/runs` or the **Recent MCP runs** panel in Robo OS to review planned, awaiting-approval, ready, blocked, completed, and failed states with the persisted policy decision and next action. Planned or unapproved ready runs can request approval, awaiting runs can be approved or denied by a Guardian operator, and every transition writes audit evidence. This approval lifecycle is intentionally non-executing until the Phase 1 runner handoff is wired.

LIMA Robotics OS is treated as the robotics runtime rather than a separate assistant. The no-hardware demo paths are shown directly in Sparkbot:

```bash
LIMA --replay run unitree-go2
LIMA --simulation run unitree-go2-agentic-mcp
LIMA run demo-camera
```

Robot-motion tools are marked critical and go through explain-plan and operator approval before execution.

Set `LIMA_MCP_URL` or `LIMA_DAEMON_URL` when a LIMA Robotics OS MCP bridge is available. Without those values, Sparkbot keeps Robo OS in replay/simulation-first mode so the demos remain usable with no hardware.

### Scheduling Tasks (Task Guardian)

Tell Sparkbot to run anything on a schedule:

```
"Every morning at 8am, run my morning briefing"
"Check my inbox every hour and let me know if anything urgent arrives"
"Send me a daily calendar preview at 7:30am"
```

Manage scheduled jobs and runtime Task Guardian status from **Command Center → Task Guardian** or from the **Company Operations** section of the Workstation. Controls remains focused on setup and configuration.

Supported schedule strings:

| Schedule | Meaning |
|----------|---------|
| `every:3600` | Run every hour |
| `daily:13:00` | Run every day at 13:00 UTC, which is 9am America/New_York during daylight time |
| `at:2026-04-24T20:00:00Z` | Run once at an exact UTC timestamp |

For a copy-ready 9am demo flow, slide outline, security notes, and Task Guardian JSON payloads, see [docs/jarvis-demo-kit.md](./docs/jarvis-demo-kit.md).

### 9am Jarvis Demo

Sparkbot now includes a demo kit for presenting the governed-assistant vision: scheduled morning briefing, policy-gated write action, approval/breakglass walkthrough, audit evidence, security notes, marketing one-pager, and roadmap.

Start here: **[Sparkbot Jarvis Demo Kit](./docs/jarvis-demo-kit.md)**.

### Knowledge Base

Feed Sparkbot documents or URLs that it can search when relevant:

```
"Remember this doc for later: [paste text]"
"Ingest https://docs.example.com/api — I'll be asking questions about it"
```

Sparkbot uses BM25 full-text search to pull relevant chunks into the conversation when you ask related questions.

---

## Configuration

Most configuration is available from **Sparkbot Controls** or the setup wizard.

- **Desktop app** — set keys in **Sparkbot Controls** (UI). Advanced settings: the `.env` file beside the installed executable.
- **Docker / local** — run `bash scripts/sparkbot-start.sh --local`; it creates and configures `.env.local`
- **Docker / server** — run `bash scripts/sparkbot-start.sh --server`; it requires a private passphrase, binds the web UI to the server network interface, and prints the public URL
- **CLI / server setup** — run `python3 sparkbot-cli.py --setup`
- **Server / systemd** — run the setup wizard first, then copy or adapt the generated values for `.env`

Advanced users may still edit env files directly.

### Minimum required (server install)

```env
ENVIRONMENT=production
SECRET_KEY=<random 32+ char string>
SPARKBOT_PASSPHRASE=<strong passphrase>
FIRST_SUPERUSER_PASSWORD=<strong admin password>
FRONTEND_HOST=https://chat.example.com
BACKEND_CORS_ORIGINS=https://chat.example.com
```

Choose SQLite with `DATABASE_TYPE=sqlite` and `SPARKBOT_DATA_DIR`, or PostgreSQL with the `POSTGRES_*` settings.

And at least one provider key: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `MINIMAX_API_KEY`, or `OPENROUTER_API_KEY`.

For the full list of every environment variable, see **[docs/capabilities.md — Environment Variables](./docs/capabilities.md#environment-variables--full-reference)**.

---

## Code Signing

The Windows desktop installer is currently unsigned. Windows SmartScreen will show a warning on first download because it has no reputation history for a new binary. To get past it:

1. Click **More info** in the SmartScreen dialog
2. Click **Run anyway**

This is a one-time step per version. We are applying for a free open-source code signing certificate via [SignPath Foundation](https://signpath.org/). Once active, the installer will be trusted automatically.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + SQLModel + litellm |
| Frontend | React + TypeScript + Vite + shadcn/ui + Tailwind |
| Desktop shell | Tauri v2 (Rust) |
| Database | SQLite (desktop/local) or PostgreSQL (server) |
| LLM routing | litellm — 100+ providers, one API |
| Terminal | xterm.js + pywinpty (Windows) / PTY (Linux/macOS) |
| Browser automation | Playwright + Chromium |
| Auth | JWT + HttpOnly cookie |

---

## Architecture

```
Browser / Tauri shell
  │
  └── FastAPI backend (127.0.0.1:8000 desktop / configurable server)
        ├── LLM routing (litellm)
        ├── Tool execution (policy-gated)
        ├── Guardian stack (memory / executive / task / token)
        ├── WebSocket (terminal, streaming)
        └── SQLite / PostgreSQL
```

Server layout with nginx:

```
nginx (your-domain.com)
  ├── /          → static frontend files
  ├── /api/      → FastAPI backend
  └── /ws/       → WebSocket upgrade
```

---

## Security

Every tool call passes through a policy layer before execution. See [SECURITY.md](./SECURITY.md) for the full architecture.

```
User message → Token Guardian → Memory Guardian → LLM
                                                    │ tool_calls
                                                    ▼
                                           Agent Shield (policy)
                                                    │ allow / confirm / deny
                                                    ▼
                                          Executive Guardian (journal)
                                                    │
                                                    ▼
                                           Tool executes → audit log
```

| Area | Behavior |
|------|----------|
| Tool policy | Every tool is classified as read, write, execute, or admin; unknown tools are denied by default |
| Policy simulator | `guardian_simulate_policy` previews allow / confirm / deny / break-glass outcomes without executing the tool |
| Approval inbox | Confirmation-gated actions are stored durably and can be approved or denied from the dashboard, Telegram, GitHub, and bridge surfaces |
| Write actions | Email, calendar writes, Slack posts, issue creation, and similar actions require confirmation |
| Shell and server access | Execution tools are behind explicit room/operator gates and can be disabled |
| Secrets | Guardian Vault stores sensitive values; break-glass mode requires an operator PIN |
| Audit trail | Tool calls are logged with timestamps, decisions, and redacted arguments |
| Browser/session auth | App sessions use HttpOnly cookies rather than exposing tokens to JavaScript |
| CI scanning | `pip-audit`, `npm audit`, and `gitleaks` run in GitHub Actions |

---

## Full Reference

- **[docs/capabilities.md](./docs/capabilities.md)** — every tool, command, integration, env var, API endpoint, and Guardian Spine route
- **[docs/skill-author-guide.md](./docs/skill-author-guide.md)** — how to write, test, and ship a skill plugin
- **[docs/guardian-job-examples.md](./docs/guardian-job-examples.md)** — copy-paste Task Guardian job templates
- **[docs/jarvis-demo-kit.md](./docs/jarvis-demo-kit.md)** — 9am presentation, demo script, security notes, roadmap, and pasteable Task Guardian payloads
- **[docs/error-handling.md](./docs/error-handling.md)** — where every layer catches failures, what the user sees, and where the full traceback goes
- **[docs/guardian-spine.md](./docs/guardian-spine.md)** — how the Guardian suite and the Spine task ledger interact in the background (loops, ingest functions, observability)
- **[docs/privacy-data-retention.md](./docs/privacy-data-retention.md)** — plain-language privacy and local data retention note
- **[Troubleshooting.md](./Troubleshooting.md)** — Playwright, Ollama CPU, terminal, SmartScreen, first-run checklist
- **[SECURITY.md](./SECURITY.md)** — security architecture
- **[SECURITY-AUDIT.md](./SECURITY-AUDIT.md)** — full security audit (v1.3.0): findings, fixes, residual risks
- **[deployment.md](./deployment.md)** — Traefik + Docker + HTTPS server setup
- **[docs/systemd-single-node.md](./docs/systemd-single-node.md)** — systemd + nginx server setup
- **[PRIVACY.md](./PRIVACY.md)** — data retention and privacy details
- **[CONTRIBUTING.md](./CONTRIBUTING.md)** — how to contribute

---

## Release History

| Version | Date | Highlights |
|---------|------|-----------|
| v1.6.55 | May 2026 | Advanced the Command Center update line for local testing and public updater/download metadata: downloader links, package versions, Tauri metadata, service worker cache, README, capabilities docs, release notes, and GitHub Pages copy now point at the v1.6.55 desktop line. |
| v1.6.54 | May 2026 | Cleaned up Controls by removing the obsolete Active custom agents display, moved Spawn Agent to the top of Agents, added packaged specialist agents, upgraded Workstation Specialty Wing offices with shared Agents dropdowns/model selection, preloaded Meetings Manager into new meeting setup, promoted Spine Ops to the official Command Center with Room Persona/System Health/Computer Control/Token Guardian/Task Guardian surfaced there, and kept downloader/docs/package metadata on the v1.6.54 desktop line. |
| v1.6.53 | May 2026 | Fixed photo processing in app uploads and Telegram by routing images through a shared vision-capable model picker; hardened meeting sends so transient network failures do not leave the room stuck while retrying with proceed/go/try again; expanded Controls onboarding for Google Drive, Google Docs, and Microsoft 365; redesigned the Workstation Specialty Wing into five fixed agent offices with Add Agent slots; downloader/docs advanced to the v1.6.53 desktop line. |
| v1.6.52 | May 2026 | Fixed Controls credential storage so GitHub tokens, GitHub SSH/App secrets, Discord, WhatsApp, and Google connector secrets save directly into Guardian Vault without requiring breakglass; connector secrets remain `use_only` for bridge/runtime use while non-secret toggles persist normally; downloader/docs advanced to the v1.6.52 desktop line. |
| v1.6.51 | May 2026 | Restored full Controls comms onboarding after the GitHub-focused update: Telegram, Discord, WhatsApp, Gmail, and Google Calendar are visible again alongside GitHub; Comms save now persists the full connector form again; downloader/docs advanced to the v1.6.51 desktop line. |
| v1.6.50 | May 2026 | Unified top navigation across Chat, Workstation, Controls, Robo OS, Spine Ops, and Info; Controls now opens as a full-page app surface at `/controls`; Robo OS tab can jump directly into the Workstation control-plane panel; downloader/docs advanced to the v1.6.50 desktop line. |
| v1.6.49 | May 2026 | GitHub onboarding now focuses on three local control paths: fine-grained token, SSH key, or GitHub App installation, with no webhook setup required in Controls; GitHub status works in local desktop mode; autonomous Roundtable meeting turns retry transient provider/network failures before surfacing errors; heartbeat notes are best-effort so note capture does not break the meeting loop; downloader/docs advanced to the v1.6.49 desktop line. |
| v1.6.48 | May 2026 | Guardian/Spine security stabilization: redact secret-like tool args from Spine approval events, redact metadata and result excerpts in executive decision JSONL, 21 new security gate tests covering vault auth denial, write-mode enforcement, PII redaction at persistence, bypass TTL expiry, and approval pruning. Preservation docs and extraction audit for LIMA-Guardian-Suite. |
| v1.6.47 | May 2026 | Memory growth controls: 30-day hot ledger rotation into month-named cold archives, pre-ledger chat-noise filtering, nightly consolidation into daily summaries, semantic fact dedup/superseding, incremental tombstone deletes with weekly compaction, ranked memory inspector/correct/remove actions, natural "forget that..." matching, low-weight fact TTL archival, and a 90-day improvement-loop outcome window. |
| v1.6.46 | Apr 2026 | Breakglass/Computer Control reliability: redesigned global ON/OFF control with a 24-hour expiry, Vault remains PIN-protected, diagnostics/tests can run while destructive edits/deletes/sends still require yes/no confirmation; fixed custom agent spawning on upgraded local SQLite installs; spawned agents now update the active registry immediately; Workstation Specialty Wing lists created agents for meeting seating; Roundtable chairs can be reassigned in-room; generated meeting notes now post into the meeting transcript and surface errors. |
| v1.6.45 | Apr 2026 | Governed Guardian Memory lifecycle: typed memory candidates, low-clutter indexing, active/stale/archive/delete-proposal states, operator-approved soft deletion, snapshot rebuild throttling, ledger archive manifests, and memory hygiene jobs |
| v1.6.43 | Apr 2026 | Reliability + observability: hard-cap chat tool catalogue at 128 (with auto-shrink retry) to fix `Invalid 'tools': array too long` on Windows builds; tool-catalogue dedup; skill loader accepts both wrapped and flat DEFINITION shapes (system_diagnostics now loads); user-friendly error messages for rate-limit / quota / auth / context / model-not-found / timeout failures; new `/perf` slash command and `/api/v1/chat/performance` endpoint surfacing model + tool latency, error counts, and last error; new docs/error-handling.md and docs/guardian-spine.md |
| v1.6.42 | Apr 2026 | Controls persistence fixes: Computer Control checkbox now stays enabled across page loads (bootstrap no longer resets execution_allowed), model stack persists correctly in multi-worker deployments (cross-worker env reload from data/.env), and startup env loading ensures saved settings survive container restarts |
| v1.6.41 | Apr 2026 | Full browser voice loop: fixed voice-route persona loading, tagged voice-origin messages, added hands-free listen-again after spoken replies, refreshed downloader/docs, and kept Workstation phone access in the release line |
| v1.6.40 | Apr 2026 | Guardian Memory retrieval governance: BM25 default retriever interface, optional hybrid embedding flag, verified fact promotion with pending approvals, nightly Task Guardian memory evaluation, precision/latency metrics, authenticated Guardian metrics endpoint, and defensive LiteLLM tool-manifest trimming for Telegram/background reliability |
| v1.6.39 | Apr 2026 | Unified Sparkbot + LIMA Robotics OS positioning; Workstation Robo OS button; MCP control-plane registry with typed manifests, policy metadata, dry-run posture, live Sparkbot health, run timeline, and no-hardware LIMA replay/simulation demos |
| v1.6.38 | Apr 2026 | Governance roadmap baseline: first-class agent identity/kill switches, run timeline API with audit hashes, connector health/scopes, workflow templates, PWA manifest, per-tool input/output guardrails, deterministic eval harness, privacy/data-retention docs, and aligned downloader versioning |
| v1.6.37 | Apr 2026 | Self-learning memory + governed orchestration: hybrid Guardian recall with provenance/confidence, memory self-introspection tools, truth/confidence guardrails, approval-first improvement proposals, policy simulator, orchestrator docs, Telegram token-safe error handling, and write-like shell confirmation in policy mode |
| v1.6.36 | Apr 2026 | Computer Control replaces the room execution gate; Workstation status now reflects the Controls checkbox; first-run 6-digit PIN setup/change flow for Break-glass, Vault, commands, browser writes, and comms sends |
| v1.6.35 | Apr 2026 | Documentation and downloader refresh: coherent README flow, public site copy cleanup, packaging docs updated, and desktop/download version markers advanced |
| v1.6.33 | Apr 2026 | Vault-backed runtime wiring for Discord, WhatsApp, GitHub, Gmail, and Google Calendar; Task Guardian supports `daily:HH:MM` schedules and Zulu one-shots; Windows-safe morning briefing; Jarvis demo kit |
| v1.6.32 | Apr 2026 | Uniform Invite Wing subscription selectors for Claude + ChatGPT/Codex; OpenClaw desk replaced by xAI Grok; Controls AI setup now surfaces Anthropic/OpenAI subscription flows and xAI API-key guidance |
| v1.6.31 | Apr 2026 | Invite Wing ChatGPT desk becomes the Codex gateway for ChatGPT-linked OpenAI keys and `codex-mini-latest`; OpenAI Codex models route as first-class invite seats |
| v1.6.30 | Apr 2026 | Telegram polling auto-enables on token save; Chat ID mirrored into operator/allowed lists |
| v1.6.26 | Apr 2026 | Fix: skills (Telegram, Spotify, Google, Microsoft) now read env vars at call time not startup — credentials saved via UI now take effect without restart |
| v1.6.25 | Apr 2026 | Telegram Chat ID field in settings UI — enables proactive alerts via send_alert skill |
| v1.6.24 | Apr 2026 | Breakglass: inline justification on activation (`/breakglass <reason>`), exact expiry timestamp in confirmation, justification logged to audit trail |
| v1.6.22 | Apr 2026 | Relationship memory (personal CRM); proactive push alerts to Telegram/Discord; time tracking; Linear + Jira; NL→SQL; audio/podcast transcription; contacts manager; Microsoft 365 (Outlook, OneDrive); Apple integrations (Contacts, Reminders, Notes); stocks + portfolio; Spotify control; YouTube summarization; configurable daily digest with weather + stocks + news |
| v1.3.0 | Apr 2026 | Security hardening: SSRF fixes in fetch_url + knowledge base; per-user KB isolation; Sentry data scrubbing; npm dep fixes; message queue (send while Sparkbot is responding) |
| v1.2.9 | Apr 2026 | Skill sandboxing (timeout + memory); 121 CI smoke tests; skill author guide + Guardian job examples |
| v1.2.8 | Apr 2026 | Process watcher (auto-throttle Ollama CPU); model latency tracking; latency API |
| v1.2.7 | Apr 2026 | system_diagnostics skill; repair-playwright scripts; Troubleshooting.md |
| v1.2.6 | Apr 2026 | Stable Playwright browser dir; LLM tool-loop guards |
| v1.2.2 | Apr 2026 | `shell_run`; Windows live terminal; browser auto-install; Invite Wing API keys |
| v1.1.x | Apr 2026 | Workstation operations dashboard; Round Table autonomous meetings; Guardian Tasks |
| v1.0.x | Mar 2026 | Code interpreter; named browser sessions; knowledge base (RAG); voice quick-capture; Spawn Agent |
| v0.9.x | Mar 2026 | Guardian Spine; break-glass; vault; Telegram/Discord/WhatsApp/GitHub bridges; full security audit |
