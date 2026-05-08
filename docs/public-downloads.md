# Public Download Packaging

The public download page points users at the latest desktop release artifacts on GitHub. The packaging script in this repo is for reproducible source bundles and CLI/public download mirrors built from committed source.

For a release, keep these pieces aligned:

- `backend/pyproject.toml`
- `frontend/package.json`
- `src-tauri/tauri.conf.json`
- `docs/index.html`
- `README.md`
- `docs/release-notes/vX.Y.Z.txt`

The current Sparkbot release is `v1.6.64`.

## Public install choices

The GitHub Pages download copy should keep the install paths this simple:

**Windows**

1. Download the installer.
2. Open Sparkbot Controls.
3. Add a provider key or choose local Ollama.
4. Start chatting.

**Linux local machine**

```bash
git clone https://github.com/armpit-symphony/Sparkbot.git
cd Sparkbot
bash scripts/sparkbot-start.sh --local
```

**Cloud server / VPS**

```bash
git clone https://github.com/armpit-symphony/Sparkbot.git
cd Sparkbot
bash scripts/sparkbot-start.sh --server
```

Server mode prompts for a private passphrase before startup, disables local
auto-login, saves the passphrase to `.env.local`, and will not print it. Hidden
passphrase input falls back to visible input when an SSH terminal cannot accept
hidden typing or paste. Do not expose Sparkbot without that passphrase gate or
reverse proxy authentication.

Server operators who want the **OpenAI Codex Subscription** provider can sign in
with the Codex CLI on the host, then run Compose with the optional override:

```bash
codex login --device-auth
codex login status
docker compose -f compose.local.yml -f compose.codex.yml up -d --build
```

The override mounts only `auth.json` read-only into the backend container. Set
`SPARKBOT_CODEX_AUTH_FILE=/absolute/path/to/auth.json` first if the host Codex
auth file is not at `$HOME/.codex/auth.json`.

Fresh Ubuntu with missing Docker plugins:

```bash
bash scripts/sparkbot-start.sh --install-docker-plugins
```

SSH troubleshooting:

```bash
bash scripts/sparkbot-start.sh --server --hide-input
```

Provider key prompts are visible by default so SSH paste works reliably. Use
`--hide-input` only if you prefer hidden provider-key entry. The passphrase
prompt remains hidden by default.

Paste-free env import for SSH servers:

```bash
export OPENAI_API_KEY="sk-..."
export SPARKBOT_PASSPHRASE="long-private-passphrase"
bash scripts/sparkbot-start.sh --server --from-env
```

Passphrase and dry-run helpers:

```bash
bash scripts/sparkbot-start.sh --server --show-passphrase-input
bash scripts/sparkbot-start.sh --server --dry-run-setup
bash scripts/sparkbot-start.sh --server --openai-key "sk-..." --passphrase "long-private-passphrase"
```

Custom frontend port:

```bash
SPARKBOT_FRONTEND_PORT=3001 bash scripts/sparkbot-start.sh --server
```

Normal users should use `scripts/sparkbot-start.sh`. Raw Docker Compose is an advanced path because Compose interpolation reads root `.env`, while the launcher also manages `.env.local`, bind mode, port fallback, setup checks, and detached startup.

**CLI**

```bash
python3 sparkbot-cli.py --setup
python3 sparkbot-cli.py
```

## Build `latest`

```bash
bash scripts/package-public-download.sh
```

Default output:

- `dist/public-download/latest/sparkbot-latest.tar.gz`
- `dist/public-download/latest/sparkbot-latest.zip`
- `dist/public-download/latest/sparkbot-cli.py`
- `dist/public-download/latest/SHA256SUMS`
- `dist/public-download/latest/RELEASE-NOTES.txt`

## Publish to the website download directory

```bash
bash scripts/package-public-download.sh \
  --publish-dir /var/www/sparkpitlabs.com/downloads/sparkbot/latest
```

If the target directory needs elevated permissions, run the script from a shell with the necessary access. The GitHub Pages download page itself is committed at `docs/index.html` and published by the Pages workflow.

## Build a versioned release

```bash
bash scripts/package-public-download.sh \
  --ref desktop-v1.6.64 \
  --artifact-prefix sparkbot-1.6.64 \
  --output-dir dist/public-download/1.6.64
```

This ties the package to a specific tag or commit instead of the current `HEAD`.

## Add release notes text

```bash
bash scripts/package-public-download.sh \
  --notes-file docs/release-notes/v1.6.64.txt
```

The script always stamps `RELEASE-NOTES.txt` with:

- version from `backend/pyproject.toml` unless overridden
- git ref used for packaging
- exact commit hash
- build timestamp

If `--notes-file` is provided, its plaintext body is appended under `Release notes:`.

## Reproducibility rules

- Packaging source is exported with `git archive`, so the bundle is built from committed source, not local junk
- Internal-only docs are removed from the staged public bundle
- Backup files, Python bytecode, cache directories, `node_modules`, and `dist` are excluded
- `SHA256SUMS` is regenerated on every run

For public download provenance, package from a tag or commit with `--ref` and keep the generated `RELEASE-NOTES.txt` and `SHA256SUMS` alongside the published artifacts.
