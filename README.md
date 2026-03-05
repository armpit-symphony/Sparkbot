# Sparkbot v2

**Sparkbot** is a self-hosted AI chat assistant built for Sparkpit Labs. It runs at [remote.sparkpitlabs.com](https://remote.sparkpitlabs.com) and is designed to grow into a full office worker agent — handling chat, file analysis, meeting capture, search, and eventually tool calling into the broader office stack.

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

| Component           | Path                                  | Port  | Status       |
|---------------------|---------------------------------------|-------|--------------|
| FastAPI backend     | `/home/sparky/sparkbot-v2/backend`    | 8091  | ✅ Running    |
| React frontend      | `/home/sparky/sparkbot-v2/frontend`   | —     | ✅ Built/deployed |
| PostgreSQL          | system service                        | 5432  | ✅ Running    |
| nginx               | `/etc/nginx/sites-available/sparkbot-remote` | 80/443 | ✅ Running |

---

## Tech Stack

**Backend**
- [FastAPI](https://fastapi.tiangolo.com) — async Python API framework
- [SQLModel](https://sqlmodel.tiangolo.com) — ORM (PostgreSQL)
- [litellm](https://docs.litellm.ai) — unified LLM routing (100+ providers)
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
- **File uploads** — images and documents with AI vision analysis (10 MB max)

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

### Meeting Mode
Activated with `/meeting start`. While active, prefix messages with:
- `note:` → captured as a meeting note
- `decided:` → recorded as a decision
- `action:` → added as an action item

`/meeting stop` exports the full notes as a dated `.md` file.

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

---

## Configuration

All configuration is via environment variables. The systemd service file at `/etc/systemd/system/sparkbot-v2.service` is the canonical place to set them.

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

After changing env vars: `sudo systemctl restart sparkbot-v2`

---

## Running Locally

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8091

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

---

## Deployment (Production)

```bash
# Build frontend
cd frontend
npm run build
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
| `POST` | `/api/v1/chat/users/login` | Login → JWT token |
| `GET` | `/api/v1/chat/rooms/{id}/messages` | Room message history |
| `POST` | `/api/v1/chat/rooms/{id}/messages/stream` | Send message, receive SSE stream |
| `POST` | `/api/v1/chat/rooms/{id}/upload` | Upload file, receive SSE stream |
| `GET` | `/api/v1/chat/messages/{id}/search?q=` | Full-text message search |
| `GET` | `/api/v1/chat/models` | List available LLM models |
| `POST` | `/api/v1/chat/model` | Set model preference `{"model": "gpt-4o"}` |
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
│   │   │       ├── rooms.py              # Room CRUD + streaming message endpoint
│   │   │       ├── messages.py           # Message CRUD + search
│   │   │       ├── uploads.py            # File upload + vision SSE
│   │   │       ├── model.py              # Model switching endpoints
│   │   │       ├── users.py              # Chat user management + bootstrap
│   │   │       └── websocket.py          # WebSocket handler
│   │   ├── models.py                     # SQLModel DB models
│   │   └── crud.py                       # DB helper functions
│   └── venv/                             # Python virtualenv
├── frontend/
│   ├── src/
│   │   ├── pages/SparkbotDmPage.tsx      # Main chat UI (streaming, commands, meeting)
│   │   ├── components/chat/
│   │   │   ├── MessageBubble.tsx         # Markdown + syntax highlight + copy button
│   │   │   └── ChatInput.tsx             # Input bar
│   │   └── lib/chat/types.ts             # Shared TypeScript types
│   └── dist/                             # Built frontend (deployed to /var/www/sparkbot-remote)
└── uploads/                              # Uploaded files storage
```

---

## Roadmap

See [`/home/sparky/sparkbot/LOGBOOK_handoff.md`](../sparkbot/LOGBOOK_handoff.md) for full session history and detailed roadmap.

**Next up:**
- Tool calling framework (web search, code execution)
- Persistent per-user memory (injected into system prompt)
- Calendar integration (Google Calendar / CalDAV)
- Reply threading UI
- Email integration (SMTP/IMAP summarisation)
