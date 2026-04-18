# Sparkbot — Playwright browser repair script (Windows)
#
# Run this if browser tools (browser_open, browser_fill_field, etc.) are not
# working or if you see errors like "Executable doesn't exist" or
# "Playwright browsers not found".
#
# Usage (from repo root or any directory):
#   powershell -ExecutionPolicy Bypass -File scripts\repair-playwright.ps1
#
# What it does:
#   1. Locates the Playwright Python package (in the active venv or global Python)
#   2. Sets PLAYWRIGHT_BROWSERS_PATH to the stable Sparkbot directory
#   3. Runs: playwright install chromium
#   4. Verifies chrome.exe exists in the install directory
#   5. Reports pass/fail with next steps

$ErrorActionPreference = "Stop"

$BrowsersDir = Join-Path $env:APPDATA "Sparkbot\playwright-browsers"
$env:PLAYWRIGHT_BROWSERS_PATH = $BrowsersDir

Write-Host ""
Write-Host "Sparkbot — Playwright Browser Repair" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Target directory: $BrowsersDir"
Write-Host ""

# Ensure the target directory exists
if (-not (Test-Path $BrowsersDir)) {
    New-Item -ItemType Directory -Path $BrowsersDir -Force | Out-Null
    Write-Host "[+] Created $BrowsersDir" -ForegroundColor Green
}

# Find playwright CLI — try venv first, then global Python
$PlaywrightCmd = $null

# Check repo venv locations
$VenvCandidates = @(
    "backend\.venv\Scripts\playwright.exe",
    "backend\venv\Scripts\playwright.exe",
    ".venv\Scripts\playwright.exe",
    "venv\Scripts\playwright.exe"
)
foreach ($candidate in $VenvCandidates) {
    $full = Join-Path (Get-Location) $candidate
    if (Test-Path $full) {
        $PlaywrightCmd = $full
        Write-Host "[+] Found playwright in venv: $PlaywrightCmd" -ForegroundColor Green
        break
    }
}

# Fall back to global playwright on PATH
if (-not $PlaywrightCmd) {
    try {
        $PlaywrightCmd = (Get-Command playwright -ErrorAction Stop).Source
        Write-Host "[+] Found playwright on PATH: $PlaywrightCmd" -ForegroundColor Green
    } catch {
        Write-Host "[-] playwright not found in any venv or on PATH." -ForegroundColor Red
        Write-Host ""
        Write-Host "To fix this, activate your Python environment and install Playwright:"
        Write-Host "  cd backend"
        Write-Host "  .venv\Scripts\activate"
        Write-Host "  pip install playwright"
        Write-Host "  playwright install chromium"
        exit 1
    }
}

# Run playwright install chromium
Write-Host ""
Write-Host "Installing Chromium browser..." -ForegroundColor Yellow
Write-Host "  Command: $PlaywrightCmd install chromium"
Write-Host "  This downloads ~150 MB on first run. Please wait."
Write-Host ""

try {
    $result = & $PlaywrightCmd install chromium 2>&1
    $result | ForEach-Object { Write-Host "  $_" }
} catch {
    Write-Host ""
    Write-Host "[-] playwright install chromium failed: $_" -ForegroundColor Red
    exit 1
}

# Verify chrome.exe exists
Write-Host ""
$ChromeExe = Get-ChildItem -Path $BrowsersDir -Recurse -Filter "chrome.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($ChromeExe) {
    Write-Host "[OK] Chromium found: $($ChromeExe.FullName)" -ForegroundColor Green
    Write-Host ""
    Write-Host "Repair complete. Browser tools should work on the next Sparkbot launch." -ForegroundColor Green

    # Write the .playwright_ready marker if we can find the exe dir
    $ExeDir = $null
    $SparkbotExe = Get-ChildItem -Path $env:LOCALAPPDATA -Recurse -Filter "Sparkbot Local.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($SparkbotExe) {
        $ExeDir = $SparkbotExe.DirectoryName
        $Marker = Join-Path $ExeDir ".playwright_ready"
        "ok" | Out-File -FilePath $Marker -Encoding ascii -NoNewline
        Write-Host "[+] Wrote .playwright_ready marker to $ExeDir" -ForegroundColor Green
    }
} else {
    Write-Host "[-] chrome.exe not found in $BrowsersDir after install." -ForegroundColor Red
    Write-Host "    Try running this script as Administrator, or check disk space."
    Write-Host "    You can also run manually:"
    Write-Host "      `$env:PLAYWRIGHT_BROWSERS_PATH = '$BrowsersDir'"
    Write-Host "      playwright install chromium"
    exit 1
}

Write-Host ""
