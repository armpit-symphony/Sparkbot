# Sparkbot v2

**Sparkbot** is a self-hosted AI chat assistant built for Sparkpit Labs. It runs at [remote.sparkpitlabs.com](https://remote.sparkpitlabs.com) and is designed to be a full office worker agent — handling chat, file analysis, meeting capture, web search, calendar access, and memory across sessions.

---

## Architecture

```
Browser
  │
  └── nginx (remote.sparkpitlabs.com)
        ├── /            → static files (/var/www/sparkbot-remote)
        ├── /api/        → FastAPI backend (port 8091)
        └── /ws/         → WebSocket (port 8091, upgrade headers)
```

| Component           | Path                                  | Port  | Status            |
|---------------------|---------------------------------------|-------|-------------------|
| FastAPI backend     | `/home/sparky/sparkbot-v2/backend`    | 8091  | ✅ Running         |
| React frontend      | `/home/sparky/sparkbot-v2/frontend`   | —     | ✅ Built/deployed  |
| PostgreSQL          | system service                        | 5432  | ✅ Running         |
| nginx               | `/etc/nginx/sites-available/sparkbot-remote` | 80/443 | ✅ Running |

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
- **Markdown rendering** — headings, lists, bold, tables, code blocks in bot replies
- **Syntax highlighting** — fenced code blocks with language detection (oneDark theme)
- **Copy-code button** — one click to clipboard on every code block
- **Message search** — full-text search across room history (`/search`)
- **File uploads** — images (vision analysis), documents (text extraction + summarisation), other files (10 MB max)

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

### Agent Tools
The bot calls tools automatically mid-conversation — a chip appears briefly in the UI while the tool runs, then disappears as the response streams in.

| Tool | Trigger emoji | Description |
|------|--------------|-------------|
| `web_search` | 🔍 | Search the web (Brave → SerpAPI → DuckDuckGo fallback chain) |
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

---

## Configuration

All configuration is via environment variables. The systemd service file at `/etc/systemd/system/sparkbot-v2.service` is the canonical place to set them for production. A `.env` file in `backend/` works for local dev.

### Required
```env
OPENAI_API_KEY=sk-...
SECRET_KEY=<random 32+ char string>
POSTGRES_SERVER=localhost
POSTGRES_DB=sparkbot
POSTGRES_USER=sparkbot
POSTGRES_PASSWORD=...
```

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
Sparkbot uses a fallback chain: Brave → SerpAPI → DuckDuckGo (no key required).
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

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -e .
uvicorn app.main:app --reload --port 8091

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
sudo cp -r dist/* /var/www/sparkbot-remote/

# Restart backend
sudo systemctl restart sparkbot-v2

# Health check
curl https://remote.sparkpitlabs.com/api/v1/utils/health-check/
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
| `GET` | `/api/v1/chat/messages/{id}/search?q=` | Full-text message search |
| `GET` | `/api/v1/chat/models` | List available LLM models |
| `POST` | `/api/v1/chat/model` | Set model preference `{"model": "gpt-4o"}` |
| `GET` | `/api/v1/chat/memory/` | List stored user memories |
| `DELETE` | `/api/v1/chat/memory/{id}` | Delete a specific memory |
| `DELETE` | `/api/v1/chat/memory/` | Clear all memories |
| `GET` | `/api/v1/chat/audit` | Recent tool audit log (room-scoped) |
| `GET` | `/api/v1/utils/health-check/` | Health check → `true` |

Interactive API docs: `http://localhost:8091/docs`

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
│   │   │       ├── model.py              # Model switching endpoints
│   │   │       ├── users.py              # Chat user management + bootstrap
│   │   │       └── websocket.py          # WebSocket handler
│   │   ├── models.py                     # SQLModel DB models
│   │   ├── crud.py                       # DB helper functions
│   │   └── alembic/                      # DB migrations
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

Sparkbot v2 has passed a full security audit (Phases A–E). Key controls:

| Area | Implementation |
|------|----------------|
| **Session tokens** | HttpOnly `Secure SameSite=Strict` cookie — never exposed to JavaScript |
| **Bearer fallback** | Old Bearer sessions still accepted until they expire (backward compat) |
| **Write-tool gate** | LLM cannot email/Slack/GitHub/Notion/Confluence/Calendar autonomously — user must confirm via modal |
| **Audit redaction** | Secret-pattern keys and token-format values redacted before audit log write |
| **Response headers** | HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Permissions-Policy, Referrer-Policy |
| **Rate limiting** | Passphrase login: 10 attempts / 15 min per IP |
| **Room authz** | All message/upload/audit endpoints gated by membership; non-members get 403 |
| **Dep scanning** | `pip-audit` + `npm audit` run on every push and weekly via GitHub Actions |
| **Secret scanning** | `gitleaks` pre-commit hook + CI gate |
| **Git history** | `.env` / `backend/.env` purged from all commits via `git filter-repo` |

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

### Security audit — all phases complete ✅
- ✅ Phase A — access control + secret hygiene
- ✅ Phase B — authentication/session hardening
- ✅ Phase C — runtime correctness
- ✅ Phase D — write-tool gate, audit redaction, HttpOnly cookies, security headers
- ✅ Phase E — dependency scanning CI workflow

### Pending (ops, not blocking)
- Key rotation — run after active testing window closes (see `ROTATION_RUNBOOK.md`)
- Message edit UI (backend PATCH endpoint exists, no frontend)
- Reply threading UI (DB + API ready, no frontend component)
