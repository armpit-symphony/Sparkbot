# Sparkbot

**Sparkbot** is a self-hosted AI workspace assistant for people who want the power of a connected AI system without handing their whole workflow to a hosted SaaS account. It can run as a desktop app on Windows, macOS, and Linux, or as a Docker/server install for a team or private network.

Use it to chat, search, summarize documents, control a browser, run shell commands, manage tasks, schedule briefings, work with email and calendars, coordinate agents, and keep an audit trail around sensitive actions.

**Download:** [armpit-symphony.github.io/Sparkbot](https://armpit-symphony.github.io/Sparkbot/)

**Current release line:** v1.6.81

> Sparkbot stores its app data locally. If you connect a cloud LLM provider or an external service, the text and actions needed for that provider or service are sent to that provider. Local models can run without an LLM cloud account.

---

## What Sparkbot Is

Sparkbot combines five pieces into one local assistant:

1. **Chat workspace** - rooms, files, memory, slash commands, meetings, and searchable history.
2. **Computer control** - browser automation, shell commands, live terminal sessions, and code execution.
3. **Connected work tools** - email, calendars, files, GitHub, Slack, Notion, Confluence, Jira, Linear, contacts, stocks, Spotify, YouTube, and more.
4. **Agent orchestrator** - multi-agent Round Table meetings, task-linked project rooms, scheduled Guardian jobs, meeting heartbeats, notes/artifacts, and owner interruptions.
5. **Guardian controls** - policy checks, confirmations, policy simulation, persistent approvals, vault-backed secrets, elevated access, scheduled-job verification, and audit logs.

Sparkbot Public is the open-source, self-hosted workstation shell. It focuses on local-first chat, model routing, shared memory, tools behind user-owned permissions, and Round Table meetings for AI agents. The Robo area stays visible as a preview/demo surface for future PC/server/runtime and robotics integrations; public Sparkbot does not wire real robot, drone, humanoid, or IoT control.

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
- **Shell** — run PowerShell or bash commands when terminal capability is configured; risky commands ask for confirmation
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
- **Multi-model** — OpenAI API, OpenAI Codex subscription, Anthropic, Google, Groq, MiniMax, OpenRouter, Ollama, LM Studio, llama.cpp, and other local OpenAI-compatible endpoints — switch live with `/model`
- **Model stack** — configure Primary, two Backups, and a Heavy Hitter; Sparkbot auto-routes and falls back across providers
- **Multi-agent rooms** — mention `@researcher`, `@coder`, `@writer`, `@analyst`, `@meetings_manager`, `@web_designer`, `@marketing_agent`, `@business_analyst`, or any custom agent for a specialist response
- **Spawn agents** — create named agents with custom system prompts and first-class identity metadata from 11 specialty templates
- **Agent identity + kill switches** — each agent exposes owner, purpose, scopes, allowed tools, expiration, risk tier, and kill-switch state; disabled agents do not route from `@mention`
- **Persistent memory** — Sparkbot stores facts about you and injects them into every conversation
- **Unified chat memory** — useful browser, Telegram, Discord, and workstation meeting turns are mirrored into per-user shared work memory for later recall
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
- **Unified top tabs** — Chat, Workstation, Robo Preview, Command Center, and Info stay visible from the main app surfaces
- **Command Center** — Sparkbot's unified operational hub includes AI Setup, security profiles/PIN controls, comms connectors, agent management, Room Persona, System Health, and advanced operator panels
- **Phone access** — the full workstation now opens on phone-sized screens as a horizontally scrollable operations map instead of blocking mobile users
- **Robo Preview** — teaser/demo panel for future runtime, PC/server, and robotics-adjacent work; real robotics/IoT control is not wired in the public core
- **Invite Wing** — customizable model seats for Codex/OpenAI, Claude/Anthropic, Grok/xAI, Local AI, and future providers; configured seats can join Round Table meetings
- **Round Table** — autonomous multi-agent meeting room; all agents contribute without you typing between turns
- **Company Operations** — view all Guardian Tasks across every room, active meetings, and launch project rooms in one click
- **Task-linked meetings** — hit **Meet** on any task and a pre-seeded project room opens
- **Orchestrated runs** — meeting rooms keep a participant manifest, run a best-effort heartbeat, save manager wrap-up notes/artifacts, and seed follow-up tasks from action items

### Proactive Mode & Scheduled Autonomy (Task Guardian)
- **Scheduled jobs** — tell Sparkbot to run any tool on a schedule (hourly, daily, custom interval)
- **Built-in health checks** — preload PC Health Check and Server Health Check templates for read-only Sparkbot Health Reports
- **Daily schedules** — use `daily:HH:MM` UTC or `daily-local:HH:MM` local-time schedules for predictable morning briefings, health reports, and calendar previews
- **Push alerts** — scheduled jobs can push results to your phone via Telegram, Discord, or Slack when explicitly configured
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
- **Security controls** — strict Guardian guardrails are owner-enabled from Command Center; routine local/server reads work by default while risky changes still ask yes/no
- **Write-tool confirmation** — confirmation and break-glass flows stop risky writes, deletes, sends, browser writes, service control, and Vault reveal/write paths
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

On first launch, Sparkbot opens **Sparkbot Controls**. Paste at least one LLM API key, or configure a local AI provider such as Ollama, LM Studio, llama.cpp / llama-server, or another OpenAI-compatible endpoint if you want local-only model execution.

| Provider | Where to get a key |
|----------|--------------------|
| OpenAI | [platform.openai.com](https://platform.openai.com) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) |
| Google | [aistudio.google.com](https://aistudio.google.com) |
| Groq | [console.groq.com](https://console.groq.com) |
| MiniMax | [minimax.io](https://www.minimax.io) |
| OpenRouter | [openrouter.ai](https://openrouter.ai) — one key, 100+ models |
| Local AI | No key required for default localhost Ollama, LM Studio, llama.cpp, or OpenAI-compatible endpoints |

**Using ChatGPT Codex subscription instead of an OpenAI API key**

Sparkbot can use your local Codex CLI ChatGPT sign-in for the **Codex Sub** provider. In PowerShell, run:

```powershell
codex login
```

Choose **ChatGPT sign-in**, finish the browser login, then restart Sparkbot. In **Sparkbot Controls -> Codex Sub**, select **GPT-5.3 Codex Spark** and save it as the default. Sparkbot detects the local Codex session at `%USERPROFILE%\.codex\auth.json` and routes `openai-codex/gpt-5.3-codex` through read-only `codex exec`, so no OpenAI Platform API key is required for this route.

If Controls still says **Codex ChatGPT sign-in needed** after login, set these advanced env values and restart Sparkbot:

```powershell
CODEX_HOME=%USERPROFILE%\.codex
SPARKBOT_CODEX_CLI=%APPDATA%\npm\codex.ps1
```

**Step 3 — Start chatting**

Click **Sparkbot** on the office floor to open the main chat. Everything else can be configured from there.

---

### Docker Local

Public Docker/source installs should use the sanitized release bundle from the [download page](https://armpit-symphony.github.io/Sparkbot/) or GitHub Releases. The full `armpit-symphony/Sparkbot` repository remains the active R&D/source reference; it is useful for contributors, but it is not the recommended casual public install path until the future `Sparkbot_shell` public repo exists.

Local machine:

```bash
curl -L -O https://github.com/armpit-symphony/Sparkbot/releases/latest/download/sparkbot-latest.tar.gz
curl -L -O https://github.com/armpit-symphony/Sparkbot/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing
tar -xzf sparkbot-latest.tar.gz
cd sparkbot-v2
bash scripts/sparkbot-start.sh --local
```

Cloud server / VPS / DigitalOcean:

```bash
curl -L -O https://github.com/armpit-symphony/Sparkbot/releases/latest/download/sparkbot-latest.tar.gz
curl -L -O https://github.com/armpit-symphony/Sparkbot/releases/latest/download/SHA256SUMS
sha256sum -c SHA256SUMS --ignore-missing
tar -xzf sparkbot-latest.tar.gz
cd sparkbot-v2
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

#### OpenAI Codex Subscription on Docker Servers

Sparkbot can use your ChatGPT Codex subscription through the local Codex CLI instead of an OpenAI Platform API key. Sign in on the host as the user that runs Sparkbot:

```bash
codex login --device-auth
codex login status
```

Then start Sparkbot with the Codex Compose override:

```bash
docker compose -f compose.local.yml -f compose.codex.yml up -d --build
```

The override mounts only the host `auth.json` into the backend container as read-only, sets `CODEX_HOME=/root/.codex`, and uses `/tmp` as the read-only Codex working directory for Sparkbot prompts. If the host auth file is somewhere else, set it explicitly:

```bash
SPARKBOT_CODEX_AUTH_FILE=/absolute/path/to/auth.json \
  docker compose -f compose.local.yml -f compose.codex.yml up -d --build
```

After startup, open **Controls → OpenAI Codex Subscription** and choose `openai-codex/gpt-5.3-codex`. Sparkbot dispatches that route through `codex exec --sandbox read-only`.

Long-running Codex subscription tasks default to a 2-hour Sparkbot-side CLI timeout. Set `SPARKBOT_CODEX_CLI_TIMEOUT_SECONDS=0` to remove Sparkbot's local timeout for difficult projects that may run much longer.

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

### Computer Control And Security

Computer Control capabilities are shown in **Command Center** and mirrored in the **Workstation → Computer Control** panel. Sparkbot now defaults to an owner-local working mode where routine local machine, server, browser, terminal, SSH, and comms read tools can run without service/SSH allowlist blockers. Obvious risky actions still ask yes/no before execution: file edits, deletes, code changes, external sends, browser writes, service control, Vault reveal/write paths, and critical admin operations.

The Command Center box is labeled **Security**. Checking it turns the stricter Guardian guardrails on, including the existing PIN, break-glass, service/SSH allowlist, and tool-input guardrail behavior. The same panel includes a custom guardrails editor with a Save button; owners can add exact tool blockers (`tool:gmail_send`), regex blockers (`regex:rm\s+-rf`), or plain text phrases that should be denied while Security is enabled.

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

Open **Command Center** from the top tabs or `/spine` (alias: `/command-center`). It is the official operator page for Room Persona, System Health, Security/PIN controls, Token Guardian, Task Guardian, and Guardian Spine queues/logs. The page uses the same top navigation pattern as Chat, Workstation, and Controls, with the old Spine Ops internals preserved behind the route/component names where needed.

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

The **Round Table** in the Workstation launches an autonomous multi-agent meeting. New meeting setup preloads `@meetings_manager` into the first seat, but you can change that chair before launch. Seat 1 is the meeting manager: after the owner kickoff, everyone gives first-pass ideas, the manager assesses, assigns jobs to the room, everyone responds to their assignment, and the manager summarizes with a plan, adjustment, continuation, or a request for owner input. Meeting notes are generated only when the operator explicitly uses the Generate Meeting Notes button or asks for notes by text/voice command. Before launch, Sparkbot checks only the providers/models assigned to the room seats and reports a concise assigned-seat readiness result. You can interrupt at any time.

The Workstation **Specialty Wing** has five office slots backed by the same packaged and custom Agents list used in Controls. The default offices are `@meetings_manager`, `@researcher`, `@analyst`, `@writer`, and `@workstation_backup_1`; each office can be changed from the compact card dropdown or the office detail-panel selector, and the assignment persists locally in the browser. Opening an office shows the selected agent details plus a model selector that saves to the same per-agent model override system as **Controls -> Agents -> Model Overrides**.

### Robo Preview

Open **Workstation -> Robo Preview** to see the public teaser for future PC/server/runtime and robotics-adjacent integrations. In the public core this is a demo surface, not a live robot, drone, humanoid, or IoT control system.

Public Sparkbot keeps the Robo area visible so users can understand the direction of the workstation, but real hardware control, private runtime bridges, emergency-stop contracts, and robotics command runners are not part of the public MVP. Future runtime integrations should stay behind explicit setup, permissions, and operator approval before any live action is possible.

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
| `daily-local:06:00` | Run every day at 6:00 AM in the host's local timezone |
| `at:2026-04-24T20:00:00Z` | Run once at an exact UTC timestamp |

PC Health Check and Server Health Check are built-in Task Guardian templates. They are disabled until added by the owner, run read-only checks, default to app-only delivery, and can optionally send reports through configured Telegram, Discord, or Slack channels.

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
BACKEND_WORKERS=1
WORKSTATION_LIVE_TERMINAL_ENABLED=false
```

Choose SQLite with `DATABASE_TYPE=sqlite` and `SPARKBOT_DATA_DIR`, or PostgreSQL with the `POSTGRES_*` settings.

And at least one provider key: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `MINIMAX_API_KEY`, or `OPENROUTER_API_KEY`.

For public v1, keep web/API workers at `1` unless you deploy a dedicated singleton scheduler or DB-backed leader lock. Higher API worker counts can duplicate recurring health checks, reminders, and Task Guardian jobs. Live terminal is raw shell access; leave it disabled for public deployments unless the instance is private and operator-only.

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
| v1.6.81 | May 2026 | Windows bridge fix + disk reclaim. Critical Windows bug: `backend/app/api/routes/chat/tools.py` did `import pwd` at module top, breaking every code path that lazy-imports it. Telegram, Discord, WhatsApp, and GitHub bridges all go through `stream_chat_with_tools` which lazy-imports `tools.py`, so every bridged chat failed with `ModuleNotFoundError: No module named 'pwd'`. The main UI worked because it doesn't hit the same lazy import. Fix: conditional import, with `_uid_name` falling back to the raw uid string when `pwd` is unavailable (the function is only meaningful for `/proc/<pid>/status` parsing on Linux containers anyway). Also added two desktop-housekeeping items: `desktop_launcher.py` now rotates `sparkbot-backend.log` to `.log.1` on startup if it exceeds 50 MB (gives v1.6.79 → v1.6.81 upgraders a clean slate without losing prior-run triage), and prunes stale `_MEI*` PyInstaller temp dirs under `%APPDATA%\Sparkbot\pyi-runtime\` (keeps newest 2; observed installs accumulated 30+ dirs / ~1.5 GB over the v1.6.6x → v1.6.8x line). Removed `.github/workflows/add-to-project.yml`, leftover FastAPI template cruft that targeted `github.com/orgs/fastapi/projects/2` and failed on every PR. 2 new regression tests assert tools.py imports without `pwd` and `_uid_name` degrades safely; 180 services + tools tests pass; downloader, package metadata, README, capabilities docs, public-download docs, service worker, and release notes advanced to v1.6.81. |
| v1.6.80 | May 2026 | Token Guardian honesty + desktop log hygiene. Live-mode now stays on the operator's current model with a clear `fallback_reason` when no preferred candidate from `routing.yaml` is configured, instead of silently jumping to the alphabetical-first configured fallback — fixes the "Token Guardian doesn't register or even work" complaint on stacks where the preferred names (`claude-sonnet-4-5`, `gpt-4o`) aren't directly configured but `claude-sub/*` / `openai-codex/*` / `openrouter/*` providers are. The Token Guardian pipeline init now mirrors the operator-configured mode in the `shadow_mode` arg so the startup log reflects reality instead of always claiming `shadow=true` even when live was set. Desktop `sparkbot-backend.log` now defaults to INFO (previously DEBUG, which produced ~600 MB of httpcore long-poll spam per busy week from the Telegram bridge); `SPARKBOT_BACKEND_LOG_LEVEL=debug` re-enables verbose. `httpcore`, `httpx`, `h2`, `rustls`, `openai._base_client`, `cookie_store`, and `primp` are pinned to WARNING by default even when root is INFO — these accounted for 90%+ of historic log volume. 2 new tests for the live stay-on-current behavior and the pipeline mode-label fix; 178 services tests still pass; downloader, package metadata, README, capabilities docs, public-download docs, service worker, and release notes advanced to v1.6.80. |
| v1.6.79 | May 2026 | Host-aware server audit competence release. Added `runtime_context`, `host_capabilities`, and `host_full_audit` server diagnostic profiles so Sparkbot can tell when it is running inside Docker, inspect the mounted host `/proc` process table, parse host TCP listeners from `/host/proc/1/net`, enumerate mounted cron jobs, identify key generic workloads such as Sparkbot, database services, web servers, SSH, Docker, cron, fail2ban, and Codex, and report coverage gaps instead of treating container-only `ps`/`ss` output as the whole server. `process_snapshot` and `network_listeners` now prefer host-backed readers when host `/proc` is mounted. Backend image installs `procps`, `iproute2`, and `lsof` for container fallback diagnostics. Prompt guidance now requires runtime scope and full host audit before answering "what else is running" or security-audit questions. Added regression tests with fake host process/listener fixtures; downloader, package metadata, README, capabilities docs, public-download docs, service worker, and release notes advanced to v1.6.79. |
| v1.6.78 | May 2026 | Security-off assistant behavior fix. Security off now lets Sparkbot act like a normal operator assistant: routine reads and ordinary writes are available without strict guardrail confirmation, while explicitly dangerous/destructive actions, external sends, service control, credential reveal/write, and critical changes still ask first. Added host-backed server inspection for containerized installs: `server_read_command` now has `process_search`, `scheduled_jobs`, and `bot_health` profiles so Sparkbot can inspect host cron entries, host processes, and recent configured local service logs through read-only mounts instead of trying `systemctl` inside the backend container. Compose now mounts host `/proc`, cron directories, and a generic optional host log root read-only for this visibility. |
| v1.6.77 | May 2026 | Security / Operator Control panel foundation. Command Center Security now reads backend-enforced posture from `/api/v1/chat/security/status`, including passphrase strength, operator mode, break-glass state, CORS, frontend exposure, `.env` permissions, frontend security headers, risky feature toggles, and provider-key storage hints. Added guarded backend write routes for rotating `SPARKBOT_PASSPHRASE`, setting explicit `SPARKBOT_OPERATOR_USERNAMES`, setting/changing the operator PIN, toggling allowlisted risky features, and fixing managed `.env` permissions to `600`; writes require operator identity, an active break-glass session where appropriate, and audit logging. The first UI actions ship as rotate passphrase, save explicit operators, and fix `.env` permissions, and the nginx frontend now emits baseline security headers. Downloader, package metadata, README, capabilities docs, public-download docs, service worker, and release notes advanced to v1.6.77. |
| v1.6.76 | May 2026 | Owner-controlled Security mode. Sparkbot now defaults to an owner-local working mode where routine local machine/server/browser/terminal/SSH/comms read tools can run without the old Computer Control and service allowlist blockers; risky actions still require confirmation/PIN, including edits, deletes, sends, browser writes, service control, code changes, and Vault reveal/write paths. Command Center relabels the old break-glass/PIN box as Security; checking it turns the stricter Guardian guardrails back on. Added a custom guardrails editor with a Save button for exact tool blockers, regex blockers, and plain text blockers while Security is enabled. Service and SSH allowlists now apply only when Security is enabled, so owner-run server installs can inspect local workloads such as trading bots without predeclaring every service. Downloader, package metadata, README, capabilities docs, security docs, service worker, public-download docs, and release notes advanced to v1.6.76. |
| v1.6.75 | May 2026 | Claude Sub + Roundtable lock reliability. Fixed the Claude Subscription route used by chats and Workstation seats: Sparkbot was launching Claude Code with an unsupported `--output-file` flag, so the installed Claude CLI rejected every `claude-sub/*` turn even though `claude auth status` showed a valid subscription. The route now reads Claude CLI stdout directly with non-interactive text output, and a live smoke test returned `OK`. Workstation Claude invite desks now prefill an explicit Claude model so saved meeting seats do not accidentally fall back to the active default model. SQLite local/desktop engine setup now enables `busy_timeout=30000`, WAL journal mode, normal sync, foreign keys, and `check_same_thread=False`, reducing Roundtable, Telegram, reminder, and meeting heartbeat lock collisions that surfaced as `database is locked` during multi-agent saves. Added focused tests for the Claude CLI command contract and SQLite pragmas; downloader, package metadata, README, capabilities docs, service worker, and release notes advanced to v1.6.75. |
| v1.6.74 | May 2026 | Self-diagnostic profiles + log hygiene. After v1.6.73 unstuck the policy gate, the bot still returned "Live diagnostics are policy-blocked" when asked for a self-diagnostic audit because it was trying to pass raw shell commands (`Get-Date`, `hostname`, `whoami`, `git --version`) as the `command` value of `server_read_command` — but that parameter is enum-constrained to curated profiles, and the validator's "Unsupported server command. Allowed: ..." message was being misnarrated as a policy block. Added two new profiles: `host_identity` (hostname + user + OS + ISO time) and `toolchain_versions` (python/git/node/npm/docker, missing tools don't abort the audit). Tightened the rejection wording to lead with "this is a parameter validation error, not a policy denial" and list curated profiles. Updated the tool description so the LLM has a self-diagnostic recipe. Also: litellm was logging system prompts, room memory excerpts, and tool-definition manifests in plaintext to `backend.log` at DEBUG — `app/main.py` now sets the litellm logger family to WARNING by default; override with `SPARKBOT_LITELLM_LOG_LEVEL=debug`. Removed two unreachable duplicate calendar skill plugins (`backend/skills/calendar_create_event.py`, `backend/skills/calendar_list_events.py`) that fired "Duplicate tool definition ignored" warnings on every launch. Split the pre-existing Windows-failing `service_logs` test into Linux/Windows variants. 4 new tests, 190 passed + 1 skipped overall. |
| v1.6.73 | May 2026 | Break-glass policy fix: `decide_tool_use` was returning `action="privileged"` (i.e. "enter your PIN with /breakglass") for tools with `requires_execution_gate=True` (`server_read_command`, `ssh_read_command`, `server_manage_service`, write-like `shell_run`, browser writes) even when break-glass was already active. The lower active-break-glass branch was unreachable because the gated-tool branch short-circuited first. Surfaced when the user triggered break-glass, asked for a self-diagnostic audit, and got "FAIL: Live diagnostics are policy-blocked in this environment; all PowerShell checks were rejected" instead of actual diagnostics. Fixed by checking `is_privileged` before `is_operator` in the gated-tool branch. 4 new regression tests, 183 services tests pass overall. |
| v1.6.72 | May 2026 | Implements both v1.6.71 improvement proposals (operator-approved via the new Improvement tab). **Autonomous-turn pacing**: new `backend/app/services/guardian/autonomous_turn_pacing.py` records per-(room, agent) outcomes. On 4xx provider failures the next attempt sleeps 2^N seconds capped at 64, and after 8 consecutive 4xx within 5 minutes the pair is paused. Wired into `rooms.py:_run_agent_turn`. New operator routes `/spine/operator/autonomous-pauses` (list/resume) back a new Task-Guardian-tab card showing paused pairs with failure counts and resume buttons. **Durable Guardian state**: new `SPARKBOT_GUARDIAN_DATA_DIR` umbrella env var consumed by `improvement.py`, `correction_lock.py`, and `autonomous_turn_pacing.py`. `desktop_launcher.py` points it at `%APPDATA%\Sparkbot\guardian-data` so proposals, correction locks, and pacing state survive desktop restarts (fixes a v1.6.71-introduced bug where the PyInstaller `_MEI*` temp dir was the default location). First-launch migration seeds the umbrella from the freshest non-empty pre-umbrella source. 21 new tests, 179 services tests pass overall. |
| v1.6.71 | May 2026 | Self-learning loop tightened in two ways. (1) Durable correction lock: when you correct a misroute ("that's not an answer", "stop dumping state"), the suppression now persists in a per-room sidecar store and survives past the 6-message lookback window and across sessions; explicit "show state" requests clear it; tunable via `SPARKBOT_CORRECTION_LOCK_DATA_DIR` / `SPARKBOT_CORRECTION_LOCK_ENABLED`. (2) Improvement proposals visible in Command Center: new operator-only routes `/spine/operator/improvement/proposals` (list, approve, reject) back a new "Improvement" tab in the Spine and Guardian Inspector showing every proposal `guardian_propose_improvement` has recorded with status, risk, suggested change, evidence, and Approve / Reject controls. Approving records operator intent only — code, config, or workflow changes still require an explicit follow-up action. Tests: 9 for the durable correction lock, 2 for `update_proposal_status`, 158 services tests pass overall. |
| v1.6.70 | May 2026 | Command Center Inspector fix: every Spine and Guardian panel at the bottom of Command Center (Overview, Queues, Projects, Events, Producers, Security, Vault, Task Guardian, Project workload, Task distribution) was returning `Unexpected token '<', "<!DOCTYPE "... is not valid JSON` in the Tauri desktop app because `spineGet`/`guardianFetch`/`roomsFetch` in `frontend/src/lib/spine.ts` used raw `fetch()` against `window.location.origin` (`tauri://localhost`) instead of routing through `apiFetch` to the backend at `127.0.0.1:8000`; the Tauri webview returned the SPA index fallback, hence the JSON parse error. All three helpers now use `apiFetch`, which resolves the desktop origin and injects the chat token as a Bearer header. Token Guardian "not registering" was the same root cause — `fetchGuardianStatus` failing silently so the SystemHealth, Computer Control, and Task Guardian cards saw no Guardian status; now they do. Home dashboard route had the same raw-fetch pattern for `/dashboard/summary` and approval actions; also replaced with `apiFetch`. Server mode unchanged. |
| v1.6.69 | May 2026 | Token Guardian truthfulness fixes: locked-provider and provider-authoritative routing payloads no longer claim `live_ready: True` while bypassing Token Guardian — they now set `live_ready: False`, `tg_bypassed: True`, `tg_bypass_reason`, and surface the underlying exception in `fallback_reason`; the chat audit log stops recording bypass payloads under `tokenguardian_live`/`tokenguardian_shadow` so the dashboard's 24h live-routes counter is accurate; Token Guardian's `_model_is_configured` no longer permissively returns True for unknown model prefixes; runtime version telemetry no longer fabricates a `1.2.3` fallback when no version marker can be read; Spine ingest failures from Token Guardian are now logged at warning level instead of silently swallowed. |
| v1.6.68 | May 2026 | Documentation correctness sweep across `release-notes.md`, the README release history table, and `docs/capabilities.md` so v1.6.65, v1.6.66, and v1.6.67 each describe what actually shipped instead of carrying stale or mislabelled entries; advanced the public downloader fallback URLs and filenames from v1.6.66 to v1.6.68 so the page is internally consistent if the GitHub releases API is briefly unreachable; corrected the desktop-release workflow's first-launch hint from "Sparkbot Controls opens on first launch" to "Sparkbot Command Center opens on first launch" to match the v1.6.67 merge. |
| v1.6.67 | May 2026 | Merged Controls into Command Center as the unified hub for AI Setup, PIN and security, comms connectors, agent management, operations, and Spine inspection; refreshed Command Center with the blue theme and redirected `/controls` to `/spine`. |
| v1.6.66 | May 2026 | Fixed Claude Sub provider save ("Unknown default provider" error) and dead AI Setup button by adding `claude_sub` to the valid providers set; added a Save button inside the Claude Sub panel; updated CLI model list to Sonnet 4.6, Opus 4.7, Haiku 4.5, and Opus 4.7 (1M context); added `claude_sub` to the agent routing override map; pinned the macOS runner to `macos-14` to unblock Tauri DMG bundling and added a `bash -x` re-run on DMG failure for diagnostics. |
| v1.6.65 | May 2026 | Fixed public downloader 404: download links now dynamically resolve the latest desktop release with uploaded assets instead of hardcoding a specific version tag; fallback URLs point at the latest confirmed working build; the JS release loader iterates all releases and picks the first non-draft, non-prerelease `desktop-v*` release with a Windows `.exe` asset. |
| v1.6.64 | May 2026 | Fixed Command Center intent misrouting that dumped runtime state on troubleshooting prompts instead of answering; added correction lock so the bot won't repeat state-dump behavior after user correction; tightened self-inspection and provider-readiness matchers with negative intent guards; removed why/how/explain from simple_qa classifier to fix reasoning misroutes; added Claude Subscription provider (claude_sub) using locally signed-in Claude Code CLI for Pro/Max/Team plan routing without API keys. |
| v1.6.63 | May 2026 | Cleaned the public downloader page so visible text is English/ASCII only, extended Codex subscription CLI routing for long-running work with an unlimited option, and mirrored useful chat turns into per-user shared work memory so browser, Telegram, Discord, and workstation meeting conversations can inform one another without crossing user boundaries. |
| v1.6.62 | May 2026 | Security maintenance release: fixed REST chat message recursion, escaped message-search wildcards, made chat-user creation operator-only, closed WebSocket DB sessions, removed closed terminal sessions from memory, pruned rate-limit buckets, limited upload MIME sniffing, stabilized local SECRET_KEY defaults while production rejects unsafe secrets, generated local Postgres passwords during setup, moved FastAPI startup/shutdown to lifespan, and advanced downloader/docs/package metadata to v1.6.62. |
| v1.6.60 | May 2026 | Smoothed Roundtable into a Seat 1 chaired working-session flow with first-pass ideas, manager assessment, assignments, assigned-work pass, and manager summary; stopped automatic meeting-note generation while preserving operator-triggered notes; limited meeting provider readiness checks to assigned room seats; fixed mobile meeting scrolling/resizing; and advanced backend, frontend, Tauri shell, public downloader, service worker, README, capabilities docs, release notes, and packaging metadata to v1.6.60. |
| v1.6.59 | May 2026 | Release stabilization for memory continuity and model routing: meeting artifacts now roll decisions/actions into shared Guardian work memory visible from main chat, duplicate meeting rollups are suppressed, desktop memory and first-run selector persistence follow `SPARKBOT_DATA_DIR`, `/chat/model` persists the primary route instead of drifting in process memory, meeting agent turns display resolved model routing, and downloader/docs/package metadata advanced to the v1.6.59 desktop line. |
| v1.6.57 | May 2026 | Public-v1 readiness hardening plus Robo preview bridge groundwork: backend worker defaults reduced to 2, production config fails closed on unsafe auth/CORS, live terminal defaults off, and Robo routes default to no-live-control public behavior. |
| v1.6.56 | May 2026 | Added a first-class OpenAI Codex subscription provider that detects the local Codex ChatGPT sign-in and dispatches `openai-codex/gpt-5.3-codex` through the Codex CLI bridge; Controls can set it as the default, Workstation ChatGPT/Codex desks prefill the subscription model, Specialty Wing office detail panels now include an agent selector for packaged or spawned agents, local desktop routing config was moved to the Codex subscription default, and downloader/docs/package metadata advanced to the v1.6.56 desktop line. |
| v1.6.55 | May 2026 | Advanced the Command Center update line for local testing and public updater/download metadata: downloader links, package versions, Tauri metadata, service worker cache, README, capabilities docs, release notes, and GitHub Pages copy now point at the v1.6.55 desktop line. |
| v1.6.54 | May 2026 | Cleaned up Controls by removing the obsolete Active custom agents display, moved Spawn Agent to the top of Agents, added packaged specialist agents, upgraded Workstation Specialty Wing offices with shared Agents dropdowns/model selection, preloaded Meetings Manager into new meeting setup, promoted Spine Ops to the official Command Center with Room Persona/System Health/Computer Control/Token Guardian/Task Guardian surfaced there, and kept downloader/docs/package metadata on the v1.6.54 desktop line. |
| v1.6.53 | May 2026 | Fixed photo processing in app uploads and Telegram by routing images through a shared vision-capable model picker; hardened meeting sends so transient network failures do not leave the room stuck while retrying with proceed/go/try again; expanded Controls onboarding for Google Drive, Google Docs, and Microsoft 365; redesigned the Workstation Specialty Wing into five fixed agent offices with Add Agent slots; downloader/docs advanced to the v1.6.53 desktop line. |
| v1.6.52 | May 2026 | Fixed Controls credential storage so GitHub tokens, GitHub SSH/App secrets, Discord, WhatsApp, and Google connector secrets save directly into Guardian Vault without requiring breakglass; connector secrets remain `use_only` for bridge/runtime use while non-secret toggles persist normally; downloader/docs advanced to the v1.6.52 desktop line. |
| v1.6.51 | May 2026 | Restored full Controls comms onboarding after the GitHub-focused update: Telegram, Discord, WhatsApp, Gmail, and Google Calendar are visible again alongside GitHub; Comms save now persists the full connector form again; downloader/docs advanced to the v1.6.51 desktop line. |
| v1.6.50 | May 2026 | Unified top navigation across Chat, Workstation, Controls, Robo Preview, Command Center, and Info; Controls now opens as a full-page app surface at `/controls`; downloader/docs advanced to the v1.6.50 desktop line. |
| v1.6.49 | May 2026 | GitHub onboarding now focuses on three local control paths: fine-grained token, SSH key, or GitHub App installation, with no webhook setup required in Controls; GitHub status works in local desktop mode; autonomous Roundtable meeting turns retry transient provider/network failures before surfacing errors; heartbeat notes are best-effort so note capture does not break the meeting loop; downloader/docs advanced to the v1.6.49 desktop line. |
| v1.6.48 | May 2026 | Guardian/Spine security stabilization: redact secret-like tool args from Spine approval events, redact metadata and result excerpts in executive decision JSONL, 21 new security gate tests covering vault auth denial, write-mode enforcement, PII redaction at persistence, bypass TTL expiry, and approval pruning. Preservation docs and extraction audit for LIMA-Guardian-Suite. |
| v1.6.47 | May 2026 | Memory growth controls: 30-day hot ledger rotation into month-named cold archives, pre-ledger chat-noise filtering, nightly consolidation into daily summaries, semantic fact dedup/superseding, incremental tombstone deletes with weekly compaction, ranked memory inspector/correct/remove actions, natural "forget that..." matching, low-weight fact TTL archival, and a 90-day improvement-loop outcome window. |
| v1.6.46 | Apr 2026 | Breakglass/Computer Control reliability: redesigned global ON/OFF control with a 24-hour expiry, Vault remains PIN-protected, diagnostics/tests can run while destructive edits/deletes/sends still require yes/no confirmation; fixed custom agent spawning on upgraded local SQLite installs; spawned agents now update the active registry immediately; Workstation Specialty Wing lists created agents for meeting seating; Roundtable chairs can be reassigned in-room; generated meeting notes now post into the meeting transcript and surface errors. |
| v1.6.45 | Apr 2026 | Governed Guardian Memory lifecycle: typed memory candidates, low-clutter indexing, active/stale/archive/delete-proposal states, operator-approved soft deletion, snapshot rebuild throttling, ledger archive manifests, and memory hygiene jobs |
| v1.6.43 | Apr 2026 | Reliability + observability: hard-cap chat tool catalogue at 128 (with auto-shrink retry) to fix `Invalid 'tools': array too long` on Windows builds; tool-catalogue dedup; skill loader accepts both wrapped and flat DEFINITION shapes (system_diagnostics now loads); user-friendly error messages for rate-limit / quota / auth / context / model-not-found / timeout failures; new `/perf` slash command and `/api/v1/chat/performance` endpoint surfacing model + tool latency, error counts, and last error; new docs/error-handling.md and docs/guardian-spine.md |
| v1.6.42 | Apr 2026 | Controls persistence fixes: Computer Control checkbox now stays enabled across page loads (bootstrap no longer resets execution_allowed), model stack persists correctly in multi-worker deployments (cross-worker env reload from data/.env), and startup env loading ensures saved settings survive container restarts |
| v1.6.41 | Apr 2026 | Full browser voice loop: fixed voice-route persona loading, tagged voice-origin messages, added hands-free listen-again after spoken replies, refreshed downloader/docs, and kept Workstation phone access in the release line |
| v1.6.40 | Apr 2026 | Guardian Memory retrieval governance: BM25 default retriever interface, optional hybrid embedding flag, verified fact promotion with pending approvals, nightly Task Guardian memory evaluation, precision/latency metrics, authenticated Guardian metrics endpoint, and defensive LiteLLM tool-manifest trimming for Telegram/background reliability |
| v1.6.39 | Apr 2026 | Early Robo preview positioning; Workstation Robo button; no-execution planning registry with typed manifests, policy metadata, dry-run posture, live Sparkbot health, and run timeline |
| v1.6.38 | Apr 2026 | Governance roadmap baseline: first-class agent identity/kill switches, run timeline API with audit hashes, connector health/scopes, workflow templates, PWA manifest, per-tool input/output guardrails, deterministic eval harness, privacy/data-retention docs, and aligned downloader versioning |
| v1.6.37 | Apr 2026 | Self-learning memory + governed orchestration: hybrid Guardian recall with provenance/confidence, memory self-introspection tools, truth/confidence guardrails, approval-first improvement proposals, policy simulator, orchestrator docs, Telegram token-safe error handling, and write-like shell confirmation in policy mode |
| v1.6.36 | Apr 2026 | Computer Control replaces the room execution gate; Workstation status now reflects the Controls checkbox; first-run 6-digit PIN setup/change flow for Break-glass, Vault, commands, browser writes, and comms sends |
| v1.6.35 | Apr 2026 | Documentation and downloader refresh: coherent README flow, public site copy cleanup, packaging docs updated, and desktop/download version markers advanced |
| v1.6.33 | Apr 2026 | Vault-backed runtime wiring for Discord, WhatsApp, GitHub, Gmail, and Google Calendar; Task Guardian supports `daily:HH:MM` schedules and Zulu one-shots; Windows-safe morning briefing; Jarvis demo kit |
| v1.6.32 | Apr 2026 | Uniform Invite Wing subscription selectors for Claude + ChatGPT/Codex; the third default model seat is xAI Grok; Controls AI setup now surfaces Anthropic/OpenAI subscription flows and xAI API-key guidance |
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
