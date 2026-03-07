# Sparkbot Logbook

> Ongoing development log — current state, decisions, fixes, and roadmap.

---

## Session — 2026-03-07 · Phase 2: Proactive Autonomy

### Goal

Enable Sparkbot to take scheduled write-actions (send email, post to Slack, create calendar events) on the user's behalf with the same confirmation flow as interactive chat — and give it a compound "morning briefing" skill that compiles a full day digest from all sources in one shot.

### What was done

**1. Task Guardian write-actions**

The Task Guardian previously blocked all write-tool scheduled jobs with:
`"Scheduled tasks cannot run confirm-required tools."` Hard block, no path around it.

Now write tools can run on schedule with explicit pre-authorization:

- **`WRITE_TASK_TOOLS`** frozenset added to `task_guardian.py`: `gmail_send`, `slack_send_message`, `calendar_create_event`
- **`TASK_GUARDIAN_WRITE_ENABLED`** env var (default: `false`). Admin opt-in — keeps the system safe out of the box.
- **Pre-authorization flow**: `guardian_schedule_task` already has `write/confirm` policy, so the existing confirmation modal fires when the user asks to schedule a write job. Once the user confirms, `schedule_task()` embeds `__pre_authorized: True` in `tool_args_json`.
- **Execution**: `_execute_internal_tool` now checks `_is_pre_authorized(tool_args)` when it sees a `confirm` policy decision. If pre-authorized, strips the `__` meta key via `_strip_meta_keys()` and proceeds to execution. If not pre-authorized, returns the original hard-deny.
- **LLM bypass**: Added `calendar_create_event` to the "skip confirm when Google unconfigured" list in `llm.py` (alongside `gmail_send`, `drive_create_folder`).
- **LLM tool description**: Updated `guardian_schedule_task` DEFINITION to clearly describe write tools, their pre-authorization requirement, and the `WRITE_ENABLED` env var.
- **Executor**: `_guardian_schedule_task` in `tools.py` now shows an early error if write tools are requested but `WRITE_ENABLED=false`, and appends a "⚠️ Write task — pre-authorized" note on success.

**To enable scheduled write actions:**
```bash
# In systemd service env or .env:
SPARKBOT_TASK_GUARDIAN_WRITE_ENABLED=true
sudo systemctl restart sparkbot-v2
```
Then say: *"Every weekday at 9am, send a good morning to team@company.com"*
→ Confirmation modal appears → User approves → Job created → Runs autonomously.

**2. Morning briefing skill** (`backend/skills/morning_briefing.py`)

A single compound skill that compiles a full morning digest in one tool call:
- **Date + time** (localized to `timezone` param — uses `zoneinfo`)
- **Google Calendar** events for today + tomorrow (configurable via `days_ahead`)
- **Gmail** unread inbox summary — sender name + subject per email, unread count
- **Pending reminders** for this room — queried directly from DB via `session` param
- **Optional weather** via wttr.in (same as `get_weather` skill, set `include_weather=true` + `location`)

Policy: `read/allow` — no confirmation required. Added to `ALLOWED_TASK_TOOLS`.

**Example Task Guardian job:**
```
guardian_schedule_task(
    name="Morning Brief",
    tool_name="morning_briefing",
    schedule="every:86400",
    tool_args={"timezone": "America/New_York", "location": "New York", "include_weather": true}
)
```
Result fans out to Telegram/Discord/WhatsApp (Phase 1 fan-out) so the brief arrives on your phone.

### New files

- `backend/skills/morning_briefing.py`

### Modified files

- `backend/app/services/guardian/task_guardian.py` — WRITE_TASK_TOOLS, TASK_GUARDIAN_WRITE_ENABLED, _is_pre_authorized, _strip_meta_keys, updated _allowed_task_tool, schedule_task, _execute_internal_tool
- `backend/app/api/routes/chat/tools.py` — updated guardian_schedule_task DEFINITION + executor
- `backend/app/api/routes/chat/llm.py` — calendar_create_event bypass when Google unconfigured

### Verified working

- 7 skills loaded (added morning_briefing)
- `morning_briefing` in `ALLOWED_TASK_TOOLS`, `gmail_send/slack_send_message/calendar_create_event` in `WRITE_TASK_TOOLS`
- `WRITE_ENABLED=false` by default — write tasks return clear error until admin enables
- Full app import clean, service restarted active

### Next actions (Phase 3 — Work UX Polish)

1. **Reply threading frontend** — `reply_to_id` is in DB + API; need a thread component in `SparkbotDmPage.tsx`
2. **Message edit UI** — backend PATCH endpoint ready; need edit button + inline editor in frontend
3. **Onboarding copy** — plain-language explanation of permissions, execution gate, confirmation flow in the dashboard
4. **Guardian health card** — single view of scheduler status, memory, routing, policy in the command center

---

## Session — 2026-03-07 · Phase 1: Personal + Work Assistant Foundations

### Goal

Make Sparkbot a desirable assistant for personal and office use. Phase 1 focuses on proactive reach-out and useful zero-config skills.

### What was done

