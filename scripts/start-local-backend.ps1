# Sparkbot v1 Local — bare-metal backend startup (Windows)
#
# Starts the Sparkbot backend without Docker using SQLite.
# Requires: Python 3.10+ and uv (https://docs.astral.sh/uv/)
#
# Usage (PowerShell):
#   .\scripts\start-local-backend.ps1
#   .\scripts\start-local-backend.ps1 -ApiPort 8001
#
# On first run: creates the SQLite database and seeds the first superuser.
# On subsequent runs: database is reused; migrations are applied if needed.
#
# To install uv (run once):
#   winget install --id=astral-sh.uv -e
#   (or download from https://docs.astral.sh/uv/getting-started/installation/)

param(
    [int]$ApiPort = 8000
)

$ErrorActionPreference = "Stop"

$ScriptDir  = $PSScriptRoot
$RepoRoot   = Split-Path $ScriptDir -Parent
$BackendDir = Join-Path $RepoRoot "backend"

# ── Locate uv ─────────────────────────────────────────────────────────────────
$UV = $null
if (Get-Command uv -ErrorAction SilentlyContinue) {
    $UV = "uv"
} elseif (Test-Path "$env:USERPROFILE\.local\bin\uv.exe") {
    $UV = "$env:USERPROFILE\.local\bin\uv.exe"
} elseif (Test-Path "$env:LOCALAPPDATA\Programs\uv\uv.exe") {
    $UV = "$env:LOCALAPPDATA\Programs\uv\uv.exe"
} else {
    Write-Host ""
    Write-Host "ERROR: uv not found. Install it with:"
    Write-Host "  winget install --id=astral-sh.uv -e"
    Write-Host "  (or: https://docs.astral.sh/uv/getting-started/installation/)"
    Write-Host ""
    exit 1
}

# ── Auto-generate a SECRET_KEY if not set ─────────────────────────────────────
if (-not $env:SECRET_KEY) {
    $bytes = New-Object Byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $env:SECRET_KEY = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLower()
}

# ── V1 Local environment ──────────────────────────────────────────────────────
$env:V1_LOCAL_MODE                      = "true"
$env:DATABASE_TYPE                      = "sqlite"
$env:WORKSTATION_LIVE_TERMINAL_ENABLED  = "false"
$env:ENVIRONMENT                        = "local"
if (-not $env:PROJECT_NAME) { $env:PROJECT_NAME = "Sparkbot" }

# ── Data directory ────────────────────────────────────────────────────────────
if (-not $env:SPARKBOT_DATA_DIR) {
    $env:SPARKBOT_DATA_DIR = Join-Path $env:APPDATA "Sparkbot"
}
if (-not $env:SPARKBOT_GUARDIAN_DATA_DIR) {
    $env:SPARKBOT_GUARDIAN_DATA_DIR = Join-Path $env:SPARKBOT_DATA_DIR "guardian"
}
New-Item -ItemType Directory -Force -Path $env:SPARKBOT_DATA_DIR | Out-Null
New-Item -ItemType Directory -Force -Path $env:SPARKBOT_GUARDIAN_DATA_DIR | Out-Null

# ── Defaults for local single-user install ────────────────────────────────────
if (-not $env:SPARKBOT_PASSPHRASE)       { $env:SPARKBOT_PASSPHRASE       = "sparkbot-local"   }
if (-not $env:FIRST_SUPERUSER)           { $env:FIRST_SUPERUSER           = "admin@example.com"    }
if (-not $env:FIRST_SUPERUSER_PASSWORD)  { $env:FIRST_SUPERUSER_PASSWORD  = "sparkbot-local"   }
if (-not $env:BACKEND_CORS_ORIGINS) {
    $env:BACKEND_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173"
}
if (-not $env:FRONTEND_HOST) { $env:FRONTEND_HOST = "http://localhost:3000" }

Write-Host ""
Write-Host "Sparkbot v1 Local — bare-metal backend"
Write-Host "  Data dir : $env:SPARKBOT_DATA_DIR"
Write-Host "  Guardian : $env:SPARKBOT_GUARDIAN_DATA_DIR"
Write-Host "  Port     : $ApiPort"
Write-Host "  DB       : SQLite"
Write-Host ""

# ── Run from backend directory ────────────────────────────────────────────────
Push-Location $BackendDir

try {
    # Initialize database schema.
    # SQLite (v1 local) uses create_all + alembic stamp to avoid ALTER TABLE issues.
    # Postgres (hosted) uses normal alembic upgrade head.
    Write-Host "Initializing database schema..."
    if ($env:DATABASE_TYPE -eq "sqlite") {
        & $UV run python app/local_db_init.py
        if ($LASTEXITCODE -ne 0) { throw "local_db_init.py failed" }
    } else {
        & $UV run alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "alembic upgrade failed" }
    }

    # Seed first superuser if not already present
    Write-Host "Seeding initial data..."
    & $UV run python app/initial_data.py
    if ($LASTEXITCODE -ne 0) { throw "initial_data.py failed" }

    # Start backend
    Write-Host ""
    Write-Host "Starting backend..."
    Write-Host "  Health check : http://127.0.0.1:$ApiPort/api/v1/utils/health-check/"
    Write-Host "  API docs     : http://127.0.0.1:$ApiPort/docs"
    Write-Host ""
    Write-Host "Press Ctrl+C to stop."
    Write-Host ""

    & $UV run fastapi run --port $ApiPort app/main.py

} finally {
    Pop-Location
}
