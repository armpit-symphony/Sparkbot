# Sparkbot — Full Capabilities Reference

This document is the complete technical reference for every feature, tool, command, integration, and configuration option in Sparkbot. The [README](../README.md) covers getting started and daily use; this doc covers everything else.

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
10. [Task Guardian (Scheduled Autonomy)](#task-guardian-scheduled-autonomy)
11. [Guardian Stack (Security)](#guardian-stack-security)
12. [Communication Bridges](#communication-bridges)
13. [Voice (Whisper + TTS)](#voice-whisper--tts)
14. [Knowledge Base (RAG)](#knowledge-base-rag)
15. [Meeting Mode & Roundtable](#meeting-mode--roundtable)
16. [Persistent Memory](#persistent-memory)
17. [Environment Variables — Full Reference](#environment-variables--full-reference)
18. [API Endpoints](#api-endpoints)
19. [Guardian Spine — Operator Reference](#guardian-spine--operator-reference)
20. [Project File Map](#project-file-map)

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

Sparkbot can control the local machine it is running on. These capabilities are available in the desktop app and on any self-hosted server where the execution gate is enabled.

### Shell (`shell_run`)

- Runs any command in PowerShell (Windows) or bash (Linux/macOS)
- Working directory **persists across messages** — `cd` carries forward within a conversation
- Output capped: 16 KB stdout + 4 KB stderr
- Default timeout: 30 seconds (max 300 seconds)
- Disable with `SPARKBOT_SHELL_DISABLE=true`

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

| Skill file | Tool name | Description |
|-----------|-----------|-------------|
| `example_weather.py` | `get_weather` | Current weather via wttr.in (no API key) |
| `calendar_list_events.py` | `calendar_list_events` | List Google Calendar events |
| `calendar_create_event.py` | `calendar_create_event` | Create Google Calendar event (confirmation required) |
| `morning_briefing.py` | `morning_briefing` | Gmail + Calendar + reminders digest |
| `news_headlines.py` | `news_headlines` | HN top stories or BBC RSS (no API key) |
| `currency_convert.py` | `currency_convert` | Live FX rates via open.er-api.com (no API key) |
| `crypto_price.py` | `crypto_price` | BTC/ETH/SOL/… prices via CoinGecko (no API key) |
| `shell_run.py` | `shell_run` | Shell command execution (PowerShell/bash) |
| `knowledge_base.py` | `ingest_document`, `search_knowledge`, `list_knowledge`, `delete_knowledge` | BM25 full-text RAG |

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

Seat any model into a Workstation desk with its own Model ID and API Key. At meeting launch, requests route directly to that provider using your key — bypassing the default stack. Supports Claude, GPT, Gemini, and Ollama.

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

Custom agents via env var:
```env
SPARKBOT_AGENTS_JSON=[{"name":"devops","emoji":"🛠","description":"DevOps specialist","system_prompt":"You are..."}]
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

### Computer Control Panel

Three capability cards visible in the Workstation:
- **Shell** — run PowerShell/bash commands via chat
- **Terminal** — interactive terminal panel (click Connect to start session)
- **Browser** — open URLs, fill forms, click, save sessions

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

### Scheduled tools (suggested)

- `morning_briefing` — daily Gmail + Calendar + reminders digest
- `gmail_fetch_inbox` — hourly inbox check
- `calendar_list_events` — daily calendar preview
- `list_tasks` — open-task digest
- `list_reminders` — pending reminders
- `news_headlines` — news headlines
- `github_get_ci_status` — PR/CI review

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
| **Write-tool gate** | LLM cannot email/Slack/GitHub/Notion/Confluence/Calendar/Drive autonomously — confirmation modal required |
| **Execution gate** | Server commands and shell access require the room owner to explicitly enable; defaults off per room |
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

1. Type `/breakglass` in chat
2. Enter your operator PIN when prompted
3. Sparkbot resumes the waiting privileged action
4. Type `/breakglass close` to end the session

All sessions are logged.

### Guardian Vault

Encrypted secret storage. Break-glass activation required before writing secrets. Accessible from the `/spine` Security tab.

### Operator Access

```env
SPARKBOT_OPERATOR_USERNAMES=your-username   # blank = any authenticated user is operator
SPARKBOT_OPERATOR_PIN_HASH=...              # generate: see .env.example
SPARKBOT_VAULT_KEY=...                      # generate: see .env.example
```

**Open mode (default):** any authenticated human user is a guardian operator. Suitable for single-user installs.

### Memory Guardian
```env
SPARKBOT_MEMORY_GUARDIAN_ENABLED=true
SPARKBOT_MEMORY_GUARDIAN_DATA_DIR=./data/memory_guardian
SPARKBOT_MEMORY_GUARDIAN_MAX_TOKENS=1200
SPARKBOT_MEMORY_GUARDIAN_RETRIEVE_LIMIT=6
```

### Executive Guardian + Task Guardian
```env
SPARKBOT_EXECUTIVE_GUARDIAN_ENABLED=true
SPARKBOT_TASK_GUARDIAN_ENABLED=true
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
SPARKBOT_OPERATOR_PIN_HASH=             # generate: see .env.example
SPARKBOT_VAULT_KEY=                     # generate: see .env.example
SPARKBOT_GUARDIAN_POLICY_ENABLED=false  # false = personal mode (all tools allowed)
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
| `GET` | `/api/v1/chat/audit` | Recent tool audit log (room-scoped) |
| `GET` | `/api/v1/utils/health-check/` | Health check → `true` |

### Agents

| Method | Path | Description |
|--------|------|-------------|
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
├── scripts/                              # Build and packaging scripts
└── .github/workflows/
    ├── desktop-release.yml               # Desktop installer CI (triggers on desktop-v* tags)
    └── build-installer.yml               # QA build (does not publish)
```
