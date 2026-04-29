# Sparkbot — Full Capabilities Reference

This document is the complete technical reference for every feature, tool, command, integration, and configuration option in Sparkbot. The [README](../README.md) covers getting started and daily use; this doc covers everything else.

---

## Positioning Snapshot

Sparkbot is a local-first agent OS with enterprise-grade governance. In practical terms, that means meetings, scheduled jobs, tools, approvals, secrets, memory, and audit evidence all live in one governed loop instead of separate assistant features.

### Orchestrator capabilities shipped today

- **Round Table meeting orchestration:** chair-led multi-agent meetings with participant manifests, owner interrupt, specialist turns, synthesis, and terminal statuses.
- **Meeting heartbeat:** each autonomous Workstation meeting can create an hourly `meeting_heartbeat` Guardian task that continues the room until it is solved, blocked, recommendation-ready, looping, or waiting on approval/user input.
- **Task-linked project rooms:** Guardian Tasks can open or re-open a dedicated meeting room with task context, stack bots, and a project notes artifact.
- **Persistent approvals:** confirmation-gated actions are stored in the Guardian approval database and surfaced through the dashboard, Telegram, GitHub, and bridge flows.
- **Policy simulation:** `guardian_simulate_policy` previews whether a proposed tool call would allow, confirm, deny, or require break-glass without executing the action.
- **Audit and evidence:** tool decisions go through policy, Executive Guardian journaling, verifier checks for risky interactive actions, Guardian Spine queues, and redacted audit logs.

### Governance roadmap alignment

| Addition | Current state |
|----------|---------------|
| Agent identity + permissions | Shipped baseline: every agent exposes owner, purpose, scopes, allowed tools, expiration, risk tier, and kill-switch metadata; disabled agents no longer route from `@mention`. |
| Trace viewer / run timeline | Shipped baseline: `/api/v1/chat/dashboard/runs/timeline` returns room-scoped policy/tool events with model, agent, decision, summary, and audit hash. |
| Policy simulator | Shipped as the `guardian_simulate_policy` chat tool. |
| Persistent approval inbox | Shipped through durable pending approvals, dashboard approval actions, and Telegram/GitHub/bridge approval flows. |
| Agent run resume | Shipped baseline: approval-gated tool calls persist exact payloads and resume on approval; full multi-hour graph serialization remains future expansion. |
| Tool guardrails before/after execution | Shipped baseline: per-tool input guardrails run before execution and output guardrails run after LLM/dashboard execution. |
| Workflow builder | Shipped baseline: `/api/v1/chat/dashboard/workflows/templates` exposes trigger -> condition -> tool/agent -> approval -> notify -> audit templates. |
| Unified MCP registry | Shipped baseline: `/api/v1/chat/mcp/registry` returns backend-owned Sparkbot and LIMA Robotics OS manifests, policy tags, approval posture, run timeline, and live health for the Workstation Robo OS panel. `POST /api/v1/chat/mcp/explain-plan` previews any manifest through Guardian policy without executing it, then the run approval endpoints can request, approve, or deny the saved plan without triggering execution. |
| Mobile companion / PWA | Shipped baseline: public site includes PWA manifest and service worker; dashboard/bridge approval surfaces remain mobile-readable. |
| Connector quality | Shipped baseline: `/api/v1/chat/dashboard/connectors/health` reports connector setup state, read/write scopes, setup-test flag, and audit metadata. |
| Evaluation harness | Shipped baseline: `/api/v1/chat/dashboard/evals/agent-behavior` runs deterministic governance eval cases for tool choice, approval requirements, guardrails, and agent routing. |

