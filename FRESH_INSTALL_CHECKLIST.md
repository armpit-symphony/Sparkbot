# SparkBot Fresh-Install Test Checklist

> Use this to validate that SparkBot works end-to-end on a machine that has never run it before.
> Run each path independently. No operator knowledge. No shortcuts.
> Mark each item ✅ pass / ❌ fail / ⚠ partial — then log findings below each section.

---

## Pre-test setup

Before starting any path:

- [ ] Use a clean machine or VM with no SparkBot, no live .env, no running services
- [ ] Only the publicly published downloads from `sparkpitlabs.com/sparkbot`
- [ ] No access to the private operator instance at `remote.sparkpitlabs.com`
- [ ] Have the public SHA256SUMS file open for checksum verification

---

## Path A — Mac / Linux fresh install (browser UI)

### 1. Download

- [ ] Navigate to `sparkpitlabs.com/sparkbot`
- [ ] Click "Mac / Linux Download" — downloads `sparkbot-latest.tar.gz`
- [ ] Download `SHA256SUMS` from the same page or linked separately

### 2. Checksum

- [ ] Run: `sha256sum sparkbot-latest.tar.gz` (or `shasum -a 256` on macOS)
- [ ] Compare against value in SHA256SUMS
- [ ] Checksums match ✅ / mismatch ❌

### 3. Extract and launch

- [ ] `tar -xzf sparkbot-latest.tar.gz`
- [ ] `cd sparkbot-v2`
- [ ] `bash scripts/quickstart.sh` — exits without error
- [ ] Browser opens automatically, OR the terminal shows the local URL
- [ ] Page loads without 404 or blank screen

### 4. First-run — Controls opens

- [ ] Sparkbot Controls opens automatically on first visit (not the main workspace)
- [ ] No error banners or broken pages in Controls
- [ ] "Connect AI (cloud or local)" step is visible as step 1

### 5A. Local-model path (Ollama)

- [ ] AI Source selector shows Cloud / Local / Hybrid options
- [ ] Selecting "Local" shows the Ollama setup panel
- [ ] "Don't have an API key yet?" helper copy is visible
- [ ] Ollama server URL field defaults to `http://localhost:11434`
- [ ] "Check" button works — shows reachable or not-found state cleanly
- [ ] If Ollama not installed: amber warning box appears with install guidance
- [ ] If Ollama installed + no models: install commands for 3 tiers shown cleanly
- [ ] If Ollama installed + model present: tier card shows "Use this model" (green button)
- [ ] Clicking "Use this model" saves immediately (no separate Save step)
- [ ] Confirmation message appears in chat or UI
- [ ] Proceed to step 6

### 5B. Cloud-provider path

- [ ] AI Source = Cloud
- [ ] At least one provider (OpenAI, Anthropic, or Google) can be configured with a real key
- [ ] "Save" or equivalent applies the key
- [ ] Provider shows as configured (green/active indicator)
- [ ] Proceed to step 6

### 5C. Hybrid path

- [ ] AI Source = Hybrid
- [ ] Cloud provider configured with real key
- [ ] Local model also set via Ollama panel
- [ ] Verify heavy_hitter stays as cloud model (not overwritten by local)
- [ ] Proceed to step 6

### 6. First chat

- [ ] Dismiss or complete Controls — enter main workspace
- [ ] Type a simple message ("Hello, what can you do?")
- [ ] Response streams correctly
- [ ] No 500 errors, no blank response, no loading hang
- [ ] `/help` slash command responds
- [ ] `/model` shows current model or lets you switch

### 7. Restart behavior

- [ ] Stop the SparkBot server (Ctrl+C or kill quickstart process)
- [ ] Re-run `bash scripts/quickstart.sh`
- [ ] Controls does NOT open again (already configured)
- [ ] Previous model/provider config is preserved
- [ ] Can send a message immediately

### 8. Comms deferred

- [ ] Comms integrations (Telegram, Slack, Discord, etc.) are NOT required
- [ ] Skipping comms setup does not block or break core chat
- [ ] Comms can be configured later from Controls without issues

---

## Path B — Windows fresh install (browser UI)

### 1. Download

- [ ] Navigate to `sparkpitlabs.com/sparkbot`
- [ ] Click "Windows Download" — downloads `sparkbot-latest.zip`
- [ ] Download `SHA256SUMS`