**1. Proactive notification fan-out (reminders + Task Guardian)**
- Reminders (`backend/app/api/routes/chat/reminders.py`) were Telegram-only. Now fan out to **Telegram, Discord, and WhatsApp** in sequence using importlib lazy-import (no circular imports, bridges that aren't configured silently skip).
- Task Guardian run notifications (`backend/app/services/guardian/task_guardian.py`) got the same treatment — all three bridges notified when a scheduled job completes.
- This is the key UX unlock: a reminder fires and you get the ping on whichever app you're actually looking at.

**2. Google Calendar skill — `calendar_list_events`** (`backend/skills/calendar_list_events.py`)
- Lists upcoming events using the Google Calendar REST API via httpx.
- Reuses `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN` (same as Gmail / Drive — no new credentials).
- Optional `GOOGLE_CALENDAR_ID` env var (default: `primary`).
- `max_results` (1–20, default 10) and `days_ahead` (1–30, default 7) parameters.
- Policy: `read / allow` — no confirmation required.

**3. Google Calendar skill — `calendar_create_event`** (`backend/skills/calendar_create_event.py`)
- Creates a calendar event with summary, start/end time, optional description, location, and attendee list.
- Policy: `write / confirm` — always shows confirmation modal before writing to calendar.
- Passes `requires_execution_gate: True` so the executive guardian journals the action.

**4. News skill — `news_headlines`** (`backend/skills/news_headlines.py`)
- Zero-config (no API key).
- `topic=technology` (default) → Hacker News official API top stories with scores.
- `topic=world/business/science/sports/health` → BBC News RSS feeds parsed via `xml.etree.ElementTree`.
- `count` parameter (1–15, default 8).

**5. Currency conversion skill — `currency_convert`** (`backend/skills/currency_convert.py`)
- Live FX rates via `open.er-api.com` (free, no key); falls back to `exchangerate-api.com`.
- `from_currency`, `to_currency`, `amount` parameters.
- Zero-config, policy: `read / allow`.

**6. Crypto price skill — `crypto_price`** (`backend/skills/crypto_price.py`)
- Real-time prices via CoinGecko public API (free, no key, no rate-limit issues at personal use scale).
- `coins` param: comma-separated names or tickers (`btc`, `eth`, `sol`, `bnb`, …). Built-in alias map → CoinGecko IDs.
- Shows price, 24h % change (▲/▼), and market cap.
- `vs_currency` param (default: `usd`).

### New files

- `backend/skills/calendar_list_events.py`
- `backend/skills/calendar_create_event.py`
- `backend/skills/news_headlines.py`
- `backend/skills/currency_convert.py`
- `backend/skills/crypto_price.py`

### Modified files

- `backend/app/api/routes/chat/reminders.py` — fan-out to all 3 bridges
- `backend/app/services/guardian/task_guardian.py` — fan-out to all 3 bridges

### Verified working

- `venv/bin/python -c "from app.services.skills import _registry; ..."` → 6 skills loaded (weather + 5 new)
- `venv/bin/python -c "from app.main import app"` → import clean
- `sudo systemctl restart sparkbot-v2` → `active`, `Application startup complete`

### Next actions (Phase 2 — Proactive Autonomy)

1. **Task Guardian write-actions** — add `gmail_send`, `calendar_create_event`, `slack_post` to `ALLOWED_TASK_TOOLS` with a confirmation gate that works in the async scheduled context (not the per-request confirm_id flow).
2. **Morning briefing canned job** — a pre-built Task Guardian template: fetch inbox + calendar + reminders → compose a summary → fan-out to all channels. User just sets their preferred time.
3. **Channel activation** — set `DISCORD_BOT_TOKEN` + `DISCORD_ENABLED=true` and `WHATSAPP_*` vars to make the fan-out actually reach phone. Ops task, no code changes needed.

---

## Session — 2026-03-07 · GitHub bridge added

### What was done

- Added a real GitHub bridge on top of the existing GitHub tools.
- New inbound webhook endpoint: `POST /api/v1/chat/github/events`
- Verified signed webhook requests with `X-Hub-Signature-256` and fail-closed behavior when the bridge is enabled but not configured.
- Added GitHub thread-to-room mapping:
  - issue comments and PR review comments map into dedicated Sparkbot rooms
  - `/sparkbot ...` and `@sparkbot ...` invoke Sparkbot inside the thread
  - `approve` / `deny` resolves pending confirmations inside the same thread
- Added outbound GitHub bridge replies so Sparkbot posts back into the issue / PR conversation using `GITHUB_TOKEN`.
- Added GitHub bridge controls to Sparkbot Controls:
  - token
  - webhook secret
  - bot login
  - default repo
  - allowed repos
  - enabled toggle
- Updated `.env.example` and `README.md` with GitHub bridge setup notes and webhook path.

### New files

- `backend/app/services/github_bridge.py`
- `backend/app/api/routes/chat/github.py`

### Modified files

- `backend/app/api/main.py`
- `backend/app/api/routes/chat/__init__.py`
- `backend/app/api/routes/chat/model.py`
- `frontend/src/pages/SparkbotDmPage.tsx`
- `.env.example`
- `README.md`

### Verified working

- Backend compile checks passed.
- `from app.main import app` passed with the new route wiring.
- Frontend build passed with the new GitHub controls card.

### Next actions

1. Create a GitHub webhook on the target repo and point it at `/api/v1/chat/github/events`.
2. Set `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `GITHUB_BOT_LOGIN`, and optionally `GITHUB_ALLOWED_REPOS`.
3. Restart `sparkbot-v2`.
4. Smoke-test:
   - `/sparkbot summarize this PR`
   - `approve`
   - `deny`
   - PR review comment flow

---

## Session — 2026-03-07 · Command center, live Token Guardian, and functional Sparkbot Controls

### What was done

- Added a real dashboard / command-center surface to the existing Sparkbot web app instead of reviving the dead separate dashboard service.
- Added dashboard aggregate APIs and a live frontend view for:
  - today summary cards
  - reminders and tasks
  - recent meeting artifacts
  - inbox summary
  - Guardian health and Task Guardian jobs
  - pending approvals
  - Token Guardian routing status
- Added durable pending approvals plus approve / deny actions directly from the dashboard.
- Switched Token Guardian from shadow-only plumbing to real live-routing support with:
  - `off` / `shadow` / `live` modes
  - allowed-model guardrails
  - fallback reasons
  - dashboard-visible routing metadata
- Expanded `Sparkbot Controls` in the DM page into a real control plane:
  - room execution gate
  - dashboard command-center summary
  - function routing / Token Guardian mode
  - model stack (`Primary`, `1st backup`, `2nd backup`, `Heavy hitter`)
  - provider token onboarding inputs
  - comms setup for Telegram / Discord / WhatsApp
- Fixed the control-plane regressions that made the new UI look broken:
  - `403` on `/api/v1/chat/models/config`
  - dashboard summary crashes from SQL count-row handling
  - room detail crash from bad `.count()` usage
  - broken dashboard link inside Sparkbot Controls that forced the user into the main web auth flow and logged them out
- Rebuilt the frontend, redeployed the static bundle, and restarted the live `sparkbot-v2` service after the fixes.

### Files changed today

- `backend/app/api/routes/chat/dashboard.py` — new dashboard aggregate + dashboard approval actions
- `backend/app/services/guardian/pending_approvals.py` — durable pending approval state
- `backend/app/services/guardian/token_guardian.py` — live routing support and status metadata
- `backend/app/api/routes/chat/llm.py` — model stack fallback + Token Guardian live routing integration
- `backend/app/api/routes/chat/model.py` — Sparkbot Controls config API, token onboarding, comms save, Token Guardian mode save
- `backend/app/api/routes/chat/rooms.py` — fixed room detail message-count path
- `backend/app/api/routes/chat/voice.py` — aligned Token Guardian / model-stack path with voice route
- `frontend/src/routes/_layout/index.tsx` — dashboard command-center route
- `frontend/src/pages/SparkbotDmPage.tsx` — functional Sparkbot Controls panel

### Verified working

- Frontend builds completed successfully.
- Backend import / compile checks completed successfully.
- Live service restarted cleanly after the control-plane and dashboard fixes.
- Sparkbot Controls now loads real config instead of blank / failing sections.
- Token Guardian mode can now be changed from Sparkbot Controls.

### Priority list status

- ~~Main dashboard / command center~~
- ~~Activate Token Guardian (shadow mode -> live mode)~~
- ~~More channels — WhatsApp or Discord next~~
  Connector work is done. Remaining work is activation, testing, and notification fan-out polish.
- Proactive autonomy — lift the read-only restriction on Task Guardian.
- Discord activation and live DM / @mention testing.
- WhatsApp activation with Meta sandbox test number and webhook verification.
- Inbox triage workflow.
- Meeting prep / follow-up workflow.

### Next actions

1. Add Task Guardian write-actions with the existing approval flow as the default safety gate.
2. Activate and test Discord end to end, including DMs, @mentions, and `/approve` / `/deny`.
3. Activate and test WhatsApp with the Meta sandbox number before using a real dedicated phone number.
4. Add channel fan-out from reminders and Task Guardian so Telegram / Discord / WhatsApp users receive proactive notifications.
5. Deepen the command center with stronger `Today`, inbox triage, and meeting follow-up workflows.

---

## Session — 2026-03-07 · Discord + WhatsApp bridges added

### What was done

Added Discord (gateway bot) and WhatsApp (Meta Cloud API webhook) as message channels.
Both follow the exact same Gateway pattern as the Telegram bridge — identical SQLite sidecar,
identical `_run_room_prompt()`, `_ensure_linked_room()`, `/approve`/`deny` confirmation flow.

### Research summary

**WhatsApp options researched:**
- Meta on-premises API: dead, sunset October 23, 2025 — do not use
- Unofficial libs (`yowsup`, `whatsapp-web.js`): dead or ban-risk — rejected
- WAHA (self-hosted unofficial REST sidecar): viable for throwaway dev numbers, high ban risk for prod
- **Meta Cloud API via `pywa` 3.8.0: chosen** — official, webhook-based, free for user-initiated replies within 24h session window. No templates needed for a reactive chatbot.

**Discord options researched:**
- discord.py 2.7.1: canonical, actively maintained — **chosen**
- py-cord, nextcord: also viable, not needed over discord.py 2.x
- Incoming webhooks: send-only, not viable for a chatbot

**Key WhatsApp gotcha**: registered phone cannot simultaneously be used in personal WhatsApp; use a dedicated number or Meta's free sandbox test number for development.

**Key Discord gotcha**: `MESSAGE_CONTENT` is a privileged intent — must be manually toggled in the Developer Portal. `message.content` is always available in DMs without it, but guild messages return empty string without it.

### New files

- `backend/app/services/discord_bridge.py`:
  - `discord.Client` with `message_content=True` + `dm_messages=True` intents
  - `on_ready` / `on_message` event handlers (module-level decorators on `bot`)
  - Responds to DMs always; guild @mentions when not `DISCORD_DM_ONLY`
  - Optional guild restriction via `DISCORD_GUILD_IDS`
  - `/start`, `/help`, `/approve`, `/deny` slash-style commands
  - `_run_room_prompt()` — full history, memory, agent routing, guardian stack
  - `_execute_pending_confirmation()` — identical to Telegram
  - `send_room_notification(room_id, text)` — for reminders / Task Guardian fan-out
  - `discord_bot_task(get_db_session)` — started via `asyncio.create_task` in startup
  - SQLite sidecar: `discord_bridge.db` — keyed on `channel_id`

- `backend/app/services/whatsapp_bridge.py`:
  - `register_whatsapp_bridge(app, get_db)` — called from `main.py` after `app = FastAPI(...)`
  - pywa mounts `GET /whatsapp` (verification challenge) + `POST /whatsapp` (updates) automatically
  - `@wa.on_message(filters.text)` handler for all inbound text messages
  - Phone allowlist via `WHATSAPP_ALLOWED_PHONES`
  - `approve` / `deny` keyword commands (text, not slash — WhatsApp has no slash commands)
  - `send_room_notification(room_id, text)` — for reminders / Task Guardian fan-out
  - SQLite sidecar: `whatsapp_bridge.db` — keyed on `wa_phone` (E.164 without +)
  - Message chunking at 4000 chars (WhatsApp max = 4096)

### Modified files

- `backend/app/main.py`:
  - `from app.services.discord_bridge import discord_bot_task`
  - `from app.services.whatsapp_bridge import register_whatsapp_bridge`
  - `register_whatsapp_bridge(app, get_db)` called after `app.include_router(...)`
  - `discord_bot_task` started in `_start_background_guardians()` via `asyncio.create_task`
  - `discord_bot_task` cancelled in `_stop_background_guardians()`
- `backend/pyproject.toml` — added `discord.py>=2.3.2` and `pywa[fastapi]>=2.0.0`
- `.env.example` — added Discord and WhatsApp config blocks with inline setup notes
- `README.md` — new Discord + WhatsApp config sections, project tree, roadmap entries

### Packages installed

```
pip install "discord.py>=2.3.2" "pywa[fastapi]>=2.0.0"
# installed: discord.py 2.7.1, pywa 3.8.0
```

### Verified working

- Both bridge modules import cleanly with `get_status()` returning expected defaults
- `python3 -c "from app.main import app"` loads without errors
- Service restarted clean; all three inbound bridges now emit explicit startup status logs. Current startup log shows:
  - `[telegram] Poller disabled`
  - `[whatsapp] Bridge disabled or not configured`
  - `[discord] Bridge disabled or DISCORD_BOT_TOKEN not set`
  - `Application startup complete.`

### To activate Discord

1. [discord.com/developers](https://discord.com/developers) → New App → Bot → copy token
2. Bot Settings → **Message Content Intent** → enable (privileged)
3. OAuth2 invite URL → scopes: `bot`, permissions: Send Messages + Read Message History
4. Set `DISCORD_BOT_TOKEN=...` and `DISCORD_ENABLED=true` in systemd service env
5. `sudo systemctl restart sparkbot-v2`

### To activate WhatsApp

1. [developers.facebook.com](https://developers.facebook.com) → New App → WhatsApp → Add Phone Number
2. System User → generate permanent token (`whatsapp_business_messaging` scope)
3. Webhook URL: `https://remote.sparkpitlabs.com/whatsapp`, Verify Token: value of `WHATSAPP_VERIFY_TOKEN`
4. Subscribe webhook field: `messages`
5. Set `WHATSAPP_PHONE_ID`, `WHATSAPP_TOKEN`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_ENABLED=true`
6. `sudo systemctl restart sparkbot-v2`

### Current state

- Both bridges are installed and imported; disabled by default (no tokens set)
- Activating either requires only setting env vars + restarting — no code changes

### Next actions

1. Test Discord: set token, enable, test DM + @mention + `/approve` / `/deny`
2. Test WhatsApp: use Meta sandbox test number to avoid real number registration
3. Consider adding `send_room_notification` calls to the reminder and Task Guardian schedulers
   (so Discord/WhatsApp users get the same proactive notifications as Telegram users)

---

## Session — 2026-03-07 · Voice input + TTS added (Whisper + OpenAI TTS)

### What was done

- Added full voice support: mic → Whisper transcription → existing LLM pipeline → optional TTS playback.
- No new packages required — `openai` 2.21.0 was already installed.

### New files

- `backend/app/api/routes/chat/voice.py` (~160 lines) — two endpoints:
  - `POST /chat/rooms/{room_id}/voice` — accepts `audio` field (≤ 5 MB multipart), transcribes via `whisper-1`, saves human message with transcript, calls `stream_chat_with_tools()`, streams SSE back. Emits a new `transcription` event (voice-only) so the UI can update the temp human message with the actual words heard before the bot replies.
  - `POST /chat/voice/tts` — accepts `{"text": "..."}` JSON, returns `audio/mpeg` stream via OpenAI TTS. Voice/model configurable via `SPARKBOT_TTS_VOICE` / `SPARKBOT_TTS_MODEL` env vars.

### Modified files

- `backend/app/api/routes/chat/__init__.py` — added `voice_router` import + `__all__` entry
- `backend/app/api/main.py` — `include_router(voice_router, prefix="/chat")`
- `frontend/src/pages/SparkbotDmPage.tsx`:
  - Added `Mic`, `Volume2`, `VolumeX` from lucide-react
  - New state: `isRecording`, `recordingSeconds`, `voiceMode` (persisted to localStorage)
  - New refs: `mediaRecorderRef`, `audioChunksRef`, `recordingTimerRef`
  - `playTTS(text)` — fetches TTS endpoint, plays via `HTMLAudioElement`, revokes blob URL on end
  - `handleVoiceSend(blob)` — mirrors SSE reader in `handleSend()`; replaces temp "🎤 …" human message with actual transcript on `transcription` event; calls `playTTS()` when voice mode on + `done` fires
  - `handleVoiceToggle()` — mic permission → `MediaRecorder` start/stop; no crash on denial
  - Mic button (pulsing red + second counter while recording) inserted between upload and text input
  - Voice mode toggle (Volume2/VolumeX) inserted after send button
- `.env.example` — added `SPARKBOT_TTS_VOICE=alloy` and `SPARKBOT_TTS_MODEL=tts-1`
- `README.md` — new Voice section, config, API table, project tree, roadmap entry

### SSE protocol for voice (superset of /messages/stream)

```
data: {"type": "transcription",  "text": "what's the weather in Tokyo?"}
data: {"type": "human_message",  "message_id": "..."}
data: {"type": "token",          "token": "..."}
data: {"type": "done",           "message_id": "..."}
```

### Security notes

- Both endpoints require auth (same cookie-first `CurrentChatUser` dep as all other routes)
- Room membership enforced on `/rooms/{room_id}/voice`; VIEWERs blocked
- `/voice/tts` requires auth; no room scope (text → audio, no room state)
- Transcribed text enters `stream_chat_with_tools()` unchanged — all policy/tool/guardian logic fires identically

### Verified working

- Frontend build: `bun run build` clean (no errors)
- Service restarted clean: `journalctl -u sparkbot-v2` shows `Application startup complete`
- Routes confirmed in OpenAPI spec: `GET /api/v1/openapi.json` shows both voice paths

### Current state

- Voice is live on production (`sparkbot-v2`)
- Requires `OPENAI_API_KEY` (already set); no extra env vars needed to enable (TTS voice/model have sensible defaults)
- Voice mode preference persists across page reloads via localStorage

### Next actions

1. Test in browser — mic permission, recording, transcription, streaming, TTS playback
2. Test with voice mode on — bot replies should play automatically after `done` fires
3. Consider adding OpenClaw voice support via the same Whisper + TTS pattern

---

## Session — 2026-03-06 · Skill plugin system added

### What was done

- Implemented a drop-a-file skill plugin system — identical in spirit to OpenClaw's AgentSkills.
- Any `.py` file placed in `backend/skills/` is auto-discovered at startup via `importlib.util` — no existing files need editing.
- New files:
  - `backend/app/services/skills.py` — `_SkillRegistry` dataclass + `_load()` scanner; runs at module import time; logs a warning and skips any file that is broken or missing the required contract.
  - `backend/skills/example_weather.py` — working `get_weather` skill using the free `wttr.in` JSON API (no key required); demonstrated live in chat.
- Modified files:
  - `backend/app/api/routes/chat/tools.py` — imports `_skill_registry`; extends `TOOL_DEFINITIONS` with skill definitions; adds skill fallback at the end of `execute_tool()` (built-in tools always win).
  - `backend/app/services/guardian/policy.py` — `get_tool_policy()` checks skill-provided policies before the unknown→deny fallback; lazy import avoids circular imports.
  - `.env.example` — added `SPARKBOT_SKILLS_DIR=skills` entry.
  - `README.md` — documented Skill Plugin System section, config var, project tree, and roadmap entry.

### Skill file contract

```python
DEFINITION = { "type": "function", "function": { "name": "my_skill", ... } }  # required
POLICY = { ... }           # optional — defaults to read/allow
async def execute(args, *, user_id=None, room_id=None, session=None) -> str: ...  # required
```

### Verified working

- `get_weather` skill loaded and confirmed called by LLM for live weather queries.
- Skill loads silently at import time (before uvicorn configures logging) — `python3 -c "from app.services.skills import _registry; print(_registry.executors)"` confirms load.
- Broken skill files (missing `execute`) log a warning and do not crash the service.

### Current state

- Skill plugin system is live on production (`sparkbot-v2`).
- `backend/skills/example_weather.py` is the reference implementation.
- Adding a new tool now requires only dropping a `.py` file and restarting — no changes to `tools.py`, `policy.py`, or any other core file.

### Next actions

1. Write additional skills (e.g. currency conversion, crypto prices, news headlines).
2. Consider a skill marketplace / built-in library as the next layer.
3. Key rotation — still deferred until active testing window closes.

---

## Session — 2026-03-06 · Telegram bridge foundation added

### What was done

- Added a native Telegram bridge in `backend/app/services/telegram_bridge.py`.
- Chose long polling for the first implementation so setup can stay simple: bot token in `.env`, no webhook ceremony required.
- Scoped the first Telegram release to private chats.
- Each Telegram chat now maps into a dedicated Sparkbot room and a synthetic chat user, so Telegram conversations are stored in the same room/message history as browser chat.
- Telegram approval flow is supported with `/approve` and `/deny` for pending confirm-required actions.
- Reminder and Task Guardian room notifications can fan back out to linked Telegram chats.
- Wired the Telegram poller into FastAPI startup/shutdown alongside reminders and Task Guardian.
- Updated `.env.example` and `README.md` with Telegram bridge configuration notes.

### Current state

- The Telegram bridge code is in `sparkbot-v2` and imports cleanly.
- The live service will keep the Telegram poller disabled until `TELEGRAM_BOT_TOKEN` is set.
- This is intentionally a first-pass bridge, not the final consumer UX.
- Dedicated PWA/mobile packaging remains deferred.

### Next actions

1. Continue real-world Telegram testing across the day.
2. Check normal chat quality, reminders, and confirm-required actions with `/approve` and `/deny`.
3. Watch for Telegram-specific UX issues such as long-message formatting, duplicate replies, or delayed polling responses.
4. After testing is stable, lock Telegram access down to the user's chat ID with `TELEGRAM_ALLOWED_CHAT_IDS`.
5. Add a browser-side linking/discovery flow later so users do not need manual chat-id allowlisting.
6. Polish Telegram UX and formatting for consumer-facing use.

## Session — 2026-03-06 · Reminder scheduling fixed + consumer handoff

### What was done

- Fixed the reminder / scheduled-action crash path in the live `sparkbot-v2` backend:
  - `stream_room_message()` now loads `room` before any confirmation or execution-gate path uses `room.execution_allowed`
  - this resolves the `name 'room' is not defined` failure seen from chat

- Fixed an async execution bug in `backend/app/services/guardian/executive.py`:
  - non-high-risk async tool calls were returning raw coroutines instead of awaited results
  - this caused follow-on chat failures like `'coroutine' object is not subscriptable`
  - the guard now awaits async results in both the high-risk and non-high-risk paths

- Restarted the live `sparkbot-v2` service after the fix and re-verified the reminder flow from chat:
  - `schedule a good morning message in 7 hours`
  - `list reminders`
  - both now work end-to-end in the live room

- Clarified a UX issue discovered during testing:
  - `/dm` and `/settings` are browser routes, not chat slash commands
  - typing them in chat correctly returns `Unknown command`

### Current state

- Reminder scheduling is working again in production.
- Task / reminder chat flows are now materially more stable after the async guard fix.
- Sparkbot has the right foundations for consumer use, but the next phase is mostly product polish, onboarding, and end-to-end reliability work rather than raw capability work.
- Telegram is now the planned next consumer-facing channel because the user already uses Sparkbot from an iPhone home-screen shortcut and wants messaging access beyond the browser.
- Dedicated PWA/mobile packaging is intentionally deferred; keep it in planning, but do not start that build until the user explicitly asks.

### Tomorrow / next-agent TODO

1. Build a Telegram bridge as the next consumer messaging channel.
2. Design the Telegram bridge so setup is simple: bot token in `.env`, chat-to-room mapping, unified memory/audit/policy flow, and confirmation handling for risky actions.
3. Make Telegram feel seamless like OpenClaw, but keep it native to Sparkbot: same reminders, tasks, Guardian controls, and room history across web and Telegram.
4. Add visible navigation or quick links for Sparkbot controls instead of expecting users to discover `/dm` or `/settings` routes manually.
5. Add canned templates for common recurring jobs and reminder workflows.
6. Add end-to-end tests for reminder creation, reminder listing, confirmation flow, Task Guardian actions, and the future Telegram bridge.
7. Add non-technical onboarding copy that explains permissions, confirmations, execution gate, and integrations.
8. Add clearer UI labels for read vs write vs execute actions before confirmation dialogs appear.
9. Add Guardian health/status surfacing so admins can see scheduler, memory, routing, and policy state in one place.
10. Run a full consumer smoke pass on login, chat, reminders, Gmail, Drive, room controls, scheduled jobs, and Telegram once the bridge exists.
11. Publish plain-language privacy/data-retention notes and a simple integrations setup guide.
12. Park dedicated PWA/mobile app work as a later phase. Current user workflow is home-screen browser access at `remote.sparkpitlabs.com`; a true dedicated PWA/mobile build is desired, but not started yet.

## Session — 2026-03-06 · Consumer readiness controls + reminder regression fix

### What was done

- Fixed the `name 'room' is not defined` regression in `stream_room_message()`:
  - room state is now loaded before tool-confirmation and tool-execution paths use `room.execution_allowed`
  - this specifically unblocked reminder / scheduled-action prompts like "schedule a good morning message in 7 hours"

- Added room-scoped Task Guardian REST endpoints:
  - list jobs
  - list recent runs
  - create a job
  - pause/resume a job
  - run a job immediately

- Tightened room and audit access:
  - room detail now requires room membership
  - room member listing now requires room membership
  - audit reads scoped by room now require room membership
  - single audit entry reads now enforce room membership when the entry is room-scoped

- Added a simple Sparkbot controls UI in the DM page:
  - execution gate toggle
  - recent policy decisions
  - Task Guardian job management

- Added a superuser Sparkbot ops tab in `/settings`
- Added `consumer_readiness_checklist.md`

### Current state

- Sparkbot is materially closer to consumer use:
  - safer room-scoped execution controls
  - visible approval/policy decisions
  - manageable recurring jobs
  - clearer ops/readiness guidance for admins

### Next actions

1. Add canned templates for common recurring jobs.
2. Add end-to-end tests for DM controls, reminder creation, and Task Guardian flows.
3. Add more beginner-friendly onboarding copy and integration setup hints.

## Session — 2026-03-06 · Gmail + Google Drive integration + stream fix

### What was done

- Fixed the live streaming chat failure in `sparkbot-v2/backend/app/api/routes/chat/rooms.py`:
  - `agent_content` was referenced before assignment in `stream_room_message()`
  - this caused the frontend to show `⚠️ Request failed.`
  - reordered agent resolution before history assembly and restarted the service

- Added Google Workspace tool support in the live `sparkbot-v2` backend:
  - Gmail: `gmail_fetch_inbox`, `gmail_search`, `gmail_get_message`, `gmail_send`
  - Google Drive: `drive_search`, `drive_get_file`, `drive_create_folder`
  - OAuth refresh-token flow via:
    - `GOOGLE_CLIENT_ID`
    - `GOOGLE_CLIENT_SECRET`
    - `GOOGLE_REFRESH_TOKEN`
    - optional `GOOGLE_GMAIL_USER`
    - optional `GOOGLE_DRIVE_SHARED_DRIVE_ID`

- Updated the LLM/tool routing in `sparkbot-v2`:
  - Sparkbot now prefers Gmail/Drive tools for relevant requests
  - `gmail_send` and `drive_create_folder` are protected by the existing write-tool confirmation flow
  - if Google OAuth is not configured, Sparkbot should surface the concrete configuration issue instead of generic capability refusal

- Updated docs:
  - `sparkbot-v2/README.md` now documents the Google Workspace env vars and recommended scopes
  - root `README.md` updated with a production-status note

### Current state

- Live backend on port `8091` restarted successfully after both fixes.
- Google Workspace code is live in `sparkbot-v2`, but actual Gmail/Drive access still requires Google OAuth credentials to be added to the live `.env`.
- The older `/home/sparky/sparkbot` repo has now been backported with the same Gmail and Drive tool set, matching env placeholders, and audit-log redaction improvements so GitHub/docs stay aligned with the active stack.
- In the older `sparkbot` repo, the safer subset was backported: Gmail/Drive tools plus prompt/routing and audit redaction. The newer `sparkbot-v2` write-confirmation flow was not fully ported because that legacy chat flow does not expose the same confirmation path cleanly.
- No secrets or personal credentials were committed.

### Next actions

1. Add Google OAuth env vars to the live `sparkbot-v2` `.env`.
2. Use a refresh token with these scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/drive.readonly`
   - `https://www.googleapis.com/auth/drive.file`
3. Restart `sparkbot-v2` after env changes.
4. Smoke test:
   - "check my Gmail"
   - "search Drive for <file>"
   - "send an email to <recipient>" and confirm the modal flow

---

## Session — 2026-03-05 · Security Audit Phases D + E + Git History Cleanup

### What was done

**Phase D3 — Security headers**
- Added to `_SecurityHeadersMiddleware` in `backend/app/main.py`:
  - `Strict-Transport-Security: max-age=63072000; includeSubDomains` (HTTPS only)
  - `Content-Security-Policy` (default-src 'self', unsafe-inline for Vite/Tailwind)
  - `Permissions-Policy: camera=(), microphone=(), geolocation=()`

**Phase D3 — HttpOnly cookie session auth**
- `POST /chat/users/login` now sets `chat_token` as `HttpOnly Secure SameSite=Strict Path=/api` cookie; response body has no token.
- `DELETE /chat/users/session` endpoint clears cookie on logout.
- `deps.py`: cookie-first, Bearer-fallback — old `localStorage` sessions keep working until JWT expiry.
- `websocket.py`: cookie-first on WS upgrade, auth-message fallback for old clients.
- Frontend (`useAuth.ts`, `SparkbotDmPage.tsx`, `ChatPage.tsx`, `websocket.ts`): all fetches use `credentials: 'include'`; auth presence tracked via `sessionStorage.chat_auth`; no token ever touches `localStorage`.

**Phase D1 — Write-tool confirmation gate**
- `WRITE_TOOLS` frozenset in `llm.py`; when LLM tries to call one, stream halts and yields `confirm_required` event with a UUID.
- Frontend shows `ConfirmModal` with a human-readable description of the action; Confirm sends `confirm_id` in next POST; Cancel shows "Action cancelled."
- Backend `rooms.py` `StreamMessageRequest` detects `confirm_id`, executes the pre-confirmed tool directly via `confirmed_stream()`, skips LLM entirely.

**Phase D2 — Audit log redaction**
- `_redact_for_audit()` in `llm.py`: strips values of JSON keys matching secret-name patterns + regex-matches OpenAI/Slack/GitHub/AWS/Notion token formats before `create_audit_log()` call.

**Phase E — Dependency scanning CI**
- `.github/workflows/dep-scan.yml`: `pip-audit` (Python) + `npm audit` (frontend) on push, PR, and weekly Monday 3am UTC. Advisory mode (`|| true`) so known vulns don't block PRs initially.

**Git history cleanup (A5)**
- Installed `git-filter-repo`; purged `.env` and `backend/.env` from all 1,269 commits.
- Restored origin remote; force-pushed to `armpit-symphony/Sparkbot` on GitHub.
- Local `.env` files untouched — will be kept as-is until testing window closes.
- Note: repo is currently public but low-traffic; moving to official org GitHub in a few days. Key rotation deferred until after testing.

**`ROTATION_RUNBOOK.md`** — expanded with git history cleanup steps and per-secret provider quick-reference table.

### Current state
- All Phase A–E security items complete except: key rotation (deliberate deferral) and streaming/WS test suite.
- Production is live at `remote.sparkpitlabs.com` — deploy frontend build + restart service to activate D3/D1/D2 changes.

### Next actions
1. Build + deploy: `cd frontend && bun run build && sudo cp -r dist/* /var/www/sparkbot-remote/ && sudo systemctl restart sparkbot-v2`
2. Browser smoke test: login → check DevTools → `chat_token` cookie should be HttpOnly, no token in localStorage.
3. Header check: `curl -I https://remote.sparkpitlabs.com/` — confirm CSP, HSTS, Permissions-Policy.
4. Rotate all keys when testing window closes (see `ROTATION_RUNBOOK.md`).
5. Move repo to official GitHub org.

---

## System Overview

| Component               | Location                              | Port  | Status          |
|-------------------------|---------------------------------------|-------|-----------------|
| sparkbot-dashboard      | `/home/sparky/sparkbot/backend`       | 8090  | ❌ Crash-looping |
| sparkbot-v2 backend     | `/home/sparky/sparkbot-v2/backend`    | 8091  | ✅ Running       |
| sparkbot (Node.js bot)  | `/home/sparky/sparkbot/sparkbot`      | 8080  | ✅ Running       |
| nginx → remote.sparkpitlabs.com | proxy                         | —     | ✅ Proxies to 8091 |

**Active stack:** nginx → port 8091 (FastAPI) → litellm → LLM provider (Node.js bot on port 8080 is now bypassed)

---

## What We Have

### Core Platform (Working)
- **Streaming AI chat** — token-by-token SSE, conversation context (last 20 msgs), bot reply saved to DB
- **Markdown rendering** — react-markdown with syntax highlighting (oneDark), copy-code button
- **Slash commands** — `/help` `/clear` `/new` `/export` `/search` `/meeting` `/model` with autocomplete picker
- **Message search** — PostgreSQL ILIKE full-text search, highlighted excerpts, debounced live results
- **Meeting mode** — `/meeting start|stop|notes`, captures `note:` / `decided:` / `action:` prefixes, exports `.md`
- **File uploads** — multipart upload, saves to `/uploads/`, images sent to vision model as base64 SSE stream
- **Multi-model switching** — `/model <id>` switches per-user; 7 providers via litellm
- **Real-time WebSocket chat** — room join/leave, typing indicators, presence tracking, auto-reconnect
- **REST API** — full message CRUD, room management, user management, pagination
- **Multi-user rooms** — roles: OWNER, MOD, MEMBER, VIEWER, BOT
- **JWT authentication** — login, token refresh, secure WebSocket auth
- **Room invite system** — token-based invites with usage limits and expiry
- **PostgreSQL database** — full schema: users, rooms, memberships, messages, invites, meeting artifacts

### LLM Provider Support (via litellm, FastAPI direct — Node.js bot bypassed)
| Model ID | Provider | Key Env Var |
|----------|----------|-------------|
| `gpt-4o-mini` | OpenAI | `OPENAI_API_KEY` |
| `gpt-4o` | OpenAI | `OPENAI_API_KEY` |
| `claude-3-5-haiku-20241022` | Anthropic | `ANTHROPIC_API_KEY` |
| `claude-sonnet-4-5` | Anthropic | `ANTHROPIC_API_KEY` |
| `gemini/gemini-2.0-flash` | Google | `GOOGLE_API_KEY` |
| `groq/llama-3.3-70b-versatile` | Groq | `GROQ_API_KEY` |
| `minimax/MiniMax-M2.5` | MiniMax | `MINIMAX_API_KEY` |

### Still Stubbed / Not Wired
- **Message reactions** — WebSocket event types defined, no backend handler
- **Reply threading UI** — `reply_to_id` in DB + API, no frontend thread component
- **Message edit frontend** — backend PATCH endpoint exists, no UI

---

## Session Log

### 2026-03-05 — Audit log (#24) (Claude Code)

**What was built:**

Every LLM tool call is now permanently recorded in the `audit_logs` SQLite table.

**DB model (`AuditLog`):**
| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID PK | |
| `created_at` | datetime | indexed, newest-first |
| `user_id` | UUID | who triggered the tool |
| `room_id` | UUID | which room |
| `tool_name` | str | indexed (e.g. `web_search`) |
| `tool_input` | str | JSON-encoded args (≤2000 chars) |
| `tool_result` | str | truncated result (≤1000 chars) |
| `agent_name` | str | active agent, if any |
| `model` | str | LLM model used |

**Recording mechanism:**
- Logging added inside `stream_chat_with_tools` in `llm.py`, after each `execute_tool` call
- Best-effort: wrapped in `try/except` so a DB error never breaks the chat stream
- `agent_name` passed through via new optional param on `stream_chat_with_tools`
- Slack bridge calls without DB session → no audit (acceptable; bridge is stateless)

**REST API:**
- `GET /api/v1/chat/audit` — recent entries, filterable by `tool`, `room_id`; paginated
- `GET /api/v1/chat/audit/{id}` — single entry with full result text
- Auth required (any logged-in user)

**Frontend:**
- `/audit` slash command — shows last 10 tool actions for the current room; displays timestamp, agent, tool name, input args, truncated result

**Alembic migration:** `744de3c4a850_add_audit_logs` — creates `audit_logs` table with 4 indexes

---

### 2026-03-05 — Multi-agent rooms (#23) (Claude Code)

**What was built:**

Named agent system — users `@mention` a specialist agent and get a response with that agent's persona and system prompt.

**Agents:**
| Agent | Emoji | Specialty |
|-------|-------|-----------|
| `@researcher` | 🔍 | Find accurate info, proactively uses web_search, cites sources |
| `@coder` | 💻 | Clean working code with explanations, asks clarifying questions |
| `@writer` | ✍️ | Writing, editing, email, docs, summaries |
| `@analyst` | 📊 | Structured reasoning, logic, data analysis, calculate tool |

**Backend (no DB migration needed):**
- New `agents.py` — agent registry; custom agents via `SPARKBOT_AGENTS_JSON` env var
- `rooms.py` — `resolve_agent_from_message()` detects `@agentname` prefix; strips @mention from LLM message; swaps system prompt; includes `"agent"` field in SSE `done` event
- `GET /api/v1/chat/agents` — returns agent list (added to model.py)

**Frontend:**
- `@` autocomplete picker — type `@` to get agent suggestions (like `/` for commands)
- Agent badge — bot messages show `🔍 RESEARCHER` etc. above the response when an agent was used
- `/agents` slash command — lists available agents with descriptions
- Loads live agent list from API on init (falls back to built-ins if request fails)

**Custom agents** via env var:
```
SPARKBOT_AGENTS_JSON=[{"name":"devops","emoji":"🖥️","description":"..","system_prompt":".."}]
```

**Usage:**
- `@researcher what's the latest on Rust 2024?` → researcher persona + web_search
- `@coder write a Python binary search` → coder persona, clean code focus
- `@writer draft a project update email` → writer persona
- `@analyst break down this cost structure` → analyst persona

---

### 2026-03-05 — Slack bridge (#22) (Claude Code)

**What was built:**

Three new outbound LLM tools + one inbound webhook handler:

| Component | Description |
|-----------|-------------|
| `slack_send_message` 💬 | Post a message to any channel (or default channel) |
| `slack_list_channels` 💬 | List public channels with IDs |
| `slack_get_channel_history` 💬 | Fetch recent messages from a channel |
| `POST /api/v1/chat/slack/events` | Slack Events API webhook — @mentions → LLM → reply |

**Inbound bridge details:**
- Verifies Slack HMAC-SHA256 signature (`X-Slack-Signature` + `SLACK_SIGNING_SECRET`)
- Responds `200 OK` immediately; LLM processing runs as FastAPI `BackgroundTask` (avoids Slack's 3s timeout)
- Handles two event types: `app_mention` (threaded reply in channel) and `message.im` (DM response)
- In-memory dedup cache prevents duplicate processing on Slack retries
- Ignores messages from bots to prevent reply loops
- **Webhook URL**: `https://remote.sparkpitlabs.com/api/v1/chat/slack/events` (tested, verified URL challenge returns correctly)

**Slack App setup (one-time):**
1. Create app at api.slack.com/apps
2. Bot Token Scopes: `chat:write`, `channels:read`, `channels:history`, `im:history`, `im:write`
3. Enable Events API → Subscribe to `app_mention` + `message.im`
4. Set Request URL → `https://remote.sparkpitlabs.com/api/v1/chat/slack/events`
5. Install app to workspace → copy Bot Token + Signing Secret → set env vars → restart

**Env vars:**
```
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_DEFAULT_CHANNEL=#general   # optional, for slack_send_message default
```

---

### 2026-03-05 — Notion + Confluence integration (#21) (Claude Code)

**What was built:**

Six new LLM tools (3 Notion + 3 Confluence) via httpx — zero new dependencies:

| Tool | Chip | Description |
|------|------|-------------|
| `notion_search` | 📝 | Search Notion pages by keyword; returns titles + URLs |
| `notion_get_page` | 📝 | Fetch full page content (blocks → markdown text) |
| `notion_create_page` | 📝 | Create a new Notion page under a parent, markdown-aware |
| `confluence_search` | 🏔️ | CQL search across Confluence; returns titles, excerpts, page URLs |
| `confluence_get_page` | 🏔️ | Fetch page content; strips Confluence storage HTML → plain text |
| `confluence_create_page` | 🏔️ | Create a page in a space (optionally under a parent) |

**Implementation details:**
- Notion: `Authorization: Bearer {NOTION_TOKEN}`, `Notion-Version: 2022-06-28`
  - `notion_get_page` fetches page metadata + blocks in parallel via `asyncio.gather`
  - `_text_to_notion_blocks()` converts `# heading`, `- list`, plain text → Notion block objects (≤100)
  - `_notion_extract_page_id()` normalises bare UUIDs and full Notion page URLs
- Confluence: HTTP Basic auth (`CONFLUENCE_USERNAME` + `CONFLUENCE_API_TOKEN`)
  - `confluence_create_page` wraps content in XHTML storage format (Confluence's native format)
  - `_strip_html()` removes storage-format HTML for readable `confluence_get_page` output
- All executors are pure async httpx — no blocking I/O

**Env vars** (templates added to `.env`):
```
NOTION_TOKEN=secret_...              # Notion integration token
NOTION_DEFAULT_PARENT_ID=<uuid>      # Default parent page for new pages
CONFLUENCE_URL=https://team.atlassian.net
CONFLUENCE_USERNAME=you@example.com
CONFLUENCE_API_TOKEN=...             # Atlassian API token
CONFLUENCE_DEFAULT_SPACE=ENG         # Default space for new pages
```

**Example usage:**
- "Find our onboarding doc in Notion" → `notion_search(query="onboarding")`
- "What does page abc123 say?" → `notion_get_page(page_id="abc123")`
- "Write up today's meeting notes in Notion" → `notion_create_page(title=..., content=...)`
- "Search Confluence for the API design spec" → `confluence_search(query="API design")`
- "Create a runbook in the OPS space" → `confluence_create_page(title=..., space_key="OPS", ...)`

---

### 2026-03-05 — GitHub integration (#20) (Claude Code)

**What was built:**

Four new LLM tools using `httpx` (already installed) against the GitHub REST API v3:

| Tool | Chip | Description |
|------|------|-------------|
| `github_list_prs` | 🐙 | List PRs with state filter (open/closed/all); shows draft status and reviewer count |
| `github_get_pr` | 🐙 | Full PR details — title, author, body, +/- stats, changed files, CI check results |
| `github_create_issue` | 🐙 | Create an issue with title, markdown body, optional comma-separated labels |
| `github_get_ci_status` | 🔬 | Latest 5 workflow runs for a branch — name, conclusion, date, head commit message |

**Implementation details:**
- `github_get_pr` fetches PR details + files + check runs in a single async gather (3 parallel HTTP calls)
- All calls use `Authorization: Bearer {GITHUB_TOKEN}` + `X-GitHub-Api-Version: 2022-11-28`
- `_resolve_repo()` falls back to `GITHUB_DEFAULT_REPO` if no repo passed — user can omit repo once it's set
- Without a token: public repos work (rate-limited to 60 req/hr); private repos need `GITHUB_TOKEN`
- Without token AND no default repo → clear "not configured" message

**Env vars** (template added to `.env`):
```
GITHUB_TOKEN=ghp_...            # Fine-grained or classic PAT; repo scope for private
GITHUB_DEFAULT_REPO=owner/repo  # Optional default so user doesn't repeat it
```

**Example usage:**
- "What PRs are open?" → `github_list_prs(state="open")`
- "Show me PR #42" → `github_get_pr(pr_number=42)`
- "Is the main branch green?" → `github_get_ci_status(branch="main")`
- "File a bug: login page crashes on mobile" → `github_create_issue(title=..., body=...)`

---

### 2026-03-05 — Email integration — IMAP/SMTP (#19) (Claude Code)

**What was built:**

Three new LLM tools in `tools.py` — zero new dependencies (all Python built-ins: `imaplib`, `smtplib`, `email`):

| Tool | Chip | Description |
|------|------|-------------|
| `email_fetch_inbox` | 📧 | Fetch N recent emails (or unread only) from IMAP inbox |
| `email_search` | 📧 | Search inbox by subject or sender keyword |
| `email_send` | 📤 | Compose and send via SMTP (plain text, optional CC) |

**Implementation details:**
- All blocking IMAP/SMTP calls wrapped in `asyncio.to_thread`
- Header decoding via RFC 2047 (`email.header.decode_header`)
- Multipart body extraction: prefers `text/plain`, falls back to HTML tag-stripped
- `email_fetch_inbox`: `max_emails` (1–20), `unread_only` flag; body snippet 300 chars
- `email_search`: OR search on SUBJECT + FROM IMAP fields; deduplicates IDs before fetch
- `email_send`: auto-selects STARTTLS (port 587) or SSL (port 465) based on `EMAIL_SMTP_PORT`
- Graceful "not configured" message if env vars absent

**Env vars** (all commented template in `.env`):
```
EMAIL_IMAP_HOST / EMAIL_IMAP_PORT (default 993)
EMAIL_IMAP_USERNAME / EMAIL_IMAP_PASSWORD
EMAIL_SMTP_HOST / EMAIL_SMTP_PORT (default 587)
EMAIL_SMTP_USERNAME / EMAIL_SMTP_PASSWORD
EMAIL_FROM_NAME (default "Sparkbot")
```

**Provider setup:**
| Provider | IMAP Host | SMTP Host | Notes |
|----------|-----------|-----------|-------|
| Gmail | `imap.gmail.com` | `smtp.gmail.com` | Needs App Password + IMAP enabled in settings |
| Outlook | `outlook.office365.com` | `smtp.office365.com` | App password or OAuth |
| Fastmail | `imap.fastmail.com` | `smtp.fastmail.com` | App password |

**Example usage:**
- "Check my email" → `email_fetch_inbox(max_emails=5)`
- "Any emails from Alice?" → `email_search(query="alice")`
- "Send Bob a meeting invite for tomorrow" → bot drafts, confirms with user, then `email_send`

---

### 2026-03-05 — Proactive reminders (#18) (Claude Code)

**What was built:**

- `Reminder` DB model (`reminders` table): `id`, `room_id`, `created_by`, `message`, `fire_at` (UTC, indexed), `recurrence` (once/daily/weekly), `status` (pending/fired/cancelled), `created_at`
- Alembic migration `b6163bffa521_add_reminders` — applied ✅
- Reminder CRUD in `crud.py`: `create_reminder`, `get_room_reminders`, `get_due_reminders`, `fire_reminder` (auto-reschedules recurring), `cancel_reminder`
- Three new LLM tools in `tools.py`:
  - `set_reminder(message, fire_at, recurrence?)` — creates a reminder; fire_at is ISO 8601 UTC; recurrence: once/daily/weekly
  - `list_reminders()` — lists pending reminders for the current room
  - `cancel_reminder(reminder_id)` — cancels by short ID prefix or full UUID
- Background asyncio scheduler in `reminders.py` — polls every 60 s:
  - Finds `status=pending AND fire_at <= now`
  - Writes bot message to DB (`⏰ **Reminder:** {message}`)
  - Broadcasts to connected WebSocket clients via `ws_manager.broadcast()`
  - Marks as `fired` (one-shot) or advances `fire_at` (recurring)
- FastAPI `lifespan` context manager added to `main.py` — starts scheduler on startup, cancels cleanly on shutdown
- REST API in `reminders.py`: `GET/POST /rooms/{id}/reminders`, `DELETE /rooms/{id}/reminders/{id}`
- Frontend `SparkbotDmPage.tsx`:
  - `set_reminder/list_reminders/cancel_reminder: "⏰"` ToolChip icons
  - `/remind` slash command — fetches pending reminders and renders as system message
  - Added `/remind` to command list + autocomplete
- Frontend built + deployed; backend restarted ✅
- Scheduler confirmed running: `INFO:app.main:[startup] Reminder scheduler started`

**Example usage:**
- "Remind us about the daily standup every day at 9am UTC" → `get_datetime` + `set_reminder(recurrence="daily")`
- "Remind me to send the invoice tomorrow at 2pm" → `set_reminder(recurrence="once")`
- "What reminders do we have?" → `list_reminders`
- "Cancel the standup reminder" → `list_reminders` then `cancel_reminder`
- `/remind` slash command → instant list without LLM

**REST API:**
- `GET  /api/v1/chat/rooms/{room_id}/reminders?status=pending|fired|cancelled|all`
- `POST /api/v1/chat/rooms/{room_id}/reminders` — `{message, fire_at, recurrence}`
- `DELETE /api/v1/chat/rooms/{room_id}/reminders/{id}`

---

### 2026-03-05 — Document summarisation (#17) (Claude Code)

**What was built:**

Extended the existing `uploads.py` to detect and extract text from documents before sending to the LLM.

**Supported formats:**
| Type | Content-Type | Extension |
|------|-------------|-----------|
| PDF | `application/pdf` | `.pdf` |
| Word | `application/vnd.openxmlformats-...wordprocessingml.document` | `.docx` |
| Plain text | `text/plain` | `.txt` |
| Markdown | `text/markdown` | `.md` |
| CSV | `text/csv` | `.csv` |

**How it works:**
1. On upload, `_extract_text()` is called in a thread (`asyncio.to_thread`) — blocking IO doesn't block the event loop
2. Extracted text is truncated to 12,000 chars (~3k tokens) if the document is large — a truncation note is appended
3. User's caption becomes the prompt (default: "Please summarise this document and highlight the key points.")
4. Full document text + prompt sent to LLM in same SSE stream protocol as images
5. If text extraction fails (scanned/image PDF, encrypted, corrupt), bot says it couldn't extract text and asks the user to clarify

**Changes to `uploads.py`:**
- Added `DOC_TYPES`, `DOC_EXTENSIONS`, `DOC_MAX_CHARS = 12_000` constants
- Added `_extract_text(data, content_type, filename)` function — handles PDF (pypdf), DOCX (python-docx), plain text/markdown/CSV (UTF-8 decode)
- Detects `is_doc` flag alongside existing `is_image`
- Human message now uses 📄 icon for extracted docs
- LLM `max_tokens` set to 1,500 for docs (vs 500 for images, 300 for other files)
- Extraction runs before the SSE generator starts (text available in closure)

**Packages installed:** `pypdf==4.3.1`, `python-docx==1.2.0`; added to `pyproject.toml`

**Limitations:**
- Scanned/image PDFs return no text (pypdf only handles text-layer PDFs)
- `.doc` (old Word format) not supported — only `.docx`
- No page-by-page Q&A — full text truncated to 12k chars before sending

---

### 2026-03-05 — Task/todo management (#16) (Claude Code)

**What was built:**

- `ChatTask` DB model (`chat_tasks` table): `id`, `room_id`, `created_by`, `assigned_to` (nullable), `title`, `description`, `status` (open/done), `due_date`, `created_at`, `updated_at`
- `TaskStatus` enum added to `models.py`
- Alembic migration `def143549f1d_add_chat_tasks` — applied ✅
- Task CRUD in `crud.py`: `create_task`, `get_tasks`, `get_task`, `complete_task`, `assign_task`, `delete_task`
- Three new LLM tools in `tools.py`:
  - `create_task(title, description?, assignee?, due_date?)` — creates a task in the current room; assignee resolved by username; due_date ISO 8601
  - `list_tasks(filter?)` — filter: "open" (default), "done", "all"; shows short IDs, assignee, due date
  - `complete_task(task_id)` — accepts 8-char prefix or full UUID; matches by prefix scan if needed
- `room_id` threaded through `execute_tool` → `stream_chat_with_tools` → `rooms.py` so task tools know which room they're in
- `tasks.py` REST API: `GET/POST /rooms/{id}/tasks`, `PATCH/DELETE /rooms/{id}/tasks/{task_id}` — all auth + room-membership gated
- Frontend `SparkbotDmPage.tsx`:
  - Added `create_task: "📋"`, `list_tasks: "📋"`, `complete_task: "✅"` to `TOOL_ICONS`
  - Added `/tasks` slash command: `/tasks` (open), `/tasks done`, `/tasks all` — fetches REST API and renders as system message with short IDs
  - Added `/tasks` to command list + autocomplete
- Frontend built + deployed; backend restarted ✅

**Example usage in chat:**
- "Add a task to review the Q1 report, assign it to alice, due Friday" → `create_task` called
- "What tasks are open?" → `list_tasks(filter="open")`
- "Mark the review task as done" → bot calls `list_tasks` to find it, then `complete_task`

**REST API:**
- `GET  /api/v1/chat/rooms/{room_id}/tasks?filter=open|done|all`
- `POST /api/v1/chat/rooms/{room_id}/tasks` — `{title, description?, assigned_to?, due_date?}`
- `PATCH /api/v1/chat/rooms/{room_id}/tasks/{task_id}` — `{status?, assigned_to?}`
- `DELETE /api/v1/chat/rooms/{room_id}/tasks/{task_id}`

---

### 2026-03-05 — Calendar integration via CalDAV (#15) (Claude Code)

**What was built:**

- Two new LLM tools added to `tools.py`:
  - `calendar_list_events(days_ahead=7)` — lists upcoming events from CalDAV server; max 30 days, up to 25 events; handles both timed and all-day events
  - `calendar_create_event(title, start, end, description?, location?)` — creates a new event via CalDAV; ISO 8601 datetime input
- Calendar config reads from env: `CALDAV_URL`, `CALDAV_USERNAME`, `CALDAV_PASSWORD`
  - If unconfigured, tools return a human-readable "not configured" message
  - CalDAV ops run in `asyncio.to_thread` (library is synchronous)
- Packages installed: `caldav==1.6.0`, `icalendar==5.0.14` (+ transitive: vobject, recurring-ical-events, pytz, x-wr-timezone, tzdata)
- `pyproject.toml` updated: added `caldav>=1.3.0,<2.0.0`, `icalendar>=5.0,<6.0`, `litellm` (was missing)
- Frontend `SparkbotDmPage.tsx`: added `calendar_list_events: "📅"` and `calendar_create_event: "📅"` to `TOOL_ICONS`
- Frontend built and deployed to `/var/www/sparkbot-remote`
- Backend restarted, health check: `true`

**Compatible CalDAV providers:**
- **Google Calendar**: URL `https://www.google.com/calendar/dav/{email}/events`, use an App Password (not main password)
- **iCloud**: URL `https://caldav.icloud.com`, use an App-Specific Password
- **Nextcloud / Baikal / Radicale**: self-hosted, URL from the server admin panel
- **Fastmail**: `https://caldav.fastmail.com/dav/`

**To activate:** add three lines to `/home/sparky/sparkbot-v2/backend/.env` (template already there, commented out), then `sudo systemctl restart sparkbot-v2.service`.

**Example usage in chat:**
- "What's on my calendar this week?" → bot calls `calendar_list_events(7)`
- "Schedule a team standup tomorrow at 9am for 30 minutes" → bot calls `calendar_create_event(...)`

---

### 2026-03-05 — OpenClaw-native web search bridge for Sparkbot (Codex)

**Context:** Requirement was OpenClaw-like “native” web search behavior without separately plugging keys into Sparkbot.

**Discovery:**
- OpenClaw on this host already has web search configured in `~/.openclaw/openclaw.json`:
  - `tools.web.search.enabled: true`
  - `tools.web.search.apiKey: <present>`
- So OpenClaw appears keyless at runtime because key is already stored in its config.

**What was implemented (sparkbot-v2):**
- `backend/app/api/routes/chat/tools.py`
  - Added provider chain in `web_search`: `Brave -> SerpAPI -> DDGS`.
  - Added bounded query cache (`SEARCH_CACHE_TTL_SECONDS`, default 300s).
  - Added provider-labeled output and clearer failure reporting.
  - Added OpenClaw bridge fallback:
    - if `BRAVE_SEARCH_API_KEY` is unset, Sparkbot now tries to read `tools.web.search.apiKey` from OpenClaw config (`~/.openclaw/openclaw.json` or `OPENCLAW_CONFIG_PATH`).
- `backend/pyproject.toml`
  - Added explicit runtime dep: `ddgs>=9.0.0,<10.0.0`.
- `.env.example`
  - Added `BRAVE_SEARCH_API_KEY`, `SERPAPI_KEY`, `SEARCH_CACHE_TTL_SECONDS`, `OPENCLAW_CONFIG_PATH`.

**Verification:**
- Direct tool smoke test returned `Search provider: brave` (confirming OpenClaw key bridge worked).
- Restarted `sparkbot-v2.service`.
- Post-restart checks:
  - service status: `active (running)`
  - listener: `127.0.0.1:8091`
  - health endpoint: `true`

**Outcome:** Sparkbot now has OpenClaw-style native web search behavior on this host without adding keys directly to Sparkbot env.

### 2026-03-05 — Web search reliability hardening (Codex)

**Issue observed:** DDGS-only web tool was brittle (inconsistent/no results under some queries and provider-side variability).

**What was changed (sparkbot-v2):**
- `backend/app/api/routes/chat/tools.py`
  - Reworked `web_search` into provider fallback chain:
    - `BRAVE_SEARCH_API_KEY` -> Brave Search API
    - `SERPAPI_KEY` -> SerpAPI (Google)
    - fallback to DDGS
  - Added provider-labeled output (`Search provider: <name>`) for debugging.
  - Added bounded in-memory cache for identical queries (`SEARCH_CACHE_TTL_SECONDS`, default 300s).
  - Added clearer failure reporting with per-provider error notes.
- `backend/pyproject.toml`
  - Added explicit runtime dependency: `ddgs>=9.0.0,<10.0.0` (prevents silent breakage after rebuild/redeploy).
- `.env.example`
  - Added `BRAVE_SEARCH_API_KEY`, `SERPAPI_KEY`, `SEARCH_CACHE_TTL_SECONDS`.

**Runtime verification:**
- Direct tool smoke returned live results (`Search provider: ddgs` with multiple current links).
- Restarted `sparkbot-v2.service` and verified:
  - systemd status: `active (running)`
  - listener on `127.0.0.1:8091`
  - health endpoint: `true`

**Recommended next step:** Set `BRAVE_SEARCH_API_KEY` in `/home/sparky/sparkbot-v2/.env` to make Brave the default provider (more stable than DDGS scraping). Keep DDGS as fallback.

### 2026-03-05 — Security/reliability audit pass + regression tests (Codex)

**Scope completed (sparkbot-v2):**
- Added targeted regression suite: `backend/tests/api/routes/test_chat_security.py`.
- Added coverage for:
  - passphrase login subject identity (`sub == chat_users.id`)
  - chat login rate limiting behavior
  - room/members/uploads/messages access control (member vs non-member)
  - audit endpoint scope (`room_id` required + room membership enforced)

**Additional backend defects found during test-driven pass and fixed:**
- `GET /chat/rooms/{room_id}` room detail count path had invalid count logic.
  - Fixed `message_count` query implementation in `backend/app/api/routes/chat/rooms.py`.
- Audit listing returned row objects in some paths and broke formatter assumptions.
  - Fixed scalar extraction in `backend/app/crud.py:get_audit_logs`.
- Closed data-exposure gap:
  - `GET /chat/rooms/{room_id}/messages` now requires authenticated room membership.

**Verification run:**
- `python3 -m py_compile app/api/routes/chat/rooms.py app/crud.py tests/api/routes/test_chat_security.py`
- `PYTHONPATH=/home/sparky/sparkbot-v2/backend/venv/lib/python3.12/site-packages pytest -q tests/api/routes/test_chat_security.py`
- Result: `4 passed`.

**Checklist sync:**
- Marked complete in this handoff:
  - A-phase verification: authz regression tests
  - A-phase verification: non-member negative tests
  - Done criteria: no cross-room access / no unauth write path / no fixed-subject identity

### 2026-03-05 — Web search debug: ddgs package rename (Claude Code)

**Issue:** Sparkbot could retrieve today's date (✅) but web search returned empty results.

**Root cause:** The `duckduckgo_search` PyPI package was renamed to `ddgs`. The old package still installs but silently returns no results. This was the only breakage — tool calling itself was working correctly.

**Fix:**
- `pip install ddgs` in backend venv
- Updated `tools.py` import: `from ddgs import DDGS`
- Backend restarted, verified: `get_datetime` ✅, `web_search` ✅ (both returning live results)

**Remaining issue:** Web search is working in direct tests but may still return inconsistent results in some queries. DuckDuckGo's free tier has rate limits and no guarantee of coverage.

**TODO — Improve web access reliability:**
- [ ] Add `BRAVE_SEARCH_API_KEY` env var support — Brave Search API is free tier (2,000 req/day), more reliable than DDG scraping
- [ ] Fallback chain: try Brave → fall back to ddgs if no key configured
- [ ] Consider adding `SERPAPI_KEY` option for Google results as a third option
- [ ] Rate-limit guard: cache search results for identical queries within a 5-minute window to avoid hammering the API

---

### 2026-03-05 — Persistent per-user memory (#13) (Claude Code)

**What was built:**

- `UserMemory` DB model added to `models.py` (`user_memories` table: id, user_id, fact, created_at)
- Alembic migration `b3197ab91f7c_add_user_memories.py` — applied ✅
- CRUD functions in `crud.py`: `get_user_memories`, `add_user_memory`, `delete_user_memory`, `clear_user_memories`
- Two new LLM tools in `tools.py`:
  - `remember_fact(fact)` — bot proactively calls this when user reveals name, timezone, preferences, projects
  - `forget_fact(memory_id)` — removes a specific stored fact
- `tools.execute_tool()` now accepts `user_id` + `session` context for memory tool access
- `llm.stream_chat_with_tools()` accepts `db_session` and passes it through to executor
- `rooms.stream_room_message` — loads memories before streaming, builds personalised system prompt with memory block injected; opens one DB session shared between tool calls and bot reply save
- Memory API endpoints (`memory.py`): `GET /chat/memory/`, `DELETE /chat/memory/{id}`, `DELETE /chat/memory/`
- Frontend `/memory` slash command:
  - `/memory` — lists stored facts with truncated IDs
  - `/memory clear` — wipes all memories via API

**How it works end-to-end:** When user says "I'm John, I work in DevOps and prefer Python" — the bot calls `remember_fact` three times mid-stream (invisible to user, chip shows briefly). Next session, those facts appear in the system prompt, so the bot greets by name and gives Python-flavoured answers automatically.

---

### 2026-03-05 — Tool calling framework (#12) (Claude Code)

**What was built:**

- `tools.py` — tool definitions (OpenAI function-calling format, litellm-compatible) + async executors:
  - `web_search(query)` — DuckDuckGo, top 4 results, no API key required
  - `get_datetime()` — current UTC date/time
  - `calculate(expression)` — safe AST-based math eval (no `eval()`), supports `+ - * / ** %`
- `llm.py` — added `stream_chat_with_tools()` async generator:
  - Yields typed event dicts: `{"type": "tool_start"|"tool_done"|"token", ...}`
  - Tool calling loop (max 5 rounds): non-streaming call → execute tools → feed results back → stream final response
  - Falls back gracefully if model doesn't support tools (`drop_params=True`)
- `rooms.py` — `stream_room_message` now uses `stream_chat_with_tools`, forwards `tool_start`/`tool_done` SSE events
- Frontend — `ToolChip` component shows animated tool activity inline in bot bubble:
  - `🔍 web search: <query>…` while searching
  - `🧮 calculate: <expression>…` while computing
  - `🕐 get datetime…` while fetching time
  - Chip disappears when tool completes, response streams in as normal
- Installed `duckduckgo-search==8.1.1` into backend venv
- Built and deployed, backend restarted ✅

**To add more tools:** Define in `TOOL_DEFINITIONS` list and add executor function in `tools.py` — the dispatcher picks them up automatically.

---

### 2026-03-05 — MiniMax M2.5 added + docs updated (Claude Code)

- Added `minimax/MiniMax-M2.5` to `AVAILABLE_MODELS` in `llm.py` — litellm routes to `https://api.minimax.io/v1` automatically when the `minimax/` prefix is used
- Requires `MINIMAX_API_KEY` env var set in systemd service; supports reasoning, function calling, and tool use
- Switch to it in chat with `/model minimax/MiniMax-M2.5`
- Rewrote `sparkbot-v2/README.md` — replaced FastAPI template boilerplate with Sparkbot-specific architecture, feature list, model table, API reference, file map, and roadmap
- Updated LOGBOOK.md — refreshed "What We Have" section to reflect current live state, added full provider table, marked Node.js bot as bypassed

---

### 2026-03-05 — litellm migration complete (Claude Code)

**Tasks:** Search (#8), Meeting mode (#9), File uploads (#10), litellm migration (#11)

**litellm migration:**
- Created `/backend/app/api/routes/chat/llm.py` — centralized LLM module: `DEFAULT_MODEL` (env: `SPARKBOT_MODEL`), `AVAILABLE_MODELS` dict (6 providers), per-user in-memory model prefs, `stream_chat()` async generator using `litellm.acompletion`, `litellm.drop_params=True`
- `send_room_message` (sync endpoint) — replaced broken `asyncio.get_event_loop().run_until_complete()` approach with `litellm.completion()` synchronous call
- `stream_room_message` (async SSE endpoint) — replaced direct `AsyncOpenAI` client with `stream_chat()` from llm.py
- `uploads.py` — replaced `AsyncOpenAI` with `litellm.acompletion()` for vision analysis
- Removed duplicate `_SYSTEM_PROMPT` constants in rooms.py and uploads.py — all use `SYSTEM_PROMPT` from llm.py
- New model-switching router: `GET /api/v1/chat/models`, `GET /api/v1/chat/model`, `POST /api/v1/chat/model` — wired into `__init__.py` and `main.py`
- Frontend: `/model` slash command added — `/model` lists available models (with ✅ active indicator), `/model <id>` calls POST endpoint to switch
- Frontend built and deployed, backend restarted ✅

**Message search (#8):** `GET /api/v1/chat/messages/{room_id}/search?q=<query>` — PostgreSQL ILIKE, minimum 2 chars, limit 30. Frontend: `/search` slash command opens `SearchPanel` overlay with live debounced search, match highlighting with context excerpt.

**Meeting mode (#9):** Client-side state machine in SparkbotDmPage. `/meeting start` activates meeting, `/meeting stop` exports `.md` file, `/meeting notes` shows draft. Messages prefixed `note:` / `decided:` / `action:` are captured into meeting state and appear in the export.

**File uploads (#10):** `POST /api/v1/chat/rooms/{room_id}/upload` — multipart form, saves to `/home/sparky/sparkbot-v2/uploads/{uuid}/{filename}`, max 10MB. Images sent to vision model as base64. SSE response same protocol as /messages/stream. Paperclip button in UI opens file picker.

---

### 2026-03-05 — Slash commands + syntax highlighting (Claude Code)

**Slash commands** — implemented client-side command registry in `SparkbotDmPage.tsx`:
- `/help` — renders command list as a system message bubble
- `/clear` — wipes visible chat (server history preserved)
- `/new` — same as clear with "fresh start" messaging
- `/export` — downloads full conversation as a dated `.md` file

**Autocomplete** — `CommandPicker` component drops up above the input when typing `/`. Click or `Enter` to complete. Dismissed with `Escape`.

**Syntax highlighting** — Added `react-syntax-highlighter` with Prism `oneDark` theme to:
- `SparkbotDmPage.tsx` `CodeBlock` component
- `MessageBubble.tsx` `CodeBlock` component
- Language auto-detected from fenced code block tag (e.g. ` ```python `)

**System message style** — Commands that produce output render as a distinct centre-aligned dashed-border bubble, separate from bot/human bubbles.

**Built and deployed** to `/var/www/sparkbot-remote`.

---

### 2026-03-05 — Streaming bug fix: SQLAlchemy session detachment (Claude Code)

**Bug:** After streaming completed, bot reply showed `⚠️ Save failed: Instance <ChatMessage> is not bound to a Session`.

**Cause (two instances of same pattern):**
1. `message.id` accessed inside generator after `SessionDep` closed — fixed by capturing `human_msg_uuid = message.id` before generator definition.
2. `str(bot_reply.id)` accessed on the line *after* `db.close()` — once the session closes, the ORM object detaches and any attribute access triggers a lazy-load refresh that fails.

**Fix:** Capture `bot_reply_id = str(bot_reply.id)` while session is still open, then call `db.close()`, then yield the captured string. Rule: always extract plain Python values from SQLAlchemy objects before closing their session.

**Status:** Verified working ✅

---

### 2026-03-05 — WO-03042026-1: Fix the Baseline (Claude Code)

**Work order:** 03042026-1

**Done:**

1. **Conversation context** — `rooms.py` now fetches the last 20 messages from DB and builds a proper OpenAI history array (user/assistant roles) before every LLM call. Bot no longer has amnesia.

2. **Streaming responses** — New `POST /api/v1/chat/rooms/{room_id}/messages/stream` endpoint added to `rooms.py`. Returns `text/event-stream` SSE events:
   - `{"type": "human_message", "message_id": "..."}` — real server ID for optimistic message
   - `{"type": "token", "token": "..."}` — each streamed token
   - `{"type": "done", "message_id": "..."}` — bot message saved, final ID
   - `{"type": "error", "error": "..."}` — on failure
   - Uses `AsyncOpenAI` with `stream=True`
   - Bot message saved to DB after stream completes

3. **Nginx SSE config** — Added `proxy_buffering off; proxy_cache off; X-Accel-Buffering: no` location block for `~* ^/api/v1/chat/rooms/[^/]+/messages/stream$` in `/etc/nginx/sites-available/sparkbot-remote`. Without this, nginx would buffer the entire response before sending.

4. **Markdown rendering + copy-code button** — `MessageBubble.tsx` now uses `react-markdown` for bot messages. Code blocks get a one-click copy button (clipboard icon → checkmark on copy). Inline code is styled distinctly. Prose wrapper for lists, headers, paragraphs.

5. **Removed broken UI stubs** — `ChatInput.tsx` cleaned up: removed Paperclip (file upload), Image, and Smile (emoji) buttons that had no backend. Component simplified to input + send button only.

6. **SparkbotDmPage.tsx rewritten** — Uses streaming endpoint. Shows optimistic human message immediately on send, bot bubble appears instantly and fills token-by-token. Typing cursor (blinking block) shown during stream. Bot/human messages styled differently (right/left alignment, primary/muted). Error states handled gracefully.

7. **Frontend built and deployed** — `bun run build` → `sudo cp dist/* /var/www/sparkbot-remote/`

8. **Backend restarted** — `sparkbot-v2.service` restarted, confirmed healthy on port 8091.

**Verified:**
- Health check: `GET /api/v1/utils/health-check/` → `true`
- Streaming endpoint registered in OpenAPI spec at `/api/v1/chat/rooms/{room_id}/messages/stream`

---

### 2026-03-05 — Initial Assessment + Health Check Fix (Claude Code)

**Assessed:**
- Full architecture review of both sparkbot and sparkbot-v2
- Confirmed sparkbot-v2 (port 8091) is the live backend proxied by nginx
- sparkbot-dashboard (port 8090) is crash-looping but not affecting production
- Node.js bot (port 8080) is running and reachable from FastAPI

**Fixed:**
- `/home/sparky/.openclaw/scripts/sparkbot_health.sh` — was checking port 8090 (dead dashboard), changed to 8091 with correct endpoint `/api/v1/utils/health-check/`
- `/home/sparky/.openclaw/workspace/sparkbot-ops-tools/sparkbot_health.sh` — same fix, same endpoint
- Removed stale comment claiming 405 = healthy (check was already for 200)
- Verified: health check now returns `OK: Backend responding (HTTP 200)`

---

## Gap Analysis

### Compared to a Production AI Chat Tool

| Feature                    | Status      | Notes                                              |
|----------------------------|-------------|----------------------------------------------------|
| Streaming responses        | ✅ Done      | SSE endpoint, token-by-token, typing cursor        |
| Markdown rendering         | ✅ Done      | react-markdown, syntax highlight, copy-code        |
| Conversation context       | ✅ Done      | Last 20 msgs as history on every LLM call          |
| File / image uploads       | ✅ Done      | Backend storage + vision SSE stream                |
| Slash commands             | ✅ Done      | /help /clear /new /export /search /meeting /model  |
| Copy code button           | ✅ Done      | Clipboard icon on all code blocks                  |
| Multi-model selector       | ✅ Done      | 7 providers via litellm, per-user in-memory pref   |
| Meeting mode               | ✅ Done      | note/decided/action capture, .md export            |
| Message search             | ✅ Done      | ILIKE endpoint + SearchPanel with highlighting     |
| Conversation export        | ✅ Done      | /export → dated .md download                       |
| Message editing            | ⚠️ Partial   | Backend PATCH endpoint exists, no frontend UI      |
| Message reactions          | ⚠️ Partial   | WS event types defined, no backend handler         |
| Reply threading UI         | ⚠️ Partial   | DB + API supports it, no frontend thread component |
| Persistent memory          | ✅ Done      | DB-backed UserMemory, injected into system prompt  |
| Tool calling               | ✅ Done      | web_search (DDG/Brave), calculate (AST), get_datetime |
| Calendar integration       | ✅ Done      | CalDAV tools: list events, create event            |
| Task management            | ✅ Done      | create/list/complete tasks; room-scoped; /tasks cmd |
| Document summarisation     | ✅ Done      | PDF/DOCX/TXT/MD/CSV → text extract → LLM summary   |
| Proactive reminders        | ✅ Done      | Scheduler, set/list/cancel tools, recurring support |
| Email integration          | ✅ Done      | IMAP fetch/search + SMTP send; 3 LLM tools          |
| GitHub integration         | ✅ Done      | list_prs, get_pr, create_issue, get_ci_status        |
| Notion integration         | ✅ Done      | search, get page, create page — 3 LLM tools          |
| Confluence integration     | ✅ Done      | search, get page, create page — 3 LLM tools          |
| Slack bridge               | ✅ Done      | 3 outbound tools + inbound webhook (@mention → LLM)   |
| Read receipts              | ❌ Missing   | No seen/delivered tracking                         |
| Usage / cost tracking      | ❌ Missing   | No token counts or provider cost display           |

---

## Proposal: Sparkbot as an Office Worker Agent

The goal is to make Sparkbot a seamless **worker agent** — not just a chatbot, but an active participant in office workflows: taking notes, managing tasks, scheduling, searching, writing, and integrating with the tools a team actually uses.

### Vision

> A user opens a room, @mentions Sparkbot, and it understands context, takes action, remembers history, and integrates with the office stack — without needing to copy-paste between tools.

---

### Phase 1 — Make It Feel Like a Real AI Chat ✅ COMPLETE
*Completed 2026-03-05 (WO-03042026-1)*

| # | Feature               | Status | Detail                                                          |
|---|-----------------------|--------|-----------------------------------------------------------------|
| 1 | **Streaming responses** | ✅ | SSE endpoint, `AsyncOpenAI` stream, token-by-token to browser  |
| 2 | **Markdown rendering**  | ✅ | `react-markdown` in MessageBubble + SparkbotDmPage             |
| 3 | **Conversation context** | ✅ | Last 20 messages passed as OpenAI history on every call        |
| 4 | **Copy code button**    | ✅ | Clipboard icon on code blocks, flips to checkmark after copy   |
| 5 | **Fix/remove stubs**    | ✅ | Removed Paperclip, Image, Emoji, noop menu items               |

---

### Phase 2 — Core Office Productivity (2-4 weeks)
*The features that make it useful for actual work.*

| # | Feature                  | Detail                                                                      |
|---|--------------------------|-----------------------------------------------------------------------------|
| 6 | **Slash commands**        | `/help`, `/clear`, `/summarize`, `/model claude`, `/export`                |
| 7 | **File uploads**          | Backend storage (local or S3), multimodal forwarding to vision models      |
| 8 | **Message search**        | Full-text search across rooms with date + sender filters                   |
| 9 | **Conversation export**   | Download as Markdown or JSON                                                |
| 10 | **Meeting mode (finish)** | Activate via `/meeting start`, bot captures agenda/notes/decisions/actions |
| 11 | **Reply threads UI**      | Wire `reply_to_id` into frontend — threaded conversations per message      |

---

### Phase 3 — Agent Capabilities ✅ Partially Complete
*What separates a chatbot from a worker agent.*

| # | Feature                    | Status | Detail                                                                         |
|---|----------------------------|--------|--------------------------------------------------------------------------------|
| 12 | **Tool calling framework** | ✅ Done | web_search (Brave/DDG), calculate (AST), get_datetime                         |
| 13 | **Persistent memory**      | ✅ Done | DB-backed UserMemory, injected into system prompt, remember/forget tools       |
| 14 | **Web search reliability** | ✅ Done | Brave → SerpAPI → DDGS fallback chain, OpenClaw key bridge, TTL cache         |
| 15 | **Calendar integration**   | ✅ Done | CalDAV tools: list events, create events — works with Google, iCloud, Nextcloud |
| 16 | **Task/todo management**   | ✅ Done | create_task, list_tasks, complete_task tools + REST API + /tasks slash command |
| 17 | **Document summarisation** | ✅ Done | PDF/DOCX/TXT/MD/CSV text extraction → LLM summarisation via upload SSE stream |
| 18 | **Proactive reminders**    | ✅ Done | asyncio scheduler, set/list/cancel tools, recurring (daily/weekly), WS push  |

---

### Phase 4 — Office Stack Integration ⬜ In Progress
*Deep integrations that make Sparkbot irreplaceable in a team workflow.*

| # | Integration          | Status | What it enables                                                          |
|---|----------------------|--------|--------------------------------------------------------------------------|
| 19 | **Email (SMTP/IMAP)** | ✅ Done | fetch_inbox, search, send — 3 LLM tools, zero new deps                 |
| 20 | **GitHub / GitLab**   | ✅ Done | PR summaries, issue creation, CI status — 4 LLM tools via httpx       |
| 21 | **Notion / Confluence** | ✅ Done | search/get/create pages — 6 LLM tools (3 Notion + 3 Confluence)     |
| 22 | **Slack bridge**      | ✅ Done | 3 outbound tools + inbound webhook; @mentions → LLM → threaded reply  |
| 23 | **Multi-agent rooms** | ✅ Done | @mention routing; 4 agents (researcher/coder/writer/analyst); agent badge UI |
| 24 | **Audit log**         | ✅ Done | audit_logs table; recorded in llm.py; REST API; /audit slash command   |

---

### Architecture Change Needed for Agent Capabilities

The current flow is:

```
User message → FastAPI → HTTP POST to port 8080 → wait → full response
```

For true agent capabilities this needs to become:

```
User message → FastAPI → Agent orchestrator → Tool calls (parallel)
                                           → LLM with tool results
                                           → Streaming back to WebSocket
```

**Recommendation:** Migrate the bot routing layer from the Node.js service (port 8080) into the FastAPI backend using `litellm` (handles 100+ providers uniformly). This:
- Eliminates the fragile inter-process HTTP call
- Enables streaming natively
- Allows tool calling via the standard LLM function-calling API
- One codebase to maintain

---

## Priority Order (Security + Reliability Remediation Plan — 2026-03-05)

### Execution Rules
- Batch only one phase per deploy window.
- No feature work merges until Phase A + Phase B are complete.
- Every phase requires: tests passing, smoke checks passing, and rollback command prepared.
- Keep `sparkbot-v2` as source of truth; only backport to `sparkbot` if explicitly needed.

### Phase A — Critical Access Control + Secret Hygiene (P0)

**A1. Enforce room-level authorization on read endpoints**
- [x] Gate `GET /rooms/{room_id}` and `GET /rooms/{room_id}/members` by membership.
- [x] Verify non-members receive 403/404 and members still receive expected payloads.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/rooms.py`

**A2. Protect uploaded file serving**
- [x] Require auth + membership on `GET /rooms/{room_id}/uploads/{file_id}/{filename}`.
- [x] Prevent direct URL access by non-members.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/uploads.py`

**A3. Lock down audit log visibility**
- [x] Restrict `/chat/audit` and `/chat/audit/{id}` to room members (or OWNER/MOD/admin policy).
- [x] Ensure tool outputs from other rooms are not visible cross-tenant.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/audit.py`
  - `sparkbot-v2/backend/app/crud.py`

**A4. Remove unauthenticated write path**
- [x] Require `CurrentChatUser` for bot-integration message endpoints.
- [x] Remove fallback `uuid.uuid4()` sender creation path.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/bot_integration.py`

**A5. Secret incident response**
- [x] Remove tracked `.env` and `backend/.env` from git index (files remain local for testing).
- [x] Rewrite git history to purge previously committed secrets — `git filter-repo` removed `.env` + `backend/.env` from all 1,269 commits; force-pushed to GitHub 2026-03-05.
- [x] Create key rotation runbook with no-downtime order and rollback (`sparkbot-v2/ROTATION_RUNBOOK.md`).
- [ ] Rotate all keys: OpenAI, Anthropic, Google, Groq, MiniMax, Slack, Notion, Confluence, GitHub, email, CalDAV, JWT `SECRET_KEY`, DB password.
- [x] Add pre-commit/CI secret scanning gate.

**A-phase verification**
- [x] Authz regression tests for rooms/uploads/audit.
- [x] Negative tests: non-member access denied.
- [ ] Smoke: login, DM bootstrap, send/stream message, upload image/doc, audit command.

### Phase B — Authentication/Session Hardening (P0/P1)

**B1. Remove implicit chat-user auto-provisioning**
- [x] Delete auto-create logic from `get_current_chat_user`.
- [x] Only accept users already provisioned by bootstrap/admin flow.
- Files:
  - `sparkbot-v2/backend/app/api/deps.py`

**B2. Improve passphrase flow**
- [x] Stop issuing token with fixed `sub="phil"`.
- [x] Issue subject tied to real chat user identity (`chat_users.id`).
- [x] Add rate limiting for `/chat/users/login` similar to `/login/access-token`.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/users.py`
  - `sparkbot-v2/backend/app/core/security.py`

**B3. WebSocket boundary hardening**
- [x] Decommission or lock down generic `/chat/ws` endpoint.
- [x] Keep `/chat/ws/rooms/{room_id}` as primary path with membership checks.
- [x] Add message-size limit on inbound WS chat messages.
- [x] Add per-connection rate guard.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/websocket.py`

**B4. Slack webhook fail-closed in production**
- [x] Reject requests when `SLACK_SIGNING_SECRET` missing in non-local env.
- [x] Keep relaxed behavior only for local dev.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/slack.py`

**B-phase verification**
- [ ] Token claim validation tests (expired, wrong signature, wrong subject, missing claims).
- [ ] WS unauthorized + non-member connection tests.
- [ ] Slack signature validation tests.

### Phase C — Reliability and Runtime Correctness (P1)

**C1. Fix streaming route runtime bug**
- [x] Resolve `agent_content` use-before-assignment in `stream_room_message`.
- [ ] Add test covering plain message and `@agent` message paths.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/rooms.py`

**C2. Resolve route/CRUD name collisions**
- [x] Rename route functions that shadow imported CRUD function names.
- [x] Ensure internal calls reference CRUD helpers, not route handlers.
- Files:
  - `sparkbot-v2/backend/app/api/routes/chat/rooms.py`
  - `sparkbot-v2/backend/app/api/routes/chat/messages.py`

**C3. Align frontend/backend message contracts**
- [x] Standardize send response shape handling and update hooks accordingly.
- [x] Remove brittle optimistic assumptions in send mutation path.
- Files:
  - `sparkbot-v2/frontend/src/lib/chat/hooks.ts`
  - `sparkbot-v2/frontend/src/lib/chat/api.ts`
  - `sparkbot-v2/backend/app/api/routes/chat/rooms.py`

**C4. Remove hardcoded dotenv absolute path**
- [x] Delete `load_dotenv("/home/sparky/sparkbot-v2/backend/.env")`.
- [x] Use environment-first config and a single predictable env file path policy.
- Files:
  - `sparkbot-v2/backend/app/main.py`

**C-phase verification**
- [ ] SSE stream test suite including tool-calls and agent routing.
- [ ] Frontend integration test for send-message success/failure UX.
- [ ] Service restart test (startup/shutdown clean, reminders scheduler starts once).

### Phase D — Tool Safety, Data Governance, and Browser Security (P1/P2)

**D1. Side-effect tool confirmation policy (server-enforced)**
- [x] `WRITE_TOOLS` frozenset in `llm.py` — `email_send`, `slack_send_message`, `github_create_issue`, `notion_create_page`, `confluence_create_page`, `calendar_create_event`.
- [x] `_pending` in-memory dict with 10-min TTL; `consume_pending()` is one-time-use.
- [x] LLM stream paused at write-tool call: yields `{"type": "confirm_required", "confirm_id": "...", "tool": "...", "input": {...}}` and returns.
- [x] Frontend `ConfirmModal` with human-readable descriptions; on Confirm sends `confirm_id` in next POST; on Cancel shows system message.
- [x] `rooms.py` `StreamMessageRequest` handles `confirm_id` → `confirmed_stream()` executes tool directly.
- Files: `llm.py`, `rooms.py`, `SparkbotDmPage.tsx`

**D2. Audit log redaction**
- [x] `_redact_for_audit(tool_input, tool_result)` in `llm.py` — redacts JSON keys matching secret-name regex + known token patterns (OpenAI, Slack, GitHub, AWS, Notion).
- [x] All `create_audit_log()` calls now pass redacted values.
- Files: `llm.py`

**D3. Browser/session hardening**
- [x] `POST /chat/users/login` now sets `HttpOnly Secure SameSite=Strict Path=/api` cookie; response body contains `{"success": true}` only — no token.
- [x] `DELETE /chat/users/session` endpoint clears cookie on logout.
- [x] `deps.py` `get_current_chat_user` reads `request.cookies.get("chat_token")` first; falls back to `Authorization: Bearer` (old sessions keep working until expiry).
- [x] `websocket.py` checks `websocket.cookies.get("chat_token")` first; falls back to auth-message token.
- [x] Frontend: all fetches use `credentials: 'include'`; auth presence tracked in `sessionStorage.chat_auth`; no token in localStorage.
- [x] CSP + HSTS (HTTPS-only) + Permissions-Policy headers added to `_SecurityHeadersMiddleware`.
- Files: `main.py`, `deps.py`, `users.py`, `websocket.py`, `useAuth.ts`, `SparkbotDmPage.tsx`, `ChatPage.tsx`, `websocket.ts`

**D-phase verification**
- [ ] XSS regression tests around markdown rendering + token handling.
- [ ] Manual browser test: no bearer token visible in localStorage — confirm `chat_token` cookie is HttpOnly.
- [ ] Header validation: `curl -I https://remote.sparkpitlabs.com/` — verify CSP, HSTS, Permissions-Policy present.

### Phase E — Ops and CI Safety Net (P2)

- [x] Dependency scan CI: `.github/workflows/dep-scan.yml` — `pip-audit` + `npm audit` on push/PR/weekly Monday.
- [x] Secret scan: `gitleaks` pre-commit hook + CI gate already in place (Phase A).
- [x] Key rotation runbook: `ROTATION_RUNBOOK.md` expanded with git history cleanup steps and per-secret quick-reference table.
- [ ] Key rotation execution — pending; user will rotate all keys after active testing window closes.

### Suggested Work Order Sequence (Implementation)
1. A1 → A4 (authz and data exposure).
2. A5 (secret cleanup and rotation).
3. B1 → B4 (identity/session boundary).
4. C1 → C4 (runtime correctness).
5. D1 → D3 (tool governance and browser hardening).
6. E (CI and operational guardrails).

### Rollback Strategy (Per Phase)
- [ ] Tag before each phase (`security-phase-A-pre`, etc.).
- [ ] Keep DB migrations backward-compatible when possible.
- [ ] If smoke fails post-deploy: rollback tag + restart service + run health checks.

### Done Criteria for This Plan
- [x] No cross-room data access by non-members (rooms, messages, uploads, audit).
- [x] No unauthenticated message write path.
- [x] No fixed-subject passphrase identity.
- [ ] Streaming/chat/websocket test suite green.
- [x] Secret scanning + dependency scanning active in CI.
- [x] `.env` secrets purged from git history (force-pushed 2026-03-05).
- [ ] Production secrets rotated — pending (user will rotate when testing window closes).
