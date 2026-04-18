#!/usr/bin/env bash
# Sparkbot — Playwright browser repair script (Linux / macOS)
#
# Run this if browser tools (browser_open, browser_fill_field, etc.) are not
# working or if you see errors like "Executable doesn't exist".
#
# Usage (from repo root or any directory):
#   bash scripts/repair-playwright.sh
#
# What it does:
#   1. Locates the Playwright Python package (in the active venv or on PATH)
#   2. Sets PLAYWRIGHT_BROWSERS_PATH to ~/.sparkbot/playwright-browsers
#   3. Runs: playwright install chromium
#   4. Verifies the chrome binary exists
#   5. Reports pass/fail with next steps

set -euo pipefail

BROWSERS_DIR="${HOME}/.sparkbot/playwright-browsers"
export PLAYWRIGHT_BROWSERS_PATH="${BROWSERS_DIR}"

echo ""
echo "Sparkbot — Playwright Browser Repair"
echo "====================================="
echo "Target directory: ${BROWSERS_DIR}"
echo ""

mkdir -p "${BROWSERS_DIR}"

# Find playwright CLI — venv first, then PATH
PLAYWRIGHT_CMD=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

for candidate in \
    "${REPO_ROOT}/backend/.venv/bin/playwright" \
    "${REPO_ROOT}/backend/venv/bin/playwright" \
    "${REPO_ROOT}/.venv/bin/playwright" \
    "${REPO_ROOT}/venv/bin/playwright"; do
    if [ -x "${candidate}" ]; then
        PLAYWRIGHT_CMD="${candidate}"
        echo "[+] Found playwright in venv: ${PLAYWRIGHT_CMD}"
        break
    fi
done

if [ -z "${PLAYWRIGHT_CMD}" ]; then
    if command -v playwright &>/dev/null; then
        PLAYWRIGHT_CMD="$(command -v playwright)"
        echo "[+] Found playwright on PATH: ${PLAYWRIGHT_CMD}"
    else
        echo "[-] playwright not found in any venv or on PATH."
        echo ""
        echo "To fix this, activate your Python environment and install Playwright:"
        echo "  cd backend"
        echo "  source .venv/bin/activate"
        echo "  pip install playwright"
        echo "  playwright install chromium"
        exit 1
    fi
fi

echo ""
echo "Installing Chromium browser..."
echo "  Command: ${PLAYWRIGHT_CMD} install chromium"
echo "  This downloads ~150 MB on first run. Please wait."
echo ""

"${PLAYWRIGHT_CMD}" install chromium

echo ""

# Verify binary exists
CHROME_BIN=$(find "${BROWSERS_DIR}" -name "chrome" -o -name "chromium" 2>/dev/null | head -1)

if [ -n "${CHROME_BIN}" ] && [ -f "${CHROME_BIN}" ]; then
    echo "[OK] Chromium found: ${CHROME_BIN}"
    echo ""
    echo "Repair complete. Browser tools should work on the next Sparkbot launch."
else
    echo "[-] Chromium binary not found in ${BROWSERS_DIR} after install."
    echo "    You may need to install system dependencies:"
    echo "      Ubuntu/Debian: sudo apt-get install -y libglib2.0-0 libnss3 libnspr4 libatk1.0-0"
    echo "      Fedora/RHEL:   sudo dnf install -y nss atk at-spi2-atk"
    echo "    Then re-run this script."
    exit 1
fi

echo ""