### 2. Checksum

- [ ] Run: `Get-FileHash sparkbot-latest.zip -Algorithm SHA256 | Select-Object Hash`
- [ ] Compare against SHA256SUMS value
- [ ] Checksums match ✅ / mismatch ❌

### 3. Extract and launch

- [ ] Right-click ZIP → Extract All (or use your preferred extractor)
- [ ] Open PowerShell in the extracted `sparkbot-v2` folder
- [ ] Run: `.\scripts\quickstart.ps1`
- [ ] Script runs without fatal errors
- [ ] Browser opens or terminal shows local URL

### 4–8. Same as Path A steps 4–8

> Run through Controls, local or cloud setup, first chat, restart, comms-deferred.
> Note any Windows-specific issues (path separators, PowerShell permissions, Python version).

---

## Path C — CLI-only fresh install

### 1. Download

- [ ] Navigate to `sparkpitlabs.com/sparkbot`
- [ ] Download `sparkbot-cli.py` directly (no bundle needed)

### 2. Setup

- [ ] `python3 sparkbot-cli.py --setup`
- [ ] Prompts for SparkBot instance URL (user's own running instance)
- [ ] Prompts for passphrase
- [ ] Lists available providers and models
- [ ] User selects model tiers interactively
- [ ] Config saved to `~/.sparkbot/cli.json` (URL + passphrase only, no keys)
- [ ] Provider keys sent to and stored on user's own SparkBot instance

### 3. First chat

- [ ] `python3 sparkbot-cli.py`
- [ ] Chat session opens in terminal
- [ ] Type a message — response streams correctly
- [ ] `/model` command works to switch active model
- [ ] `/help` responds

### 4. Restart CLI

- [ ] Exit the CLI session
- [ ] Re-run `python3 sparkbot-cli.py`
- [ ] Previous config is remembered (no re-setup needed)

---

## Path D — Server install (headless)

### 1. Download and extract

- [ ] `curl -O https://sparkpitlabs.com/downloads/sparkbot/latest/sparkbot-latest.tar.gz`
- [ ] Checksum verified (same as Path A step 2)
- [ ] `tar -xzf sparkbot-latest.tar.gz && cd sparkbot-v2`

### 2. Configure server env

- [ ] `cp .env.example .env`
- [ ] Replace every `REPLACE_WITH_...` placeholder with real values
- [ ] At least one LLM provider key is configured
- [ ] `DATABASE_TYPE` is chosen intentionally (`sqlite` for single-node or `postgresql` for external DB)

### 3. Install the backend service

- [ ] Create the venv and install backend dependencies
- [ ] Copy `deploy/systemd/sparkbot-v2.service.example` into `/etc/systemd/system/sparkbot-v2.service`
- [ ] Service file paths and `User=` are updated for the target machine
- [ ] `systemctl enable --now sparkbot-v2` succeeds
- [ ] `curl http://127.0.0.1:8091/api/v1/utils/health-check/` returns healthy

### 4. Remote browser access

- [ ] Navigate to `http://<server-ip>:<port>` from another machine
- [ ] Controls opens on first visit
- [ ] Setup completes over remote browser (no local GUI required)

### 5. Cloud provider or local (server)

- [ ] Cloud path: provider key entered, model responds remotely
- [ ] Local path: note that Ollama must run on the same server; document if it's missing

### 6. Restart behavior (server)

- [ ] Kill and restart server process
- [ ] Config persists on restart
- [ ] Clients can reconnect without re-running setup

---

## Friction log

> After completing each path, write down anything that was confusing, missing, or broke.
> Be honest. Pretend you are the user, not the builder.

### Path A findings
```
(write here)
```

### Path B findings
```
(write here)
```

### Path C findings
```
(write here)
```

### Path D findings
```
(write here)
```

---

## Pass/fail summary

| Path | Result | Notes |
|------|--------|-------|
| A — Mac/Linux browser | | |
| B — Windows browser | | |
| C — CLI-only | | |
| D — Server headless | | |

---

## Next steps after testing

- Log all ❌ failures as GitHub issues or logbook entries
- Log all ⚠ partial items as polish tasks
- If any path is fully ✅, mark it as validated in the logbook
- Do not publish v1.1.0 until at least Path A and Path C are fully ✅
