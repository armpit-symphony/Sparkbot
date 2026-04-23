# Sparkbot

**Sparkbot** is a self-hosted AI assistant that runs entirely on your own machine. No cloud subscription, no data sharing, no monthly fee. Download the installer, add a provider key, and you have a personal AI that controls your desktop, reads your email, manages your calendar, runs code, fills out web forms, and remembers everything you tell it — across every conversation.

> **Desktop app (Windows · macOS · Linux)** — [Download at sparkpitlabs.com](https://armpit-symphony.github.io/Sparkbot/)
> **Self-host on a server** — one Docker command, full HTTPS, any VPS

---

## What Sparkbot Can Do

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
- **Multi-agent rooms** — mention `@researcher`, `@coder`, `@writer`, `@analyst`, or any custom agent for a specialist response
- **Spawn agents** — create named agents with custom system prompts from 11 specialty templates
- **Persistent memory** — Sparkbot stores facts about you and injects them into every conversation
- **Knowledge base** — ingest any document or URL; Sparkbot searches it with BM25 full-text ranking when relevant
- **Skill plugins** — drop a `.py` file into `backend/skills/` to add a new tool; auto-discovered on restart

### Media & Content
- **YouTube summarization** — paste a YouTube URL and get a transcript + summary; no API key required
- **Podcast/audio transcription** — upload or link an audio file; transcribed via OpenAI Whisper
- **News headlines** — Hacker News top stories or BBC RSS (world, tech, business, science, sports, health)
- **Spotify** — play, pause, skip, search, and control volume; works on any active Spotify device
- **Stocks & portfolio** — real-time quotes for any ticker; track a personal portfolio with P&L

### Workstation
- **Office floor** — visual grid of all your AI desks: Sparkbot, model stack companions, agents, invite seats, terminal
- **Invite Wing** — seat any model with its own API key and model ID; routes directly to that provider. The **Claude** and **ChatGPT** desks now use a matching `API Key / Subscription` setup pattern for Anthropic and OpenAI subscription-linked credentials, and the third desk is preset for **xAI Grok**
- **Round Table** — autonomous multi-agent meeting room; all agents contribute without you typing between turns
- **Company Operations** — view all Guardian Tasks across every room, active meetings, and launch project rooms in one click
- **Task-linked meetings** — hit **Meet** on any task and a pre-seeded project room opens

### Proactive Mode & Scheduled Autonomy (Task Guardian)
- **Scheduled jobs** — tell Sparkbot to run any tool on a schedule (hourly, daily, custom interval)
- **Push alerts** — scheduled jobs can push results to your phone via Telegram or Discord — works even when you're away from the desktop
- **Autonomous execution** — jobs run in the background and post results to the room
- **Write-action scheduling** — opt-in to scheduled email, Slack, and calendar writes
- **Verifier guardian** — each scheduled run is evaluated before commit; bounded retries with escalation

### Communication Channels
- **Telegram** — private chats map to Sparkbot rooms; `/approve` / `/deny` resolve confirmations; receives proactive push alerts
- **Discord** — DMs and @mentions map to rooms; same approval flow; receives push alerts
- **WhatsApp** — Meta Cloud API webhook; free-form replies in the 24-hour session window
- **GitHub** — signed webhook for issue and PR comments; `approve` / `deny` resolves in-thread

### Platform Integrations
- **Microsoft 365** — Outlook mail + calendar, OneDrive (requires Azure app registration)
- **Apple (macOS)** — Contacts, Reminders, and Notes via native AppleScript; no API key required
- **Google Workspace** — Gmail, Google Calendar, Google Drive, Google Contacts
- **Natural language → SQL** — query any local SQLite database using plain English

### Security
- **Policy layer** — every tool classified read / write / execute / admin; unknown tools denied by default
- **Write-tool confirmation** — Sparkbot cannot email, post to Slack, or commit autonomously; a confirmation modal is required
- **Execution gate** — shell and server access require the room owner to explicitly enable; defaults off
- **Guardian Vault** — encrypted secret storage; break-glass PIN required before writing secrets
- **Audit trail** — every tool call logged with allow/confirm/deny, redacted args, and timestamps
- **HttpOnly cookies** — session tokens never exposed to JavaScript
- **Dep scanning** — `pip-audit` + `npm audit` + `gitleaks` on every push

---

## Getting Started

### Desktop App (Windows · macOS · Linux)

The desktop app is a standalone installer — no Docker, no terminal, no WSL required.

**Step 1 — Download and install**

Go to [sparkpitlabs.com](https://armpit-symphony.github.io/Sparkbot/) and download the installer for your platform.

- **Windows:** run `Sparkbot.Local_x.x.x_x64-setup.exe`. If Windows SmartScreen appears, click **More info → Run anyway** (the app is unsigned; see [Code Signing](#code-signing) below).
- **macOS:** open the `.dmg` and drag Sparkbot to Applications.
- **Linux:** make the `.AppImage` executable and run it.

**Step 2 — Add a provider key**

On first launch, Sparkbot opens **Sparkbot Controls**. Paste at least one LLM API key:

| Provider | Where to get a key |
|----------|--------------------|
| OpenAI | [platform.openai.com](https://platform.openai.com) |
| Anthropic | [console.anthropic.com](https://console.anthropic.com) |
| Google | [aistudio.google.com](https://aistudio.google.com) |
| Groq | [console.groq.com](https://console.groq.com) |
| OpenRouter | [openrouter.ai](https://openrouter.ai) — one key, 100+ models |

**Step 3 — Start chatting**

Click **Sparkbot** on the office floor to open the main chat. Everything else can be configured from there.

---

### Self-Hosted (Docker)

```bash
# Clone and configure
git clone https://github.com/armpit-symphony/Sparkbot.git
cd Sparkbot
cp .env.local.example .env.local   # add at least one LLM API key

# Start
docker compose -f compose.local.yml up --build
```

Open `http://localhost:3000`. Default passphrase: `sparkbot-local`.

For a public server with HTTPS, see [deployment.md](./deployment.md) (Traefik + Let's Encrypt) or [docs/systemd-single-node.md](./docs/systemd-single-node.md) (systemd + nginx).

---

### CLI (No Browser Required)

```bash
python sparkbot-cli.py                          # interactive
python sparkbot-cli.py --setup                  # configure provider keys + model roles
python sparkbot-cli.py "What's on my calendar?" # one-shot
echo "Summarise my inbox" | python sparkbot-cli.py
```

Requires Python 3.10+, no extra packages. On first run it prompts for your server URL and passphrase and saves them to `~/.sparkbot/cli.json`.

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
| `/clear` | Clear view (history preserved on server) |

### Computer Control

Computer Control capabilities are shown in the **Workstation → Computer Control** panel.

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

Type `@` in the input to get the autocomplete picker. Create custom agents in **Controls → Spawn Agent**.

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

The **Round Table** in the Workstation launches an autonomous multi-agent meeting. Click **Auto-fill Stack** to seat your configured models, then start the meeting. The agents take turns contributing without you needing to type between replies. You can interrupt at any time.

### Scheduling Tasks (Task Guardian)

Tell Sparkbot to run anything on a schedule:

```
"Every morning at 8am, run my morning briefing"
"Check my inbox every hour and let me know if anything urgent arrives"
"Send me a daily calendar preview at 7:30am"
```

Manage scheduled jobs from **Controls → Task Guardian** or from the **Company Operations** section of the Workstation.

### Knowledge Base

Feed Sparkbot documents or URLs that it can search when relevant:

```
"Remember this doc for later: [paste text]"
"Ingest https://docs.example.com/api — I'll be asking questions about it"
```

Sparkbot uses BM25 full-text search to pull relevant chunks into the conversation when you ask related questions.

---

## Configuration

All configuration is via environment variables.

- **Desktop app** — set keys in **Sparkbot Controls** (UI). Advanced settings: the `.env` file beside the installed executable.
- **Docker / local** — copy `.env.local.example` to `.env.local`
- **Server / systemd** — copy `.env.example` to `.env`

### Minimum required (server install)

```env
ENVIRONMENT=production
SECRET_KEY=<random 32+ char string>
SPARKBOT_PASSPHRASE=<strong passphrase>
FIRST_SUPERUSER_PASSWORD=<strong admin password>
FRONTEND_HOST=https://chat.example.com
BACKEND_CORS_ORIGINS=https://chat.example.com
```

Plus one of: `DATABASE_TYPE=sqlite` + `SPARKBOT_DATA_DIR=...`
or `DATABASE_TYPE=postgresql` + `POSTGRES_*` variables.

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

| What competitors do | What Sparkbot does |
|--------------------|-------------------|
| LLM calls tools freely | Policy layer classifies every tool: read / write / execute / admin |
| External writes happen silently | Confirmation modal required before any external mutation |
| No audit trail | Every tool call logged + redacted args stored |
| Secrets may leak into logs | Audit redaction strips key-name and token-pattern values at write time |
| Session token in localStorage | HttpOnly `Secure SameSite=Strict` cookie — never reachable from JavaScript |
| No dependency scanning | `pip-audit` + `npm audit` on every push via GitHub Actions |

---

## Full Reference

- **[docs/capabilities.md](./docs/capabilities.md)** — every tool, command, integration, env var, API endpoint, and Guardian Spine route
- **[docs/skill-author-guide.md](./docs/skill-author-guide.md)** — how to write, test, and ship a skill plugin
- **[docs/guardian-job-examples.md](./docs/guardian-job-examples.md)** — copy-paste Task Guardian job templates
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
| v1.6.26 | Apr 2026 | Fix: skills (Telegram, Spotify, Google, Microsoft) now read env vars at call time not startup — credentials saved via UI now take effect without restart |
| v1.6.25 | Apr 2026 | Telegram Chat ID field in settings UI — enables proactive alerts via send_alert skill |
| v1.6.24 | Apr 2026 | Breakglass: inline justification on activation (`/breakglass <reason>`), exact expiry timestamp in confirmation, justification logged to audit trail |
| v1.6.22 | Apr 2026 | Relationship memory (personal CRM); proactive push alerts to Telegram/Discord; time tracking; Linear + Jira; NL→SQL; audio/podcast transcription; contacts manager; Microsoft 365 (Outlook, OneDrive); Apple integrations (Contacts, Reminders, Notes); stocks + portfolio; Spotify control; YouTube summarization; configurable daily digest with weather + stocks + news |
| v1.3.0 | Apr 2026 | Security hardening: SSRF fixes in fetch_url + knowledge base; per-user KB isolation; Sentry data scrubbing; npm dep fixes; message queue (send while Sparkbot is responding) |
| v1.2.9 | Apr 2026 | Skill sandboxing (timeout + memory); 121 CI smoke tests; skill author guide + Guardian job examples |
| v1.2.8 | Apr 2026 | Process watcher (auto-throttle Ollama CPU); model latency tracking; latency API |
| v1.2.7 | Apr 2026 | system_diagnostics skill; repair-playwright scripts; Troubleshooting.md |
| v1.2.6 | Apr 2026 | Stable Playwright browser dir; LLM tool-loop guards |
| v1.6.32 | Apr 2026 | Uniform Invite Wing subscription selectors for Claude + ChatGPT/Codex; OpenClaw desk replaced by xAI Grok; Controls AI setup now surfaces Anthropic/OpenAI subscription flows and xAI API-key guidance |
| v1.6.31 | Apr 2026 | Invite Wing ChatGPT desk becomes the Codex gateway for ChatGPT-linked OpenAI keys and `codex-mini-latest`; OpenAI Codex models route as first-class invite seats |
| v1.6.30 | Apr 2026 | Telegram polling auto-enables on token save; Chat ID mirrored into operator/allowed lists |
| v1.2.2 | Apr 2026 | `shell_run`; Windows live terminal; browser auto-install; Invite Wing API keys |
| v1.1.x | Apr 2026 | Workstation operations dashboard; Round Table autonomous meetings; Guardian Tasks |
| v1.0.x | Mar 2026 | Code interpreter; named browser sessions; knowledge base (RAG); voice quick-capture; Spawn Agent |
| v0.9.x | Mar 2026 | Guardian Spine; break-glass; vault; Telegram/Discord/WhatsApp/GitHub bridges; full security audit |
