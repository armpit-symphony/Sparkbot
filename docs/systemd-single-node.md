# Sparkbot systemd single-node install

This is the simplest production-ish server profile in the repo. It matches the
working server layout closely:

- repo checked out at `/home/youruser/sparkbot-v2`
- backend launched by `systemd`
- environment loaded from repo-root `.env`
- uvicorn bound to `127.0.0.1:8091`
- nginx or another reverse proxy terminates TLS in front

## 1. Prepare the repo

If you want the guided Docker/server path instead of managing systemd by hand,
use `bash scripts/sparkbot-start.sh --server`; it handles `.env.local`, provider
setup, bind mode, port fallback, and detached Compose startup. Continue below
only when you want the manual systemd profile.

```bash
git clone https://github.com/armpit-symphony/Sparkbot.git
cd Sparkbot
SPARKBOT_SETUP_SKIP_COMPOSE_CHECK=1 \
SPARKBOT_ENV_FILE=.env \
SPARKBOT_ENV_TEMPLATE=.env.example \
  bash scripts/sparkbot-setup.sh
```

The wizard creates `.env`, prompts for provider keys or a local Ollama model,
and avoids printing stored secrets itself. Provider key prompts are visible by
default so SSH paste works reliably; add `--hide-input` only if you prefer
hidden provider-key entry. To import exported shell keys without prompts, add
`--from-env`. Advanced users may still edit `.env` directly. For a production
public hostname, confirm these values before starting systemd:

```env
ENVIRONMENT=production
FRONTEND_HOST=https://chat.example.com
BACKEND_CORS_ORIGINS=https://chat.example.com
BACKEND_WORKERS=2
WORKSTATION_LIVE_TERMINAL_ENABLED=false
SECRET_KEY=REPLACE_WITH_RANDOM_64_HEX
FIRST_SUPERUSER_PASSWORD=REPLACE_WITH_ADMIN_PASSWORD
SPARKBOT_PASSPHRASE=REPLACE_WITH_STRONG_PASSPHRASE
DATABASE_TYPE=sqlite
SPARKBOT_DATA_DIR=/home/youruser/sparkbot-v2/backend/data
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
GROQ_API_KEY=
MINIMAX_API_KEY=
OPENROUTER_API_KEY=
```

Set at least one LLM provider key or an Ollama model before expecting chat responses.

OpenAI Codex subscription routing can use a ChatGPT sign-in instead of
`OPENAI_API_KEY`. Install the Codex CLI for the service user, sign in, and keep
`CODEX_HOME` pointing at that user's Codex directory:

```bash
codex login --device-auth
codex login status
```

For systemd, add these to the service environment if the defaults do not match
your user:

```env
CODEX_HOME=/home/youruser/.codex
SPARKBOT_CODEX_WORKDIR=/tmp
```

Then choose **OpenAI Codex Subscription** in Controls with
`openai-codex/gpt-5.3-codex`. Docker installs should prefer
`compose.codex.yml` from `deployment.md`, which mounts only `auth.json`
read-only into the backend container.

Use 2 web/API workers for v1. Do not increase until background jobs are
leader-locked and load-tested. Live terminal is raw shell access; keep it
disabled on public deployments unless the instance is private and operator-only.

## 2. Create the backend venv

```bash
python3 -m venv backend/venv
./backend/venv/bin/pip install --upgrade pip
./backend/venv/bin/pip install -e ./backend
```

Optional browser tooling:

```bash
./backend/venv/bin/python -m playwright install chromium
```

## 3. Install the service

```bash
sudo cp deploy/systemd/sparkbot-v2.service.example /etc/systemd/system/sparkbot-v2.service
sudoedit /etc/systemd/system/sparkbot-v2.service
sudo systemctl daemon-reload
sudo systemctl enable --now sparkbot-v2
```

Update the example paths and `User=` before starting it.

## 4. Verify

```bash
systemctl status sparkbot-v2
curl http://127.0.0.1:8091/api/v1/utils/health-check/
```

If you are serving the browser UI publicly, build the frontend separately and
proxy `/api/` and `/ws/` to the backend service. For the full Traefik + Docker
Compose path, see `deployment.md`.

For an API subdomain such as `api.sparkpitlabs.com`, first create DNS pointing
the subdomain to the server. Then configure nginx to proxy to the private
backend:

```nginx
server {
    server_name api.sparkpitlabs.com;

    location / {
        proxy_pass http://127.0.0.1:8091;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Issue TLS only after DNS resolves:

```bash
sudo certbot --nginx -d api.sparkpitlabs.com
curl -f https://api.sparkpitlabs.com/api/v1/utils/health-check/
```
