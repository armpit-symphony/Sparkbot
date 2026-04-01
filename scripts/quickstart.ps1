# Sparkbot Quick Start — Windows (PowerShell)
#
# Starts Sparkbot on your local machine using Docker Desktop.
# After running this script, open http://localhost:3000
#
# Usage (run in PowerShell as normal user):
#   .\scripts\quickstart.ps1
#
# To set an API key before starting:
#   $env:OPENAI_API_KEY = "sk-..."
#   .\scripts\quickstart.ps1
#
# Or create .env.local from the template first:
#   Copy-Item .env.local.example .env.local   (then edit .env.local with your keys)

# ── checks ────────────────────────────────────────────────────────────────────

$ErrorActionPreference = "Stop"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "Docker is required but not found."
    Write-Host "Install Docker Desktop from: https://docs.docker.com/get-docker/"
    Write-Host ""
    exit 1
}

try {
    docker info | Out-Null
} catch {
    Write-Host ""
    Write-Host "Docker daemon is not running. Please start Docker Desktop and try again."
    Write-Host ""
    exit 1
}

# ── API key prompt ─────────────────────────────────────────────────────────────

$hasKey = $env:OPENAI_API_KEY -or $env:ANTHROPIC_API_KEY -or `
          $env:GOOGLE_API_KEY -or $env:GROQ_API_KEY
$hasEnvLocal = Test-Path ".env.local"

if (-not $hasKey -and -not $hasEnvLocal) {
    Write-Host ""
    Write-Host "No LLM API key found. At least one is required."
    Write-Host "Press Enter to skip and add keys to .env.local later."
    Write-Host ""
    $inputKey = Read-Host "  OpenAI API key (sk-...)"
    if ($inputKey) {
        $env:OPENAI_API_KEY = $inputKey
    }
    Write-Host ""
}

# ── personal vs office mode ────────────────────────────────────────────────────

Write-Host "How will you use Sparkbot?"
Write-Host "  1. Personal assistant (default) — actions run freely, no confirmation gates"
Write-Host "  2. Office / team                — full Guardian policy with confirmation gates"
Write-Host ""
$_modeChoice = Read-Host "  Choice [1]"
Write-Host ""

if ($_modeChoice -eq "2") {
    $env:SPARKBOT_GUARDIAN_POLICY_ENABLED = "true"
    Write-Host "Office mode selected: Guardian policy enforcement enabled."
} else {
    $env:SPARKBOT_GUARDIAN_POLICY_ENABLED = "false"
    Write-Host "Personal mode selected: no confirmation gates."
}
Write-Host ""

# Write the mode to .env.local so it persists across restarts
if (-not (Test-Path ".env.local")) { New-Item ".env.local" -ItemType File | Out-Null }
$envContent = Get-Content ".env.local" -ErrorAction SilentlyContinue | Where-Object { $_ -notmatch "^SPARKBOT_GUARDIAN_POLICY_ENABLED=" }
$envContent + "SPARKBOT_GUARDIAN_POLICY_ENABLED=$($env:SPARKBOT_GUARDIAN_POLICY_ENABLED)" | Set-Content ".env.local"

# ── generate secret key if not set ────────────────────────────────────────────

if (-not $env:SECRET_KEY) {
    $bytes = New-Object Byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $env:SECRET_KEY = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLower()
}

# ── start ─────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Starting Sparkbot..."
Write-Host ""

docker compose -f compose.local.yml up --build -d

Write-Host ""
Write-Host "Sparkbot is running!"
Write-Host ""
Write-Host "  Web UI:    http://localhost:3000"
Write-Host "  API:       http://localhost:8000"
Write-Host "  API docs:  http://localhost:8000/docs"
Write-Host ""
Write-Host "Default passphrase: sparkbot-local"
Write-Host "  (set SPARKBOT_PASSPHRASE in .env.local to change)"
Write-Host ""
Write-Host "CLI chat:"
Write-Host "  python sparkbot-cli.py"
Write-Host ""
Write-Host "To stop:      docker compose -f compose.local.yml down"
Write-Host "To view logs: docker compose -f compose.local.yml logs -f backend"
Write-Host ""
