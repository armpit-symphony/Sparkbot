# Sparkbot systemd single-node install

This is the simplest production-ish server profile in the repo. It matches the
working server layout closely:

- repo checked out at `/home/youruser/sparkbot-v2`
- backend launched by `systemd`
- environment loaded from repo-root `.env`
- uvicorn bound to `127.0.0.1:8091`
- nginx or another reverse proxy terminates TLS in front

## 1. Prepare the repo

```bash
git clone https://github.com/armpit-symphony/Sparkbot.git
cd Sparkbot
SPARKBOT_SETUP_SKIP_COMPOSE_CHECK=1 \
SPARKBOT_ENV_FILE=.env \
SPARKBOT_ENV_TEMPLATE=.env.example \
  bash scripts/sparkbot-setup.sh
```

The wizard creates `.env`, prompts for provider keys or a local Ollama model,
and avoids printing secrets. If SSH hidden input makes paste feedback unclear,
add `--show-input`. To import exported shell keys, add `--from-env`. Advanced
users may still edit `.env` directly. For a production public hostname, confirm
these values before starting systemd:

```env
ENVIRONMENT=production
FRONTEND_HOST=https://chat.example.com
BACKEND_CORS_ORIGINS=https://chat.example.com
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