References used for this roadmap framing: [Okta's 2026 agent governance framing](https://www.okta.com/newsroom/press-releases/showcase-2026/), [OpenAI Agents SDK tracing guidance](https://openai.github.io/openai-agents-js/guides/tracing/), [OpenAI human-in-the-loop guidance](https://openai.github.io/openai-agents-js/guides/human-in-the-loop/), and [OpenAI guardrails guidance](https://openai.github.io/openai-agents-js/guides/guardrails/).

---

## Table of Contents

1. [Chat Features](#chat-features)
2. [Slash Commands](#slash-commands)
3. [Computer Control](#computer-control)
4. [Agent Tools (Built-In)](#agent-tools-built-in)
5. [Skill Plugins (Drop-In)](#skill-plugins-drop-in)
6. [Integrations](#integrations)
7. [AI & Model Configuration](#ai--model-configuration)
8. [Multi-Agent System](#multi-agent-system)
9. [Workstation](#workstation)
10. [MCP Control Plane & Robo OS](#mcp-control-plane--robo-os)
11. [Task Guardian (Scheduled Autonomy)](#task-guardian-scheduled-autonomy)
12. [Guardian Stack (Security)](#guardian-stack-security)
13. [Communication Bridges](#communication-bridges)
14. [Voice (Whisper + TTS)](#voice-whisper--tts)
15. [Knowledge Base (RAG)](#knowledge-base-rag)
16. [Meeting Mode & Roundtable](#meeting-mode--roundtable)
17. [Persistent Memory](#persistent-memory)
18. [Environment Variables — Full Reference](#environment-variables--full-reference)
19. [API Endpoints](#api-endpoints)
20. [Guardian Spine — Operator Reference](#guardian-spine--operator-reference)
21. [Process Watcher & Model Throttling](#process-watcher--model-throttling)
22. [Model Latency Tracking](#model-latency-tracking)
23. [Skill Sandboxing](#skill-sandboxing)
24. [API Usage Examples](#api-usage-examples)
25. [Versioning & Compatibility](#versioning--compatibility)
26. [Project File Map](#project-file-map)

---

## Chat Features

| Feature | Details |
|---------|---------|
| Streaming responses | Token-by-token SSE via `/messages/stream`, typing cursor |
| Conversation context | Last 20 messages passed as history on every LLM call |
| Markdown rendering | Headings, lists, bold, tables, code blocks in bot replies |
| Syntax highlighting | Fenced code blocks with language detection (oneDark theme) |
| Copy-code button | One click to clipboard on every code block |
| Message search | `/search <query>` — full-text search across room history |
| File uploads | Images (vision analysis), documents (text extraction), other files — 10 MB max |
| Reply threading | Hover any message to reply; quoted snippet shown above input |
| Message edit | Hover own messages to edit inline; `· edited` timestamp badge shown |
| Voice input | Click mic → record → Whisper transcribes → enters normal LLM pipeline |
| Text-to-speech | Enable voice mode (speaker icon) to hear bot replies spoken aloud |
| Self-inspection | Sparkbot can report its own provider/model stack, routing, and guardian status from chat |

### Document Summarisation

Upload a PDF, DOCX, TXT, Markdown, or CSV. Use the caption field as your prompt.

| Format | Extraction method |
|--------|------------------|
| `.pdf` | pypdf (text-layer PDFs; scanned/image PDFs return no text) |
| `.docx` | python-docx |
| `.txt` / `.md` / `.csv` | UTF-8 decode |

Up to 12,000 characters (~3k tokens) sent to the LLM. Large documents are truncated with a note.

---

## Slash Commands

Type `/` in the chat input to get autocomplete.

| Command | Description |
|---------|-------------|
| `/help` | List all commands |
| `/clear` | Clear local view (server history preserved) |
| `/new` | Fresh start — new conversation |
| `/export` | Download conversation as `.md` |
| `/search <query>` | Search message history with highlighting |
| `/meeting start` | Begin meeting mode |
| `/meeting stop` | End meeting and export notes as `.md` |
| `/meeting notes` | Show captured notes mid-meeting |
| `/breakglass` | Open privileged mode; Sparkbot prompts for your operator PIN |
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

---

## Computer Control

Sparkbot can control the local machine it is running on. These capabilities are available in the desktop app and on any self-hosted server where Computer Control is enabled or a break-glass PIN session is active.

### Shell (`shell_run`)

- Runs any command in PowerShell (Windows) or bash (Linux/macOS)
- Working directory **persists across messages** — `cd` carries forward within a conversation
- Output capped: 16 KB stdout + 4 KB stderr
- Default timeout: 30 seconds (max 300 seconds)
- Disable with `SPARKBOT_SHELL_DISABLE=true`
- In Guardian policy mode, write-like shell commands such as file changes, package installs, builds, destructive commands, and git mutations require confirmation before execution

**Example prompts:**
- *"Run `git status` in my project folder"*
- *"List all files in Downloads"*
- *"Install the requests package with pip"*

### Live Terminal (`terminal_send` / `terminal_list_sessions`)

- Full interactive xterm.js terminal panel in the Workstation
- Sparkbot can inject commands into the terminal while you watch
- Cross-platform: ConPTY via `pywinpty` on Windows; PTY/fcntl on Linux/macOS
- Multiple sessions supported; `terminal_list_sessions` lists active ones
- Connect from the Workstation panel (Computer Control → Terminal)

### Browser Automation

Sparkbot opens a real Chromium browser and can:

| Tool | What it does |
|------|-------------|
| `browser_open` | Open a URL in Chromium |
| `browser_snapshot` | Read the current page content |
| `browser_click` | Click a button or link |
| `browser_fill_field` | Fill a form field |
| `browser_save_session` | Save cookies/localStorage for re-use |
| `browser_restore_session` | Load a saved login session |
| `browser_list_sessions` | List active and saved sessions |

Chromium is auto-downloaded on first desktop launch (~150 MB, one-time). Browser window is visible by default on the desktop app.

**Example prompts:**
- *"Open Google and search for Python tutorials"*
- *"Log in to my GitHub and check my notifications"*
- *"Fill out and submit the contact form at example.com"*

### Code Execution (`run_code`)

Run code directly from chat and get output back.

| Language | Runtime |
|----------|---------|
| Python 3 | subprocess-sandboxed |
| Node.js | subprocess-sandboxed |
| Bash | subprocess-sandboxed |

Default timeout: 30 seconds (max 120 seconds). Disable with `SPARKBOT_CODE_DISABLE=true`.

### Server Operations (Self-Hosted)

| Tool | Description |
|------|-------------|
| `server_read_command` | Read-only diagnostics: system overview, memory, disk, listeners, processes, service status, recent logs |
| `server_manage_service` | Start/stop/restart an approved systemd service |
| `ssh_read_command` | Read-only diagnostics on an approved SSH host alias |

Configuration:
```env
SPARKBOT_ALLOWED_SERVICES=sparkbot-v2
SPARKBOT_SERVICE_USE_SUDO=false
SPARKBOT_SERVER_COMMAND_TIMEOUT_SECONDS=20
SPARKBOT_SSH_ALLOWED_HOSTS=
SPARKBOT_SSH_ALLOWED_SERVICES=
SPARKBOT_SSH_CONNECT_TIMEOUT_SECONDS=10
SPARKBOT_SSH_COMMAND_TIMEOUT_SECONDS=30
```

---

## Agent Tools (Built-In)

These tools are called automatically mid-conversation. A chip appears briefly in the UI while the tool runs, then disappears as the response streams in.

### Core Tools

| Tool | Emoji | Description |
|------|-------|-------------|
| `web_search` | 🔍 | Search the web (Brave → SerpAPI → DuckDuckGo fallback chain) |
| `fetch_url` | 🌐 | Fetch and read the full content of any public URL |
| `get_datetime` | 🕐 | Current UTC date and time |
| `calculate` | 🧮 | Safe AST-based math evaluator (no `eval()`) |

### Task Management

| Tool | Emoji | Description |
|------|-------|-------------|
| `create_task` | 📋 | Create a task in the current room (optional assignee + due date) |
| `list_tasks` | 📋 | List open/done/all tasks in the current room |
| `complete_task` | ✅ | Mark a task as done by ID |
| `set_reminder` | ⏰ | Schedule a reminder (once/daily/weekly) to post in this room |
| `list_reminders` | ⏰ | List pending reminders for this room |
| `cancel_reminder` | ⏰ | Cancel a reminder by ID |

### Guardian Governance

| Tool | Emoji | Description |
|------|-------|-------------|
| `guardian_simulate_policy` | 🛡️ | Preview allow / confirm / deny / break-glass for a proposed tool call without executing it |
| `guardian_propose_improvement` | 🛡️ | Record a governed Sparkbot self-improvement proposal for operator approval |
| `guardian_list_improvements` | 🛡️ | List pending self-improvement proposals |
| `guardian_list_tasks` | 🛡️ | List Task Guardian jobs for the room |
| `guardian_list_runs` | 🛡️ | List recent Task Guardian runs |
| `guardian_run_task` | 🛡️ | Run a Task Guardian job immediately |
| `guardian_pause_task` | 🛡️ | Pause or resume a Task Guardian job |

### Email

| Tool | Emoji | Description |
|------|-------|-------------|
| `gmail_fetch_inbox` | 📬 | Fetch recent Gmail messages via Google Workspace API |
| `gmail_search` | 📬 | Search Gmail using Gmail query syntax |
| `gmail_get_message` | 📬 | Read a Gmail message in detail by message ID |
| `gmail_send` | 📤 | Send an email through Gmail API (requires confirmation) |
| `email_fetch_inbox` | 📧 | Fetch recent/unread emails from IMAP inbox |
| `email_search` | 📧 | Search inbox by subject or sender keyword |
| `email_send` | 📤 | Send an email via SMTP (requires confirmation) |

### Calendar

| Tool | Emoji | Description |
|------|-------|-------------|
| `calendar_list_events` | 📅 | List upcoming calendar events via CalDAV |
| `calendar_create_event` | 📅 | Create a calendar event via CalDAV (requires confirmation) |

### Google Workspace

| Tool | Emoji | Description |
|------|-------|-------------|
| `drive_search` | 📁 | Search Google Drive files and folders |
| `drive_get_file` | 📁 | Read Drive file metadata and text content |
| `drive_create_folder` | 📁 | Create a folder in Google Drive (requires confirmation) |

### Dev & Project Tools

| Tool | Emoji | Description |
|------|-------|-------------|
| `github_list_prs` | 🐙 | List pull requests (open/closed/all) for a repo |
| `github_get_pr` | 🐙 | Full PR details — title, body, diff stats, files, CI checks |
| `github_create_issue` | 🐙 | Create a GitHub issue (requires confirmation) |
| `github_get_ci_status` | 🔬 | Latest workflow run results for a branch |

### Collaboration

| Tool | Emoji | Description |
|------|-------|-------------|
| `notion_search` | 📝 | Search Notion pages by keyword |
| `notion_get_page` | 📝 | Read a Notion page |
| `notion_create_page` | 📝 | Create a Notion page (requires confirmation) |
| `confluence_search` | 🏔️ | CQL search across Confluence spaces |
| `confluence_get_page` | 🏔️ | Read a Confluence page |
| `confluence_create_page` | 🏔️ | Create a Confluence page (requires confirmation) |
| `slack_send_message` | 💬 | Post a message to a Slack channel (requires confirmation) |
| `slack_list_channels` | 💬 | List public Slack channels |
| `slack_get_channel_history` | 💬 | Fetch recent messages from a channel |

### Memory

| Tool | Description |
|------|-------------|
| `remember_fact` | Store a fact about the user for future sessions |
| `forget_fact` | Remove a stored fact by ID |

Tool calling uses litellm's function-calling API (OpenAI format). Up to 20 tool-calling rounds per message.

---

## Skill Plugins (Drop-In)

Drop a `.py` file into `backend/skills/` and it auto-loads on the next restart. No other files need editing.

### Required exports

```python
DEFINITION = {
    "name": "my_tool",
    "description": "What this tool does",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Input"}
        },
        "required": ["query"]
    }
}

async def execute(args, *, user_id=None, room_id=None, session=None) -> str:
    return "result"
```

### Optional — Policy declaration

```python
POLICY = {
    "scope": "read",           # read | write | execute | admin
    "resource": "external",    # external | local_machine | system
    "default_action": "allow", # allow | confirm | deny
    "action_type": "data_read",
    "high_risk": False,
    "requires_execution_gate": False,
}
```

### Multi-tool skills

A single `.py` file can register multiple tools via `_register_extra(registry)`.

### Built-in skills (pre-installed)

| Skill file | Tool name(s) | Description |
|-----------|-----------|-------------|
| `example_weather.py` | `get_weather` | Current weather via wttr.in (no API key) |
| `calendar_list_events.py` | `calendar_list_events` | List Google Calendar events |
| `calendar_create_event.py` | `calendar_create_event` | Create Google Calendar event (confirmation required) |
| `morning_briefing.py` | `morning_briefing` | Configurable daily digest: weather, stocks, Gmail/Outlook, calendar, news, reminders |
| `news_headlines.py` | `news_headlines` | HN top stories or BBC RSS (no API key) |
| `currency_convert.py` | `currency_convert` | Live FX rates via open.er-api.com (no API key) |
| `crypto_price.py` | `crypto_price` | BTC/ETH/SOL/… prices via CoinGecko (no API key) |
| `shell_run.py` | `shell_run` | Shell command execution (PowerShell/bash) |
| `knowledge_base.py` | `ingest_document`, `search_knowledge`, `list_knowledge`, `delete_knowledge` | BM25 full-text RAG |
| `relationship_memory.py` | `remember_person`, `recall_person`, `list_people`, `log_interaction`, `forget_person_fact`, `forget_person` | Personal CRM — store facts, notes, and interaction history per person |
| `proactive_alerts.py` | `send_alert` | Push notifications to Telegram/Discord from scheduled jobs |
| `time_tracking.py` | `time_start`, `time_stop`, `time_log`, `time_report`, `time_status` | Project time tracking with reports |
| `linear_jira.py` | `linear_list_issues`, `linear_create_issue`, `linear_update_issue`, `jira_list_issues`, `jira_create_issue`, `jira_add_comment` | Linear and Jira issue tracker integration |
| `nl_sql.py` | `execute_sql`, `list_databases`, `describe_table` | Natural language → SQL against local SQLite databases |
| `audio_transcribe.py` | `transcribe_audio` | Transcribe audio files and podcasts via OpenAI Whisper |
| `contacts.py` | `contacts_search`, `contacts_add`, `contacts_update`, `contacts_delete`, `contacts_sync_google` | Personal contacts manager with Google Contacts sync |
| `microsoft_graph.py` | `outlook_read_mail`, `outlook_send_mail`, `outlook_calendar_list`, `outlook_calendar_create`, `onedrive_list`, `onedrive_read` | Microsoft 365 — Outlook, Calendar, OneDrive |
| `apple_integrations.py` | `apple_contacts_search`, `apple_reminders_list`, `apple_reminders_create`, `apple_notes_search`, `apple_notes_create` | macOS Contacts, Reminders, and Notes via AppleScript |
| `stocks.py` | `stock_quote`, `stock_history`, `portfolio_add`, `portfolio_view`, `portfolio_remove` | Real-time stock quotes and personal portfolio tracker |
| `spotify.py` | `spotify_play`, `spotify_pause`, `spotify_next`, `spotify_previous`, `spotify_now_playing`, `spotify_search`, `spotify_volume` | Spotify music control and search |
| `youtube_summarize.py` | `youtube_transcript`, `youtube_summarize` | Fetch YouTube captions and prepare for summarization (no API key) |

Set `SPARKBOT_SKILLS_DIR` env var to change the directory (relative to `backend/` or absolute).

Skills are guarded by the same policy/executive/memory stack as built-in tools. Built-in tools always take priority — skills are only reached as fallback.

---

## Integrations

### Email

**Gmail (Google Workspace API)**
```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
GOOGLE_GMAIL_USER=me
```
Required OAuth scopes: `gmail.readonly`, `gmail.send`

**IMAP / SMTP (any provider)**
```env
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USER=you@example.com
IMAP_PASSWORD=...
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=you@example.com
SMTP_PASSWORD=...
```

### Calendar

**CalDAV (Google, iCloud, Nextcloud, Fastmail, Baikal, Radicale)**
```env
CALDAV_URL=https://www.google.com/calendar/dav/you@gmail.com/events
CALDAV_USERNAME=you@gmail.com
CALDAV_PASSWORD=your-app-password
```

| Provider | URL |
|----------|-----|
| Google Calendar | `https://www.google.com/calendar/dav/{email}/events` |
| iCloud | `https://caldav.icloud.com` |
| Nextcloud | `https://your-server/remote.php/dav/` |
| Fastmail | `https://caldav.fastmail.com/dav/` |
| Baikal / Radicale | Your server URL |

### Google Drive
```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
GOOGLE_DRIVE_SHARED_DRIVE_ID=...   # optional, for shared drive
```
Required OAuth scopes: `drive.readonly`, `drive.file`

### GitHub
```env
GITHUB_TOKEN=ghp_...
GITHUB_DEFAULT_REPO=owner/repo
```

### Slack
```env
SLACK_BOT_TOKEN=xoxb-...
```

### Notion
```env
NOTION_API_KEY=secret_...
```

### Confluence
```env
CONFLUENCE_URL=https://your-org.atlassian.net/wiki
CONFLUENCE_USER=you@example.com
CONFLUENCE_API_TOKEN=...
```

### Web Search

Fallback chain: **Brave → SerpAPI → DuckDuckGo**. DuckDuckGo works out of the box with no key.

```env
BRAVE_SEARCH_API_KEY=...       # free tier: 2k req/day
SERPAPI_KEY=...                # fallback
SEARCH_CACHE_TTL_SECONDS=300   # cache identical queries (default 300s)
```

---

## AI & Model Configuration

### Supported Providers

| Provider | Env var | Notes |
|---------|---------|-------|
| OpenAI | `OPENAI_API_KEY` | GPT-4o, o1, o3, GPT-5 |
| Anthropic | `ANTHROPIC_API_KEY` | Claude Sonnet, Haiku, Opus |
| Google | `GOOGLE_API_KEY` | Gemini 2.0 Flash, Pro |
| Groq | `GROQ_API_KEY` | Llama 3.3 70B (very fast) |
| MiniMax | `MINIMAX_API_KEY` | MiniMax M2.5 |
| OpenRouter | `OPENROUTER_API_KEY` | 100+ models via one key |
| Ollama | `OLLAMA_BASE_URL` | Local models — **not recommended for tool-heavy tasks** |

### Model Stack

Configure four model roles for automatic routing and fallback:

```env
SPARKBOT_MODEL=gpt-4o-mini         # Primary — used for most messages
SPARKBOT_BACKUP_MODEL=claude-sonnet-4-5  # Backup 1 — if primary fails
SPARKBOT_BACKUP_MODEL_2=gemini/gemini-2.0-flash  # Backup 2
SPARKBOT_HEAVY_MODEL=gpt-4o        # Heavy Hitter — complex reasoning tasks
```

Switch live from chat: `/model <id>` — changes take effect immediately for your session.

### Invite Wing (Per-Seat API Keys)

Seat any model into a Workstation desk with its own Model ID and API Key. At meeting launch, requests route directly to that provider using your key — bypassing the default stack. Supports Claude, Codex/GPT, Grok, Gemini, and Ollama.

**Claude Subscription (OAuth).** When the provider is **Anthropic**, the invite modal shows an `API Key / Claude Subscription` segmented toggle. Picking **Claude Subscription** lets you paste an OAuth access token (`sk-ant-oat01-…`) instead of an `sk-ant-api03-…` API key — the same credential format used by [openclaw](https://github.com/instavm/openclaw) and [Hermes](https://github.com/HumanLayer/hermes). Anthropic allows Claude Pro/Max plans to drive API calls via OAuth with no per-token billing.

How to get the token:

1. Install Claude Code: `npm i -g @anthropic-ai/claude-code` (or use an existing install).
2. Run `claude setup-token` and finish the browser sign-in — it prints an OAuth access token.
   - Or copy the `access_token` value out of `~/.claude/credentials.json` (macOS/Linux) / `%USERPROFILE%\.claude\credentials.json` (Windows).
3. In Sparkbot: **Workstation → Invite Wing → Claude** (or any Anthropic seat) → **Claude Subscription** → paste the token → **Invite**.

Sparkbot sends the token via `Authorization: Bearer` with the `anthropic-beta: oauth-2025-04-20` header, so meetings launched through that seat spend against your subscription quota rather than API credits. Tokens expire — paste a fresh one if Anthropic starts rejecting requests.

**Codex with your ChatGPT plan.** The **ChatGPT** Invite Wing desk is also the **Codex** gateway. Pick `API Key / Subscription`, keep the model set to `codex-mini-latest` (or switch to another OpenAI model), and paste the OpenAI API key created when you sign in to Codex with ChatGPT. OpenAI’s current official flow is `codex --login` (or `codex --free` for the promo path), which links the ChatGPT plan and creates an API key automatically. Sparkbot stores that key locally and uses it only when the invited seat joins a meeting.

**xAI (Grok).** The third Invite Wing desk is preset for **xAI Grok**. Per xAI’s official developer docs, Sparkbot uses the xAI API path: create an xAI account and API key, then paste `XAI_API_KEY`. Grok app / X subscription linking applies to consumer access on xAI properties and does not replace the API key in Sparkbot.

### Token Guardian Shadow Mode

Logs a routing recommendation per prompt (classification, confidence, recommended model, estimated cost) without changing live dispatch.
```env
SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED=true
```

---

## Multi-Agent System

### Built-in agents

| Agent | Mention | Specialty |
|-------|---------|-----------|
| Researcher | `@researcher` | Accurate info; uses web search proactively; cites sources |
| Coder | `@coder` | Clean, working code with explanations |
| Writer | `@writer` | Writing, editing, emails, summaries, docs |
| Analyst | `@analyst` | Structured reasoning, data analysis, calculations |

Type `@` in the input to get an autocomplete picker. The bot's response shows an agent badge (e.g. `🔍 RESEARCHER`).

### Spawning custom agents

In **Controls → Spawn Agent**, choose from 11 specialty templates:

Data Scientist · DevOps · Legal Advisor · HR Manager · Marketing · Finance · Customer Support · PM · Security Analyst · Technical Writer · Custom

Each agent gets a full system prompt, emoji, name, and description. Spawned agents are:
- Immediately available via `@name` mention (no restart required)
- Persisted in the database across restarts
- Removable from the Controls interface (built-in agents are protected)

### Agent identity and permissions

Every agent now exposes first-class identity metadata:

| Field | Meaning |
|-------|---------|
| `owner` | Accountable owner or source of the agent |
| `purpose` | Why the agent exists and what it should do |
| `scopes` | Work categories the agent is intended to perform |
| `allowed_tools` | Tool families the agent is expected to use, still enforced through Guardian policy |
| `expires_at` | Optional expiry timestamp for temporary agents |
| `risk_tier` | Low / standard / medium / high operating risk |
| `kill_switch` | If true, the agent is listed as disabled and `@mention` routing will not invoke it |

Operators can set `SPARKBOT_DISABLED_AGENTS=researcher,coder` as a coarse kill switch, or use `SPARKBOT_AGENT_IDENTITY_JSON` for structured identity overrides.

Custom agents via env var:
```env
SPARKBOT_AGENTS_JSON=[{"name":"devops","emoji":"🛠","description":"DevOps specialist","system_prompt":"You are..."}]
SPARKBOT_AGENT_IDENTITY_JSON={"devops":{"owner":"platform","scopes":["ci","diagnostics"],"allowed_tools":["read_tools"],"risk_tier":"medium","kill_switch":false}}
```

---

## Workstation

The Workstation is the visual operations hub. Access it from the main navigation.

### Office Floor

A visual grid showing all active desks:
- **Main Desk** — your primary Sparkbot DM
- **Stack Desks** — Primary, Backup 1, Backup 2, Heavy Hitter model companions
- **Invite Wing** — externally-keyed model seats
- **Specialty Agents** — spawned custom agents
- **Terminal Desk** — live xterm.js terminal panel
- **Computer Control** — shell, terminal, and browser capability panel
- **Robo OS** — unified MCP control-plane panel for Sparkbot tools and LIMA Robotics OS skills

### Computer Control Panel

Three capability cards visible in the Workstation:
- **Shell** — run PowerShell/bash commands via chat
- **Terminal** — interactive terminal panel (click Connect to start session)
- **Browser** — open URLs, fill forms, click, save sessions

The Workstation Computer Control card mirrors Sparkbot Controls: **Always on** means the room checkbox is enabled, and **PIN gated** means Sparkbot will ask for break-glass PIN authorization before risky commands, edits, browser writes, vault access, or comms sends.

---

## MCP Control Plane & Robo OS

The **Robo OS** button opens the first unified MCP registry in Workstation. It positions the system as:

| Layer | Ownership |
|-------|-----------|
| Sparkbot | Governed agentic assistant and command center for chat, computer work, cloud ops, business workflows, approvals, memory, Vault, and audit |
| LIMA Robotics OS | Local Intelligent Machine Agent runtime for robot skills and physical-world execution exposed through MCP |
| Together | One assistant surface for computer work, connected services, and robotics |

The panel loads from `GET /api/v1/chat/mcp/registry` and falls back to the bundled frontend manifests only if the API is unavailable. It shows typed manifests for Sparkbot tools and LIMA robot skills with:

- Runtime owner: `sparkbot` or `lima-robo-os`
- Policy tags: `read-only`, `write`, `destructive`, `external-send`, `robot-motion`, `secret-use`
- Risk level: low, medium, high, critical
- Required secrets or daemon endpoints
- Health source: Sparkbot API, Task Guardian, Guardian Vault, or external MCP
- Live status: configured, missing secrets, bridge needed, disabled, or demo-ready
- Approval posture: whether the tool requires operator approval before execution
- Dry-run posture: native dry run, explain-plan, or required-before-motion

Click **Explain** on a manifest to call `POST /api/v1/chat/mcp/explain-plan`. Sparkbot maps the manifest to the concrete policy tool name, supplies safe sample args when none are provided, runs Guardian policy simulation, writes an `mcp_explain_plan` audit entry, and returns:

- Simulation-only flag
- Policy decision and reason
- Whether dry run or approval is required
- Whether execution can happen now
- Next required operator action
- Timeline steps from user request through audit evidence

The explain-plan also creates a durable MCP run record in `mcp_runs.db` under the Guardian data directory. The Robo OS panel shows recent runs, and API clients can inspect them with:

- `GET /api/v1/chat/mcp/runs`
- `GET /api/v1/chat/mcp/runs/{run_id}`
- `POST /api/v1/chat/mcp/runs/{run_id}/request-approval`
- `POST /api/v1/chat/mcp/runs/{run_id}/approve`
- `POST /api/v1/chat/mcp/runs/{run_id}/deny`

Run statuses are `planned`, `awaiting_approval`, `ready`, `blocked`, `completed`, or `failed`. The current implementation records planning, policy, and approval state only. Approval marks a run `ready` for future runner handoff, denial marks it `blocked`, and neither path executes the underlying Sparkbot or LIMA tool yet.

No hardware is required for the Robo OS demo path. LIMA replay/simulation commands are surfaced directly in Sparkbot:

```bash
LIMA --replay run unitree-go2
LIMA --simulation run unitree-go2-agentic-mcp
LIMA run demo-camera
```

Robot-motion tools such as `navigate`, `follow_route`, `return_home`, and `stop` are marked critical. They should produce a dry-run/explain-plan, then require operator approval and audit evidence before execution.

Set `LIMA_MCP_URL` or `LIMA_DAEMON_URL` to mark live LIMA bridge tools as configured. If neither is set, Robo OS still exposes the replay/simulation manifests as demo-ready so the control plane remains testable without hardware.

The universal run timeline is:

1. User request
2. Parsed intent and context pack
3. Tool manifests matched
4. Policy tags and risk evaluated
5. Dry run or explain plan
6. Operator approval when required
7. Execution
8. Audit evidence and run summary

### Round Table

Launch a multi-agent autonomous meeting room. Features:
- Fresh meeting instance each launch
- Chair-led autonomous mode: framing → specialist perspectives → synthesis → recommendation
- Owner can interrupt at any time
- **Auto-fill Stack** button seats all four stack models instantly
- Meetings manager shows ongoing meetings with end/delete controls

### Company Operations Dashboard

Below the office floor:
- All Guardian Tasks across every room with live status dots
- Active meeting rooms list
- **Meet** button per task — opens a pre-seeded project meeting room
- **New Project** button — launches a named meeting room with stack bots auto-seated

### Task-Linked Project Meetings

Hitting **Meet** on a Guardian Task creates a dedicated room with:
- Task context pre-seeded (name, tool, schedule, last status)
- Stack bots auto-seated
- Project notes artifact ready
- Re-entering the same task re-opens the same room

### Meeting Room Tasks Tab

Every meeting room has a **Tasks** sidebar tab showing Guardian Tasks registered in that room with live status, last run time, and a one-click Run trigger.

---

## Task Guardian (Scheduled Autonomy)

Task Guardian runs tools on a schedule and posts results back into the room.

### Creating a scheduled job

From chat: *"Every morning at 8am, run my morning briefing"*
Or from the **Controls → Task Guardian** panel.

Supported schedule strings are `every:<seconds>`, `daily:<HH:MM>` in UTC, and `at:<ISO-8601 UTC datetime>` for one-shot runs. For a complete demo pack, see [Sparkbot Jarvis Demo Kit](./jarvis-demo-kit.md).

### Scheduled tools (suggested)

- `morning_briefing` — daily digest: weather, stocks, Gmail, calendar, news, reminders
- `send_alert` — push a notification to Telegram/Discord from any scheduled job
- `gmail_fetch_inbox` — hourly inbox check; pair with `send_alert` to push urgent emails to phone
- `calendar_list_events` — daily calendar preview
- `stock_quote` — daily market prices for your watchlist
- `list_tasks` — open-task digest
- `news_headlines` — news headlines
- `github_get_ci_status` — PR/CI review
- `time_report` — weekly time tracking summary

### Write-action scheduling (opt-in)

`gmail_send`, `slack_send_message`, and `calendar_create_event` can run on a schedule. Pre-authorized via the confirmation modal during job setup.

```env
SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true
```

### Configuration
```env
SPARKBOT_TASK_GUARDIAN_ENABLED=true
SPARKBOT_TASK_GUARDIAN_POLL_SECONDS=60
SPARKBOT_TASK_GUARDIAN_MAX_OUTPUT=2000
SPARKBOT_GUARDIAN_DATA_DIR=./data/guardian
```

### Verifier Guardian

Each scheduled run is evaluated before commit. Bounded retries with escalation instead of silent loops.

### Self-Improvement Proposals

Sparkbot can record governed improvement proposals when it notices repeated misses, uncertain behavior, stale docs, missing tools, or safer workflow ideas.

| Tool | Description |
|------|-------------|
| `guardian_propose_improvement` | Records a proposal with evidence, suggested change, risk, and approval-required status |
| `guardian_list_improvements` | Lists pending self-improvement proposals for the room |

Proposals are durable and mirrored into Guardian Spine as awaiting approval. Sparkbot must wait for explicit operator approval before applying code, config, docs, scheduled-job, or external write changes.

### Policy Simulator

Use `guardian_simulate_policy` to test a proposed tool call before enabling an automation. The simulator returns the tool classification, current or requested Computer Control/operator context, and the resulting action: `allow`, `confirm`, `deny`, `privileged`, or `privileged_reveal`.

Example:

```text
Use guardian_simulate_policy for gmail_send with to=alex@example.com and subject=Status update.
```

The simulator is read-only. It does not grant access, create an approval, send data, mutate files, or execute the requested tool.

---

## Guardian Stack (Security)

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

### Controls

| Control | Behavior |
|---------|---------|
| **Policy layer** | Every tool classified read / write / execute / admin; unknown tools denied by default |
| **Policy simulator** | `guardian_simulate_policy` previews policy outcomes without executing the target tool |
| **Write-tool gate** | LLM cannot email/Slack/GitHub/Notion/Confluence/Calendar/Drive autonomously unless Computer Control is on or the operator PIN has opened break-glass |
| **Computer Control** | Room-level always-on control for shell, terminal, browser writes, service actions, and comms sends; when off, these actions require the 6-digit operator PIN |
| **Approval inbox** | Confirmation-gated actions are persisted and can be approved/denied from the dashboard, Telegram, GitHub, and comms bridges |
| **Self-improvement gate** | Sparkbot can propose its own improvements, but applying code/config/docs/workflow changes requires explicit approval |
| **Truth/confidence rule** | Statements under 90% confidence must say what could be wrong and what information or verification is missing |
| **Executive journal** | High-risk actions written to a decision log before and after execution |
| **Audit trail** | Every tool call logged (allow/confirm/deny) with redacted args and timestamps |
| **Audit redaction** | Secret-pattern keys and token-format values stripped at write time |
| **Session tokens** | HttpOnly `Secure SameSite=Strict` cookie — never exposed to JavaScript |
| **Response headers** | HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy, Referrer-Policy |
| **Rate limiting** | Passphrase login: 10 attempts / 15 min per IP |
| **Room authz** | All message/upload/audit endpoints gated by membership; non-members get 403 |
| **Dep scanning** | `pip-audit` + `npm audit` on every push and weekly via GitHub Actions |
| **Secret scanning** | `gitleaks` pre-commit hook + CI gate |

### Break-Glass

PIN-gated privileged mode for operator workflows.

1. Set the 6-digit operator PIN once in Sparkbot Controls
2. Type `/breakglass` in chat
3. Enter your operator PIN when prompted
4. Sparkbot resumes the waiting privileged action
5. Type `/breakglass close` to end the session

All sessions are logged.

### Guardian Vault

Encrypted secret storage. Break-glass activation required before writing secrets. Accessible from the `/spine` Security tab.

### Operator Access

```env
SPARKBOT_OPERATOR_USERNAMES=your-username   # blank = any authenticated user is operator
SPARKBOT_OPERATOR_PIN_HASH=...              # optional; Controls can create/change the local PIN hash
SPARKBOT_VAULT_KEY=...                      # generate: see .env.example
```

**Open mode (default):** any authenticated human user is a guardian operator. Suitable for single-user installs.

### Memory Guardian
```env
SPARKBOT_MEMORY_GUARDIAN_ENABLED=true
SPARKBOT_MEMORY_GUARDIAN_DATA_DIR=./data/memory_guardian
SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS=1200
SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT=6
SPARKBOT_MEMORY_GUARDIAN_RETRIEVER=fts             # fts | hybrid (default fts)
SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS=false   # set true to enable hybrid embedding rerank
```

Guardian Memory uses a Sparkbot-level retriever interface. The default implementation is
a BM25 shim over SQLite FTS5, so fresh installs do not write embedding indexes. Optional
hybrid retrieval combines BM25 candidates with a hashing-trick cosine rerank when
`SPARKBOT_MEMORY_GUARDIAN_ENABLE_EMBEDDINGS=true`. The embedding index ships in-process:
no external service or model downloads.

Every memory write is tagged with provenance (`source`, e.g. `fact.user_authored`,
`tool.gmail_search`, `chat.user`), confidence, verification state, and whether redaction
was applied. Durable fact promotion calls `verify_fact()` first; low-confidence or
uncertain facts create `pending_approvals` records instead of entering the long-term KB.

Task Guardian also runs a nightly memory verification/evaluation pass. It verifies recent
memory events, records promotion and pending-approval stats, evaluates BM25 vs hybrid
retrieval with `retrieval_eval.py`, and exports the five digest metrics:
`memory_hit_rate`, `recall_precision@5`, `avg_retrieval_latency`,
`guardian_job_success_rate`, and `pending_approvals_rate`. Operators can read the same
data from `/api/v1/chat/guardian/metrics`.

Built-in memory tools (read-only by default; whitelisted for Task Guardian scheduling):

| Tool | Purpose |
|------|---------|
| `memory_recall` | BM25 recall by default, optional hybrid recall when embeddings are enabled; returns ranked items with provenance + score |
| `memory_retrieval_stats` | In-process telemetry: writes, recalls, hit rate, precision@5, latency, retriever mode, Guardian job success, pending approval rate, embed index size |
| `memory_reindex` | Rebuild FTS + embedding indexes from the on-disk ledger (idempotent; safe to schedule nightly) |

### Executive Guardian + Task Guardian
```env
SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED=true
SPARKBOT_TASK_GUARDIAN_ENABLED=true
SPARKBOT_IMPROVEMENT_LOOP_ENABLED=true
SPARKBOT_IMPROVEMENT_DATA_DIR=./data/improvement_loop
```

---

## Communication Bridges

### Telegram
```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_POLL_ENABLED=true
TELEGRAM_ALLOWED_CHAT_IDS=          # blank = all private chats allowed
TELEGRAM_REQUIRE_PRIVATE_CHAT=true
TELEGRAM_POLL_TIMEOUT_SECONDS=45
TELEGRAM_POLL_RETRY_SECONDS=5
```
- Long-poll bridge — no webhook server needed
- Each private Telegram chat maps to a dedicated Sparkbot room
- `/approve` or `/deny` resolves pending tool confirmations
- Reminders and Task Guardian results fan out to linked Telegram chats
- Telegram API errors redact bot tokens from logs and user-facing failure text. If a token has already appeared in service logs, rotate it in @BotFather and paste the replacement in the Comms panel.

### Discord
```env
DISCORD_BOT_TOKEN=
DISCORD_ENABLED=false
DISCORD_DM_ONLY=false               # true = DMs only
DISCORD_GUILD_IDS=                  # comma-separated snowflakes (optional)
```
Setup:
1. Discord Developer Portal → New App → Bot → copy token
2. Bot Settings → **Message Content Intent** must be enabled
3. OAuth2 → URL Generator → scopes: `bot` + permissions: Send Messages, Read Message History
4. Set `DISCORD_ENABLED=true`

### WhatsApp (Meta Cloud API)
```env
WHATSAPP_ENABLED=false
WHATSAPP_PHONE_ID=
WHATSAPP_TOKEN=
WHATSAPP_VERIFY_TOKEN=sparkbot-wa-verify
WHATSAPP_APP_ID=
WHATSAPP_APP_SECRET=
WHATSAPP_ALLOWED_PHONES=
PUBLIC_URL=https://your-domain.com
```
Setup:
1. Meta Developer Portal → New App → WhatsApp → Add Phone Number
2. System User → permanent token with `whatsapp_business_messaging` scope
3. Webhook URL: `https://yourdomain.com/whatsapp`
4. Subscribe to: `messages`

Note: The registered phone cannot be simultaneously used in personal WhatsApp or WhatsApp Business App.

### GitHub Bridge
```env
GITHUB_BRIDGE_ENABLED=false
GITHUB_TOKEN=
GITHUB_WEBHOOK_SECRET=
GITHUB_BOT_LOGIN=sparkbot
GITHUB_DEFAULT_REPO=owner/repo
GITHUB_ALLOWED_REPOS=owner/repo,owner/another-repo
```
Setup:
1. GitHub repo → Settings → Webhooks → Add webhook
2. Payload URL: `https://yourdomain.com/api/v1/chat/github/events`
3. Content type: `application/json`; Events: `Issue comments` + `Pull request review comments`
4. Invoke with `/sparkbot your request` or `@sparkbot your request` in a comment

---

## Voice (Whisper + TTS)

Requires `OPENAI_API_KEY`.

```env
SPARKBOT_TTS_VOICE=alloy    # alloy | echo | fable | onyx | nova | shimmer
SPARKBOT_TTS_MODEL=tts-1    # tts-1 (fast) or tts-1-hd (higher quality)
```

### Input bar controls

| Button | State | Action |
|--------|-------|--------|
| 🎙 Mic | idle | Start recording |
| 🔴 `Ns` | recording | Stop + send to Whisper |
| 🔇 VolumeX | voice mode off | Toggle on — replies spoken aloud |
| 🔊 Volume2 | voice mode on | Toggle off |

Voice mode preference is persisted in `localStorage`.

### Voice quick-capture

- **Voice mode OFF** — mic transcribes and pastes to input (no auto-send); edit before sending
- **Voice mode ON** — full voice-message flow: mic → Whisper → LLM → TTS readback

### SSE protocol (superset of `/messages/stream`)

```
data: {"type": "transcription",  "text": "what's the weather in Tokyo?"}
data: {"type": "human_message",  "message_id": "..."}
data: {"type": "token",          "token": "..."}
data: {"type": "done",           "message_id": "..."}
```

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat/rooms/{id}/voice` | Audio → Whisper → SSE stream (multipart, `audio` field ≤ 5 MB) |
| `POST` | `/api/v1/chat/voice/tts` | Text → `audio/mpeg` stream |

---

## Knowledge Base (RAG)

Zero extra dependencies. Uses SQLite FTS5 with BM25 full-text ranking.

| Tool | Description |
|------|-------------|
| `ingest_document(text, name, source?)` | Store text or auto-fetch a URL and index it |
| `search_knowledge(query)` | Retrieve relevant chunks with full-text ranking |
| `list_knowledge()` | List all indexed documents |
| `delete_knowledge(name)` | Remove a document from the index |

**Example:** *"Ingest this URL and remember it: https://docs.example.com/api"*

---

## Meeting Mode & Roundtable

### Meeting Mode

Activated with `/meeting start`. While active, prefix messages with:

| Prefix | Captured as |
|--------|------------|
| `note:` | Meeting note |
| `decided:` | Decision |
| `action:` | Action item |

`/meeting stop` exports the full notes as a dated `.md` file.
`/meeting notes` shows captured notes mid-meeting.

### Roundtable

Launches a fresh multi-agent meeting room. Autonomous chair-led flow:

1. Framing — chair sets the agenda
2. Specialist perspectives — each seated agent contributes
3. Synthesis — chair consolidates
4. Optional refinement round
5. Final recommendation or action plan

The meeting stops when: solved, blocked, looping, ready for approval, or needs owner input.

The Roundtable UI includes a meetings manager to open, end, or delete ongoing meetings.

---

## Persistent Memory

Sparkbot proactively calls `remember_fact` when you reveal your name, role, timezone, preferences, or ongoing projects.

- `/memory` — list stored facts (with short IDs)
- `/memory clear` — wipe all stored facts
- API: `GET /api/v1/chat/memory/`, `DELETE /api/v1/chat/memory/{id}`, `DELETE /api/v1/chat/memory/`

Memory Guardian layer retains redacted message/tool context and injects relevant packed memory into every prompt.

Memory sessions:
- `user:{user_id}` — durable user profile
- `room:{room_id}:user:{user_id}` — room-context memory

---

## Environment Variables — Full Reference

For normal Docker/server installs, run the guided setup instead of editing env
files by hand:

```bash
bash scripts/sparkbot-start.sh --local   # personal machine, binds to 127.0.0.1
bash scripts/sparkbot-start.sh --server  # VPS/cloud server, binds web UI to 0.0.0.0
```

The setup wizard creates `.env.local`, prompts for provider keys or local
Ollama, preserves existing values, and supports Docker Compose v2
(`docker compose`) plus legacy Docker Compose v1.29.x (`docker-compose`).
The launcher starts Compose detached by default, exports and mirrors only the
non-secret frontend bind/port values into root `.env` for Compose interpolation,
auto-selects a free frontend port when 3000 is busy, and prints the real URL.
Server mode disables local auto-login and prompts for a private
`SPARKBOT_PASSPHRASE` when needed; defaults, blanks, placeholders, and short
values are rejected, the accepted passphrase is saved to `.env.local`, and the
launcher does not print it. Hidden passphrase input is used only when the
terminal can handle it; SSH sessions fall back to visible passphrase input with
a warning so setup can continue.
Provider key prompts are visible by default so SSH paste works reliably; the
wizard warns before visible key entry and does not print stored secrets itself.
Advanced operators can still edit env files or run Compose directly.

SSH setup helpers:

```bash
bash scripts/sparkbot-start.sh --install-docker-plugins
bash scripts/sparkbot-start.sh --server --hide-input  # optional hidden provider-key entry
export OPENAI_API_KEY="sk-..."
export SPARKBOT_PASSPHRASE="long-private-passphrase"
bash scripts/sparkbot-start.sh --server --from-env  # import exported provider keys
bash scripts/sparkbot-start.sh --server --show-passphrase-input
bash scripts/sparkbot-start.sh --server --dry-run-setup
bash scripts/sparkbot-start.sh --server --openai-key "sk-..." --passphrase "long-private-passphrase"
SPARKBOT_FRONTEND_PORT=3001 bash scripts/sparkbot-start.sh --server
```

### Core / Required

```env
PROJECT_NAME=Sparkbot
ENVIRONMENT=production              # local | production
SECRET_KEY=<random 32+ chars>
FIRST_SUPERUSER_PASSWORD=<strong>
SPARKBOT_PASSPHRASE=<passphrase>
FRONTEND_HOST=https://chat.example.com
BACKEND_CORS_ORIGINS=https://chat.example.com
```

### Database

```env
DATABASE_TYPE=sqlite                # sqlite | postgresql
SPARKBOT_DATA_DIR=./data            # for sqlite
# PostgreSQL only:
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_USER=sparkbot
POSTGRES_PASSWORD=...
POSTGRES_DB=sparkbot
```

### LLM Providers

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=gsk_...
MINIMAX_API_KEY=...
OPENROUTER_API_KEY=sk-or-...
OLLAMA_BASE_URL=http://localhost:11434
SPARKBOT_MODEL=gpt-4o-mini
SPARKBOT_BACKUP_MODEL=claude-sonnet-4-5
SPARKBOT_BACKUP_MODEL_2=gemini/gemini-2.0-flash
SPARKBOT_HEAVY_MODEL=gpt-4o
```

### Features (On/Off)

```env
SPARKBOT_SHELL_DISABLE=false
SPARKBOT_CODE_DISABLE=false
SPARKBOT_BROWSER_HEADLESS=false         # desktop app: show browser window
SPARKBOT_DM_EXECUTION_DEFAULT=true      # desktop app: enable execution in DM room
WORKSTATION_LIVE_TERMINAL_ENABLED=true
V1_LOCAL_MODE=true                      # desktop app mode
```

### Guardian Security

```env
SPARKBOT_OPERATOR_USERNAMES=            # blank = open mode (any user is operator)
SPARKBOT_OPERATOR_PIN_HASH=             # optional; Controls can create/change the local PIN hash
SPARKBOT_VAULT_KEY=                     # generate: see .env.example
SPARKBOT_GUARDIAN_POLICY_ENABLED=true   # true = Computer Control/PIN policy enforced
SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED=true
SPARKBOT_GUARDIAN_DATA_DIR=./data/guardian
```

### Memory Guardian

```env
SPARKBOT_MEMORY_GUARDIAN_ENABLED=true
SPARKBOT_MEMORY_GUARDIAN_DATA_DIR=./data/memory_guardian
SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS=1200
SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT=6
```

### Task Guardian

```env
SPARKBOT_TASK_GUARDIAN_ENABLED=true
SPARKBOT_TASK_GUARDIAN_POLL_SECONDS=60
SPARKBOT_TASK_GUARDIAN_MAX_OUTPUT=2000
SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=false   # allow scheduled email/Slack/calendar writes
```

### Token Guardian

```env
SPARKBOT_TOKEN_GUARDIAN_SHADOW_ENABLED=true
```

### Voice

```env
SPARKBOT_TTS_VOICE=alloy
SPARKBOT_TTS_MODEL=tts-1
```

### Skills

```env
SPARKBOT_SKILLS_DIR=skills
```

### System Prompt

```env
SPARKBOT_SYSTEM_PROMPT_FILE=./prompts/system.md   # override default system prompt
```

### Server Operations

```env
SPARKBOT_ALLOWED_SERVICES=sparkbot-v2
SPARKBOT_SERVICE_USE_SUDO=false
SPARKBOT_SERVER_COMMAND_TIMEOUT_SECONDS=20
SPARKBOT_SSH_ALLOWED_HOSTS=
SPARKBOT_SSH_ALLOWED_SERVICES=
SPARKBOT_SSH_CONNECT_TIMEOUT_SECONDS=10
SPARKBOT_SSH_COMMAND_TIMEOUT_SECONDS=30
```

### Web Search

```env
BRAVE_SEARCH_API_KEY=
SERPAPI_KEY=
SEARCH_CACHE_TTL_SECONDS=300
```

### Google Workspace

```env
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_GMAIL_USER=me
GOOGLE_DRIVE_SHARED_DRIVE_ID=
```

### IMAP / SMTP

```env
IMAP_HOST=
IMAP_PORT=993
IMAP_USER=
IMAP_PASSWORD=
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
```

### CalDAV

```env
CALDAV_URL=
CALDAV_USERNAME=
CALDAV_PASSWORD=
```

### GitHub

```env
GITHUB_TOKEN=
GITHUB_DEFAULT_REPO=owner/repo
GITHUB_BRIDGE_ENABLED=false
GITHUB_WEBHOOK_SECRET=
GITHUB_BOT_LOGIN=sparkbot
GITHUB_ALLOWED_REPOS=
```

### Slack

```env
SLACK_BOT_TOKEN=xoxb-...
```

### Notion

```env
NOTION_API_KEY=secret_...
```

### Confluence

```env
CONFLUENCE_URL=
CONFLUENCE_USER=
CONFLUENCE_API_TOKEN=
```

### Telegram

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_POLL_ENABLED=true
TELEGRAM_ALLOWED_CHAT_IDS=
TELEGRAM_REQUIRE_PRIVATE_CHAT=true
TELEGRAM_POLL_TIMEOUT_SECONDS=45
TELEGRAM_POLL_RETRY_SECONDS=5
```

### Discord

```env
DISCORD_BOT_TOKEN=
DISCORD_ENABLED=false
DISCORD_DM_ONLY=false
DISCORD_GUILD_IDS=
```

### WhatsApp

```env
WHATSAPP_ENABLED=false
WHATSAPP_PHONE_ID=
WHATSAPP_TOKEN=
WHATSAPP_VERIFY_TOKEN=sparkbot-wa-verify
WHATSAPP_APP_ID=
WHATSAPP_APP_SECRET=
WHATSAPP_ALLOWED_PHONES=
PUBLIC_URL=
```

---

## API Endpoints

### Auth & Users

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat/users/bootstrap` | Auto-create user + DM room, return room_id |
| `POST` | `/api/v1/chat/users/login` | Login with passphrase → sets HttpOnly `chat_token` cookie |
| `DELETE` | `/api/v1/chat/users/session` | Logout → clears session cookie |

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/chat/rooms/{id}/messages` | Room message history |
| `POST` | `/api/v1/chat/rooms/{id}/messages/stream` | Send message, receive SSE stream |
| `PATCH` | `/api/v1/chat/messages/{room_id}/message/{message_id}` | Edit a message |
| `POST` | `/api/v1/chat/rooms/{id}/upload` | Upload file, receive SSE stream |
| `POST` | `/api/v1/chat/rooms/{id}/voice` | Voice recording → Whisper → SSE stream |
| `POST` | `/api/v1/chat/rooms/{id}/voice/transcribe` | Voice → transcript only (no LLM) |
| `POST` | `/api/v1/chat/voice/tts` | Text → `audio/mpeg` TTS stream |
| `GET` | `/api/v1/chat/messages/{id}/search?q=` | Full-text message search |

### Models & Memory

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/chat/models` | List available LLM models |
| `POST` | `/api/v1/chat/model` | Set model preference `{"model": "gpt-4o"}` |
| `GET` | `/api/v1/chat/memory/` | List stored user memories |
| `DELETE` | `/api/v1/chat/memory/{id}` | Delete a specific memory |
| `DELETE` | `/api/v1/chat/memory/` | Clear all memories |

### Skills & Audit

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/chat/skills` | List loaded skill plugins (name, description, policy flags) |
| `GET` | `/api/v1/chat/mcp/registry` | Unified Sparkbot + LIMA MCP registry: manifests, policy metadata, approval posture, health, and run timeline |
| `POST` | `/api/v1/chat/mcp/explain-plan` | No-execution dry-run plan for a registry manifest using Guardian policy simulation |
| `GET` | `/api/v1/chat/mcp/runs` | Recent durable MCP explain-plan/run records for the current user |
| `GET` | `/api/v1/chat/mcp/runs/{run_id}` | One MCP run record with persisted explain-plan payload |
| `POST` | `/api/v1/chat/mcp/runs/{run_id}/request-approval` | Move a planned or unapproved ready MCP run to awaiting approval without executing it |
| `POST` | `/api/v1/chat/mcp/runs/{run_id}/approve` | Guardian-operator approval that marks an awaiting MCP run ready for future runner handoff without executing it |
| `POST` | `/api/v1/chat/mcp/runs/{run_id}/deny` | Guardian-operator denial that blocks an awaiting MCP run with an audit reason |
| `GET` | `/api/v1/chat/audit` | Recent tool audit log (room-scoped) |
| `GET` | `/api/v1/utils/health-check/` | Health check → `true` |

### Governance Dashboard

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/chat/dashboard/summary` | Dashboard summary: rooms, tasks, approvals, jobs, meetings, inbox, token routing |
| `GET` | `/api/v1/chat/dashboard/runs/timeline` | Room-scoped run timeline with policy/tool events and audit hashes |
| `GET` | `/api/v1/chat/dashboard/connectors/health` | Connector setup state, read/write scopes, setup-test status, audit metadata |
| `GET` | `/api/v1/chat/dashboard/workflows/templates` | Workflow-builder templates: trigger, condition, tool/agent, approval, notification, audit |
| `GET` | `/api/v1/chat/dashboard/evals/agent-behavior` | Deterministic governance eval harness cases |
| `POST` | `/api/v1/chat/dashboard/approvals/{confirm_id}/approve` | Approve and resume a pending tool action |
| `POST` | `/api/v1/chat/dashboard/approvals/{confirm_id}/deny` | Deny and discard a pending tool action |

### Agents

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/chat/agents` | List agents with identity, risk, scopes, allowed tools, and kill-switch state |
| `POST` | `/api/v1/chat/agents` | Create a custom agent with identity metadata |
| `DELETE` | `/api/v1/chat/agents/{name}` | Delete a custom agent |
| `POST` | `/agents/{name}/invite-route` | Seat an external model with its own API key |

Interactive API docs: `http://localhost:8000/docs`

---

## Guardian Spine — Operator Reference

Guardian Spine is Sparkbot's background operating subsystem — the canonical cross-guardian catalog and history layer. It is not exposed in chat; it runs behind the scenes.

### Room inspection routes

| Route | Description |
|-------|-------------|
| `GET /api/v1/chat/rooms/{id}/spine/overview` | Room overview |
| `GET /api/v1/chat/rooms/{id}/spine/tasks` | All tasks in room |
| `GET /api/v1/chat/rooms/{id}/spine/tasks/orphaned` | Orphaned tasks |
| `GET /api/v1/chat/rooms/{id}/spine/tasks/{task_id}/lineage` | Task lineage |
| `GET /api/v1/chat/rooms/{id}/spine/tasks/{task_id}/approvals` | Task approvals |
| `GET /api/v1/chat/rooms/{id}/spine/events` | Room events |
| `GET /api/v1/chat/rooms/{id}/spine/handoffs` | Handoff events |
| `GET /api/v1/chat/rooms/{id}/spine/projects` | Projects in room |
| `GET /api/v1/chat/rooms/{id}/spine/task-master/overview` | Task Master overview |

### Operator/global inspection routes

| Route | Description |
|-------|-------------|
| `GET /api/v1/chat/spine/operator/events/recent` | Recent events across all rooms |
| `GET /api/v1/chat/spine/operator/queues/open` | Open task queue |
| `GET /api/v1/chat/spine/operator/queues/blocked` | Blocked tasks |
| `GET /api/v1/chat/spine/operator/queues/approval-waiting` | Awaiting approval |
| `GET /api/v1/chat/spine/operator/queues/stale` | Stale tasks |
| `GET /api/v1/chat/spine/operator/queues/orphaned` | Orphaned tasks |
| `GET /api/v1/chat/spine/operator/projects` | All projects |
| `GET /api/v1/chat/spine/operator/projects/workload` | Project workload summary |
| `GET /api/v1/chat/spine/operator/task-master/overview` | Global Task Master view |
| `GET /api/v1/chat/spine/operator/signals/high-priority-blocked` | High-priority blocked |
| `GET /api/v1/chat/spine/operator/signals/fragmentation` | Fragmentation indicators |

---

## Process Watcher & Model Throttling

Sparkbot automatically monitors and throttles local model processes (Ollama, LM Studio, llama.cpp) to prevent them from saturating the CPU and blocking UI responsiveness.

### How it works

A background asyncio task (`backend/app/services/process_watcher.py`) polls every 30 seconds. When a watched process exceeds the CPU threshold, its OS priority is lowered automatically. When it drops back below the restore threshold, priority is restored.

- **Windows:** uses Win32 `SetPriorityClass` to set `BELOW_NORMAL_PRIORITY_CLASS`
- **Linux/macOS:** uses `os.nice(10)`
- No processes are killed or paused — only priority is adjusted

### Configuration

```env
SPARKBOT_PROCESS_WATCHER_ENABLED=true   # auto-enabled in desktop (V1_LOCAL_MODE)
SPARKBOT_PROCESS_WATCHER_INTERVAL=30    # poll interval in seconds
SPARKBOT_CPU_THRESHOLD=70               # % CPU above which priority is lowered
SPARKBOT_CPU_RESTORE_THRESHOLD=40       # % CPU below which priority is restored
SPARKBOT_WATCHED_PROCESSES=ollama,ollama_llama_server,lmstudio,llama-server,llama.cpp
```

### Status endpoint

```
GET /api/v1/chat/system/watcher
```

Response:
```json
{
  "enabled": true,
  "poll_interval_seconds": 30,
  "cpu_threshold_pct": 70.0,
  "restore_threshold_pct": 40.0,
  "watched_process_names": ["llama-server", "lmstudio", "ollama", "ollama_llama_server"],
  "currently_throttled": [
    {"pid": 4821, "name": "ollama.exe"}
  ]
}
```

### Manual process management (PowerShell)

```powershell
# Check if Ollama is running and its CPU usage
Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Select-Object Id, CPU, WorkingSet

# Manually lower priority
$proc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($proc) { $proc.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal }

# Stop Ollama entirely
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue

# Limit Ollama thread count before starting (set in system/user env)
[System.Environment]::SetEnvironmentVariable("OLLAMA_NUM_THREAD", "4", "User")
```

### Manual process management (bash)

```bash
# Check Ollama CPU usage
ps aux | grep ollama | grep -v grep

# Lower priority (nice = 10, range -20 to 19, higher = lower priority)
OLLAMA_PID=$(pgrep ollama); [ -n "$OLLAMA_PID" ] && renice 10 $OLLAMA_PID

# Stop Ollama
pkill -f ollama

# Linux: limit Ollama to 4 CPU cores via cgroup
systemctl set-property ollama.service CPUQuota=400%  # 400% = 4 cores
```

---

## Model Latency Tracking

Sparkbot records the wall-clock response time for every successful LLM call per model. Latency is surfaced in the `/models` endpoint and a dedicated `/models/latency` endpoint.

### How it works

`_acompletion_with_fallback` in `llm.py` wraps every `litellm.acompletion` call with `time.perf_counter()`. The last 10 samples per model are kept in memory (resets on restart). Stats are computed on-demand.

### Endpoints

**All models with latency stats:**
```
GET /api/v1/chat/models
```

Latency added to each model entry:
```json
{
  "id": "gpt-4o-mini",
  "description": "GPT-4o Mini — fast, cost-effective",
  "active": true,
  "configured": true,
  "provider": "openai",
  "latency": {
    "samples": 10,
    "avg_s": 1.43,
    "min_s": 0.91,
    "max_s": 3.12,
    "last_s": 1.21
  }
}
```

`null` values mean no calls have been made to that model this session.

**Dedicated latency view (models with data only):**
```
GET /api/v1/chat/models/latency
```

```json
{
  "latency": {
    "gpt-4o-mini": {"samples": 10, "avg_s": 1.43, "min_s": 0.91, "max_s": 3.12, "last_s": 1.21},
    "claude-sonnet-4-5": {"samples": 4, "avg_s": 2.11, "min_s": 1.87, "max_s": 2.54, "last_s": 1.99}
  }
}
```

### Latency also appears in the backend log

Every successful LLM call logs:
```
INFO LLM route applied: ... applied_model=gpt-4o-mini latency_s=1.43
```

Use this to correlate slow responses with specific models or times of day:
```powershell
# Windows — find slowest LLM calls today
Select-String -Path "$env:LOCALAPPDATA\Sparkbot Local\sparkbot-backend.log" -Pattern "latency_s" |
  Where-Object { $_ -match "latency_s=([5-9]\d|[1-9]\d{2})" }
```
```bash
# Linux — calls over 5 seconds
grep "latency_s" ~/.sparkbot/sparkbot-backend.log | awk -F'latency_s=' '{print $2}' | awk '$1 > 5'
```

---

## Skill Sandboxing

Every skill execution is wrapped by `backend/app/services/skill_executor.py` with timeout and memory guardrails.

### Timeout enforcement

All skill calls use `asyncio.wait_for()` with a configurable wall-clock limit. Skills that hang (e.g., waiting on a slow network call) are cancelled after the timeout and return a clean error message to the LLM.

```env
SPARKBOT_SKILL_TIMEOUT_SECONDS=60    # default timeout for all skills
```

Individual skills can override this by setting `TIMEOUT = 30` at module level.

**Timeout error returned to LLM:**
```
Skill [my_tool] timed out after 62.1s (limit: 60s). The operation may still
be running in the background. To increase the limit set SPARKBOT_SKILL_TIMEOUT_SECONDS.
```

### Memory monitoring

```env
SPARKBOT_SKILL_MAX_MEMORY_MB=0       # 0 = disabled (default)
                                      # e.g. 2048 = refuse to start skill if process > 2 GB
```

When enabled:
- **Pre-execution:** if process RSS already exceeds the limit, the skill is refused before running
- **Post-execution:** if RSS grew past the limit during execution, a warning is logged

### Error reporting

Skills no longer surface raw Python tracebacks to the LLM. All errors — timeout, memory, uncaught exception — are returned as structured strings the LLM can report back to the user.

For skill authoring guidance, see **[docs/skill-author-guide.md](./skill-author-guide.md)**.

---

## API Usage Examples

### Authentication

All endpoints require an HttpOnly session cookie. Obtain it at login:

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/v1/chat/users/login \
  -H "Content-Type: application/json" \
  -d '{"passphrase": "sparkbot-local"}'
```

Subsequent requests use the cookie automatically:
```bash
curl -b cookies.txt http://localhost:8000/api/v1/utils/health-check/
# → true
```

### Send a message and stream the response

```bash
# Replace ROOM_ID with your room ID (get it from /users/bootstrap)
ROOM_ID="your-room-id"

curl -b cookies.txt -N \
  -X POST "http://localhost:8000/api/v1/chat/rooms/$ROOM_ID/messages/stream" \
  -H "Content-Type: application/json" \
  -d '{"content": "What is the weather in New York?"}'
```

SSE response format:
```
data: {"type": "token", "token": "The"}
data: {"type": "token", "token": " weather"}
data: {"type": "token", "token": " in"}
...
data: {"type": "done", "message_id": "abc123"}
```

### Bootstrap a new user and get their room ID

```bash
curl -c cookies.txt -X POST http://localhost:8000/api/v1/chat/users/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"passphrase": "sparkbot-local"}'
# → {"room_id": "uuid-here", "user_id": "uuid-here"}
```

### Switch the active model

```bash
curl -b cookies.txt -X POST http://localhost:8000/api/v1/chat/model \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-5"}'
```

### Run code via shell_run tool (triggering from API)

```bash
curl -b cookies.txt -N \
  -X POST "http://localhost:8000/api/v1/chat/rooms/$ROOM_ID/messages/stream" \
  -H "Content-Type: application/json" \
  -d '{"content": "Run: echo Hello from the API"}'
```

### JavaScript / TypeScript (fetch)

```typescript
// Login
const loginRes = await fetch('/api/v1/chat/users/login', {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ passphrase: 'sparkbot-local' }),
});

// Stream a message
const res = await fetch(`/api/v1/chat/rooms/${roomId}/messages/stream`, {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ content: 'What can you do?' }),
});

const reader = res.body!.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  for (const line of text.split('\n')) {
    if (!line.startsWith('data: ')) continue;
    const event = JSON.parse(line.slice(6));
    if (event.type === 'token') process.stdout.write(event.token);
    if (event.type === 'done') console.log('\n[done]');
  }
}
```

### Check model latency

```bash
curl -b cookies.txt http://localhost:8000/api/v1/chat/models/latency | python -m json.tool
```

### Check process watcher status

```bash
curl -b cookies.txt http://localhost:8000/api/v1/chat/system/watcher | python -m json.tool
```

---

## Versioning & Compatibility

### Version scheme

| Component | Version | Location |
|-----------|---------|----------|
| Desktop app | `src-tauri/tauri.conf.json` → `version` |
| Download page | `docs/index.html` |
| Python backend | `backend/pyproject.toml` → `version` |
| Desktop release tag | `desktop-v{major}.{minor}.{patch}` |

Desktop release tags and app versions are aligned on the `1.6.x` release line.

For `v1.6.40`, the backend, frontend, Tauri shell, README, public download page, and release note are all advanced together so the installer, runtime self-inspection, and GitHub Pages downloader tell the same version story.

### How to upgrade safely

1. **Read the release notes** under `docs/release-notes/` for breaking changes
2. **Back up your `.env`** (contains API keys) before upgrading the desktop app
3. **Check skill POLICY dicts** after upgrading — see the known breaking change below
4. **Restart the backend** after any env var change

### Known breaking changes

**v1.2.5 — ToolPolicy signature change**

Skills written before v1.2.5 may use incorrect POLICY keys and will crash on load with:
```
TypeError: ToolPolicy.__init__() got an unexpected keyword argument 'category'
```

**Fix:** Replace `category` and `description` with the correct keys:
```python
# ❌ Old (broken)
POLICY = {
    "category": "read",
    "description": "My tool",
    "default_action": "allow",
    "high_risk": False,
}

# ✅ New (correct)
POLICY = {
    "scope": "read",
    "resource": "external",
    "default_action": "allow",
    "action_type": "data_read",
    "high_risk": False,
    "requires_execution_gate": False,
}
```

The CI skill test suite (`tests/test_skills.py`) catches this automatically on every push.

### Pinned dependency recommendations

For stable desktop builds, pin these key packages in `backend/pyproject.toml`:

```toml
"litellm>=1.0.0,<2.0.0"       # major version bump may change tool-call API
"playwright>=1.52.0"            # minor versions add browser support; safe to float
"psutil>=5.9.0"                 # stable API; safe to float
"pywinpty>=2.0.0"               # Windows PTY; major version may break terminal
"fastapi[standard]<1.0.0"       # pre-1.0 FastAPI; pin to avoid breaking changes
"pydantic>2.0"                  # Pydantic v2+ required; v1 is incompatible
```

### How to check your installed versions

```bash
cd backend
uv pip list | grep -E "litellm|playwright|psutil|fastapi|pydantic"
```

### Migration checklist (version upgrades)

- [ ] Back up `%APPDATA%\Sparkbot\.env` (desktop) or `.env` (server)
- [ ] Read `release-notes.md` for this version
- [ ] If skills exist outside `backend/skills/`: run `pytest tests/test_skills.py` against them
- [ ] After upgrade: verify health check responds: `curl .../api/v1/utils/health-check/`
- [ ] After upgrade: send a test message and confirm streaming works
- [ ] After upgrade: check `sparkbot-backend.log` for any `WARNING` or `ERROR` lines at startup

---

## Project File Map

```
sparkbot/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── main.py                    # Router assembly
│   │   │   └── routes/chat/
│   │   │       ├── llm.py                 # litellm routing, model registry, tool loop guards
│   │   │       ├── tools.py               # Tool definitions + executors
│   │   │       ├── rooms.py               # Room CRUD + streaming message endpoint
│   │   │       ├── messages.py            # Message CRUD + search
│   │   │       ├── memory.py              # User memory CRUD endpoints
│   │   │       ├── uploads.py             # File upload + vision SSE
│   │   │       ├── voice.py               # Whisper transcription + TTS endpoints
│   │   │       ├── model.py               # Model switching endpoints
│   │   │       ├── github.py              # GitHub webhook bridge
│   │   │       └── users.py               # Chat user management + bootstrap
│   │   ├── services/
│   │   │   ├── skills.py                  # Skill plugin auto-loader
│   │   │   ├── terminal_service.py        # Cross-platform PTY manager (ConPTY/PTY)
│   │   │   ├── telegram_bridge.py         # Telegram long-poll bridge
│   │   │   ├── discord_bridge.py          # Discord gateway bot bridge
│   │   │   ├── whatsapp_bridge.py         # WhatsApp Cloud API bridge (pywa)
│   │   │   ├── github_bridge.py           # GitHub webhook bridge service
│   │   │   └── guardian/                  # Policy, executive, memory, task guardian
│   │   ├── models.py                      # SQLModel DB models
│   │   ├── crud.py                        # DB helper functions
│   │   └── alembic/                       # DB migrations
│   ├── skills/                            # Drop .py skill files here — auto-loaded on restart
│   ├── prompts/system.md                  # Editable system prompt
│   ├── pyproject.toml                     # Python dependencies
│   └── desktop_launcher.py                # PyInstaller entry point for desktop app
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── SparkbotDmPage.tsx         # Main chat UI
│   │   │   └── WorkstationPage.tsx        # Workstation / office floor UI
│   │   ├── hooks/
│   │   │   └── useTerminalSession.ts      # Terminal WebSocket hook
│   │   ├── components/chat/
│   │   │   ├── MessageBubble.tsx          # Markdown + syntax highlight + copy button
│   │   │   └── ChatInput.tsx              # Input bar (mic, upload, voice mode)
│   │   └── lib/
│   │       └── apiBase.ts                 # apiFetch / apiWebSocketUrl (Tauri-safe)
│   └── dist/                             # Built frontend
├── src-tauri/
│   ├── tauri.conf.json                    # App name, version, window config
│   └── src/                              # Rust Tauri shell
├── sparkbot-backend.spec                  # PyInstaller bundle spec
├── docs/
│   ├── capabilities.md                    # This file — full feature reference
│   ├── index.html                         # Public download page
│   └── systemd-single-node.md            # Server deployment guide
├── deploy/systemd/                        # systemd service examples
├── scripts/
│   ├── sparkbot-setup.sh                 # First-run provider/model setup wizard
│   ├── sparkbot-start.sh                 # One-command Docker/server launcher
│   └── quickstart.sh                     # Compatibility wrapper for sparkbot-start.sh
└── .github/workflows/
    ├── desktop-release.yml               # Desktop installer CI (triggers on desktop-v* tags)
    └── build-installer.yml               # QA build (does not publish)
```
