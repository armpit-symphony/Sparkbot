# Privacy & Data Retention — Sparkbot

Sparkbot is self-hosted software. You run it on your own computer, server, or homelab. Sparkpitlabs does not have access to your data, your conversations, or your API keys.

---

## What Sparkbot stores (on your machine)

| Data | Where | Kept until |
|------|-------|------------|
| Chat messages | PostgreSQL database (your machine) | You delete the room or the database |
| Tasks and reminders | PostgreSQL database (your machine) | You delete them or they fire and expire |
| Meeting notes and exports | PostgreSQL database + optional `.md` exports | You delete them |
| Uploaded files | `/uploads/` folder on your machine | You delete them manually |
| Audit logs (tool call records) | PostgreSQL database (your machine) | No automatic expiry — delete manually |
| Guardian decision journal | `data/guardian/executive/decisions/` on your machine | No automatic expiry — delete manually |
| Bridge state (Telegram/Discord/WhatsApp/GitHub) | SQLite sidecar files on your machine | Persists until you delete the file |

## What leaves your machine

- **Your prompts and conversation context** are sent to the AI provider (OpenAI, Anthropic, Google, etc.) whose API key you configured. Each provider has its own privacy policy.
- **Tool calls** (web search, Gmail, Drive, Calendar, Slack, GitHub, etc.) are executed using credentials you supplied. Data passes from the integration directly to Sparkbot on your machine — not through any Sparkpitlabs server.
- **Nothing** is sent to Sparkpitlabs.

## API keys and tokens

- API keys are stored in your `.env` file (or environment variables) on your machine.
- Keys entered through the UI are saved to your `.env` and never echoed back to the browser.
- Keys are **never** committed to git (`.env` is gitignored; a `gitleaks` pre-commit hook is active).
- Audit logs redact secret-pattern values before writing, so keys do not appear in logs even if accidentally passed as tool arguments.

## Comms integrations (Telegram, Discord, WhatsApp, GitHub)

Each comms bridge stores only a mapping between an external chat ID and a Sparkbot room ID. No message content from these platforms is stored beyond what you send through the Sparkbot chat interface, which is stored locally in your PostgreSQL database.

## Deletion

To permanently delete your data, delete the PostgreSQL database and the `data/` and `uploads/` directories. There is no remote copy.

## Questions

Open an issue at [github.com/sparkpitlabs/sparkbot](https://github.com/sparkpitlabs/sparkbot).
