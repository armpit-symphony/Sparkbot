# Public Download Packaging

The public download page points users at the latest desktop release artifacts on GitHub. The packaging script in this repo is for reproducible source bundles and CLI/public download mirrors built from committed source.

For a release, keep these pieces aligned:

- `backend/pyproject.toml`
- `frontend/package.json`
- `src-tauri/tauri.conf.json`
- `docs/index.html`
- `README.md`
- `docs/release-notes/vX.Y.Z.txt`

The current governed Sparkbot + Robo OS control-plane release is `v1.6.39`.

## Public install choices

The GitHub Pages download copy should keep the install paths this simple:

**Windows**

1. Download the installer.
2. Open Sparkbot Controls.
3. Add a provider key or choose local Ollama.
4. Start chatting.

**Linux / Server**

```bash
git clone https://github.com/armpit-symphony/Sparkbot.git
cd Sparkbot
bash scripts/sparkbot-start.sh
```

Fresh Ubuntu with missing Docker plugins:

```bash
bash scripts/sparkbot-start.sh --install-docker-plugins
```

SSH troubleshooting:

```bash
bash scripts/sparkbot-start.sh --show-input
```

Paste-free env import:

```bash
export OPENAI_API_KEY="sk-..."
bash scripts/sparkbot-start.sh --from-env
```

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
  --ref desktop-v1.6.39 \
  --artifact-prefix sparkbot-1.6.39 \
  --output-dir dist/public-download/1.6.39
```

This ties the package to a specific tag or commit instead of the current `HEAD`.

## Add release notes text

```bash
bash scripts/package-public-download.sh \
  --notes-file docs/release-notes/v1.6.39.txt
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
