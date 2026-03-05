# Sparkbot Secret Rotation Runbook

This runbook defines a low-risk sequence for rotating secrets in `sparkbot-v2` without breaking your current remote chat login/testing flow.

## Current Constraint

During your active test window:

- Keep `SPARKBOT_PASSPHRASE` unchanged.
- Keep `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD` unchanged.

Rotate those only after you confirm test completion.

## Scope

Secrets to rotate:

- LLM/API keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GROQ_API_KEY`, `MINIMAX_API_KEY`
- Integrations: `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `NOTION_TOKEN`, `CONFLUENCE_API_TOKEN`, `GITHUB_TOKEN`
- Office channels: `EMAIL_IMAP_PASSWORD`, `EMAIL_SMTP_PASSWORD`, `CALDAV_PASSWORD`
- Platform: `SECRET_KEY`, `POSTGRES_PASSWORD`

## Pre-Rotation Checklist

1. Confirm clean deploy state and active service health:
   - `curl -fsS https://remote.sparkpitlabs.com/api/v1/utils/health-check/`
2. Export current environment snapshot (private, local only).
3. Prepare rollback snapshot of current service env file.
4. Ensure incident contacts are available for key owners (Slack/GitHub/Notion/etc).

## Rotation Order (Safe Sequence)

1. Rotate third-party read/write integration keys first:
   - Slack, GitHub, Notion, Confluence, Email, CalDAV
2. Rotate model provider keys:
   - OpenAI, Anthropic, Google, Groq, MiniMax
3. Rotate platform secrets:
   - `POSTGRES_PASSWORD` (with DB/user update plan)
   - `SECRET_KEY` (JWT signing key; forces token refresh/re-login)
4. Rotate auth credentials after testing window:
   - `SPARKBOT_PASSPHRASE`
   - `FIRST_SUPERUSER_PASSWORD`

## Per-Secret Procedure

For each secret:

1. Generate new credential in upstream provider.
2. Update backend runtime env.
3. Restart service:
   - `sudo systemctl restart sparkbot-v2`
4. Validate:
   - Health check endpoint returns success.
   - One real integration smoke test succeeds.
5. Revoke old credential in upstream provider.

Do not rotate more than one provider class at once.

## Validation Matrix

- Core platform:
  - Login works
  - `/api/v1/chat/users/bootstrap` works
  - `/api/v1/chat/rooms/{id}/messages/stream` works
- Tool integrations:
  - Web search
  - Slack send/list
  - GitHub PR list
  - Notion search
  - Confluence search
  - Email fetch
  - Calendar list
- Audit:
  - `/api/v1/chat/audit?room_id=<room_uuid>` returns room-scoped entries

## Rollback

If any rotation breaks production:

1. Restore previous env snapshot.
2. Restart service:
   - `sudo systemctl restart sparkbot-v2`
3. Re-run health check and login smoke.
4. Pause further rotations and record failing provider.

## Post-Rotation Tasks

1. Invalidate stale sessions after `SECRET_KEY` rotation.
2. Confirm all clients re-authenticate cleanly.
3. Update secure secret inventory with new issue/expiry dates.
4. Close A5 checklist items in `LOGBOOK_handoff.md`.

---

## Git History Cleanup (purge committed .env files)

**WARNING: force-push permanently rewrites git history. Coordinate with all contributors first.**

### Step 1 — Confirm secrets were committed

```bash
git log --all --oneline -- .env backend/.env
```

If no output: nothing to purge. Stop here.

### Step 2 — Rewrite history using git filter-repo (preferred)

```bash
pip install git-filter-repo
git filter-repo --path .env --invert-paths --force
git filter-repo --path backend/.env --invert-paths --force
```

Or with BFG Repo Cleaner (requires Java):

```bash
java -jar bfg.jar --delete-files .env
java -jar bfg.jar --delete-files backend/.env
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

### Step 3 — Force push (REQUIRES explicit approval from repo owner)

```bash
git push --force --tags origin main
```

⚠️ **Before running this step**, confirm:
- All collaborators have committed and pushed their local branches
- CI is paused or aware of the rewrite
- You have a backup of the current state

### Step 4 — Post-cleanup

1. Immediately rotate ALL secrets that were in the committed file (see Per-Secret Procedure above).
2. Revoke the old credentials — they are now in the hands of anyone who cloned the repo.
3. Ask GitHub support to purge the cached views of the removed commits if the repo is public.
4. Add `.env` and `backend/.env` to `.gitignore` if not already present.

### Per-secret rotation quick-reference

| Secret | Provider dashboard |
|--------|-------------------|
| `OPENAI_API_KEY` | platform.openai.com → API keys |
| `ANTHROPIC_API_KEY` | console.anthropic.com → API keys |
| `GOOGLE_API_KEY` | console.cloud.google.com → Credentials |
| `GROQ_API_KEY` | console.groq.com → API keys |
| `MINIMAX_API_KEY` | minimaxi.com → API keys |
| `SLACK_BOT_TOKEN` | api.slack.com → Your Apps → OAuth |
| `SLACK_SIGNING_SECRET` | api.slack.com → Your Apps → Basic Info |
| `NOTION_TOKEN` | notion.so → Settings → Integrations |
| `CONFLUENCE_API_TOKEN` | id.atlassian.com → Security → API tokens |
| `GITHUB_TOKEN` | github.com → Settings → Developer Settings → PATs |
| `EMAIL_IMAP_PASSWORD` | Email provider account settings |
| `EMAIL_SMTP_PASSWORD` | Email provider account settings |
| `CALDAV_PASSWORD` | CalDAV provider account settings |
| `SECRET_KEY` | Generate: `python3 -c "import secrets; print(secrets.token_hex(64))"` |
| `POSTGRES_PASSWORD` | `ALTER USER sparkbot WITH PASSWORD 'newpassword';` (restart service after) |
| `SPARKBOT_PASSPHRASE` | Update `backend/.env`, restart `sparkbot-v2.service` |
