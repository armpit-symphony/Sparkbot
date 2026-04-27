# Sparkbot — Troubleshooting Guide

Quick reference for the most common issues. Each section describes the symptom, the root cause, and the fix.

---

## Table of Contents

1. [Browser tools not working / "Executable doesn't exist"](#1-browser-tools-not-working--executable-doesnt-exist)
2. [Terminal shows "Not Found" when connecting](#2-terminal-shows-not-found-when-connecting)
3. [Windows SmartScreen blocks the installer](#3-windows-smartscreen-blocks-the-installer)
4. [Sparkbot says it can't do anything / tool errors](#4-sparkbot-says-it-cant-do-anything--tool-errors)
5. [Responses take 10+ minutes / tool loop](#5-responses-take-10-minutes--tool-loop)
6. [Ollama saturating CPU / system becomes unresponsive](#6-ollama-saturating-cpu--system-becomes-unresponsive)
7. [Slow responses — general triage](#7-slow-responses--general-triage)
8. [Sparkbot Controls doesn't save my API key](#8-sparkbot-controls-doesnt-save-my-api-key)
9. [Desktop app crashes on launch / blank screen](#9-desktop-app-crashes-on-launch--blank-screen)
10. [First-run checklist](#10-first-run-checklist)

---

## 1. Browser tools not working / "Executable doesn't exist"

**Symptom:** Asking Sparkbot to open a browser or visit a URL fails. The log shows:
```
browser_open failed: Executable doesn't exist at ...playwright-browsers\chromium-...\chrome.exe
```
or the browser_open tool just hangs for several minutes with no result.

**Root cause:** Chromium is downloaded once to a stable directory on first launch. If that directory was cleared, the app was moved, or the download was interrupted, Chromium is missing.

**Fix:**

Run the repair script:

```powershell
# Windows
powershell -ExecutionPolicy Bypass -File scripts\repair-playwright.ps1
```
```bash
# Linux / macOS
bash scripts/repair-playwright.sh
```

This installs Chromium to `%APPDATA%\Sparkbot\playwright-browsers` (Windows) or `~/.sparkbot/playwright-browsers` (Linux/macOS) — a stable location that survives app restarts and updates.

After the script finishes, restart Sparkbot. The first browser call after a fresh install takes 5–15 seconds while Chromium launches. Subsequent calls are faster.

**Manual fix (if script not available):**
```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$env:APPDATA\Sparkbot\playwright-browsers"
playwright install chromium
```

---

## 2. Terminal shows "Not Found" when connecting

**Symptom:** Clicking **Connect** in the terminal panel returns a 404 error or `{"detail": "Not Found"}`.

**Root cause:** The terminal router failed to register because `pywinpty` (the Windows PTY library) was not installed. This happens if:
- The app was built without `pywinpty` in the lock file
- The package failed to install during the build

**Fix (desktop app):** Download the latest installer — this was fixed in v1.2.5+. The `pywinpty` dependency is now in `uv.lock` and bundled correctly.

**Fix (self-hosted / development):**
```bash
cd backend
pip install pywinpty
# or with uv:
uv pip install pywinpty
```
Then restart the backend.

**To verify the terminal router is loaded**, check the backend log for:
```
INFO: terminal router registered
```
If it's missing, look for an import error above it in the log.

---

## 3. Windows SmartScreen blocks the installer

**Symptom:** After downloading the installer, Windows shows a blue dialog: *"Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting."*

**Root cause:** The installer is currently unsigned. Every new unsigned binary starts with zero SmartScreen reputation, regardless of content.

**Fix:** Click **More info**, then **Run anyway**. This is a one-time step per version.

**Why it's safe:** The installer is built from this open-source repository via GitHub Actions. You can inspect the build at `.github/workflows/desktop-release.yml` and verify the artifact SHA matches the release.

**Permanent fix (in progress):** We are applying for a free open-source code signing certificate via [SignPath Foundation](https://signpath.org/). Once active, the installer will pass SmartScreen automatically.

**If Unblock-File doesn't help:**
```powershell
# Right-click the .exe → Properties → check "Unblock" at the bottom
# Or:
Unblock-File -Path "Sparkbot.Local_x.x.x_x64-setup.exe"
```

---

## 4. Sparkbot says it can't do anything / tool errors

**Symptom:** You ask Sparkbot to run a command or open a browser and it replies "I'm unable to do that" or "I don't have the ability to control your computer."

**Common causes and fixes:**

**A — Computer Control is off or no PIN is configured (most common)**
Shell, terminal, browser-write, server, Vault, and comms-send tools require **Computer Control** to be on, or a break-glass PIN session to be active.
- In Sparkbot DM, open **Sparkbot Controls** and either enable **Computer Control** or set the 6-digit operator PIN.
- With Computer Control off, type `/breakglass`, enter the PIN, then resend or approve the waiting privileged action.

**B — Wrong model in stack**
Local models (especially Ollama) often produce malformed tool calls, causing them to fail silently or loop. The model tells Sparkbot it can't do anything when it can't format a valid tool call.
- Switch to an API model: `/model gpt-4o` or `/model claude-sonnet-4-5`
- Move Ollama to Backup 2 or remove it from the active stack

**C — Skill POLICY error (TypeError in log)**
A skill's POLICY dict has incorrect keys, causing a crash before any tool runs. Check the backend log for:
```
TypeError: ToolPolicy.__init__() got an unexpected keyword argument 'category'
```
Fix: update the skill's POLICY dict to use `scope`, `resource`, `default_action`, `action_type`, `high_risk`, `requires_execution_gate`.

**D — Guardian policy denying the tool**
Check the audit log (`/audit` in chat) to see if the tool was denied by policy. If `SPARKBOT_GUARDIAN_POLICY_ENABLED=true` and the tool isn't registered, it defaults to deny.

---

## 5. Responses take 10+ minutes / tool loop

**Symptom:** After asking Sparkbot to do something, it runs for 10+ minutes with no result. CPU stays high. Resetting the chat fixes it.

**Root cause:** The LLM retries a failing tool call up to 20 times. If the tool fails on every attempt (e.g., browser can't find Chromium, or a local model produces malformed tool calls), the loop runs to exhaustion.

**Immediate fix:** Click the stop button or start a new chat (`/new`).

**Root fixes:**
- **Browser loop** → fix Chromium install (see [section 1](#1-browser-tools-not-working--executable-doesnt-exist))
- **Local model loop** → switch to an API model (see [section 4B](#4-sparkbot-says-it-cant-do-anything--tool-errors))
- **General** → loop guards were added in v1.2.6: after 2 `shell_run` calls or 1 `browser_open`+`browser_snapshot`, the LLM is forced to stop retrying. Update to v1.2.6+ if on an older version.

---

## 6. Ollama saturating CPU / system becomes unresponsive

**Symptom:** After running an Ollama-backed model, your system fan spins up, the UI becomes sluggish, and CPU stays at 80–100%.

**Root cause:** Ollama loads large model weights into memory and uses all available CPU threads for inference. It does not yield to other processes.

**Fixes:**

**A — Lower Ollama process priority (Windows)**
```powershell
# Find the Ollama process ID, then set to BelowNormal priority
$proc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($proc) {
    $proc.PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
    Write-Host "Ollama priority lowered"
}
```

**B — Limit Ollama thread count**
Set this in your environment before launching Ollama:
```
OLLAMA_NUM_THREAD=4    # limit to 4 CPU threads (default = all cores)
```

**C — Move Ollama out of the active tool-call stack**
Ollama models are not reliable for tool calling — they frequently produce malformed JSON and cause loops (see section 5). Keep Ollama as a fallback for simple chat only:
- Set Primary / Backup 1 to API models (GPT, Claude, Gemini)
- Set Backup 2 or Heavy Hitter to Ollama if you want it available
- Avoid Ollama in any position where it will be asked to call tools

**D — Pause Ollama when not in use**
```powershell
# Stop Ollama service
Stop-Service -Name "Ollama" -ErrorAction SilentlyContinue
# or kill the process
Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
```
Restart it when you need local model inference.

---

## 7. Slow responses — general triage

Work through these in order:

| Check | How |
|-------|-----|
| Which model is active? | Type `/model` — API models (GPT, Claude) respond in 2–10s; local models can take 30–120s |
| Is the backend running? | `curl http://127.0.0.1:8000/api/v1/utils/health-check/` should return `true` |
| Is the backend log showing errors? | Desktop: `%LOCALAPPDATA%\Sparkbot Local\sparkbot-backend.log` |
| Is CPU at 100%? | Check Task Manager — Ollama or chrome processes may be saturating it |
| Is the tool looping? | Check the log for repeated `tool_call:` lines with the same tool name |
| Is a provider down? | Check [status.openai.com](https://status.openai.com) / [anthropicstatus.com](https://www.anthropicstatus.com) |

**Log locations:**

| Platform | Log path |
|----------|---------|
| Windows desktop | `%LOCALAPPDATA%\Sparkbot Local\sparkbot-backend.log` |
| Self-hosted systemd | `journalctl -u sparkbot-v2 -n 100` |
| Docker | `docker compose logs -f backend` |

---

## 8. Sparkbot Controls doesn't save my API key

**Symptom:** You paste an API key in Controls, click Save, but the model still says the key isn't configured.

**Fixes:**

- **Desktop app:** Keys are saved to `%APPDATA%\Sparkbot\.env`. Verify the file exists and contains your key after saving. Restart Sparkbot after the first key save.
- **Self-hosted:** Keys go into the repo-root `.env` file. After editing, restart the backend:
  ```bash
  sudo systemctl restart sparkbot-v2
  # or
  docker compose restart backend
  ```
- **Key format:** Make sure there are no leading/trailing spaces and the key starts with the correct prefix (`sk-` for OpenAI, `sk-ant-` for Anthropic).

**To verify the key is loaded**, ask Sparkbot: *"What providers are you configured with?"* — it will report its live stack from the backend.

---

## 9. Desktop app crashes on launch / blank screen

**Symptom:** The app window opens and immediately closes, or shows a blank white/black screen.

**Step 1 — Check the crash log:**
```
%LOCALAPPDATA%\Sparkbot Local\sparkbot-backend-crash.txt
```
This file captures the Python traceback if the backend crashes before the server starts.

**Step 2 — Check the backend log:**
```
%LOCALAPPDATA%\Sparkbot Local\sparkbot-backend.log
```
Look for `ERROR` or `CRITICAL` lines near the bottom.

**Common causes:**

| Symptom in log | Fix |
|----------------|-----|
| `Address already in use` on port 8000 | Another process is using port 8000. Kill it or change `--port` in the Tauri config. |
| `ModuleNotFoundError` | The PyInstaller bundle may be corrupt. Reinstall the app. |
| `alembic.util.exc.CommandError` | DB migration issue. Delete `sparkbot.db` from `%APPDATA%\Sparkbot\` and restart. |
| SSL / certificate error | Certifi bundle issue. Check `SSL_CERT_FILE` env var points to a valid cert file. |

**Step 3 — Clean reinstall:**
1. Uninstall via Add/Remove Programs
2. Delete `%APPDATA%\Sparkbot\` (backs up your `.env` first — it contains your API keys)
3. Download and reinstall the latest version

---

## 10. First-Run Checklist

Complete this in order on a fresh install:

- [ ] **Download and install** from [sparkpitlabs.com](https://armpit-symphony.github.io/Sparkbot/)
- [ ] **SmartScreen warning** — click More info → Run anyway (unsigned installer, safe to proceed)
- [ ] **Launch Sparkbot** — it opens Sparkbot Controls automatically on first run
- [ ] **Add at least one API key** — OpenAI, Anthropic, Google, Groq, or OpenRouter
- [ ] **Save and wait** — the backend restarts with your key; wait ~5 seconds
- [ ] **Click the Sparkbot desk** on the office floor to open the main chat
- [ ] **Test basic chat** — *"What's today's date?"* should get an instant response
- [ ] **Test web search** — *"Search for today's AI news"*
- [ ] **Test shell** — *"Run `echo Hello from Sparkbot` in PowerShell"*
- [ ] **Test browser** — *"Open google.com"* (first call downloads Chromium if needed — allow 2–5 minutes)
- [ ] **Set up a morning briefing** — *"Schedule a morning briefing every day at 8am"*

**If any step fails**, find the relevant section above and follow the fix. If it's not covered here, check `sparkbot-backend.log` and open an issue at [github.com/armpit-symphony/Sparkbot](https://github.com/armpit-symphony/Sparkbot/issues).

---

*Last updated: April 2026 — v1.2.6*
